frappe.query_reports["AR Aging Summary"] = {
    "filters": [
        {
            "fieldname": "as_of_date",
            "label": __("Tính Tuổi Nợ Đến Ngày"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname": "company",
            "label": __("Company (Khách Hàng)"),
            "fieldtype": "Link",
            "options": "Customer",
            "reqd": 0
        }
    ]
};
