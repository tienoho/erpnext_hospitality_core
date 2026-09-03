frappe.ui.form.on('Hospitality Police Settings', {
    refresh: function (frm) {
        frm.set_intro(__('Cấu hình thông tin cơ sở lưu trú và kết nối Cổng Dịch vụ công Quản lý Xuất nhập cảnh & Tạm trú Công an tỉnh Quảng Ninh.'), 'blue');
        
        if (frm.doc.immigration_portal_url) {
            frm.add_custom_button(__('Mở Cổng XNC Quảng Ninh'), function () {
                window.open(frm.doc.immigration_portal_url, '_blank');
            }, 'Actions');
        }

        frm.add_custom_button(__('📊 Tải Excel XNC (XLSX)'), function () {
            let today = frappe.datetime.now_date();
            window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_quangninh_immigration_report_xlsx?target_date=${today}`);
        }, 'Actions');

        frm.add_custom_button(__('📊 Tải Excel Tạm Trú Toàn Bộ (XLSX)'), function () {
            let today = frappe.datetime.now_date();
            window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_police_declaration_xlsx?target_date=${today}`);
        }, 'Actions');

        frm.add_custom_button(__('Tải Biểu Mẫu CSV XNC'), function () {
            let today = frappe.datetime.now_date();
            window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_quangninh_immigration_report?target_date=${today}`);
        }, 'Actions');
    }
});
