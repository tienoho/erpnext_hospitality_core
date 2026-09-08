import frappe
from frappe import _
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

@frappe.whitelist()
def check_availability_counts(start_date, end_date):
    if not frappe.has_permission("Hotel Reservation", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    # TRƯỚC ĐÂY: get_all() với is_enabled — frappe.get_all() đặt
    # ignore_permissions=True, khiến permission_query_conditions của
    # Property v2 bị bỏ qua hoàn toàn (không tự động lọc như tưởng). Cả
    # rooms lẫn reservations dưới đây đều cần lọc thủ công theo property.
    allowed_properties = allowed_properties_for_report()
    room_filters = {"is_enabled": 1}
    property_condition = ""
    params = {"start": start_date, "end": end_date}
    if allowed_properties is not None:
        room_filters["property"] = ["in", allowed_properties or [""]]
        property_condition = "AND property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    # 1. Get all Enabled Rooms
    rooms = frappe.get_all("Hotel Room",
        fields=["name", "room_number", "room_type", "floor", "status as current_status"],
        filters=room_filters,
        order_by="floor asc, room_number asc"
    )

    # 2. Get all Overlapping Reservations
    reservations = frappe.db.sql(f"""
        SELECT room, status, name, guest
        FROM `tabHotel Reservation`
        WHERE status IN ('Reserved', 'Checked In')
        AND arrival_date < %(end)s
        AND departure_date > %(start)s
        {property_condition}
    """, params, as_dict=True)

    # Keep ALL overlapping reservations per room (not just the last one seen) so a
    # double-booked room isn't silently reported as if only one guest holds it.
    reservation_map = {}
    for r in reservations:
        room_key = r.get("room") if isinstance(r, dict) else getattr(r, "room", None)
        reservation_map.setdefault(room_key, []).append(r)

    room_details = []
    summary_map = {}

    for room in rooms:
        room_name = room.get("name") if isinstance(room, dict) else getattr(room, "name", "")
        room_number = room.get("room_number") if isinstance(room, dict) else getattr(room, "room_number", room_name)
        room_type = room.get("room_type") if isinstance(room, dict) else getattr(room, "room_type", "")
        floor = room.get("floor") if isinstance(room, dict) else getattr(room, "floor", "")
        current_status = room.get("current_status") if isinstance(room, dict) else getattr(room, "current_status", "")

        res_list = reservation_map.get(room_name) or []
        status = "Available"
        details = ""
        # Docname of the single reservation to open on click — sent as its own
        # field so the client can route to it directly instead of parsing it
        # back out of the free-text `details` string (which embeds the Guest
        # docname, itself the guest's raw full name per Guest's
        # autoname="format:{full_name}" — regex-extracting a reservation name
        # out of a string containing untrusted guest-entered text is fragile,
        # and interpolating that same string into an onclick attribute without
        # escaping is a stored-XSS risk).
        reservation = None

        if current_status == "Out of Order":
            status = "Out of Order"
            details = "Maintenance"
        elif current_status in ("Dirty", "Cleaning") and not res_list:
            # Housekeeping hasn't turned the room over yet — not sellable even
            # though no reservation currently overlaps it.
            status = current_status
            details = "Housekeeping"
        elif current_status == "Occupied" and not res_list:
            # Marked Occupied (e.g. a manual walk-in) with no matching reservation.
            status = "Occupied"
            details = "Manual"
        elif res_list:
            if len(res_list) > 1:
                # Double-booking: surface every overlapping reservation instead of
                # silently keeping only one. Ambiguous which one to route to on
                # click, so `reservation` stays None (client falls back to the list view).
                parts = []
                for res in res_list:
                    res_name = res.get("name") if isinstance(res, dict) else getattr(res, "name", "")
                    res_guest = res.get("guest") if isinstance(res, dict) else getattr(res, "guest", "")
                    parts.append(f"{res_name} ({res_guest})")
                status = "Conflict"
                details = "CONFLICT: " + " | ".join(parts)
            else:
                res = res_list[0]
                res_status = res.get("status") if isinstance(res, dict) else getattr(res, "status", "")
                res_name = res.get("name") if isinstance(res, dict) else getattr(res, "name", "")
                res_guest = res.get("guest") if isinstance(res, dict) else getattr(res, "guest", "")
                if res_status == "Checked In":
                    status = "Occupied"
                else:
                    status = "Reserved"
                details = f"{res_name} ({res_guest})"
                reservation = res_name

        room_details.append({
            "room": room_name,
            "room_number": room_number or room_name,
            "room_type": room_type,
            "floor": floor or _("Floor 1"),
            "status": status,
            "details": details,
            "reservation": reservation
        })

        # Summary Logic
        if room_type not in summary_map:
            summary_map[room_type] = {"room_type": room_type, "total": 0, "occupied": 0, "available": 0}
        
        summary_map[room_type]["total"] += 1
        if status in ["Occupied", "Reserved", "Out of Order", "Dirty", "Cleaning", "Conflict"]:
            summary_map[room_type]["occupied"] += 1
        else:
            summary_map[room_type]["available"] += 1

    total_all = 0
    occupied_all = 0
    available_all = 0

    for row in summary_map.values():
        total_all += row["total"]
        occupied_all += row["occupied"]
        available_all += row["available"]
        row["occupancy_pct"] = round((row["occupied"] / row["total"]) * 100.0, 1) if row["total"] > 0 else 0.0

    overall_occ_pct = round((occupied_all / total_all) * 100.0, 1) if total_all > 0 else 0.0

    return {
        "stats": {
            "total_rooms": total_all,
            "occupied": occupied_all,
            "available": available_all,
            "occupancy_pct": overall_occ_pct
        },
        "summary": list(summary_map.values()),
        "room_details": room_details
    }