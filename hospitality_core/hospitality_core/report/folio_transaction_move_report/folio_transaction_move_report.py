import frappe
from frappe import _
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    columns, data = [], []
    
    columns = get_columns()
    data = get_data(filters)
    
    return columns, data

def get_columns():
    return [
        {
            "label": _("Move Date"),
            "fieldname": "move_datetime",
            "fieldtype": "Datetime",
            "width": 160
        },
        {
            "label": _("Transaction ID"),
            "fieldname": "transaction_name",
            "fieldtype": "Data",
            "width": 140
        },
        {
            "label": _("Item"),
            "fieldname": "item",
            "fieldtype": "Link",
            "options": "Item",
            "width": 120
        },
        {
            "label": _("Amount"),
            "fieldname": "amount",
            "fieldtype": "Currency",
            "width": 100
        },
        {
            "label": _("Source Folio"),
            "fieldname": "source_folio",
            "fieldtype": "Link",
            "options": "Guest Folio",
            "width": 140
        },
        {
            "label": _("Target Folio"),
            "fieldname": "target_folio",
            "fieldtype": "Link",
            "options": "Guest Folio",
            "width": 140
        },
        {
            "label": _("User"),
            "fieldname": "user",
            "fieldtype": "Link",
            "options": "User",
            "width": 120
        }
    ]

def get_data(filters):
    conditions = ""
    params = {}
    if filters:
        if filters.get("from_date"):
            conditions += " AND move_datetime >= %(from_date)s"
            params["from_date"] = filters.get("from_date")
        if filters.get("to_date"):
            conditions += " AND move_datetime <= %(to_date)s"
            params["to_date"] = f"{filters.get('to_date')} 23:59:59"

    allowed_properties = allowed_properties_for_report()
    if allowed_properties is not None:
        conditions += " AND property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    data = frappe.db.sql(f"""
        SELECT
            move_datetime, transaction_name, item, amount,
            source_folio, target_folio, user
        FROM `tabFolio Transaction Move Log`
        WHERE 1=1 {conditions}
        ORDER BY move_datetime DESC
    """, params, as_dict=1)

    return data
