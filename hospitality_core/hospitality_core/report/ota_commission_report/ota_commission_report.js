frappe.query_reports["OTA Commission Report"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
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
            "fieldname": "ota_platform",
            "label": __("Kênh OTA"),
            "fieldtype": "Select",
            "options": "\nAgoda\nBooking.com\nTraveloka\nTrip.com\nOther",
            "reqd": 0
        }
    ]
};
