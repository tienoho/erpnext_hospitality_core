import frappe
from frappe import _
from hospitality_core.hospitality_core.api.reservation import check_availability

@frappe.whitelist()
def process_room_move(reservation_name, new_room, new_rate_plan=None):
    """
    Moves a checked-in guest to a new room.
    1. Validate permissions.
    2. Validate New Room availability.
    3. Mark Old Room 'Available'.
    4. Mark New Room 'Occupied'.
    5. Update Reservation and Folio.
    """
    
    allowed = ["Frontdesk Supervisor", "Hospitality Manager", "System Manager"]
    user_roles = frappe.get_roles() if hasattr(frappe, "get_roles") else []
    if not (any(r in user_roles for r in allowed) or frappe.session.user == "Administrator"):
        frappe.throw(_("Access Denied. Only Frontdesk Supervisors, Hospitality Managers, and Administrators can move rooms."))

    res = frappe.get_doc("Hotel Reservation", reservation_name, for_update=True)
    res.check_permission('write')
    if res.get('property'):
        from hospitality_core.hospitality_core.api.property_scope import require_property
        require_property(res.property)
        if frappe.db.get_value('Hotel Room', new_room, 'property') != res.property:
            frappe.throw(_('Chuyển phòng không được đổi cơ sở; cần booking mới có liên kết nguồn.'))
    
    if res.status != "Checked In":
        frappe.throw(_("Room moves are only allowed for Checked In guests."))
        
    if res.room == new_room:
        frappe.throw(_("New Room cannot be the same as Current Room."))

    old_room = res.room
    new_room_type = frappe.db.get_value("Hotel Room", new_room, "room_type")
    if new_room_type == 'Virtual':
        frappe.throw(_('Không được chuyển khách lưu trú vào phòng ảo.'))
    from hospitality_core.hospitality_core.api.rate_plan import snapshot_for
    import json
    new_snapshot = None
    room_type_changed = new_room_type != res.room_type
    rate_plan_changed = (new_rate_plan or None) != (res.rate_plan or None)
    # TRƯỚC ĐÂY: hàm này chỉ nhận reservation_name/new_room, chưa có tham số
    # new_rate_plan — dialog "Move Room" (hotel_reservation.js) đã được thêm ô
    # chọn "Bảng giá sau chuyển phòng" (cho phép chọn 1 rate plan mới hợp lệ
    # cho hạng phòng mới, hoặc bỏ trống để dùng giá mặc định), NHƯNG đoạn code
    # này vẫn hardcode `snapshot_for(None, new_room_type)` — bỏ hoàn toàn qua
    # tham số new_rate_plan vừa nhận. Hậu quả nghiêm trọng: res.rate_plan bị
    # set = new_rate_plan (dòng res.db_set('rate_plan', ...) bên dưới) trong
    # khi snapshot lưu lại vẫn mang rate_plan=None — reservation_snapshot()
    # (rate_plan.py) phát hiện lệch (snapshot.rate_plan != res.rate_plan) và
    # frappe.throw() ngay từ lần tính tiền/xem trước TIẾP THEO, khiến đặt
    # phòng này KHÔNG THỂ tính tiền được nữa cho tới khi có người can thiệp
    # thủ công vào DB — lưu lại (save) thông thường KHÔNG tự sửa được, vì
    # prepare_reservation() không phát hiện gì thay đổi (rate_plan đã khớp
    # sẵn giữa old/new do db_set() đã ghi từ trước).
    if room_type_changed or rate_plan_changed:
        # Xây lại căn cứ giá theo ĐÚNG rate_plan mới được chọn (có thể là
        # None/rỗng — nghĩa là dùng giá mặc định của hạng phòng mới).
        # snapshot_for() tự validate rate_plan có khớp room_type mới không,
        # khớp đúng quy ước dùng ở mọi nơi khác trong app.
        new_snapshot = snapshot_for(new_rate_plan, new_room_type, res.get('currency'), res.get('property'))
        if res.get('loyalty_snapshot'):
            policy = json.loads(res.loyalty_snapshot)
            new_snapshot.update(vip_percent=policy.get('vip_percent', 0), loyalty=policy)

    # 1. Validate Availability (for the remaining dates)
    # We check from Today to Departure Date
    check_availability(new_room, frappe.utils.nowdate(), res.departure_date, ignore_reservation=res.name)

    # 2. Update Statuses
    # Old Room -> Dirty (housekeeping needs to turnover and clean)
    frappe.db.set_value("Hotel Room", old_room, "status", "Dirty")
    
    # New Room -> Occupied
    frappe.db.set_value("Hotel Room", new_room, "status", "Occupied")

    # 3. Update Documents (Bypass set_only_once restriction)
    res.db_set("room", new_room)
    if new_room_type and res.room_type != new_room_type:
        res.db_set("room_type", new_room_type)
    if new_snapshot:
        res.db_set('rate_plan', new_rate_plan)
        res.db_set('rate_snapshot', json.dumps(new_snapshot, ensure_ascii=False))
    
    # Update Folio
    if res.folio:
        # pos_bridge.py routes restaurant/bar/minibar charges to whichever Open
        # folio has this room — refuse to create a second one so a previous
        # occupant's still-open folio can't silently absorb the new guest's charges.
        conflicting_folio = frappe.db.get_value("Guest Folio", {
            "room": new_room,
            "status": "Open",
            "name": ["!=", res.folio]
        }, "name")
        if conflicting_folio:
            frappe.throw(_(
                "Cannot move to Room {0}: Folio {1} for that room is still Open. "
                "Please close/settle it before moving a new guest in."
            ).format(new_room, conflicting_folio))

        frappe.db.set_value("Guest Folio", res.folio, "room", new_room)

    # 4. Log the Move (Optional: Add a comment)
    comment = _("Moved from Room {0} to Room {1} on {2}").format(
        old_room, new_room, frappe.utils.now_datetime()
    )
    # Cảnh báo/ghi chú khi căn cứ giá thực sự đổi (đổi hạng phòng VÀ/HOẶC đổi
    # rate plan) — KHÔNG khẳng định "chắc chắn mất LOS" nếu lễ tân đã chủ động
    # chọn 1 rate plan mới cho hạng phòng mới (rate plan đó có thể vẫn có
    # seasons/LOS riêng); chỉ khẳng định chắc chắn mất LOS khi new_rate_plan
    # rỗng (rơi về giá mặc định của hạng phòng, chắc chắn không có seasons/LOS).
    if new_snapshot:
        if new_rate_plan:
            comment += " — " + _(
                "Đổi căn cứ giá: hạng phòng {0} → {1}, Rate Plan → {2}. Giá phòng từ đêm này trở đi tính theo "
                "Rate Plan mới được chọn."
            ).format(res.room_type, new_room_type, new_rate_plan)
        else:
            comment += " — " + _(
                "Đổi căn cứ giá ({0} → {1}): giá phòng từ đêm này trở đi chuyển về giá mặc định của hạng mới, "
                "KHÔNG còn áp dụng giảm giá theo số đêm lưu trú (LOS) hay bảng giá theo mùa vụ của rate plan cũ. "
                "Vui lòng gán lại Rate Plan phù hợp cho hạng phòng mới nếu cần."
            ).format(res.room_type, new_room_type)
    res.add_comment("Info", comment)

    if new_snapshot and not new_rate_plan:
        frappe.msgprint(_(
            "Đã chuyển khách sang phòng {0} (hạng phòng {1}). LƯU Ý: giá phòng từ đêm này trở đi sẽ dùng giá mặc "
            "định của hạng phòng mới — mọi giảm giá theo số đêm lưu trú (LOS) hoặc bảng giá theo mùa vụ đang áp "
            "dụng trước đó KHÔNG còn hiệu lực cho phòng mới. Vui lòng gán lại Rate Plan cho đặt phòng này nếu "
            "khách vẫn nên được hưởng ưu đãi tương ứng."
        ).format(new_room, new_room_type), indicator="orange")
    elif new_snapshot:
        frappe.msgprint(_(
            "Đã chuyển khách sang phòng {0} và cập nhật Rate Plan → {1}. Giá phòng từ đêm này trở đi tính theo "
            "Rate Plan mới."
        ).format(new_room, new_rate_plan), indicator="blue")
    else:
        frappe.msgprint(_("Successfully moved guest to Room {0}").format(new_room))

    return True
