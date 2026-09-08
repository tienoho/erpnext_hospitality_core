import json
import frappe
from frappe import _
from hospitality_core.hospitality_core.api.housekeeping_mobile import log_room_status_change
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

@frappe.whitelist()
def get_room_statuses():
    allowed_props = allowed_properties_for_report()
    filters = {"is_enabled": 1}
    if allowed_props is not None:
        filters["property"] = ["in", allowed_props or [""]]

    return frappe.get_all(
        "Hotel Room",
        fields=["name", "room_number", "status", "room_type", "floor", "hotel_reception", "property"],
        filters=filters,
        order_by="room_number asc"
    )

@frappe.whitelist()
def set_room_status(room, status):
    # Security check: Ensure user is Housekeeping or Manager
    if not frappe.has_permission("Hotel Room", "write"):
        frappe.throw(_("Not authorized to change room status"), frappe.PermissionError)

    valid_statuses = ["Dirty", "Cleaning", "Inspected", "Available", "Occupied", "Out of Order"]
    if status not in valid_statuses:
        frappe.throw(_("Invalid status: {0}").format(status))

    from hospitality_core.hospitality_core.doctype.hotel_room.hotel_room import resolve_hotel_room
    room = resolve_hotel_room(room)

    if not frappe.db.exists("Hotel Room", room):
        frappe.throw(_("Không tìm thấy phòng {0}.").format(room))

    frappe.db.sql("SELECT name FROM `tabHotel Room` WHERE name=%s FOR UPDATE", room)

    if status == "Available":
        active_res = frappe.db.exists("Hotel Reservation", {
            "room": room,
            "status": "Checked In"
        })
        if active_res:
            status = "Occupied"

    previous_status = frappe.db.get_value("Hotel Room", room, "status")
    frappe.db.set_value("Hotel Room", room, "status", status)
    log_room_status_change(room, previous_status, status)
    return {"success": True, "status": status, "room": room}

@frappe.whitelist()
def batch_set_room_status(rooms, status):
    if not frappe.has_permission("Hotel Room", "write"):
        frappe.throw(_("Not authorized to change room status"), frappe.PermissionError)

    if isinstance(rooms, str):
        try:
            rooms = json.loads(rooms)
        except Exception:
            rooms = [r.strip() for r in rooms.split(",") if r.strip()]

    if not rooms:
        return {"success": False, "message": _("No rooms provided.")}

    updated_count = 0
    for r in rooms:
        try:
            set_room_status(r, status)
            updated_count += 1
        except Exception:
            continue

    return {
        "success": True,
        "updated_count": updated_count,
        "message": _("Đã cập nhật trạng thái {0} cho {1} phòng.").format(status, updated_count)
    }