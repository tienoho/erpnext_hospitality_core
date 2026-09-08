import frappe
from frappe import _
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": _("Date Reported"), "fieldname": "creation", "fieldtype": "Date", "width": 100},
        {"label": _("Request ID"), "fieldname": "name", "fieldtype": "Link", "options": "Hotel Maintenance Request", "width": 140},
        {"label": _("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Hotel Room", "width": 80},
        {"label": _("Issue Type"), "fieldname": "issue_type", "fieldtype": "Data", "width": 100},
        {"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 250},
        {"label": _("Reported By"), "fieldname": "reported_by_name", "fieldtype": "Data", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": _("Resolution Notes"), "fieldname": "resolution_notes", "fieldtype": "Data", "width": 200}
    ]

    conditions = "1=1"
    params = {}

    if filters.get("from_date") and filters.get("to_date"):
        conditions += " AND DATE(hmr.creation) BETWEEN %(from_date)s AND %(to_date)s"
        params["from_date"] = filters.get("from_date")
        params["to_date"] = filters.get("to_date")

    if filters.get("status"):
        conditions += " AND hmr.status = %(status)s"
        params["status"] = filters.get("status")

    allowed_properties = allowed_properties_for_report()
    if allowed_properties is not None:
        conditions += " AND hmr.property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    sql = f"""
        SELECT
            DATE(hmr.creation) as creation,
            hmr.name,
            hmr.room,
            hmr.issue_type,
            hmr.description,
            u.full_name as reported_by_name,
            hmr.status,
            hmr.resolution_notes
        FROM
            `tabHotel Maintenance Request` hmr
        LEFT JOIN
            `tabUser` u ON hmr.reported_by = u.name
        WHERE
            {conditions}
        ORDER BY
            hmr.creation DESC
    """
    
    data = frappe.db.sql(sql, params, as_dict=True)
    
    return columns, data