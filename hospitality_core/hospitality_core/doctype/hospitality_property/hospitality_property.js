frappe.ui.form.on('Hospitality Property', {
    refresh(frm) {
        frm.set_intro(__('Cơ sở chỉ được kích hoạt sau khi có cấu hình kế toán, mapping dữ liệu và nghiệm thu tích hợp.'), 'blue');
        if (frm.is_new()) return;
        frm.add_custom_button(__('Cấu hình cơ sở'), () => frappe.set_route('Form', 'Hospitality Property Settings', frm.doc.name));
        frm.add_custom_button(__('Sao chép cấu hình cũ'), () => frappe.call({
            method: 'hospitality_core.hospitality_core.api.property_setup.copy_legacy_settings',
            args: {property: frm.doc.name}, callback: r => frappe.set_route('Form', 'Hospitality Property Settings', r.message)
        }));
        frm.add_custom_button(__('Ánh xạ dữ liệu'), () => {
            let preview = null;
            const dialog = new frappe.ui.Dialog({title: __('Ánh xạ dữ liệu vào cơ sở'), fields: [
                {fieldname: 'mapping', label: __('DocType và mã bản ghi (JSON)'), fieldtype: 'Code', options: 'JSON', reqd: 1,
                    description: __('Ví dụ: {"Hotel Room": ["101"], "Hotel Room Type": ["Deluxe"]}'), onchange() { preview = null; }},
                {fieldname: 'confirmed_currency', label: __('Tiền tệ đã xác minh của dữ liệu lịch sử'), fieldtype: 'Link', options: 'Currency', reqd: 1},
                {fieldname: 'result', fieldtype: 'HTML'}
            ], primary_action_label: __('Kiểm tra mapping'), primary_action(values) {
                const submitted = values.mapping;
                frappe.call({method: 'hospitality_core.hospitality_core.api.property_setup.inspect_mapping',
                    args: {property: frm.doc.name, mapping: submitted}, callback(r) {
                        if (dialog.get_value('mapping') !== submitted) return;
                        const data = r.message;
                        preview = data.errors.length ? null : submitted;
                        dialog.fields_dict.result.$wrapper.text(JSON.stringify(data, null, 2));
                    }});
            }});
            dialog.set_secondary_action_label(__('Áp dụng mapping đã kiểm tra'));
            dialog.set_secondary_action(() => {
                const values = dialog.get_values();
                if (!values || preview !== values.mapping) {
                    frappe.msgprint(__('Cần kiểm tra lại mapping trước khi áp dụng.'));
                    return;
                }
                frappe.call({method: 'hospitality_core.hospitality_core.api.property_setup.apply_mapping',
                    args: {property: frm.doc.name, mapping: values.mapping, confirmed_currency: values.confirmed_currency},
                    freeze: true, callback() { dialog.hide(); frm.reload_doc(); }});
            });
            dialog.show();
        });
        frm.add_custom_button(__('Kiểm tra điều kiện cơ sở'), () => frappe.call({
            method: 'hospitality_core.hospitality_core.api.property_setup.verify_property', args: {property: frm.doc.name},
            freeze: true, callback() { frm.reload_doc(); }
        }));
    }
});
