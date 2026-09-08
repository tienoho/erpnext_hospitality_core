import frappe
from frappe import _
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": _("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Hotel Room", "width": 80},
        {"label": _("Folio ID"), "fieldname": "name", "fieldtype": "Link", "options": "Guest Folio", "width": 140},
        {"label": _("Guest Name"), "fieldname": "guest_name", "fieldtype": "Data", "width": 160},
        {"label": _("Arr Date"), "fieldname": "arrival_date", "fieldtype": "Date", "width": 100},
        {"label": _("Dep Date"), "fieldname": "departure_date", "fieldtype": "Date", "width": 100},
        {"label": _("Charges"), "fieldname": "total_charges", "fieldtype": "Currency", "width": 100},
        {"label": _("Payments"), "fieldname": "total_payments", "fieldtype": "Currency", "width": 100},
        {"label": _("Balance Due"), "fieldname": "balance_due", "fieldtype": "Currency", "width": 120},
        {"label": _("Excess Payment"), "fieldname": "excess_payment", "fieldtype": "Currency", "width": 120}
    ]

    conditions = "gf.status = 'Open'"

    if not filters.get("show_corporate"):
        conditions += " AND (gf.company IS NULL OR gf.company = '')"
    else:
        # A company-billed charge lives on the guest's own folio AND, once
        # mirrored, also on that company's Master Folio. Only show a non-master
        # folio here when its company has no Master Folio to mirror into yet,
        # so the same charge isn't listed (and totalled) twice.
        conditions += """ AND (
            gf.company IS NULL OR gf.company = '' OR gf.is_company_master = 1
            OR NOT EXISTS (
                SELECT 1 FROM `tabGuest Folio` m
                WHERE m.company = gf.company AND m.is_company_master = 1
                AND m.status = 'Open' AND m.name != gf.name
            )
        )"""

    params = {}
    allowed_properties = allowed_properties_for_report()
    if allowed_properties is not None:
        conditions += " AND gf.property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    sql = f"""
        SELECT
            gf.room,
            gf.name,
            guest.full_name as guest_name,
            res.arrival_date,
            res.departure_date,
            gf.total_charges,
            gf.total_payments,
            CASE WHEN gf.outstanding_balance > 0 THEN gf.outstanding_balance ELSE 0 END as balance_due,
            gf.excess_payment
        FROM
            `tabGuest Folio` gf
        LEFT JOIN
            `tabGuest` guest ON gf.guest = guest.name
        LEFT JOIN
            `tabHotel Reservation` res ON gf.reservation = res.name
        WHERE
            {conditions}
            AND (gf.outstanding_balance != 0)
        ORDER BY
            gf.room ASC
    """

    data = frappe.db.sql(sql, params, as_dict=True)
    
    # Add Total Row
    if data:
        total_due = sum(d.balance_due for d in data)
        total_excess = sum(d.excess_payment for d in data)
        data.append({
            "guest_name": "<b>TOTALS</b>",
            "balance_due": total_due,
            "excess_payment": total_excess
        })

    return columns, data