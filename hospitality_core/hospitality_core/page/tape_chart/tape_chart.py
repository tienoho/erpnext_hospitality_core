import frappe
from frappe import _
from frappe.utils import getdate
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

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
    if not frappe.has_permission("Hotel Reservation", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    # TRƯỚC ĐÂY: get_all() với is_enabled — frappe.get_all() đặt
    # ignore_permissions=True, khiến build_match_conditions() (nơi áp
    # permission_query_conditions của Property v2) bị bỏ qua hoàn toàn —
    # KHÔNG tự động lọc property như tưởng. Cả rooms lẫn bookings dưới đây
    # đều cần lọc thủ công.
    allowed_properties = allowed_properties_for_report()
    room_filters = {"is_enabled": 1}
    property_condition = ""
    params = {"start": start_date, "end": end_date}
    if allowed_properties is not None:
        room_filters["property"] = ["in", allowed_properties or [""]]
        property_condition = "AND res.property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    # 1. Get all Enabled Rooms
    rooms = frappe.get_all(
        "Hotel Room",
        filters=room_filters,
        fields=["name", "room_number", "room_type", "status", "floor"],
        order_by="room_number asc",
    )

    # 2. Get Reservations in range, enriched with guest + folio balance so the
    #    frontend can render tooltips/popovers without extra round-trips.
    # Logic: Arrival < End AND Departure > Start
    bookings = frappe.db.sql(
        f"""
        SELECT
            res.name, res.guest, res.room, COALESCE(r.room_number, res.room) as room_number,
            res.arrival_date, res.departure_date,
            res.status, res.folio, res.booking_source, res.ota_platform,
            res.external_booking_id, res.is_complimentary, res.is_group_guest,
            res.is_company_guest,
            g.full_name as guest_name,
            g.mobile_no as guest_phone,
            f.outstanding_balance
        FROM `tabHotel Reservation` res
        LEFT JOIN `tabGuest` g ON res.guest = g.name
        LEFT JOIN `tabGuest Folio` f ON res.folio = f.name
        LEFT JOIN `tabHotel Room` r ON res.room = r.name
        WHERE res.status IN ('Reserved', 'Checked In')
        AND res.arrival_date < %(end)s AND res.departure_date > %(start)s
        {property_condition}
        """,
        params,
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
    Kéo thả đổi phòng trên Tape Chart 2.0:
    - Nếu khách đang ở (Checked In): tái sử dụng process_room_move (chuyển phòng in-house,
      cập nhật trạng thái buồng phòng cũ Dirty/mới Occupied, đồng bộ folio, snapshot giá).
    - Nếu đặt phòng trước (Reserved): chuyển gán buồng phòng trước nhận phòng (pre-arrival
      reassignment), kiểm tra tình trạng trống theo toàn bộ khoảng thời gian lưu trú,
      đồng bộ room_type & folio nếu có, ghi comment lịch sử mà không can thiệp trạng thái phòng thực tế.
    """
    res = frappe.get_doc("Hotel Reservation", reservation_name, for_update=True)
    res.check_permission("write")

    if res.status == "Checked In":
        from hospitality_core.hospitality_core.api.room_move import process_room_move
        return process_room_move(reservation_name, new_room)

    elif res.status == "Reserved":
        from hospitality_core.hospitality_core.doctype.hotel_room.hotel_room import resolve_hotel_room, get_room_number

        canonical_new_room = resolve_hotel_room(new_room, property=res.get("property")) or new_room
        if res.room == canonical_new_room:
            frappe.throw(_("Phòng mới không được trùng với phòng hiện tại."))

        if res.get("property"):
            from hospitality_core.hospitality_core.api.property_scope import require_property
            require_property(res.property)
            if frappe.db.get_value("Hotel Room", canonical_new_room, "property") != res.property:
                frappe.throw(_("Chuyển phòng không được đổi cơ sở; cần booking mới có liên kết nguồn."))

        new_room_type = frappe.db.get_value("Hotel Room", canonical_new_room, "room_type")
        if new_room_type == "Virtual":
            frappe.throw(_("Không được gán đặt phòng vào phòng ảo."))

        old_room = res.room
        res.room = canonical_new_room
        res.save()

        if res.folio:
            frappe.db.set_value("Guest Folio", res.folio, "room", canonical_new_room)

        old_room_no = get_room_number(old_room) or old_room or _("Chưa gán")
        new_room_no = get_room_number(canonical_new_room) or canonical_new_room

        comment = _("Đổi phòng trước nhận phòng từ phòng {0} sang phòng {1} trên Sơ đồ Tape Chart").format(
            old_room_no, new_room_no
        )
        res.add_comment("Info", comment)
        frappe.msgprint(_("Đã chuyển đặt phòng sang phòng {0} thành công.").format(new_room_no), indicator="green")
        return True

    else:
        frappe.throw(_("Chỉ có thể chuyển phòng cho đặt phòng ở trạng thái 'Reserved' hoặc 'Checked In'."))

