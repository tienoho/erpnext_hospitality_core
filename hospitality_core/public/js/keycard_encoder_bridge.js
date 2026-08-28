// keycard_encoder_bridge.js
// Tuần Châu Resort Hạ Long - Door Lock Keycard Encoder Bridge Client Helper

frappe.provide('frappe.hospitality');

frappe.hospitality.BRIDGE_URL = 'http://127.0.0.1:8765';

/**
 * Kiểm tra trạng thái kết nối tới Local Hardware Bridge
 */
frappe.hospitality.check_bridge_status = async function() {
    try {
        const response = await fetch(`${frappe.hospitality.BRIDGE_URL}/api/status`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        if (response.ok) {
            const data = await response.json();
            return { online: true, data: data };
        }
    } catch (err) {
        console.warn('[KeycardBridge] Local Hardware Bridge not reachable at 127.0.0.1:8765', err);
    }
    return { online: false, message: 'Chưa khởi động Hardware Bridge trên máy tính Lễ tân' };
};

/**
 * Ghi thẻ từ phòng khách sạn cho Lễ tân
 */
frappe.hospitality.encode_keycard = async function(room_no, checkin_time, checkout_time, guest_name, is_duplicate) {
    frappe.show_alert({
        message: __('Đang kết nối đầu đọc thẻ từ...'),
        indicator: 'blue'
    });

    try {
        const response = await fetch(`${frappe.hospitality.BRIDGE_URL}/api/lock/encode_card`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                room_no: room_no,
                checkin_time: checkin_time || frappe.datetime.now_datetime(),
                checkout_time: checkout_time || frappe.datetime.add_days(frappe.datetime.now_date(), 1) + ' 12:00:00',
                guest_name: guest_name || '',
                is_duplicate: is_duplicate || false
            })
        });

        const result = await response.json();
        if (result.success) {
            frappe.msgprint({
                title: __('Ghi Thẻ Phòng Thành Công'),
                indicator: 'green',
                message: `
                    <div style="padding: 10px; line-height: 1.6;">
                        <p><b>Số phòng:</b> <span class="badge badge-success" style="font-size: 14px;">${result.room_no}</span></p>
                        <p><b>Khách lưu trú:</b> ${result.guest_name || 'Khách lẻ'}</p>
                        <p><b>Mã thẻ UID:</b> <code>${result.card_uid}</code></p>
                        <p><b>Hạn sử dụng:</b> Từ ${result.checkin_time} đến ${result.checkout_time}</p>
                        <p style="color: green;">✔ Đã nạp dữ liệu khóa thành công vào thẻ từ.</p>
                    </div>
                `
            });
            return result;
        } else {
            frappe.msgprint({
                title: __('Lỗi Ghi Thẻ'),
                indicator: 'red',
                message: result.error || result.message || __('Không thể ghi thẻ từ.')
            });
        }
    } catch (err) {
        frappe.msgprint({
            title: __('Lỗi Kết Nối Đầu Đọc Thẻ'),
            indicator: 'red',
            message: `
                <p>Không thể kết nối tới dịch vụ phần cứng tại <b>http://127.0.0.1:8765</b>.</p>
                <p>Vui lòng kiểm tra:</p>
                <ul>
                    <li>1. Đã cắm đầu đọc thẻ vào cổng USB máy tính Lễ tân.</li>
                    <li>2. Đã chạy tệp <code>run_bridge.bat</code> trên máy tính.</li>
                </ul>
            `
        });
    }
};

/**
 * Xóa/Thu hồi thẻ phòng
 */
frappe.hospitality.clear_keycard = async function() {
    try {
        const response = await fetch(`${frappe.hospitality.BRIDGE_URL}/api/lock/clear_card`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await response.json();
        if (result.success) {
            frappe.show_alert({
                message: __('Đã xóa và thu hồi thẻ phòng thành công!'),
                indicator: 'green'
            });
        }
    } catch (err) {
        frappe.show_alert({
            message: __('Không thể kết nối đầu đọc thẻ!'),
            indicator: 'red'
        });
    }
};
