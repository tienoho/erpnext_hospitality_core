import frappe
from frappe import _

@frappe.whitelist()
def clear_reservations():
    # Destructive, irreversible bulk wipe — restrict to System Manager only.
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Access Denied. Only System Managers can clear all reservations."), frappe.PermissionError)

    # TRƯỚC ĐÂY: mỗi bước tự nuốt lỗi riêng, chỉ print() ra console SERVER
    # (admin gọi endpoint này từ trình duyệt không bao giờ thấy được) — rồi
    # vẫn frappe.db.commit() VÔ ĐIỀU KIỆN dù có bước lỗi giữa chừng, không
    # hề báo cho người gọi biết bước nào thật sự thành công/thất bại. Với 1
    # thao tác XÓA DỮ LIỆU VĨNH VIỄN, im lặng như vậy là nguy hiểm — thu thập
    # kết quả từng bước và trả về rõ ràng cho người gọi thay vì chỉ log
    # server.
    results = []

    # 1. Clear Hotel Reservations and child tables
    try:
        res_count = frappe.db.count("Hotel Reservation")
        frappe.db.delete("Hotel Reservation")
        frappe.db.sql("DELETE FROM `tabReservation Routing`", ignore_ddl=True)
        results.append(f"✔ Deleted {res_count} Hotel Reservations.")
    except Exception as e:
        results.append(f"✘ Error clearing Hotel Reservations: {e}")
        frappe.log_error(f"clear_reservations: error clearing Hotel Reservations: {e}", "Cleanup Error")

    # 2. Clear Group Bookings and child tables
    try:
        gb_count = frappe.db.count("Hotel Group Booking")
        frappe.db.delete("Hotel Group Booking")
        frappe.db.sql("DELETE FROM `tabHotel Group Booking Room`", ignore_ddl=True)
        results.append(f"✔ Deleted {gb_count} Group Bookings.")
    except Exception as e:
        results.append(f"✘ Error clearing Group Bookings: {e}")
        frappe.log_error(f"clear_reservations: error clearing Group Bookings: {e}", "Cleanup Error")

    # 3. Reset Room Statuses
    try:
        frappe.db.sql("UPDATE `tabHotel Room` SET status = 'Available'")
        results.append("✔ Room statuses reset.")
    except Exception as e:
        results.append(f"✘ Could not reset rooms: {e}")
        frappe.log_error(f"clear_reservations: could not reset rooms: {e}", "Cleanup Error")

    frappe.db.commit()

    had_error = any(r.startswith("✘") for r in results)
    summary = "\n".join(results)
    frappe.msgprint(summary, title=_("Reservation Cleanup Result"), indicator="orange" if had_error else "green")
    return {"success": not had_error, "log": results}
