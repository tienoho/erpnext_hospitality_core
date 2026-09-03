frappe.ui.form.on('Hotel Reservation', {
    onload: function (frm) {
        if (frm.is_new()) {
            frm.set_value('status', 'Reserved');
            frm.set_value('is_company_guest', 0);
            frm.set_value('company', ''); // Ensure company is empty
        }
    },
    validate: function (frm) {
        if (!frm.doc.is_company_guest) {
            frm.set_value('company', null);
        }
    },
    is_company_guest: function (frm) {
        if (!frm.doc.is_company_guest) {
            frm.set_value('company', null);
        }
    },
    refresh: function (frm) {
        // Keep room type aligned with the selected room on load and refresh.
        sync_room_type_from_room(frm);

        // Filter Rooms based on Room Type AND Availability
        frm.set_query('room', function () {
            return {
                query: 'hospitality_core.hospitality_core.api.reservation.get_available_rooms_for_picker',
                filters: {
                    'arrival_date': frm.doc.arrival_date,
                    'departure_date': frm.doc.departure_date,
                    'room_type': frm.doc.room_type,
                    'ignore_reservation': frm.doc.name
                }
            };
        });

        // Add Workflow Buttons
        if (!frm.is_new()) {

            // CHECK IN BUTTON WITH SURCHARGE DETECTION
            if (frm.doc.status === 'Reserved') {
                frm.add_custom_button(__('Check In'), function () {
                    // Kiểm tra phụ thu nhận phòng sớm
                    frappe.call({
                        method: 'hospitality_core.hospitality_core.api.surcharge_engine.calculate_checkin_surcharge',
                        args: { reservation_name: frm.doc.name },
                        callback: function (res) {
                            let sur = res.message;
                            if (sur && sur.applicable) {
                                let d = new frappe.ui.Dialog({
                                    title: __('⏰ Phát Hiện Nhận Phòng Sớm (Early Check-in)'),
                                    fields: [
                                        {
                                            fieldname: 'info_html',
                                            fieldtype: 'HTML',
                                            options: `
                                                <div style="background: #fffbeb; border: 1px solid #fef3c7; border-radius: 8px; padding: 14px; margin-bottom: 12px;">
                                                    <div style="font-size: 14px; color: #92400e; margin-bottom: 8px;">
                                                        Khách đến nhận phòng lúc <b>${sur.checkin_time}</b> (Trước giờ quy chuẩn).
                                                    </div>
                                                    <div style="font-size: 13px; color: #451a03; line-height: 1.6;">
                                                        • Bậc phụ thu: <b>${sur.tier_label}</b><br>
                                                        • Giá phòng gốc: <b>${format_currency(sur.base_rate)}</b><br>
                                                        • Mức phụ thu dự kiến: <b style="color: #e11d48; font-size: 16px;">${sur.formatted_amount}</b>
                                                    </div>
                                                </div>
                                            `
                                        }
                                    ],
                                    primary_action_label: __('✔ Áp Dụng Phụ Thu & Check In'),
                                    primary_action: function () {
                                        d.hide();
                                        frappe.dom.freeze(__('Đang áp dụng phụ thu và Check In...'));
                                        frappe.call({
                                            method: 'hospitality_core.hospitality_core.api.surcharge_engine.apply_surcharge_to_folio',
                                            args: {
                                                reservation_name: frm.doc.name,
                                                surcharge_type: 'Early Check-in',
                                                amount: sur.amount,
                                                description: sur.description
                                            },
                                            callback: function () {
                                                frm.call({
                                                    method: 'check_in_guest',
                                                    args: { name: frm.doc.name },
                                                    callback: function () {
                                                        frappe.dom.unfreeze();
                                                        frappe.msgprint(__('Đã nhận phòng và ghi nhận phụ thu vào Folio.'));
                                                        frm.reload_doc();
                                                    }
                                                });
                                            }
                                        });
                                    },
                                    secondary_action_label: __('Miễn Phụ Thu & Check In')
                                });
                                d.set_secondary_action(function () {
                                    d.hide();
                                    frappe.prompt([
                                        {
                                            label: __('Lý do miễn phụ thu nhận sớm (Ghi nhận kiểm toán)'),
                                            fieldname: 'reason',
                                            fieldtype: 'Select',
                                            options: '\nKhách VIP / Thân thiết\nBan Giám Đốc phê duyệt\nLỗi buồng phòng / Bù đắp trải nghiệm\nTheo hợp đồng đại lý lữ hành\nKhác',
                                            reqd: 1
                                        },
                                        {
                                            label: __('Ghi chú chi tiết'),
                                            fieldname: 'note',
                                            fieldtype: 'Small Text'
                                        }
                                    ], function (vals) {
                                        frappe.call({
                                            method: 'frappe.desk.form.utils.add_comment',
                                            args: {
                                                reference_doctype: 'Hotel Reservation',
                                                reference_name: frm.doc.name,
                                                content: `<b>[KIỂM TOÁN LỄ TÂN] Miễn phụ thu nhận phòng sớm:</b> ${vals.reason} - ${vals.note || ''}`,
                                                comment_email: frappe.session.user,
                                                comment_by: frappe.session.user_fullname
                                            }
                                        });
                                        frm.call({
                                            method: 'check_in_guest',
                                            args: { name: frm.doc.name },
                                            freeze: true,
                                            callback: function (r) {
                                                if (!r.exc) {
                                                    frappe.show_alert({
                                                        message: __('Guest Checked In Successfully (Đã ghi nhận lý do miễn phụ thu).'),
                                                        indicator: 'green'
                                                    });
                                                    frm.reload_doc();
                                                }
                                            }
                                        });
                                    }, __('Xác Nhận Miễn Phụ Thu Nhận Phòng Sớm'), __('Xác Nhận & Check In'));
                                });
                                d.show();
                            } else {
                                frappe.confirm(
                                    'Are you sure you want to Check In this guest?',
                                    function () {
                                        frm.call({
                                            method: 'check_in_guest',
                                            args: { name: frm.doc.name },
                                            freeze: true,
                                            callback: function (r) {
                                                if (!r.exc) {
                                                    frappe.msgprint('Guest Checked In Successfully');
                                                    frm.reload_doc();
                                                }
                                            }
                                        });
                                    }
                                );
                            }
                        }
                    });
                }).addClass("btn-primary");
            }

            // NEW CHECK OUT BUTTON (Primary Action WITH SURCHARGE DETECTION)
            if (frm.doc.status === 'Checked In') {
                frm.page.set_primary_action(__('Check Out'), function () {
                    // Pre-check Departure Date
                    if (frm.doc.departure_date !== frappe.datetime.nowdate()) {
                        frappe.msgprint({
                            title: __('Early Departure?'),
                            message: __('Cannot Check Out. The Departure Date must be today. Please update the Departure Date/Shorten Stay first.'),
                            indicator: 'orange'
                        });
                        return;
                    }

                    // Kiểm tra phụ thu trả phòng muộn
                    frappe.call({
                        method: 'hospitality_core.hospitality_core.api.surcharge_engine.calculate_checkout_surcharge',
                        args: { reservation_name: frm.doc.name },
                        callback: function (res) {
                            let sur = res.message;
                            if (sur && sur.applicable) {
                                let d = new frappe.ui.Dialog({
                                    title: __('⏰ Phát Hiện Trả Phòng Muộn (Late Check-out)'),
                                    fields: [
                                        {
                                            fieldname: 'info_html',
                                            fieldtype: 'HTML',
                                            options: `
                                                <div style="background: #fff1f2; border: 1px solid #ffe4e6; border-radius: 8px; padding: 14px; margin-bottom: 12px;">
                                                    <div style="font-size: 14px; color: #9f1239; margin-bottom: 8px;">
                                                        Khách trả phòng lúc <b>${sur.checkout_time}</b> (Sau giờ quy chuẩn).
                                                    </div>
                                                    <div style="font-size: 13px; color: #4c0519; line-height: 1.6;">
                                                        • Bậc phụ thu: <b>${sur.tier_label}</b><br>
                                                        • Giá phòng gốc: <b>${format_currency(sur.base_rate)}</b><br>
                                                        • Mức phụ thu dự kiến: <b style="color: #e11d48; font-size: 16px;">${sur.formatted_amount}</b>
                                                    </div>
                                                </div>
                                            `
                                        }
                                    ],
                                    primary_action_label: __('✔ Áp Dụng Phụ Thu & Check Out'),
                                    primary_action: function () {
                                        d.hide();
                                        frappe.dom.freeze(__('Đang áp dụng phụ thu và Check Out...'));
                                        frappe.call({
                                            method: 'hospitality_core.hospitality_core.api.surcharge_engine.apply_surcharge_to_folio',
                                            args: {
                                                reservation_name: frm.doc.name,
                                                surcharge_type: 'Late Check-out',
                                                amount: sur.amount,
                                                description: sur.description
                                            },
                                            callback: function () {
                                                frm.call({
                                                    method: 'check_out_guest',
                                                    args: { name: frm.doc.name },
                                                    callback: function () {
                                                        frappe.dom.unfreeze();
                                                        frappe.msgprint(__('Đã trả phòng và ghi nhận phụ thu vào Folio.'));
                                                        frm.reload_doc();
                                                    }
                                                });
                                            }
                                        });
                                    },
                                    secondary_action_label: __('Miễn Phụ Thu & Check Out')
                                });
                                d.set_secondary_action(function () {
                                    d.hide();
                                    frappe.prompt([
                                        {
                                            label: __('Lý do miễn phụ thu trả muộn (Ghi nhận kiểm toán)'),
                                            fieldname: 'reason',
                                            fieldtype: 'Select',
                                            options: '\nKhách VIP / Thân thiết\nBan Giám Đốc phê duyệt\nLỗi buồng phòng / Bù đắp trải nghiệm\nTheo hợp đồng đại lý lữ hành\nKhác',
                                            reqd: 1
                                        },
                                        {
                                            label: __('Ghi chú chi tiết'),
                                            fieldname: 'note',
                                            fieldtype: 'Small Text'
                                        }
                                    ], function (vals) {
                                        frappe.call({
                                            method: 'frappe.desk.form.utils.add_comment',
                                            args: {
                                                reference_doctype: 'Hotel Reservation',
                                                reference_name: frm.doc.name,
                                                content: `<b>[KIỂM TOÁN LỄ TÂN] Miễn phụ thu trả phòng muộn:</b> ${vals.reason} - ${vals.note || ''}`,
                                                comment_email: frappe.session.user,
                                                comment_by: frappe.session.user_fullname
                                            }
                                        });
                                        frm.call({
                                            method: 'check_out_guest',
                                            args: { name: frm.doc.name },
                                            freeze: true,
                                            callback: function (r) {
                                                if (!r.exc) {
                                                    frappe.show_alert({
                                                        message: __('Guest Checked Out Successfully (Đã ghi nhận lý do miễn phụ thu).'),
                                                        indicator: 'green'
                                                    });
                                                    frm.reload_doc();
                                                }
                                            }
                                        });
                                    }, __('Xác Nhận Miễn Phụ Thu Trả Phòng Muộn'), __('Xác Nhận & Check Out'));
                                });
                                d.show();
                            } else {
                                frappe.warn(
                                    'Confirm Checkout',
                                    `Are you sure you want to Check Out <b>${frm.doc.guest}</b> from Room <b>${frm.doc.room}</b>?<br><br>This will close the folio and mark the room as Available.`,
                                    function () {
                                        frm.call({
                                            method: 'check_out_guest',
                                            args: { name: frm.doc.name },
                                            freeze: true,
                                            callback: function (r) {
                                                if (!r.exc) {
                                                    frappe.msgprint('Guest Checked Out Successfully');
                                                    frm.reload_doc();
                                                }
                                            }
                                        });
                                    }
                                );
                            }
                        }
                    });
                });
            }

            // CANCEL RESERVATION BUTTON
            // Visible for Reserved AND Checked In, Restricted to Supervisors
            let is_supervisor = frappe.user_roles.includes('Frontdesk Supervisor') ||
                frappe.user_roles.includes('System Manager') ||
                frappe.session.user === 'Administrator';

            if (['Reserved', 'Checked In'].includes(frm.doc.status) && is_supervisor) {
                frm.add_custom_button(__('Cancel Reservation'), function () {
                    frappe.confirm(
                        'Are you sure you want to Cancel this Reservation?',
                        function () {
                            frm.call({
                                method: 'cancel_reservation',
                                args: {
                                    name: frm.doc.name
                                },
                                freeze: true,
                                callback: function (r) {
                                    if (!r.exc) {
                                        frappe.msgprint('Reservation Cancelled.');
                                        frm.reload_doc();
                                    }
                                }
                            });
                        }
                    );
                }, null).addClass('btn-danger'); // Add class for styling if possible, or just standard custom button
            }

            // Quick Access to Folio
            if (frm.doc.folio) {
                frm.add_custom_button(__('Open Folio'), function () {
                    frappe.set_route('Form', 'Guest Folio', frm.doc.folio);
                }, 'View');
            }

        }

        set_reservation_read_only_state(frm);

        // ROOM MOVE BUTTON
        let can_move_room = frappe.user_roles.includes('Frontdesk Supervisor') ||
            frappe.session.user === 'Administrator';

        if (frm.doc.status === 'Checked In' && can_move_room) {
            frm.add_custom_button(__('Move Room'), function () {

                var d = new frappe.ui.Dialog({
                    title: 'Move Guest to New Room',
                    fields: [
                        {
                            label: 'New Room',
                            fieldname: 'new_room',
                            fieldtype: 'Link',
                            options: 'Hotel Room',
                            get_query: function () {
                                return {
                                    filters: {
                                        'is_enabled': 1,
                                        'name': ['!=', frm.doc.room]
                                    }
                                };
                            },
                            reqd: 1
                        }
                    ],
                    primary_action_label: 'Move',
                    primary_action: function (values) {
                        frm.call({
                            method: 'hospitality_core.hospitality_core.api.room_move.process_room_move',
                            args: {
                                reservation_name: frm.doc.name,
                                new_room: values.new_room
                            },
                            freeze: true,
                            callback: function (r) {
                                if (!r.exc) {
                                    d.hide();
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                });
                d.show();

            }, __('Actions'));
        }

        // KEYCARD ENCODER BUTTONS (Hardware Bridge Integration)
        if (['Reserved', 'Checked In'].includes(frm.doc.status) && frm.doc.room) {
            frm.add_custom_button(__('Ghi Thẻ Phòng'), function () {
                if (window.frappe && frappe.hospitality && frappe.hospitality.encode_keycard) {
                    frappe.hospitality.encode_keycard(
                        frm.doc.room,
                        frm.doc.arrival_date + ' 14:00:00',
                        frm.doc.departure_date + ' 12:00:00',
                        frm.doc.guest,
                        false
                    );
                } else {
                    // Direct fetch fallback if keycard_encoder_bridge.js is not loaded
                    fetch('http://127.0.0.1:8765/api/lock/encode_card', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            room_no: frm.doc.room,
                            checkin_time: frm.doc.arrival_date + ' 14:00:00',
                            checkout_time: frm.doc.departure_date + ' 12:00:00',
                            guest_name: frm.doc.guest,
                            is_duplicate: false
                        })
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            frappe.show_alert({ message: __('Ghi thẻ phòng thành công: ') + data.card_uid, indicator: 'green' });
                        } else {
                            frappe.msgprint({ title: __('Lỗi Ghi Thẻ'), message: data.error || data.message, indicator: 'red' });
                        }
                    })
                    .catch(err => {
                        frappe.msgprint({
                            title: __('Không thể kết nối Đầu đọc thẻ'),
                            indicator: 'red',
                            message: __('Vui lòng chạy Hardware Bridge tại <b>http://127.0.0.1:8765</b> trên máy trạm Lễ tân.')
                        });
                    });
                }
            }, __('Khóa Thẻ Từ'));

            frm.add_custom_button(__('Ghi Thẻ Phụ (Duplicate)'), function () {
                fetch('http://127.0.0.1:8765/api/lock/encode_card', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        room_no: frm.doc.room,
                        checkin_time: frm.doc.arrival_date + ' 14:00:00',
                        checkout_time: frm.doc.departure_date + ' 12:00:00',
                        guest_name: frm.doc.guest,
                        is_duplicate: true
                    })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        frappe.show_alert({ message: __('Ghi thẻ phụ thành công: ') + data.card_uid, indicator: 'green' });
                    }
                })
                .catch(() => {
                    frappe.show_alert({ message: __('Chưa kết nối Hardware Bridge'), indicator: 'red' });
                });
            }, __('Khóa Thẻ Từ'));

            frm.add_custom_button(__('Xóa / Thu Hồi Thẻ'), function () {
                fetch('http://127.0.0.1:8765/api/lock/clear_card', { method: 'POST' })
                    .then(res => res.json())
                    .then(data => {
                        frappe.show_alert({ message: __('Đã xóa và thu hồi thẻ phòng!'), indicator: 'green' });
                    })
                    .catch(() => {
                        frappe.show_alert({ message: __('Chưa kết nối Hardware Bridge'), indicator: 'red' });
                    });
            }, __('Khóa Thẻ Từ'));
        }
    },

    room_type: function (frm) {
        if (frm.__syncing_room_type) {
            return;
        }

        // Clear room if type changes
        frm.set_value('room', '');
    },

    arrival_date: function (frm) {
        calculate_nights(frm);
        validate_room_availability(frm);
        render_room_rate_preview(frm);
    },

    departure_date: function (frm) {
        calculate_nights(frm);
        validate_room_availability(frm);
    },
    
    room: function (frm) {
        sync_room_type_from_room(frm);
        render_room_rate_preview(frm);
    },
    
    rate_plan: function (frm) {
        render_room_rate_preview(frm);
    },
    
    discount_type: function (frm) {
        render_room_rate_preview(frm);
    },
    
    discount_value: function (frm) {
        render_room_rate_preview(frm);
    },
    
    is_complimentary: function (frm) {
        render_room_rate_preview(frm);
    }
});

function sync_room_type_from_room(frm) {
    if (!frm.doc.room) {
        return;
    }

    frappe.db.get_value('Hotel Room', frm.doc.room, 'room_type').then(r => {
        let room_type = r.message ? r.message.room_type : null;
        if (!room_type || frm.doc.room_type === room_type) {
            return;
        }

        frm.__syncing_room_type = true;
        return frm.set_value('room_type', room_type).then(() => {
            frm.__syncing_room_type = false;
            render_room_rate_preview(frm);
        });
    });
}

function set_reservation_read_only_state(frm) {
    if (!frm.fields_dict) return;

    let exceptions = [];
    if (frm.doc.status === 'Checked In') {
        exceptions = [
            'departure_date',
            'discount_value',
            'is_company_guest',
            'company',
            'allow_pos_posting'
        ];
    }

    let should_lock = ['Checked In', 'Checked Out', 'Cancelled'].includes(frm.doc.status);

    Object.keys(frm.fields_dict).forEach(fieldname => {
        let field = frm.fields_dict[fieldname];
        if (!field || !field.df) return;

        let is_readonly = fieldname === 'status' || (should_lock && !exceptions.includes(fieldname));
        frm.set_df_property(fieldname, 'read_only', is_readonly ? 1 : 0);
    });
}

function render_room_rate_preview(frm) {
    if (!frm.fields_dict.room_rate_preview) return;
    
    let wrapper = frm.fields_dict.room_rate_preview.$wrapper;
    
    if (!frm.doc.room) {
        wrapper.html("<div class='text-muted small'>Select a room to see rate.</div>");
        return;
    }
    
    // Show loading state
    wrapper.html("<div class='text-muted small'>Calculating rate...</div>");
    
    frappe.call({
        method: "hospitality_core.hospitality_core.api.reservation.get_room_rate",
        args: {
            room: frm.doc.room,
            rate_plan: frm.doc.rate_plan,
            room_type: frm.doc.room_type,
            arrival_date: frm.doc.arrival_date,
            discount_type: frm.doc.discount_type,
            discount_value: frm.doc.discount_value,
            is_complimentary: frm.doc.is_complimentary
        },
        callback: function(r) {
            if (r.message) {
                let d = r.message;
                let currency = frappe.boot.sysdefaults.currency;
                
                let html = `<div style="padding: 15px; border: 1px solid #d1d8dd; border-radius: 4px; background-color: #f7fafc;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                        <span class="text-muted">Base Rate:</span>
                        <span style="font-weight: 500;">${format_currency(d.base_rate, currency)}</span>
                    </div>`;
                    
                if (d.discount_amount > 0) {
                    html += `<div style="display: flex; justify-content: space-between; margin-bottom: 5px; color: #e74c3c;">
                        <span>Discount:</span>
                        <span>- ${format_currency(d.discount_amount, currency)}</span>
                    </div>`;
                }
                
                html += `<div style="display: flex; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px solid #d1d8dd;">
                        <span style="font-weight: 600; font-size: 1.1em;">Final Rate / Night:</span>
                        <span style="font-weight: 700; font-size: 1.1em; color: #2ecc71;">${format_currency(d.final_rate, currency)}</span>
                    </div>
                </div>`;
                
                wrapper.html(html);
            }
        }
    });
}

function calculate_nights(frm) {
    if (frm.doc.arrival_date && frm.doc.departure_date) {
        var diff = frappe.datetime.get_diff(frm.doc.departure_date, frm.doc.arrival_date);
        if (diff < 1) {
            frappe.msgprint("Departure must be after Arrival");
        }
    }
}

function validate_room_availability(frm) {
    if (frm.doc.room && frm.doc.arrival_date && frm.doc.departure_date) {
        frappe.call({
            method: "hospitality_core.hospitality_core.api.reservation.check_availability",
            args: {
                room: frm.doc.room,
                arrival_date: frm.doc.arrival_date,
                departure_date: frm.doc.departure_date,
                ignore_reservation: frm.doc.name
            },
            callback: function (r) {
                if (r.exc) {
                    frm.set_value('room', '');
                }
            }
        });
    }
}