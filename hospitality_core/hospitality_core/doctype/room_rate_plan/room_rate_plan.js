frappe.ui.form.on('Room Rate Plan', {
    refresh(frm) {
        frm.set_intro(__('Cuối tuần: thứ 6 và thứ 7. Giá cuối tuần để trống/0 dùng giá ngày thường. Ngoài mùa vụ dùng giá mặc định và không áp LOS.'));
        frm.add_custom_button(__('Thử bảng giá'), () => {
            if (!frm.doc.room_type) {
                frappe.msgprint(__('Chọn loại phòng trước khi thử giá.'));
                return;
            }
            let sequence = 0;
            const dialog = new frappe.ui.Dialog({
                title: __('Thử bảng giá theo kỳ lưu trú'),
                fields: [
                    {fieldname: 'arrival_date', fieldtype: 'Date', label: __('Ngày đến'), reqd: 1,
                        default: frappe.datetime.get_today()},
                    {fieldname: 'departure_date', fieldtype: 'Date', label: __('Ngày đi'), reqd: 1,
                        default: frappe.datetime.add_days(frappe.datetime.get_today(), 3)},
                    {fieldname: 'result', fieldtype: 'HTML'}
                ],
                primary_action_label: __('Tính giá'),
                primary_action(values) {
                    const request = ++sequence;
                    dialog.get_primary_btn().prop('disabled', true);
                    frappe.call({
                        method: 'hospitality_core.hospitality_core.api.rate_plan.preview_plan_configuration',
                        args: {room_type: frm.doc.room_type, seasons: JSON.stringify(frm.doc.seasons || []),
                            los_discounts: JSON.stringify(frm.doc.los_discounts || []), ...values},
                        callback(response) {
                            if (request !== sequence || !response.message) return;
                            const quote = response.message;
                            const escape = value => frappe.utils.escape_html(String(value ?? ''));
                            let html = '<div class="table-responsive"><table class="table table-bordered">' +
                                '<thead><tr><th>Đêm</th><th>Mùa vụ</th><th>Giá gốc</th><th>Giảm LOS</th><th>Thành tiền</th></tr></thead><tbody>';
                            for (const row of quote.nightly_rates) html += `<tr><td>${escape(row.date)}</td>` +
                                `<td>${escape(row.season_name || 'Giá mặc định')}</td><td>${format_currency(row.base_rate)}</td>` +
                                `<td>${format_currency(row.los_discount)} (${escape(row.los_percent)}%)</td>` +
                                `<td>${format_currency(row.final_rate)}</td></tr>`;
                            dialog.fields_dict.result.$wrapper.html(html + `</tbody></table></div>` +
                                `<p><strong>Tổng ${escape(quote.nights)} đêm: ${format_currency(quote.total)}</strong></p>` +
                                '<p class="text-muted">Đây là giá thử theo cấu hình trên form, chưa gồm phụ thu hoặc giảm giá riêng của đặt phòng.</p>');
                        },
                        always() { if (request === sequence) dialog.get_primary_btn().prop('disabled', false); }
                    });
                }
            });
            dialog.show();
        });
    },
    validate(frm) {
        const seasons = frm.doc.seasons || [];
        for (let i = 0; i < seasons.length; i++) {
            const a = seasons[i];
            if (a.valid_from && a.valid_to && a.valid_from > a.valid_to)
                frappe.throw(__('Mùa vụ dòng {0}: ngày bắt đầu sau ngày kết thúc.', [a.idx]));
            for (let j = 0; j < i; j++) {
                const b = seasons[j];
                if (a.valid_from && a.valid_to && b.valid_from && b.valid_to && a.valid_from <= b.valid_to && a.valid_to >= b.valid_from)
                    frappe.throw(__('Mùa vụ dòng {0} trùng ngày với dòng {1}.', [a.idx, b.idx]));
            }
        }
        const thresholds = new Map();
        for (const tier of frm.doc.los_discounts || []) {
            if (thresholds.has(Number(tier.min_nights)))
                frappe.throw(__('Bậc LOS dòng {0} trùng số đêm với dòng {1}.', [tier.idx, thresholds.get(Number(tier.min_nights))]));
            thresholds.set(Number(tier.min_nights), tier.idx);
        }
    }
});
