frappe.query_reports["Housekeeping Productivity Report"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_days(frappe.datetime.get_today(), -7),
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname": "staff",
            "label": __("Nhân Viên"),
            "fieldtype": "Link",
            "options": "User",
            "reqd": 0
        }
    ]
};
