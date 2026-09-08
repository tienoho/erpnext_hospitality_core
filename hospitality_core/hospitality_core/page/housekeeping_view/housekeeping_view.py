import frappe
from hospitality_core.hospitality_core.api.housekeeping_mobile import log_room_status_change

@frappe.whitelist()
def get_room_statuses():
    return frappe.get_all("Hotel Room", 
        fields=["name", "room_number", "status", "room_type"],
        filters={"is_enabled": 1},
        order_by="room_number asc"
    )

@frappe.whitelist()
def set_room_status(room, status):
    # Security check: Ensure user is Housekeeping or Manager
    if not frappe.has_permission("Hotel Room", "write"):
        frappe.throw("Not authorized to change room status")

    # Cùng danh sách hợp lệ như housekeeping_mobile.update_room_status() — nếu
    # không, một request thủ công/lỗi client có thể ghi một chuỗi tùy ý vào
    # Select field "status" của Hotel Room.
    valid_statuses = ["Dirty", "Cleaning", "Inspected", "Available", "Occupied", "Out of Order"]
    if status not in valid_statuses:
        frappe.throw(f"Invalid status: {status}")

    # Lock this room row so a concurrent check-in (which also writes this same
    # row's status to "Occupied" in process_check_in) can't race with the
    # exists-check below — whichever transaction gets here first blocks the
    # other until it commits, so the check-in state seen here is always current.
    frappe.db.sql("SELECT name FROM `tabHotel Room` WHERE name=%s FOR UPDATE", room)

    # If marking as "Available" (Clean), checking if there is still an active guest
    if status == "Available":
        active_res = frappe.db.exists("Hotel Reservation", {
            "room": room,
            "status": "Checked In"
        })
        if active_res:
            # Guest is still here, so status should be Occupied, not Available
            status = "Occupied"

    previous_status = frappe.db.get_value("Hotel Room", room, "status")
    frappe.db.set_value("Hotel Room", room, "status", status)
    log_room_status_change(room, previous_status, status)
    return True