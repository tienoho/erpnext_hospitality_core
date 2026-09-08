frappe.pages['guest-360'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __('Hồ sơ khách'), single_column: true});
    wrapper.guest_content = $('<div class="p-3"></div>').appendTo($(wrapper).find('.layout-main-section'));
    wrapper.guest_request = 0;
    page.add_field({fieldname: 'guest', label: __('Khách'), fieldtype: 'Link', options: 'Guest', change() {
        render_guest_profile(wrapper, page.fields_dict.guest.get_value());
    }});
    wrapper.guest_content.text(__('Chọn khách để xem hồ sơ và lịch sử trong phạm vi được cấp quyền.'));
};

function render_guest_profile(wrapper, guest) {
    const request = ++wrapper.guest_request;
    const body = wrapper.guest_content;
    body.empty();
    if (!guest) return;
    body.text(__('Đang tải hồ sơ…'));
    const escape = value => frappe.utils.escape_html(String(value ?? ''));
    const amounts = values => Object.entries(values || {}).map(([currency, value]) =>
        `<div>${escape(format_currency(value, currency))}</div>`).join('') || '—';
    const table = (headers, rows) => `<div class="table-responsive"><table class="table table-bordered">
        <thead><tr>${headers.map(h => `<th>${escape(h)}</th>`).join('')}</tr></thead>
        <tbody>${rows.length ? rows.map(row => `<tr>${row.map(cell => `<td>${escape(cell)}</td>`).join('')}</tr>`).join('') :
        `<tr><td colspan="${headers.length}">${escape(__('Chưa có dữ liệu'))}</td></tr>`}</tbody></table></div>`;
    frappe.call({method: 'hospitality_core.hospitality_core.page.guest_360.guest_360.get_guest_details', args: {guest},
        callback(r) {
            if (request !== wrapper.guest_request) return;
            const d = r.message;
            if (!d) { body.empty(); return; }
            body.html(`<div class="row"><div class="col-md-4"><h3>${escape(d.guest.full_name)}</h3>
                <p>${escape(d.guest.email_id || '—')}<br>${escape(d.guest.mobile_no || '—')}</p>
                <p>${escape(d.guest.address || '')}</p><button class="btn btn-default" data-guest-edit>${escape(__('Mở hồ sơ'))}</button>
                </div><div class="col-md-4"><h4>${escape(__('Chi tiêu theo tiền tệ'))}</h4>${amounts(d.spend_by_currency)}</div>
                <div class="col-md-4"><h4>${escape(__('Công nợ theo tiền tệ'))}</h4>${amounts(d.balances_by_currency)}</div></div>
                <hr><h4>${escape(__('Sở thích còn hiệu lực'))}</h4>
                ${table([__('Loại'), __('Sở thích'), __('Phạm vi')], (d.preferences || []).map(p => [p.preference_type, p.preference_value, p.sharing_scope === 'Group' ? __('Dùng chung') : p.property]))}
                <h4>${escape(__('Hội viên theo pháp nhân'))}</h4>
                ${table([__('Chương trình'), __('Pháp nhân'), __('Hạng'), __('Điểm khả dụng'), __('Đang giữ')],
                    (d.memberships || []).map(m => [m.program, m.operating_company, m.tier, m.available, m.held]))}
                <h4>${escape(__('Yêu cầu đang xử lý'))}</h4>
                ${table([__('Nội dung'), __('Cơ sở'), __('Trạng thái'), __('Phụ trách')],
                    (d.interactions || []).map(i => [i.subject, i.property, i.status, i.assigned_to]))}
                <h4>${escape(__('Lịch sử lưu trú'))}</h4>
                ${table([__('Đặt phòng'), __('Cơ sở'), __('Phòng'), __('Ngày đến'), __('Ngày đi'), __('Trạng thái'), __('Còn lại')],
                    (d.history || []).map(h => [h.name, h.property, h.room, h.arrival_date, h.departure_date, h.status,
                        h.balance === null ? '—' : format_currency(h.balance, h.currency)]))}`);
            body.find('[data-guest-edit]').on('click', () => frappe.set_route('Form', 'Guest', d.guest.name));
        },
        error() {
            if (request === wrapper.guest_request) body.text(__('Không tải được hồ sơ. Vui lòng thử lại.'));
        }
    });
}
