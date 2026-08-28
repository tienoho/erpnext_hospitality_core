// Copyright (c) 2026, Tuần Châu Group and contributors
// For license information, please see license.txt

frappe.query_reports["Police Guest Registration Report"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Công Ty"),
            fieldtype: "Link",
            options: "Company",
            default: "CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO",
            reqd: 1
        },
        {
            fieldname: "target_date",
            label: __("Ngày Khai Báo"),
            fieldtype: "Date",
            default: frappe.datetime.nowdate(),
            reqd: 1
        },
        {
            fieldname: "room",
            label: __("Số Phòng"),
            fieldtype: "Link",
            options: "Hotel Room"
        }
    ],

    onload: function (report) {
        // Nút Xuất Tệp Excel / CSV Chuẩn Công An tỉnh Quảng Ninh
        report.page.add_inner_button(__('Xuất File Excel/CSV (Có Dấu)'), function () {
            const values = report.get_values() || {};
            const target_date = values.target_date || frappe.datetime.nowdate();
            const company = encodeURIComponent(values.company || "CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO");
            const url = `/api/method/hospitality_core.hospitality_core.api.police_declaration.export_police_declaration_csv?target_date=${target_date}&company=${company}`;
            window.open(url, '_blank');
        }, __('Khai Báo Công An'));

        // Nút Xuất Tệp XML Nạp Cổng Dịch Vụ Công Quốc Gia
        report.page.add_inner_button(__('Xuất File XML (Cổng DVC)'), function () {
            const values = report.get_values() || {};
            const target_date = values.target_date || frappe.datetime.nowdate();
            const company = encodeURIComponent(values.company || "CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO");
            const url = `/api/method/hospitality_core.hospitality_core.api.police_declaration.export_police_declaration_xml?target_date=${target_date}&company=${company}`;
            window.open(url, '_blank');
        }, __('Khai Báo Công An'));
    }
};
