import frappe

@frappe.whitelist()
def check_availability_counts(start_date, end_date):
    # 1. Get all Enabled Rooms
    rooms = frappe.get_all("Hotel Room", 
        fields=["name", "room_number", "room_type", "floor", "status as current_status"],
        filters={"is_enabled": 1},
        order_by="floor asc, room_number asc"
    )

    # 2. Get all Overlapping Reservations
    reservations = frappe.db.sql("""
        SELECT room, status, name, guest
        FROM `tabHotel Reservation`
        WHERE status IN ('Reserved', 'Checked In')
        AND arrival_date < %s
        AND departure_date > %s
    """, (end_date, start_date), as_dict=True)

    reservation_map = {(r.get("room") if isinstance(r, dict) else getattr(r, "room", None)): r for r in reservations}

    room_details = []
    summary_map = {}

    for room in rooms:
        room_name = room.get("name") if isinstance(room, dict) else getattr(room, "name", "")
        room_number = room.get("room_number") if isinstance(room, dict) else getattr(room, "room_number", room_name)
        room_type = room.get("room_type") if isinstance(room, dict) else getattr(room, "room_type", "")
        floor = room.get("floor") if isinstance(room, dict) else getattr(room, "floor", "")
        current_status = room.get("current_status") if isinstance(room, dict) else getattr(room, "current_status", "")

        res = reservation_map.get(room_name)
        status = "Available"
        details = ""

        if current_status == "Out of Order":
            status = "Out of Order"
            details = "Maintenance"
        elif res:
            res_status = res.get("status") if isinstance(res, dict) else getattr(res, "status", "")
            res_name = res.get("name") if isinstance(res, dict) else getattr(res, "name", "")
            res_guest = res.get("guest") if isinstance(res, dict) else getattr(res, "guest", "")
            if res_status == "Checked In":
                status = "Occupied"
            else:
                status = "Reserved"
            details = f"{res_name} ({res_guest})"
        
        room_details.append({
            "room": room_name,
            "room_number": room_number or room_name,
            "room_type": room_type,
            "floor": floor or _("Floor 1"),
            "status": status,
            "details": details
        })

        # Summary Logic
        if room_type not in summary_map:
            summary_map[room_type] = {"room_type": room_type, "total": 0, "occupied": 0, "available": 0}
        
        summary_map[room_type]["total"] += 1
        if status in ["Occupied", "Reserved", "Out of Order"]:
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