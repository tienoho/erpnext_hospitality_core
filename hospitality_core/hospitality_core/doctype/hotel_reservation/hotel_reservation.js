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
    guest: function (frm) {
        check_guest_blacklist_warning(frm);
        render_room_rate_preview(frm);
    },
    membership: function (frm) { render_room_rate_preview(frm); },
    currency: function (frm) { render_room_rate_preview(frm); },
    refresh: function (frm) {
        // Cảnh báo trực quan nếu khách đang trong danh sách đen — server
        // (validate_blacklist() trong hotel_reservation.py) mới là chốt chặn
        // thật sự, đây chỉ là tín hiệu để lễ tân biết SỚM thay vì đợi lưu
        // xong mới thấy lỗi. Gọi lại ở refresh (không chỉ ở sự kiện guest)
        // để hiển thị đúng cả khi mở lại một đặt phòng đã có sẵn khách.
        check_guest_blacklist_warning(frm);

        // Keep room type aligned with the selected room on load and refresh.
        sync_room_type_from_room(frm);
        frm.set_query('rate_plan', () => ({filters: {room_type: frm.doc.room_type, active: 1,
            ...(frm.doc.property ? {property: frm.doc.property, currency: frm.doc.currency} : {})}}));
        frm.set_query('room_type', () => ({filters: frm.doc.property ? {property: frm.doc.property} : {}}));
        frm.set_query('membership', () => ({filters: {guest: frm.doc.guest, operating_company: frm.doc.operating_company, enabled: 1}}));
        render_room_rate_preview(frm);

        // Filter Rooms based on Room Type AND Availability
        frm.set_query('room', function () {
            return {
                query: 'hospitality_core.hospitality_core.api.reservation.get_available_rooms_for_picker',
                filters: {
                    'arrival_date': frm.doc.arrival_date,
                    'departure_date': frm.doc.departure_date,
                    'room_type': frm.doc.room_type,
                    'ignore_reservation': frm.doc.name
                    , 'property': frm.doc.property
                }
            };
        });

        // Add Workflow Buttons
        if (!frm.is_new()) {

            // CHECK IN BUTTON WITH SURCHARGE DETECTION
            if (frm.doc.status === 'Reserved') {
                let $checkin_btn = frm.add_custom_button(__('Check In'), function () {
                    // Vô hiệu hóa nút ngay khi bấm — server đã tự khóa dòng đặt
                    // phòng (xem check_in_guest() trong hotel_reservation.py),
                    // nhưng vẫn nên chặn double-click ở phía client để không gửi
                    // 2 request song song cho cùng 1 lượt check-in (tính phòng 2 lần).
                    // Chỉ cần bật lại khi có lỗi/hủy — thành công thì frm.reload_doc()
                    // vẽ lại toàn bộ thanh nút nên không cần bật lại thủ công.
                    $checkin_btn.prop('disabled', true);
                    let reenable = () => $checkin_btn.prop('disabled', false);

                    let proceed = function () {
                    // Kiểm tra phụ thu nhận phòng sớm
                    frappe.call({
                        method: 'hospitality_core.hospitality_core.api.surcharge_engine.calculate_checkin_surcharge',
                        args: { reservation_name: frm.doc.name },
                        error: reenable,
                        callback: function (res) {
                            let sur = res.message;
                            if (sur && sur.applicable) {
                                let checkin_proceeding = false;
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
                                        checkin_proceeding = true;
                                        d.hide();
                                        // freeze:true lets Frappe unfreeze the screen itself whether the
                                        // call succeeds or throws — a manual dom.freeze()/unfreeze() pair
                                        // never runs the unfreeze half on an error response.
                                        frappe.call({
                                            method: 'hospitality_core.hospitality_core.api.surcharge_engine.apply_surcharge_to_folio',
                                            args: {
                                                reservation_name: frm.doc.name,
                                                surcharge_type: 'Early Check-in',
                                                description: sur.description
                                            },
                                            freeze: true,
                                            freeze_message: __('Đang áp dụng phụ thu và Check In...'),
                                            error: reenable,
                                            callback: function (r) {
                                                if (r.exc) { reenable(); return; }
                                                if (!r.message || !r.message.success) {
                                                    frappe.msgprint({
                                                        message: (r.message && r.message.message) || __('Không thể ghi nhận phụ thu.'),
                                                        indicator: 'red'
                                                    });
                                                    reenable();
                                                    return;
                                                }
                                                frm.call({
                                                    method: 'check_in_guest',
                                                    args: { name: frm.doc.name },
                                                    error: reenable,
                                                    callback: function () {
                                                        frappe.msgprint(__('Đã nhận phòng và ghi nhận phụ thu vào Folio.'));
                                                        frm.reload_doc();
                                                    }
                                                });
                                            }
                                        });
                                    },
                                    secondary_action_label: __('Miễn Phụ Thu & Check In')
                                });
                                // Nếu người dùng đóng dialog mà không chọn hành động nào (bấm X/ESC),
                                // vẫn phải bật lại nút "Check In" — nếu không sẽ kẹt vĩnh viễn cho
                                // đến khi tải lại trang, dù chưa hề gửi request check-in nào.
                                d.$wrapper.on('hidden.bs.modal', function () {
                                    if (!checkin_proceeding) reenable();
                                });
                                d.set_secondary_action(function () {
                                    checkin_proceeding = true;
                                    d.hide();
                                    let waive_prompt_submitted = false;
                                    let p = frappe.prompt([
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
                                        waive_prompt_submitted = true;
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
                                            error: reenable,
                                            callback: function (r) {
                                                if (!r.exc) {
                                                    frappe.show_alert({
                                                        message: __('Guest Checked In Successfully (Đã ghi nhận lý do miễn phụ thu).'),
                                                        indicator: 'green'
                                                    });
                                                    frm.reload_doc();
                                                } else {
                                                    reenable();
                                                }
                                            }
                                        });
                                    }, __('Xác Nhận Miễn Phụ Thu Nhận Phòng Sớm'), __('Xác Nhận & Check In'));
                                    // Nếu người dùng đóng prompt (bấm X) mà không bấm nút xác nhận,
                                    // vẫn cần bật lại nút "Check In" gốc.
                                    if (p && p.$wrapper) {
                                        p.$wrapper.on('hidden.bs.modal', function () {
                                            if (!waive_prompt_submitted) reenable();
                                        });
                                    }
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
                                            error: reenable,
                                            callback: function (r) {
                                                if (!r.exc) {
                                                    frappe.msgprint('Guest Checked In Successfully');
                                                    frm.reload_doc();
                                                } else {
                                                    reenable();
                                                }
                                            }
                                        });
                                    },
                                    reenable
                                );
                            }
                        }
                    });
                    };

                    // Lưu form TRƯỚC khi check-in nếu có sửa đổi chưa lưu — TRƯỚC
                    // ĐÂY nếu lễ tân vừa sửa discount_type/discount_value/
                    // is_complimentary (preview giá cập nhật ngay lập tức, không
                    // cần lưu form) rồi bấm "Check In" luôn mà CHƯA lưu, server
                    // tính tiền dựa trên bản ghi ĐÃ LƯU trong DB (check_in_guest()
                    // đọc lại document từ DB, không đọc frm.doc trên trình duyệt)
                    // — khách bị tính tiền theo giá CŨ dù màn hình vừa hiện giá đã
                    // giảm giá/miễn phí.
                    if (frm.is_dirty()) {
                        frm.save().then(proceed).catch(reenable);
                    } else {
                        proceed();
                    }
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
                                        frappe.call({
                                            method: 'hospitality_core.hospitality_core.api.surcharge_engine.apply_surcharge_to_folio',
                                            args: {
                                                reservation_name: frm.doc.name,
                                                surcharge_type: 'Late Check-out',
                                                description: sur.description
                                            },
                                            freeze: true,
                                            freeze_message: __('Đang áp dụng phụ thu và Check Out...'),
                                            callback: function (r) {
                                                if (r.exc) return;
                                                if (!r.message || !r.message.success) {
                                                    frappe.msgprint({
                                                        message: (r.message && r.message.message) || __('Không thể ghi nhận phụ thu.'),
                                                        indicator: 'red'
                                                    });
                                                    return;
                                                }
                                                frm.call({
                                                    method: 'check_out_guest',
                                                    args: { name: frm.doc.name },
                                                    callback: function () {
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
                            onchange() {
                                const room = d.get_value('new_room');
                                if (!room) return;
                                frappe.db.get_value('Hotel Room', room, 'room_type').then(r => {
                                    if (d.get_value('new_room') !== room) return;
                                    const type = r.message.room_type;
                                    d.set_value('new_room_type', type);
                                    d.set_value('new_rate_plan', type === frm.doc.room_type ? frm.doc.rate_plan : '');
                                });
                            },
                            get_query: function () {
                                return {
                                    filters: {
                                        'is_enabled': 1,
                                        'name': ['!=', frm.doc.room]
                                    }
                                };
                            },
                            reqd: 1
                        },
                        {fieldname: 'new_room_type', fieldtype: 'Link', options: 'Hotel Room Type', label: 'Hạng phòng mới', read_only: 1},
                        {fieldname: 'new_rate_plan', fieldtype: 'Link', options: 'Room Rate Plan', label: 'Bảng giá sau chuyển phòng',
                            description: 'Đổi hạng phòng mà không chọn bảng giá: dùng giá mặc định của hạng mới.',
                            get_query: () => ({filters: {room_type: d.get_value('new_room_type'), active: 1}})}
                    ],
                    primary_action_label: 'Move',
                    primary_action: function (values) {
                        // Disable immediately to prevent a double-click firing two
                        // concurrent process_room_move calls before the first resolves.
                        d.get_primary_btn().prop('disabled', true);
                        frm.call({
                            method: 'hospitality_core.hospitality_core.api.room_move.process_room_move',
                            args: {
                                reservation_name: frm.doc.name,
                                new_room: values.new_room,
                                new_rate_plan: values.new_rate_plan || null
                            },
                            freeze: true,
                            callback: function (r) {
                                if (!r.exc) {
                                    d.hide();
                                    frm.reload_doc();
                                } else {
                                    d.get_primary_btn().prop('disabled', false);
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
                get_keycard_time_window(frm, function (checkin_time, checkout_time) {
                    if (window.frappe && frappe.hospitality && frappe.hospitality.encode_keycard) {
                        frappe.hospitality.encode_keycard(
                            frm.doc.room,
                            checkin_time,
                            checkout_time,
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
                                checkin_time: checkin_time,
                                checkout_time: checkout_time,
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
                });
            }, __('Khóa Thẻ Từ'));

            frm.add_custom_button(__('Ghi Thẻ Phụ (Duplicate)'), function () {
                get_keycard_time_window(frm, function (checkin_time, checkout_time) {
                    fetch('http://127.0.0.1:8765/api/lock/encode_card', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            room_no: frm.doc.room,
                            checkin_time: checkin_time,
                            checkout_time: checkout_time,
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

        // Một plan chỉ áp dụng cho đúng hạng phòng.
        frm.set_value('rate_plan', '');
        frm.set_value('room', '');
        render_room_rate_preview(frm);
    },

    arrival_date: function (frm) {
        calculate_nights(frm);
        validate_room_availability(frm);
        render_room_rate_preview(frm);
    },

    departure_date: function (frm) {
        calculate_nights(frm);
        validate_room_availability(frm);
        render_room_rate_preview(frm);
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

// Chuẩn giờ mở/khóa thẻ từ theo giờ chuẩn, nhưng nới rộng nếu khách đã trả
// phụ thu nhận phòng sớm / trả phòng muộn cho Folio này — tránh việc thẻ
// khóa cửa dù khách đã trả tiền để vào/ở lại ngoài giờ chuẩn.
function get_keycard_time_window(frm, callback) {
    let checkin_time = frm.doc.arrival_date + ' 14:00:00';
    let checkout_time = frm.doc.departure_date + ' 12:00:00';

    if (!frm.doc.folio) {
        callback(checkin_time, checkout_time);
        return;
    }

    frappe.db.get_list('Folio Transaction', {
        filters: {
            parent: frm.doc.folio,
            item: ['in', ['SURCHARGE-EARLY', 'SURCHARGE-LATE']],
            is_void: 0
        },
        fields: ['item'],
        limit: 0
    }).then(rows => {
        rows = rows || [];
        if (rows.some(r => r.item === 'SURCHARGE-EARLY')) {
            checkin_time = frappe.datetime.now_datetime();
        }
        if (rows.some(r => r.item === 'SURCHARGE-LATE')) {
            checkout_time = frm.doc.departure_date + ' 23:59:59';
        }
        callback(checkin_time, checkout_time);
    }).catch(() => callback(checkin_time, checkout_time));
}

function check_guest_blacklist_warning(frm) {
    if (!frm.doc.guest) return;

    frappe.db.get_value('Guest', frm.doc.guest, 'guest_type').then((r) => {
        if (r.message && r.message.guest_type === 'Blacklisted') {
            frm.dashboard.add_indicator(
                __('⚠ Khách Trong Danh Sách Đen (Blacklisted) — Cần Supervisor Phê Duyệt & Ghi Lý Do'),
                'red'
            );
        }
    });
}

function sync_room_type_from_room(frm) {
    if (!frm.doc.room) {
        return;
    }

    const selectedRoom = frm.doc.room;
    frappe.db.get_value('Hotel Room', selectedRoom, 'room_type').then(r => {
        if (frm.doc.room !== selectedRoom) return;
        let room_type = r.message ? r.message.room_type : null;
        if (!room_type || frm.doc.room_type === room_type) {
            return;
        }

        if (frm.doc.status === 'Reserved' || frm.is_new()) frm.set_value('rate_plan', '');
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
    const wrapper = frm.fields_dict.room_rate_preview.$wrapper;
    const requestId = frm.__rate_preview_request = (frm.__rate_preview_request || 0) + 1;
    if (!frm.doc.room || !frm.doc.arrival_date || !frm.doc.departure_date) {
        wrapper.html('<div class="text-muted small">Chọn phòng, ngày đến và ngày đi để xem giá.</div>');
        return;
    }
    const args = {
        room: frm.doc.room, room_type: frm.doc.room_type, rate_plan: frm.doc.rate_plan,
        arrival_date: frm.doc.arrival_date, departure_date: frm.doc.departure_date,
        discount_type: frm.doc.discount_type, discount_value: frm.doc.discount_value,
        is_complimentary: frm.doc.is_complimentary,
        property: frm.doc.property, currency: frm.doc.currency, membership: frm.doc.membership, guest: frm.doc.guest,
        reservation_name: frm.is_new() ? null : frm.doc.name
    };
    wrapper.html('<div class="text-muted small">Đang tính giá từng đêm…</div>');
    frappe.call({
        method: 'hospitality_core.hospitality_core.api.reservation.get_room_rate', args,
        callback(r) {
            if (requestId !== frm.__rate_preview_request || !r.message) return;
            const d = r.message;
            const escape = value => frappe.utils.escape_html(String(value ?? ''));
            const currency = d.currency || frm.doc.currency || frappe.boot.sysdefaults.currency;
            const amount = value => format_currency(value, currency);
            let html = '<div class="table-responsive"><table class="table table-bordered table-condensed">' +
                '<thead><tr><th>Đêm</th><th>Mùa vụ</th><th>Giá gốc</th><th>Giảm LOS</th><th>Giảm VIP</th><th>Giảm khác</th><th>Thành tiền</th></tr></thead><tbody>';
            for (const row of d.nightly_rates || []) {
                html += `<tr><td>${escape(row.date)}</td><td>${escape(row.season_name || 'Giá mặc định')}</td>` +
                    `<td>${amount(row.base_rate)}</td><td>${amount(row.los_discount)} (${escape(row.los_percent)}%)</td>` +
                    `<td>${amount(row.vip_discount || 0)}</td><td>${amount(row.manual_discount)}</td><td>${amount(row.final_rate)}</td></tr>`;
            }
            html += `</tbody></table></div><p><strong>Tổng ${escape(d.nights)} đêm: ${amount(d.total)}</strong></p>`;
            html += '<p class="text-muted small">Tiền phòng theo bảng giá; thuế/phí theo cấu hình cơ sở. Thứ tự giảm: LOS → VIP → giảm riêng.</p>';
            if (d.snapshot_locked) html += '<p class="text-muted small">Đang dùng căn cứ giá đã lưu lúc đặt phòng.</p>';
            if (d.checkin_charge) html += `<p>Nhận phòng lúc này: ghi tiền ngày <strong>${escape(d.checkin_charge.date)}</strong>, ` +
                `<strong>${amount(d.checkin_charge.final_rate)}</strong> (trước 08:00 tính ngày trước).</p>`;
            wrapper.html(html);
        },
        error() {
            if (requestId === frm.__rate_preview_request)
                wrapper.html('<div class="text-danger">Không tính được giá. Kiểm tra ngày lưu trú và bảng giá đã chọn.</div>');
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
