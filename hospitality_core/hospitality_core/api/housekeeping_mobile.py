import frappe
from frappe import _
from frappe.utils import flt, nowdate, now_datetime


def log_room_status_change(room, previous_status, new_status):
	"""
	Ghi lại lịch sử chuyển trạng thái phòng — trước đây cả `set_room_status()`
	(Housekeeping Board desktop) và `update_room_status()` (PWA di động) đều
	dùng `frappe.db.set_value()` để ghi thẳng, không để lại dấu vết ai đã dọn
	phòng nào lúc nào — không có cách nào xây báo cáo năng suất buồng phòng
	theo nhân viên từ dữ liệu cũ. Dùng chung 1 hàm cho cả 2 luồng để tránh
	lệch logic ghi log giữa desktop và mobile.
	"""
	if previous_status == new_status:
		return
	try:
		frappe.get_doc({
			"doctype": "Housekeeping Room Status Log",
			"room": room,
			"room_type": frappe.db.get_value("Hotel Room", room, "room_type"),
			"previous_status": previous_status,
			"new_status": new_status,
			"changed_by": frappe.session.user,
			"changed_on": now_datetime(),
		}).insert(ignore_permissions=True)
	except Exception:
		# Không để lỗi ghi log làm hỏng thao tác đổi trạng thái phòng thật —
		# đây chỉ là dữ liệu phục vụ báo cáo, không phải nghiệp vụ chính.
		frappe.log_error(frappe.get_traceback(), "Housekeeping Room Status Log Write Error")


@frappe.whitelist()
def get_my_board(floor=None):
    """
    Room board for the Mobile Housekeeping PWA. Same underlying data as the
    desktop Housekeeping Board, just filterable by floor for a phone-sized
    screen.
    """
    filters = {"is_enabled": 1}
    if floor:
        filters["floor"] = floor

    return frappe.get_all(
        "Hotel Room",
        fields=["name", "room_number", "room_type", "floor", "status"],
        filters=filters,
        order_by="floor asc, room_number asc",
    )


@frappe.whitelist()
def get_floors():
    return frappe.get_all(
        "Hotel Room",
        filters={"is_enabled": 1, "floor": ["is", "set"]},
        pluck="floor",
        distinct=True,
        order_by="floor asc",
    )


@frappe.whitelist()
def update_room_status(room, status):
    """
    Housekeeping status workflow: Dirty -> Cleaning -> Inspected -> Available.
    `Available` is the only status that actually clears a room for sale, so
    this mirrors the same "still occupied" guard as the desktop Housekeeping
    Board to avoid a phone accidentally freeing up an occupied room.
    """
    if not frappe.has_permission("Hotel Room", "write"):
        frappe.throw(_("Not authorized to change room status"))

    valid_statuses = ["Dirty", "Cleaning", "Inspected", "Available", "Out of Order"]
    if status not in valid_statuses:
        frappe.throw(_("Invalid status: {0}").format(status))

    # TRƯỚC ĐÂY: thiếu khóa row so với housekeeping_view.py's set_room_status()
    # (bản desktop) — cùng 1 fix chống race điều kiện đã áp dụng ở đó (khóa
    # dòng Hotel Room trước khi kiểm tra "còn khách checked-in không") không
    # được mang sang PWA mobile này — 1 đường khác dẫn tới CÙNG 1 dữ liệu mà
    # bị bỏ sót fix. Nhân viên buồng phòng bấm "Đã dọn xong" trên điện thoại
    # đúng lúc lễ tân check-in khách vào phòng đó: câu exists-check có thể
    # chạy TRƯỚC KHI transaction check-in commit xong, khiến phòng bị ghi đè
    # về "Available"/"Inspected" dù khách vừa nhận phòng thật — phòng có
    # khách hiện ra như đang trống, có thể bị bán/gán cho khách khác.
    frappe.db.sql("SELECT name FROM `tabHotel Room` WHERE name=%s FOR UPDATE", room)

    if status in ("Available", "Inspected"):
        active_res = frappe.db.exists("Hotel Reservation", {"room": room, "status": "Checked In"})
        if active_res:
            status = "Occupied"

    previous_status = frappe.db.get_value("Hotel Room", room, "status")
    frappe.db.set_value("Hotel Room", room, "status", status)
    log_room_status_change(room, previous_status, status)
    return status


@frappe.whitelist()
def log_minibar_consumption(room, items):
    """
    Posts minibar consumption directly onto the guest's open Folio for the
    given room. `items` is a list of {item, qty, amount}.
    """
    if not frappe.has_permission("Guest Folio", "write"):
        frappe.throw(_("Not authorized to post minibar charges."), frappe.PermissionError)

    if isinstance(items, str):
        import json
        items = json.loads(items)

    if not items:
        frappe.throw(_("No items provided."))

    reservation = frappe.db.get_value(
        "Hotel Reservation", {"room": room, "status": "Checked In"}, ["name", "folio"], as_dict=True
    )
    if not reservation or not reservation.folio:
        frappe.throw(_("No in-house guest with an open folio found for Room {0}.").format(room))

    folio = frappe.get_doc("Guest Folio", reservation.folio)
    if folio.status != "Open":
        frappe.throw(_("Folio {0} is not Open.").format(folio.name))

    posted = []
    for line in items:
        amount = flt(line.get("amount"))
        qty = flt(line.get("qty") or 1)
        if amount <= 0:
            continue

        if not frappe.db.exists("Item", line.get("item")):
            frappe.throw(_("Item {0} does not exist.").format(line.get("item")))

        txn = frappe.get_doc({
            "doctype": "Folio Transaction",
            "parent": folio.name,
            "parenttype": "Guest Folio",
            "parentfield": "transactions",
            "posting_date": nowdate(),
            "item": line.get("item"),
            "description": _("Minibar consumption logged via Mobile Housekeeping"),
            "qty": qty,
            "amount": amount,
            "bill_to": "Guest",
            "is_void": 0,
        })
        txn.insert(ignore_permissions=True)
        posted.append(txn.name)

    if posted:
        from hospitality_core.hospitality_core.api.folio import sync_folio_balance
        sync_folio_balance(frappe.get_doc("Guest Folio", folio.name))

    return posted


@frappe.whitelist()
def create_lost_and_found_report(item_name, found_location, finder=None):
    if not frappe.has_permission("Lost and Found Item", "create"):
        frappe.throw(_("Not authorized to log a Lost and Found report"), frappe.PermissionError)

    doc = frappe.get_doc({
        "doctype": "Lost and Found Item",
        "item_name": item_name,
        "found_location": found_location,
        "found_date": nowdate(),
        "finder": finder or frappe.session.user,
        "status": "Found",
    })
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def report_maintenance_issue(room, issue_type, description, image=None):
    if not frappe.has_permission("Hotel Maintenance Request", "create"):
        frappe.throw(_("Not authorized to report a maintenance issue"), frappe.PermissionError)

    doc = frappe.get_doc({
        "doctype": "Hotel Maintenance Request",
        "room": room,
        "issue_type": issue_type,
        "description": description,
        "image": image,
        "reported_by": frappe.session.user,
    })
    doc.insert(ignore_permissions=True)
    frappe.msgprint(_("Maintenance request {0} created and sent to the Technical team.").format(doc.name))
    return doc.name
