import frappe
from frappe.utils import getdate

# Color mapping used by Tape Chart 2.0 to group bookings by acquisition channel.
# Kept in Python (not just JS) so any future export/report can reuse the same mapping.
SOURCE_COLORS = {
    "OTA": "#2f80ed",          # Blue
    "Complimentary": "#9b51e0",  # Purple
    "Group": "#f2994a",        # Orange
    "Corporate": "#27ae60",    # Green
    "Direct": "#8d99a6",       # Grey (individual walk-in / direct booking)
}


@frappe.whitelist()
def get_chart_data(start_date, end_date):
    # 1. Get all Enabled Rooms
    rooms = frappe.get_all(
        "Hotel Room",
        filters={"is_enabled": 1},
        fields=["name", "room_number", "room_type", "status"],
        order_by="room_number asc",
    )

    # 2. Get Reservations in range, enriched with guest + folio balance so the
    #    frontend can render tooltips/popovers without extra round-trips.
    # Logic: Arrival < End AND Departure > Start
    bookings = frappe.db.sql(
        """
        SELECT
            res.name, res.guest, res.room, res.arrival_date, res.departure_date,
            res.status, res.folio, res.booking_source, res.ota_platform,
            res.external_booking_id, res.is_complimentary, res.is_group_guest,
            res.is_company_guest,
            g.full_name as guest_name,
            f.outstanding_balance
        FROM `tabHotel Reservation` res
        LEFT JOIN `tabGuest` g ON res.guest = g.name
        LEFT JOIN `tabGuest Folio` f ON res.folio = f.name
        WHERE res.status IN ('Reserved', 'Checked In')
        AND res.arrival_date < %(end)s AND res.departure_date > %(start)s
        """,
        {"start": start_date, "end": end_date},
        as_dict=True,
    )

    for b in bookings:
        b["source_category"] = _resolve_source_category(b)
        b["color"] = SOURCE_COLORS[b["source_category"]]

    return {"rooms": rooms, "bookings": bookings, "source_colors": SOURCE_COLORS}


def _resolve_source_category(booking):
    """
    Prefer the explicit `booking_source` field (set by the Channel Manager
    Gateway for OTA bookings). Fall back to the legacy boolean flags for
    reservations created before that field existed.
    """
    if booking.get("booking_source"):
        return booking["booking_source"]
    if booking.get("is_complimentary"):
        return "Complimentary"
    if booking.get("is_group_guest"):
        return "Group"
    if booking.get("is_company_guest"):
        return "Corporate"
    return "Direct"


@frappe.whitelist()
def move_booking(reservation_name, new_room):
    """
    Thin wrapper so the Tape Chart's drag-and-drop can reuse the existing,
    already-audited room move logic (permission checks, availability check,
    folio update, comment log) instead of duplicating it.
    """
    from hospitality_core.hospitality_core.api.room_move import process_room_move

    return process_room_move(reservation_name, new_room)
