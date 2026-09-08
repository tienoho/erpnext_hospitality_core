frappe.query_reports["Monthly Revenue by Room Type"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -6),
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
            "fieldname": "room_type",
            "label": __("Room Type"),
            "fieldtype": "Link",
            "options": "Hotel Room Type",
            "reqd": 0
        }
    ]
};
