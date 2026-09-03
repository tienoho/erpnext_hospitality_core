frappe.ui.form.on('Hotel Group Booking', {
    refresh: function (frm) {
        if (!frm.is_new()) {

            // Hiển thị thanh đo lường hạn mức tín dụng Đại lý (Traffic Light Badge)
            if (frm.doc.master_payer) {
                frappe.call({
                    method: 'hospitality_core.hospitality_core.api.city_ledger.get_agent_credit_status',
                    args: { customer_name: frm.doc.master_payer },
                    callback: function (r) {
                        if (!r.exc && r.message && r.message.has_credit_limit) {
                            let c = r.message;
                            let bg = c.status_level === 'RED' ? '#fee2e2' : (c.status_level === 'YELLOW' ? '#fef3c7' : '#dcfce7');
                            let color = c.status_level === 'RED' ? '#991b1b' : (c.status_level === 'YELLOW' ? '#92400e' : '#166534');
                            let border = c.status_level === 'RED' ? '#f87171' : (c.status_level === 'YELLOW' ? '#fcd34d' : '#86efac');
                            frm.dashboard.set_headline(`
                                <div style="background: ${bg}; border: 1px solid ${border}; border-radius: 6px; padding: 8px 14px; display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
                                    <div>
                                        <span style="font-weight: 700; color: ${color};">💳 Hạn Mức Tín Dụng Đại Lý (${c.status_label}):</span>
                                        <span style="margin-left: 8px; color: ${color};">Hạn mức: <b>${c.formatted_credit_limit}</b> | Dư nợ: <b>${c.formatted_outstanding}</b> (Đã dùng ${c.usage_pct}%)</span>
                                    </div>
                                    <div style="font-weight: 700; color: ${color}; font-size: 13px;">Còn lại: ${c.formatted_available}</div>
                                </div>
                            `);
                        }
                    }
                });
            }

            // Button: Kiểm tra và áp dụng phòng FOC cho HDV
            frm.add_custom_button(__('🎁 Kiểm Tra Phòng FOC'), function () {
                frappe.call({
                    method: 'hospitality_core.hospitality_core.api.city_ledger.calculate_group_foc_rooms',
                    args: { group_booking_name: frm.doc.name },
                    freeze: true,
                    callback: function (r) {
                        if (!r.exc && r.message) {
                            let f = r.message;
                            if (!f.policy_enabled) {
                                frappe.msgprint(__('Chính sách phòng FOC hiện đang tắt trong Hospitality Surcharge Settings.'));
                                return;
                            }
                            let msg = `
                                <div style="padding: 10px; line-height: 1.6;">
                                    <p>• Tổng số phòng đoàn: <b>${f.total_rooms}</b></p>
                                    <p>• Tỷ lệ tặng phòng: <b>${f.rooms_per_foc} phòng trả tiền = 1 phòng FOC</b></p>
                                    <p>• Số phòng FOC đủ điều kiện: <b style="color: #0284c7; font-size: 16px;">${f.foc_eligible} phòng</b></p>
                                    <p>• Đã áp dụng: <b>${f.current_foc_count}</b> phòng | Còn lại: <b>${f.remaining_foc_quota}</b> phòng</p>
                                </div>
                            `;

                            let d = new frappe.ui.Dialog({
                                title: __('🎁 Chính Sách Phòng FOC Hướng Dẫn Viên'),
                                fields: [
                                    { fieldname: 'info', fieldtype: 'HTML', options: msg },
                                    {
                                        fieldname: 'reservation',
                                        label: __('Chọn Đặt Phòng Của Hướng Dẫn Viên'),
                                        fieldtype: 'Link',
                                        options: 'Hotel Reservation',
                                        get_query: () => ({
                                            filters: {
                                                group_booking: frm.doc.name,
                                                status: ['!=', 'Cancelled'],
                                                is_complimentary: 0
                                            }
                                        }),
                                        depends_on: 'eval:' + (f.remaining_foc_quota > 0)
                                    }
                                ],
                                primary_action_label: f.remaining_foc_quota > 0 ? __('Áp Dụng Phòng FOC (Miễn Phí 100%)') : __('Đóng'),
                                primary_action: function (vals) {
                                    if (f.remaining_foc_quota <= 0 || !vals.reservation) {
                                        d.hide();
                                        return;
                                    }
                                    frappe.confirm(
                                        __('Xác nhận áp dụng chính sách FOC (Miễn phí tiền phòng 100%) cho đặt phòng của Hướng dẫn viên <b>{0}</b>?', [vals.reservation]),
                                        function () {
                                            frappe.dom.freeze(__('Đang áp dụng phòng FOC...'));
                                            frappe.call({
                                                method: 'hospitality_core.hospitality_core.api.city_ledger.apply_foc_to_reservation',
                                                args: {
                                                    group_booking_name: frm.doc.name,
                                                    reservation_name: vals.reservation
                                                },
                                                callback: function (res) {
                                                    frappe.dom.unfreeze();
                                                    if (!res.exc) {
                                                        d.hide();
                                                        frappe.show_alert({ message: res.message.message, indicator: 'green' });
                                                        frm.reload_doc();
                                                    }
                                                }
                                            });
                                        }
                                    );
                                }
                            });
                            d.show();
                        }
                    }
                });
            }, 'Actions');

            // Button: Create Master Folio
            if (!frm.doc.master_folio) {
                frm.add_custom_button(__('Create Master Folio'), function () {
                    frm.call({
                        method: 'hospitality_core.hospitality_core.api.group_booking.create_master_folio',
                        args: { group_booking_name: frm.doc.name },
                        freeze: true,
                        callback: function (r) {
                            if (!r.exc) frm.reload_doc();
                        }
                    });
                }).addClass("btn-primary");
            } else {
                // Link to Folio
                frm.add_custom_button(__('View Master Folio'), function () {
                    frappe.set_route('Form', 'Guest Folio', frm.doc.master_folio);
                });
            }

            // Button: Add Reservations
            frm.add_custom_button(__('Link Reservations'), function () {
                new frappe.ui.form.MultiSelectDialog({
                    doctype: "Hotel Reservation",
                    target: frm,
                    setters: {
                        status: 'Reserved',
                    },
                    get_query() {
                        return {
                            filters: {
                                'group_booking': ['is', 'not set'],
                                'status': 'Reserved'
                            }
                        };
                    },
                    action(selections) {
                        if (selections.length === 0) {
                            frappe.msgprint(__('Please select at least one reservation.'));
                            return;
                        }
                        frm.call({
                            method: 'hospitality_core.hospitality_core.api.group_booking.add_rooms_to_group',
                            args: {
                                group_booking: frm.doc.name,
                                rooms: JSON.stringify(selections)
                            },
                            freeze: true,
                            callback: function (r) {
                                if (!r.exc) {
                                    frappe.msgprint(__('Reservations linked successfully.'));
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                });
            });

            // Button: Bulk Reserve
            frm.add_custom_button(__('Bulk Reserve'), function () {
                if (!frm.doc.arrival_date || !frm.doc.departure_date) {
                    frappe.msgprint(__('Please set Arrival and Departure dates for the group first.'));
                    return;
                }

                let d = new frappe.ui.Dialog({
                    title: __('Bulk Reservation'),
                    fields: [
                        {
                            label: __('Guest'),
                            fieldname: 'guest',
                            fieldtype: 'Link',
                            options: 'Guest',
                            reqd: 1
                        },
                        {
                            label: __('Room Type'),
                            fieldname: 'room_type',
                            fieldtype: 'Link',
                            options: 'Hotel Room Type'
                        },
                        {
                            label: __('Discount Type'),
                            fieldname: 'discount_type',
                            fieldtype: 'Select',
                            options: '\nPercentage\nAmount'
                        },
                        {
                            label: __('Discount Value'),
                            fieldname: 'discount_value',
                            fieldtype: 'Currency'
                        },
                        {
                            label: __('Available Rooms'),
                            fieldname: 'rooms_html',
                            fieldtype: 'HTML'
                        }
                    ],
                    primary_action_label: __('Reserve'),
                    primary_action(values) {
                        let selected_rooms = [];
                        d.$wrapper.find('.room-checkbox:checked').each(function () {
                            selected_rooms.push($(this).val());
                        });

                        if (selected_rooms.length === 0) {
                            frappe.msgprint(__('Please select at least one room.'));
                            return;
                        }

                        frappe.call({
                            method: 'hospitality_core.hospitality_core.api.group_booking.bulk_reserve_rooms',
                            args: {
                                group_booking: frm.doc.name,
                                guest: values.guest,
                                rooms: JSON.stringify(selected_rooms),
                                arrival_date: frm.doc.arrival_date,
                                departure_date: frm.doc.departure_date,
                                discount_type: values.discount_type || null,
                                discount_value: values.discount_value || 0
                            },
                            freeze: true,
                            callback: function (r) {
                                if (!r.exc) {
                                    let msg = __('Successfully reserved {0} rooms.').format(r.message.created.length);
                                    let indicator = 'green';

                                    if (r.message.errors && r.message.errors.length > 0) {
                                        msg += "<br><br>" + __("<b>Failures:</b>") + "<br><ul><li>" + r.message.errors.join("</li><li>") + "</li></ul>";
                                        indicator = 'orange';
                                    }

                                    frappe.msgprint({
                                        title: __('Bulk Reservation Status'),
                                        message: msg,
                                        indicator: indicator
                                    });

                                    if (r.message.created.length > 0) {
                                        d.hide();
                                        frm.reload_doc();
                                    }
                                }
                            }
                        });
                    }
                });

                d.fields_dict.room_type.df.onchange = () => {
                    refresh_rooms();
                };

                let refresh_rooms = () => {
                    let room_type = d.get_value('room_type') || '';
                    frappe.call({
                        method: 'hospitality_core.hospitality_core.api.reservation.get_available_rooms_for_picker',
                        args: {
                            doctype: 'Hotel Room',
                            txt: '',
                            searchfield: 'name',
                            start: 0,
                            page_len: 200,
                            filters: {
                                arrival_date: frm.doc.arrival_date,
                                departure_date: frm.doc.departure_date,
                                room_type: room_type
                            }
                        },
                        callback: function (r) {
                            let rooms = r.message || [];
                            let html = '<div style="max-height: 250px; overflow-y: auto; border: 1px solid #d1d8dd; border-radius: 4px; padding: 10px; background: #f8f9fa;">';
                            if (rooms.length === 0) {
                                html += `<p class="text-muted text-center">${__('No rooms available for the selected dates/type.')}</p>`;
                            } else {
                                html += '<div class="row">';
                                rooms.forEach(room => {
                                    html += `
                                        <div class="col-sm-6">
                                            <div class="checkbox" style="margin-top: 5px; margin-bottom: 5px;">
                                                <label style="font-weight: normal; cursor: pointer;">
                                                    <input type="checkbox" class="room-checkbox" value="${room[0]}">
                                                    <span class="label label-info" style="margin-right: 5px;">${room[0]}</span>
                                                    <small class="text-muted">${room[1]}</small>
                                                </label>
                                            </div>
                                        </div>
                                    `;
                                });
                                html += '</div>';
                            }
                            html += '</div>';
                            d.fields_dict.rooms_html.$wrapper.html(html);
                        }
                    });
                };

                d.show();
                refresh_rooms();
            }, __('Actions'));

            // Button: Mass Check In
            if (frm.doc.status === 'Confirmed' || frm.doc.status === 'In House') {
                frm.add_custom_button(__('Check In Group'), function () {
                    frappe.confirm('Check In all RESERVED guests in this group?', () => {
                        frm.call({
                            method: 'hospitality_core.hospitality_core.api.group_booking.mass_check_in',
                            args: { group_booking: frm.doc.name },
                            freeze: true,
                            callback: function (r) {
                                if (!r.exc) {
                                    let indicator = (r.message.error_count > 0) ? 'orange' : 'green';
                                    frappe.msgprint({
                                        title: __('Group Check-In Status'),
                                        message: r.message.message,
                                        indicator: indicator
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    });
                }, 'Actions');
            }

            // Button: Mass Check Out
            if (frm.doc.status === 'In House' || frm.doc.status === 'Checked Out') {
                frm.add_custom_button(__('Check Out Group'), function () {
                    frappe.confirm('Check Out all IN-HOUSE guests in this group?', () => {
                        frm.call({
                            method: 'hospitality_core.hospitality_core.api.group_booking.mass_check_out',
                            args: { group_booking: frm.doc.name },
                            freeze: true,
                            callback: function (r) {
                                if (!r.exc) {
                                    let indicator = (r.message.error_count > 0) ? 'orange' : 'green';
                                    frappe.msgprint({
                                        title: __('Group Check-Out Status'),
                                        message: r.message.message,
                                        indicator: indicator
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    });
                }, 'Actions');
            }
        }
    }
});