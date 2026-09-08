import frappe
from frappe import _
from frappe.utils import add_days, nowdate, getdate, flt
from hospitality_core.hospitality_core.api.folio import sync_folio_balance, mirror_to_company_folio, mirror_to_group_folio

def run_daily_audit():
    """
    Scheduled Job: Runs at 2 PM daily.
    1. Auto-cancels no-show reservations (arrival passed, still Reserved).
    2. Checks for Overstays and extends departure date for ALL checked-in rooms.
    3. Posts Room Rent + Discounts for all rooms currently Checked In.
    4. SKIPS posting if a Room Rent charge already exists for the current date.
    5. Đối chiếu trạng thái Room <-> Reservation <-> Folio toàn hệ thống, và
       ghi lại toàn bộ kết quả (không chỉ msgprint/log_error rời rạc như
       trước) vào một bản ghi Night Audit Log — có thể tra cứu lịch sử.

    TRƯỚC ĐÂY: toàn bộ hàm xử lý MỌI Hotel Reservation trên toàn site trong 1
    lượt duy nhất, không phân biệt property nào — kể cả khi hệ thống đa cơ sở
    (Property v2) được kích hoạt. Hậu quả: (1) Night Audit Log là 1 bản ghi
    TRỘN LẪN số liệu của TẤT CẢ cơ sở, mất khả năng theo dõi riêng từng cơ sở;
    (2) nghiêm trọng hơn, Night Audit Log nằm trong danh sách SCOPED của
    property_scope.py — property_scope.validate_document()'s cơ chế tự suy ra
    property cho bản ghi mới sẽ THROW ngay khi có từ 2 property "enabled" trở
    lên (vì không thể suy ra DUY NHẤT 1 property cho 1 bản ghi lẫn lộn dữ
    liệu nhiều cơ sở) — nghĩa là ngay khi cơ sở thứ 2 được kích hoạt, MỌI lần
    ghi Night Audit Log sẽ ném lỗi, bị nuốt bởi try/except trong
    _write_night_audit_log() (chỉ còn dấu vết trong Error Log) — audit log
    coi như NGỪNG HOẠT ĐỘNG vĩnh viễn cho MỌI cơ sở, mỗi đêm, không ai để ý.
    Sửa: chạy audit RIÊNG cho từng property đã enabled (nếu hệ thống đa cơ sở
    đang hoạt động), mỗi property ra đúng 1 Night Audit Log của chính nó;
    KHÔNG có property nào cấu hình (site 1-cơ-sở như hiện tại) thì chạy đúng
    NGUYÊN VẸN như trước đây (property=None xuyên suốt, không lọc gì thêm) —
    không đổi hành vi cho vận hành thật hiện tại.
    """
    properties = [None]
    try:
        from hospitality_core.hospitality_core.api.property_scope import installed as _property_system_installed
        if _property_system_installed():
            enabled_properties = frappe.get_all("Hospitality Property", filters={"enabled": 1}, pluck="name")
            if enabled_properties:
                properties = enabled_properties
    except Exception as e:
        frappe.log_error(f"Night Audit: failed to resolve property list, falling back to single global run: {e}",
            "Night Audit Property Resolve Error")

    for prop in properties:
        _run_daily_audit_for_property(prop)


def _run_daily_audit_for_property(property=None):
    posting_date = nowdate()
    start_time = frappe.utils.now_datetime()

    no_show_count = 0
    count = 0
    overstay_count = 0
    error_details = []

    # Step 1: Cancel no-shows before anything else — TRƯỚC ĐÂY không có
    # try/except ở đây: nếu cancel_no_shows() (hoặc câu get_all bên trong nó)
    # ném lỗi, toàn bộ run_daily_audit() dừng đột ngột NGAY TỪ ĐẦU, không bao
    # giờ chạy tới _write_night_audit_log() — mất trắng luôn cả bản ghi audit
    # của đêm đó (không phải chỉ thiếu 1 vài số liệu, mà KHÔNG CÓ log nào).
    try:
        no_show_count = cancel_no_shows(posting_date, property=property)
    except Exception as e:
        error_message = f"Night Audit No-Show Step Failure: {str(e)}"
        frappe.log_error(error_message, "Night Audit No-Show Step Error")
        error_details.append(error_message)

    # Step 2: Fetch active reservations with Discount settings — cùng lý do,
    # bọc try/except để 1 lỗi fetch không làm mất luôn bản ghi audit.
    active_reservations = []
    try:
        filters = {"status": "Checked In"}
        if property:
            filters["property"] = property
        active_reservations = frappe.get_all("Hotel Reservation",
            filters=filters,
            fields=[
                "name", "guest", "room", "room_type", "rate_plan",
                "arrival_date", "departure_date", "company", "folio",
                "is_complimentary", "discount_type", "discount_value",
                "is_company_guest", "is_group_guest", "group_booking"
            ]
        )
    except Exception as e:
        error_message = f"Night Audit Fetch Active Reservations Failure: {str(e)}"
        frappe.log_error(error_message, "Night Audit Fetch Error")
        error_details.append(error_message)

    for res in active_reservations:
        try:
            billed, overstayed, step_error = process_single_reservation(res, posting_date)
            if billed:
                count += 1
            if overstayed:
                overstay_count += 1
            if step_error:
                error_details.append(step_error)
        except Exception as e:
            # Truncate title to 140 characters to prevent CharacterLengthExceededError
            error_title = f"Night Audit Error: {res.name}"
            error_message = f"Night Audit Failure for Reservation {res.name}: {str(e)}"
            frappe.log_error(error_message, error_title)
            error_details.append(error_message)

    if count > 0:
        frappe.msgprint(_("Auto-Bill (2 PM): Posted charges for {0} rooms.").format(count))

    # Step 5: Đối chiếu trạng thái toàn hệ thống — TRƯỚC ĐÂY hoàn toàn không
    # có bước này, run_daily_audit() chỉ xử lý no-show/overstay/tính tiền cho
    # các bản ghi đã ở trạng thái "biết trước là đúng", không hề phát hiện
    # trường hợp Room/Reservation/Folio bị lệch trạng thái với nhau (VD một
    # thao tác thủ công/lỗi hệ thống khiến Room vẫn "Occupied" dù Reservation
    # đã Checked Out).
    reconciliation_details = []
    try:
        reconciliation_details = reconcile_room_reservation_folio_status(property=property)
    except Exception as e:
        error_message = f"Night Audit Reconciliation Failure: {str(e)}"
        frappe.log_error(error_message, "Night Audit Reconciliation Error")
        error_details.append(error_message)

    _write_night_audit_log(
        audit_date=posting_date,
        run_datetime=start_time,
        no_show_count=no_show_count,
        overstay_count=overstay_count,
        room_charge_posted_count=count,
        reconciliation_details=reconciliation_details,
        error_details=error_details,
        property=property
    )

def cancel_no_shows(posting_date, property=None):
    """
    Cancels all reservations where:
    - status = 'Reserved' (not yet checked in)
    - arrival_date < today (arrival date has already passed)
    Also cancels the linked folio if it exists.

    Trả về số lượng đã hủy (dùng để ghi vào Night Audit Log).
    """
    filters = {
        "status": "Reserved",
        "arrival_date": ["<", posting_date]
    }
    if property:
        filters["property"] = property
    no_shows = frappe.get_all("Hotel Reservation",
        filters=filters,
        fields=["name", "folio", "room", "guest", "arrival_date"]
    )

    cancelled_count = 0
    for res in no_shows:
        frappe.db.savepoint('no_show_cancel')
        try:
            # TRƯỚC ĐÂY: hủy thẳng bằng frappe.db.set_value() cho cả Hotel
            # Reservation lẫn Guest Folio — bỏ qua hoàn toàn
            # process_cancel()'s logic hoàn trả tiền tạm ứng dư (excess
            # payment) vào Guest Balance Ledger. Khách no-show ĐÃ đặt cọc
            # trước (rất phổ biến với booking OTA/trực tiếp yêu cầu trả
            # trước) bị Night Audit tự động hủy sẽ có folio mang số dư ÂM
            # (tiền cọc) nhưng KHÔNG BAO GIỜ được ghi nhận vào Guest Balance
            # Ledger để hoàn tiền — tiền cọc coi như biến mất khỏi mọi sổ
            # sách theo dõi. Gọi lại đúng process_cancel() (đã qua review,
            # có dedup guard chống double-credit) thay vì lặp lại logic hủy
            # lần thứ 3 ở đây — đồng thời khóa for_update=True để nhất quán
            # với check_in_guest()/check_out_guest()/cancel_reservation().
            doc = frappe.get_doc("Hotel Reservation", res.name, for_update=True)
            doc.process_cancel()

            # Đếm NGAY sau khi trạng thái đã thực sự đổi trong DB — TRƯỚC ĐÂY
            # cancelled_count += 1 nằm SAU add_comment(), nên nếu add_comment()
            # ném lỗi (VD giới hạn độ dài, lỗi validate comment), đặt phòng đã
            # bị hủy thật trong DB nhưng vẫn không được tính vào no_show_count
            # của Night Audit Log — số liệu sai dù thao tác đã thành công.
            cancelled_count += 1

            try:
                doc.add_comment("Info", _("Auto-Cancelled (Night Audit): Guest did not arrive. Arrival date was {0}.").format(res.arrival_date))
            except Exception as comment_error:
                frappe.log_error(
                    f"Failed to add auto-cancel comment for {res.name}: {str(comment_error)}",
                    f"Night Audit No-Show Comment Error: {res.name}"
                )
        except Exception as e:
            frappe.db.rollback(save_point='no_show_cancel')
            frappe.log_error(
                f"No-Show Cancellation Error for {res.name}: {str(e)}",
                f"Night Audit No-Show Error: {res.name}"
            )

    if cancelled_count > 0:
        frappe.msgprint(_("Night Audit: Auto-cancelled {0} no-show reservation(s).").format(cancelled_count))

    return cancelled_count

def process_single_reservation(res, posting_date):
    """Mỗi đặt phòng là một đơn vị nguyên tử, kể cả khi worker tiếp tục sau lỗi."""
    from hospitality_core.hospitality_core.api.rate_plan import post_daily_charge, is_virtual
    frappe.db.savepoint('rate_plan_audit')
    try:
        res = frappe.get_doc('Hotel Reservation', res.name, for_update=True)
        if res.status != 'Checked In' or is_virtual(res):
            return False, False, None
        overstayed = getdate(res.departure_date) <= getdate(posting_date)
        if overstayed:
            handle_overstay(res, posting_date)
        return post_daily_charge(res, posting_date), overstayed, None
    except Exception as error:
        frappe.db.rollback(save_point='rate_plan_audit')
        return False, False, f'Night audit {res.name}: {error}'


def reconcile_room_reservation_folio_status(property=None):
    """
    Đối chiếu trạng thái Room <-> Reservation <-> Folio toàn hệ thống — phần
    "kiểm toán" (audit) thật sự mà trước đây module này chưa hề có (chỉ xử lý
    no-show/overstay/tính tiền cho các bản ghi giả định là đã đúng trạng
    thái). Trả về list các chuỗi mô tả từng trường hợp lệch, để lễ tân/kế
    toán đêm kiểm tra thủ công — hàm này CHỈ PHÁT HIỆN, không tự sửa, vì tự
    động sửa trạng thái sai mà không rõ nguyên nhân thực tế có thể che giấu
    một vấn đề vận hành cần con người xử lý (VD khách đã trả phòng nhưng
    buồng phòng quên dọn/cập nhật).
    """
    mismatches = []
    room_filters = {"status": "Occupied"}
    res_filters = {"status": "Checked In"}
    if property:
        room_filters["property"] = property
        res_filters["property"] = property

    # 1. Phòng đang "Occupied" nhưng không có Reservation nào đang "Checked In"
    # khớp với phòng đó.
    occupied_rooms = frappe.get_all("Hotel Room", filters=room_filters, pluck="name")
    if occupied_rooms:
        checked_in_rooms = set(frappe.get_all(
            "Hotel Reservation",
            filters={"room": ["in", occupied_rooms], "status": "Checked In"},
            pluck="room"
        ))
        for room in occupied_rooms:
            if room not in checked_in_rooms:
                mismatches.append(
                    f"Phòng {room}: trạng thái Room = 'Occupied' nhưng KHÔNG có Hotel Reservation nào "
                    f"đang 'Checked In' cho phòng này."
                )

    # 2 & 3. Reservation "Checked In" nhưng Room không phải "Occupied", hoặc
    # Folio đi kèm không phải "Open".
    checked_in_reservations = frappe.get_all(
        "Hotel Reservation",
        filters=res_filters,
        fields=["name", "room", "folio"]
    )
    if checked_in_reservations:
        rooms_involved = [r.room for r in checked_in_reservations if r.room]
        room_status_map = {}
        if rooms_involved:
            room_status_map = {
                r.name: r.status
                for r in frappe.get_all("Hotel Room", filters={"name": ["in", rooms_involved]}, fields=["name", "status"])
            }

        for res in checked_in_reservations:
            if not res.room:
                mismatches.append(f"Đặt phòng {res.name}: trạng thái 'Checked In' nhưng KHÔNG gắn với phòng nào.")
            else:
                room_status = room_status_map.get(res.room)
                if room_status != "Occupied":
                    mismatches.append(
                        f"Đặt phòng {res.name} (phòng {res.room}): 'Checked In' nhưng Room.status = "
                        f"'{room_status}' (không phải 'Occupied')."
                    )

            if res.folio:
                folio_status = frappe.db.get_value("Guest Folio", res.folio, "status")
                if folio_status != "Open":
                    mismatches.append(
                        f"Đặt phòng {res.name}: 'Checked In' nhưng Guest Folio {res.folio} có status = "
                        f"'{folio_status}' (không phải 'Open')."
                    )
            else:
                mismatches.append(f"Đặt phòng {res.name}: 'Checked In' nhưng KHÔNG có Guest Folio gắn kèm.")

    return mismatches


def _write_night_audit_log(audit_date, run_datetime, no_show_count, overstay_count,
                            room_charge_posted_count, reconciliation_details, error_details, property=None):
    """Ghi 1 bản ghi Night Audit Log bất biến cho mỗi lần chạy — trước đây chỉ
    có msgprint (mất ngay sau khi job chạy xong, không ai xem lại được) và
    các dòng log_error rời rạc trong Error Log (không tổng hợp thành 1 bản
    kiểm toán duy nhất, dễ tra cứu theo ngày).

    `property`: TRƯỚC ĐÂY không hề gán — Night Audit Log nằm trong SCOPED của
    property_scope.py, nên khi có từ 2 property "enabled" trở lên,
    validate_document()'s cơ chế tự suy ra property cho bản ghi mới sẽ THROW
    (không thể suy ra DUY NHẤT 1 property) — insert() ném lỗi, bị try/except
    dưới đây nuốt mất, khiến audit log NGỪNG ghi được vĩnh viễn mỗi đêm mà
    không ai để ý. Gán rõ property (do run_daily_audit() truyền vào, ứng với
    đúng property đang audit) để không bao giờ rơi vào nhánh tự suy đoán đó."""
    try:
        log_dict = {
            "doctype": "Night Audit Log",
            "audit_date": audit_date,
            "run_datetime": run_datetime,
            "run_by": frappe.session.user,
            "no_show_count": no_show_count,
            "overstay_count": overstay_count,
            "room_charge_posted_count": room_charge_posted_count,
            "reconciliation_mismatch_count": len(reconciliation_details),
            "reconciliation_details": "\n".join(reconciliation_details),
            "error_count": len(error_details),
            "error_details": "\n".join(error_details)
        }
        if property:
            log_dict["property"] = property
        log = frappe.get_doc(log_dict)
        log.insert(ignore_permissions=True)
    except Exception as e:
        # Không được để việc ghi log audit làm hỏng toàn bộ job Night Audit đã
        # chạy xong thành công — chỉ ghi 1 dòng log_error để biết mà xử lý.
        frappe.log_error(f"Failed to write Night Audit Log: {str(e)}", "Night Audit Log Write Error")

def already_charged_today(folio_name, date, room=None):
    filters = {
        "parent": folio_name,
        "posting_date": date,
        "is_void": 0,
        "item": ["in", get_room_rent_item_codes()]
    }
    if room:
        # Crucial for Group Payer Folio which contains mirrored charges for many rooms.
        # Match both the room docname hash and physical room number as whole tokens
        # so room "10" doesn't false-positive match a description mentioning room "101".
        from hospitality_core.hospitality_core.doctype.hotel_room.hotel_room import get_room_number
        room_number = get_room_number(room)
        candidates = frappe.get_all("Folio Transaction", filters=filters, pluck="description")
        tokens = {str(room).strip()}
        if room_number:
            tokens.add(str(room_number).strip())
        import re
        patterns = [re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)") for t in tokens if t]
        return any(any(p.search(desc or "") for p in patterns) for desc in candidates)

    return frappe.db.exists("Folio Transaction", filters)

def get_room_rent_item_codes():
    return frappe.db.sql_list("SELECT name FROM `tabItem` WHERE item_code='ROOM-RENT' OR item_group='Accommodation'")

def handle_overstay(res, posting_date=None):
    """Gia hạn qua lifecycle để kiểm tra phòng trống và đối soát LOS."""
    res.departure_date = add_days(posting_date or nowdate(), 1)
    res.save(ignore_permissions=True)
    res.add_comment('Info', _('Tự gia hạn do khách vẫn đang lưu trú.'))

def get_rate(rate_plan, room_type, date, arrival_date=None, departure_date=None):
    """API tương thích: trả giá sau LOS, chưa trừ giảm giá riêng của đặt phòng."""
    from hospitality_core.hospitality_core.api.rate_plan import snapshot_for
    from hospitality_core.hospitality_core.api.rate_calculation import quote_day
    return quote_day(snapshot_for(rate_plan, room_type), date,
                     arrival_date, departure_date)['rate_after_los']

def post_room_charge(res, base_amount, date):
    """Giữ chữ ký cũ; số tiền luôn được tính lại từ căn cứ giá ở server."""
    from hospitality_core.hospitality_core.api.rate_plan import post_daily_charge
    return post_daily_charge(res, date)

def ensure_item_exists(code, name):
    if not frappe.db.exists("Item", code):
        item = frappe.new_doc("Item")
        item.item_code = code
        item.item_name = name
        item.item_group = "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups"
        item.is_stock_item = 0
        stock_uom = (frappe.db.get_single_value('Stock Settings', 'stock_uom')
                     or frappe.db.get_value('Item', 'ROOM-RENT', 'stock_uom'))
        if not stock_uom or not frappe.db.exists('UOM', stock_uom):
            if frappe.db.exists('UOM', 'Nos'):
                stock_uom = 'Nos'
            elif frappe.db.exists('UOM', 'Unit'):
                stock_uom = 'Unit'
            else:
                first_uom = frappe.db.get_value('UOM', {}, 'name')
                stock_uom = first_uom or 'Nos'
        item.stock_uom = stock_uom
        item.insert(ignore_permissions=True)
