import frappe
from frappe import _
from frappe.utils import nowdate
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    if not filters:
        filters = {}
        
    columns = [
        {"label": _("Reservation"), "fieldname": "name", "fieldtype": "Link", "options": "Hotel Reservation", "width": 140},
        {"label": _("Guest Name"), "fieldname": "guest_name", "fieldtype": "Data", "width": 160},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": _("Arrival Time"), "fieldname": "arrival_time", "fieldtype": "Time", "width": 100},
        {"label": _("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Hotel Room", "width": 100},
        {"label": _("Room Type"), "fieldname": "room_type", "fieldtype": "Link", "options": "Hotel Room Type", "width": 120},
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Customer", "width": 140},
        {"label": _("Booked By"), "fieldname": "owner", "fieldtype": "Data", "width": 120}
    ]

    target_date = filters.get("date") or nowdate()
    filters["target_date"] = target_date

    # Definition: "customers that were checkedin for a specific day"
    # This implies ACTUAL arrivals.
    # We exclude 'Reserved' because they haven't checked in yet.
    # We include 'Checked Out' because if they arrived today and left today, they were still an arrival.
    
    conditions = ""
    if filters.get("hotel_reception"):
        conditions += " AND res.hotel_reception = %(hotel_reception)s"

    allowed_properties = allowed_properties_for_report()
    if allowed_properties is not None:
        conditions += " AND res.property IN %(_properties)s"
        filters["_properties"] = allowed_properties or [""]

    sql = """
        SELECT
            res.name,
            guest.full_name as guest_name,
            res.status,
            TIME(res.creation) as arrival_time, 
            res.room,
            res.room_type,
            res.company,
            res.owner
        FROM
            `tabHotel Reservation` res
        LEFT JOIN
            `tabGuest` guest ON res.guest = guest.name
        WHERE
            res.arrival_date = %(target_date)s
            AND res.status IN ('Checked In', 'Checked Out')
            {conditions}
        ORDER BY
            res.creation ASC
    """
    
    # Note: Using TIME(res.creation) as a proxy for Check-in time if no specific check-in timestamp field exists.
    # Ideally, you might want a 'check_in_time' custom field set on transition.
    
    data = frappe.db.sql(sql.format(conditions=conditions), filters, as_dict=True)
    return columns, data