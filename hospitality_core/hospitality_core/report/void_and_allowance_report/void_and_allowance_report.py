import frappe
from frappe import _
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Folio"), "fieldname": "parent", "fieldtype": "Link", "options": "Guest Folio", "width": 140},
        {"label": _("Room"), "fieldname": "room", "fieldtype": "Data", "width": 80},
        {"label": _("Guest"), "fieldname": "guest_name", "fieldtype": "Data", "width": 150},
        {"label": _("Type"), "fieldname": "type", "fieldtype": "Data", "width": 100},
        {"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 200},
        {"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Reason"), "fieldname": "void_reason", "fieldtype": "Data", "width": 150},
        {"label": _("User"), "fieldname": "owner", "fieldtype": "Data", "width": 120}
    ]

    # Filters
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    data = []

    allowed_properties = allowed_properties_for_report()
    property_condition = ""
    property_params = ()
    if allowed_properties is not None:
        property_condition = "AND ft.property IN %s"
        property_params = (allowed_properties or [""],)

    # 1. Fetch Voids (Logically deleted/reversed transactions)
    # is_void = 1
    voids = frappe.db.sql(f"""
        SELECT
            ft.posting_date,
            ft.parent,
            gf.room,
            g.full_name as guest_name,
            'Void' as type,
            ft.description,
            ft.amount,
            ft.void_reason,
            ft.owner
        FROM `tabFolio Transaction` ft
        JOIN `tabGuest Folio` gf ON ft.parent = gf.name
        LEFT JOIN `tabGuest` g ON gf.guest = g.name
        WHERE ft.posting_date BETWEEN %s AND %s
        AND ft.is_void = 1
        AND COALESCE(ft.mirror_source, '') = ''
        {property_condition}
    """, (from_date, to_date) + property_params, as_dict=True)

    # 2. Fetch Allowances/Discounts (Negative amounts, not payments)
    # Exclude Payment Items
    payment_items = frappe.get_all("Item", filters={"item_group": "Payment"}, pluck="name")
    # If using specific codes like PAYMENT-CASH, ensure logic covers it.
    # We look for amounts < 0 AND item NOT IN payment_items
    
    # Also check for "Complimentary" in description or specific Reason Codes
    
    allowances = frappe.db.sql(f"""
        SELECT
            ft.posting_date,
            ft.parent,
            gf.room,
            g.full_name as guest_name,
            CASE
                WHEN ft.description LIKE '%%Discount%%' THEN 'Discount'
                WHEN ft.description LIKE '%%Complimentary%%' THEN 'Complimentary'
                ELSE 'Allowance'
            END as type,
            ft.description,
            ft.amount,
            ft.void_reason,
            ft.owner
        FROM `tabFolio Transaction` ft
        JOIN `tabGuest Folio` gf ON ft.parent = gf.name
        LEFT JOIN `tabGuest` g ON gf.guest = g.name
        WHERE ft.posting_date BETWEEN %s AND %s
        AND ft.is_void = 0
        AND ft.amount < 0
        AND ft.item NOT IN (SELECT name FROM `tabItem` WHERE item_group = 'Payment')
        AND ft.description NOT LIKE '%%Payment%%'
        AND ft.description NOT LIKE '%%Transfer%%'
        AND COALESCE(ft.mirror_source, '') = ''
        AND ft.reference_doctype != 'Folio Transaction'
        {property_condition}
    """, (from_date, to_date) + property_params, as_dict=True)

    data = voids + allowances
    
    # Sort by Date
    data.sort(key=lambda x: x['posting_date'])

    # Chart Data
    void_total = sum([d['amount'] for d in voids])
    allowance_total = sum([abs(d['amount']) for d in allowances]) # Display positive for chart
    
    chart = {
        "data": {
            "labels": ["Voids", "Discounts/Allowances"],
            "datasets": [{"name": "Total Impact", "values": [void_total, allowance_total]}]
        },
        "type": "donut"
    }
    
    # Summary Row
    if data:
        data.append({
            "description": "<b>TOTAL IMPACT</b>",
            "amount": sum([d['amount'] for d in data])
        })

    return columns, data, None, chart