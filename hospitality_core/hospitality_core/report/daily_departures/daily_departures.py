import frappe
from frappe import _
from frappe.utils import nowdate
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    if not filters:
        filters = {}
    
    target_date = filters.get("date") or nowdate()

    columns = [
        {"label": _("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Hotel Room", "width": 80},
        {"label": _("Guest Name"), "fieldname": "guest_name", "fieldtype": "Data", "width": 150},
        {"label": _("Reservation"), "fieldname": "name", "fieldtype": "Link", "options": "Hotel Reservation", "width": 140},
        {"label": _("Checkout Time"), "fieldname": "checkout_time", "fieldtype": "Time", "width": 100},
        {"label": _("Folio"), "fieldname": "folio", "fieldtype": "Link", "options": "Guest Folio", "width": 140},
        {"label": _("Billed To"), "fieldname": "bill_to", "fieldtype": "Data", "width": 140},
        {"label": _("Total Bill"), "fieldname": "total_charges", "fieldtype": "Currency", "width": 120},
        {"label": _("Receipts"), "fieldname": "total_payments", "fieldtype": "Currency", "width": 120}
    ]

    # Definition: "list of people that checked out per day"
    # Logic: Status is 'Checked Out' AND Departure Date is Target Date.
    
    sql = """
        SELECT
            res.room,
            guest.full_name as guest_name,
            res.name,
            TIME(res.modified) as checkout_time,
            res.folio,
            COALESCE(res.company, 'Guest') as bill_to,
            folio.total_charges,
            folio.total_payments
        FROM
            `tabHotel Reservation` res
        LEFT JOIN
            `tabGuest` guest ON res.guest = guest.name
        LEFT JOIN
            `tabGuest Folio` folio ON res.folio = folio.name
        WHERE
            res.departure_date = %(target_date)s
            AND res.status = 'Checked Out'
            {property_condition}
        ORDER BY
            res.modified ASC
    """

    # Note: We use TIME(res.modified) as proxy for checkout time because
    # the Reservation is submitted/modified upon checkout.

    params = {"target_date": target_date}
    allowed_properties = allowed_properties_for_report()
    property_condition = ""
    if allowed_properties is not None:
        property_condition = "AND res.property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    data = frappe.db.sql(sql.format(property_condition=property_condition), params, as_dict=True)
    return columns, data