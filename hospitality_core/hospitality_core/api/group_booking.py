import frappe
from frappe import _
from hospitality_core.hospitality_core.api.reservation import check_bulk_availability

@frappe.whitelist()
def create_master_folio(group_booking_name):
    if not frappe.has_permission("Hotel Group Booking", "write", doc=group_booking_name):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    doc = frappe.get_doc("Hotel Group Booking", group_booking_name)
    
    if doc.master_folio:
        frappe.throw(_("Master Folio already exists: {0}").format(doc.master_folio))

    if not doc.master_payer:
        frappe.throw(_("Please select a Master Payer (Customer) before creating a Folio."))

    # Create a "Dummy" Guest record for the Group if needed, or link to a generic placeholder.
    # Ideally, we create a Guest record representing the Event Organizer.
    # For this implementation, we assume a Guest record exists or we create one on the fly.
    
    organizer_guest = frappe.db.get_value("Guest", {"customer": doc.master_payer}, "name")
    if not organizer_guest:
        # Create a proxy guest for the company
        g = frappe.new_doc("Guest")
        g.full_name = doc.group_name
        g.customer = doc.master_payer
        g.insert(ignore_permissions=True)
        organizer_guest = g.name

    # Create the Master Folio
    folio = frappe.new_doc("Guest Folio")
    folio.guest = organizer_guest
    folio.company = doc.master_payer
    # TRƯỚC ĐÂY: không set property/operating_company/currency — đây là nút
    # thủ công thay thế cho create_master_payer_reservation() (luồng tự động,
    # đã có sẵn throw rõ ràng khi lệch property). Vì Guest Folio KHÔNG được
    # liên kết room/reservation nào (không có gì cho validate_document()'s
    # LINKS tự suy ra property), property_scope.py sẽ hoặc throw (nếu >1
    # property đang enabled) hoặc âm thầm gán bừa property DUY NHẤT đang
    # enabled — không đối chiếu với property của CHÍNH Hotel Group Booking
    # này. Set tường minh từ group booking để nhất quán với luồng tự động.
    if doc.get('property'):
        folio.property = doc.property
        folio.operating_company = doc.get('operating_company')
        folio.currency = doc.get('currency')
    # We don't link a specific room or reservation, but we flag it as a Group Master
    folio.status = "Open"
    folio.save(ignore_permissions=True)

    if doc.get('property') and folio.get('property') != doc.property:
        frappe.throw(_("Master Folio vừa tạo không cùng cơ sở (property) với Group Booking — vui lòng kiểm tra lại."))

    # Link back
    doc.db_set("master_folio", folio.name)

    return folio.name


@frappe.whitelist(methods=['POST'])
def record_group_deposit(group_booking, mode_of_payment, amount=None, reference_no='', remarks=''):
    """
    Ghi nhận tiền đặt cọc đoàn bằng 1 Payment Entry THẬT trên Master Folio.

    TRƯỚC ĐÂY: `deposit_status` (hotel_group_booking.py's validate_deposit())
    chỉ là field thông tin THUẦN TÚY, hoàn toàn tách biệt khỏi
    outstanding_balance thật của Master Folio — đánh dấu "Received" qua
    dropdown KHÔNG hề trừ tiền vào số dư, khiến City Ledger/AR Aging báo
    THỪA số tiền còn nợ (đã thu cọc thật nhưng báo cáo vẫn hiện đủ 100%
    công nợ, có thể khiến kế toán đòi thu lại tiền đã thu). Cố ý làm thành
    1 hàm RIÊNG, tường minh (không tự động kích hoạt ngay khi đổi dropdown
    trong validate()) — thu cọc là hành động tài chính thật (tạo GL), nhân
    viên cần chủ động xác nhận qua hành động này, không phải side-effect ẩn
    của việc đổi 1 trường trạng thái.
    """
    doc = frappe.get_doc("Hotel Group Booking", group_booking)
    if not doc.master_folio:
        frappe.throw(_("Đoàn {0} chưa có Master Folio để ghi nhận đặt cọc.").format(group_booking))

    from frappe.utils import flt
    deposit_amount = flt(amount) if amount else flt(doc.deposit_required)
    if deposit_amount <= 0:
        frappe.throw(_("Số tiền đặt cọc phải lớn hơn 0."))

    from hospitality_core.hospitality_core.api.payment_bridge import create_company_folio_payment
    result = create_company_folio_payment(
        doc.master_folio, deposit_amount, mode_of_payment,
        hotel_reception=None,
        reference_no=reference_no,
        remarks=remarks or _("Đặt cọc đoàn {0}").format(doc.group_name or doc.name)
    )

    doc.flags.hospitality_service = True
    doc.deposit_status = "Received"
    doc.save(ignore_permissions=True)

    return result

@frappe.whitelist()
def add_rooms_to_group(group_booking, rooms):
    """
    rooms: JSON string list of room names or reservations
    Logic to mass-update reservations to link them to this group.
    """
    if not frappe.has_permission("Hotel Reservation", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    import json
    room_list = json.loads(rooms)
    
    # room_list might be strings (IDs) or objects depending on client input
    for res_data in room_list:
        res_name = res_data if isinstance(res_data, str) else res_data.get('name') or res_data.get('hotel_reservation')
        if res_name:
            frappe.db.set_value("Hotel Reservation", res_name, {
                "group_booking": group_booking,
                "is_group_guest": 1 # Auto-flag as group guest
            })
        
    return True

@frappe.whitelist()
def mass_check_in(group_booking):
    """
    Finds all 'Reserved' bookings linked to this group and checks them in.
    This includes both regular group reservations and the master payer reservation.
    """
    if not frappe.has_permission("Hotel Reservation", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    # Get group doc to check for master folio
    group_doc = frappe.get_doc("Hotel Group Booking", group_booking)

    # 0. Kiểm tra hạn mức tín dụng của Đại lý lữ hành trước khi Check-in
    if group_doc.master_payer:
        from hospitality_core.hospitality_core.api.city_ledger import get_agent_credit_status
        credit_info = get_agent_credit_status(group_doc.master_payer)
        if credit_info.get("status_level") == "RED":
            frappe.throw(
                _("Đại lý <b>{0}</b> đã vượt trần tín dụng!<br>"
                  "Hạn mức: {1} | Dư nợ hiện tại: {2} (Đã dùng {3}%)<br>"
                  "Vui lòng thanh toán hoặc yêu cầu Kế toán trưởng bảo lãnh trước khi nhận phòng đoàn.").format(
                    credit_info.get("customer_name"),
                    credit_info.get("formatted_credit_limit"),
                    credit_info.get("formatted_outstanding"),
                    credit_info.get("usage_pct")
                )
            )
    
    # Get all reservations linked to this group
    # TRƯỚC ĐÂY: mỗi bước ở đây (kể cả khi hoàn toàn thành công) đều gọi
    # frappe.log_error(..., "Mass Check-in Debug") — làm rác Error Log List
    # bằng thông tin gỡ lỗi không phải lỗi thật, khiến khó phát hiện lỗi thật
    # khi rà soát. Đã bỏ toàn bộ log debug, chỉ giữ log_error thật ở nhánh
    # except bên dưới ("Mass Check-in Error").
    reservations = frappe.get_all("Hotel Reservation",
        filters={"group_booking": group_booking, "status": "Reserved"},
        fields=["name"]
    )

    # Also check for master payer reservation by folio if it exists
    if group_doc.master_folio:
        master_res = frappe.get_all("Hotel Reservation",
            filters={
                "folio": group_doc.master_folio,
                "status": "Reserved"
            },
            fields=["name"]
        )
        # Add master reservation if not already in list
        for m_res in master_res:
            if m_res not in reservations:
                reservations.append(m_res)

    if not reservations:
        return {"message": _("No reserved bookings found for this group.")}

    count = 0
    errors = []
    for r in reservations:
        frappe.db.savepoint('group_rate_checkin')
        try:
            doc = frappe.get_doc("Hotel Reservation", r.name, for_update=True)
            doc.process_check_in()
            count += 1
        except Exception as e:
            frappe.db.rollback(save_point='group_rate_checkin')
            err_msg = str(e) or _("Unknown error")
            errors.append(f"<b>{r.name}</b>: {err_msg}")
            frappe.log_error(f"Failed to check in {r.name}: {err_msg}", "Mass Check-in Error")
            
    res_msg = _("Successfully Checked In {0} guests.").format(count)
    if errors:
        res_msg += "<br><br>" + _("<b>Failures:</b>") + "<br><ul><li>" + "</li><li>".join(errors) + "</li></ul>"
        
    return {"message": res_msg, "success_count": count, "error_count": len(errors)}

@frappe.whitelist()
def mass_check_out(group_booking):
    """
    Finds all 'Checked In' bookings linked to this group and checks them out.
    """
    if not frappe.has_permission("Hotel Reservation", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    reservations = frappe.get_all("Hotel Reservation",
        filters={"group_booking": group_booking, "status": "Checked In"},
        fields=["name"]
    )
    
    if not reservations:
        return {"message": _("No in-house guests found for this group to check out.")}
        
    count = 0
    errors = []
    for r in reservations:
        # Khớp savepoint/rollback đã dùng ở mass_check_in() (bên trên) —
        # TRƯỚC ĐÂY vòng lặp này không có, nên nếu process_check_out() ném
        # lỗi SAU KHI đã ghi 1 phần giao dịch (VD tạo transaction TRANSFER
        # sang City Ledger) nhưng TRƯỚC KHI cập nhật xong trạng thái, phần đã
        # ghi vẫn ở lại trong DB dù toàn bộ lượt check-out của khách đó coi
        # như thất bại — không đối xứng với luồng check-in đã được bảo vệ.
        frappe.db.savepoint('group_rate_checkout')
        try:
            # for_update=True — TRƯỚC ĐÂY đọc doc THƯỜNG (không khóa), khác với
            # `check_out_guest()` (whitelisted wrapper cho check-out ĐƠN LẺ) vừa
            # được thêm for_update=True cùng phiên này để chặn race điều kiện
            # snapshot cũ. Nếu 1 nhân viên bấm "Check Out" đơn lẻ (đi qua
            # check_out_guest(), có khóa) đúng lúc 1 nhân viên khác bấm
            # "Mass Check Out" cho cả đoàn (đi qua đây, KHÔNG khóa) trên CÙNG 1
            # đặt phòng, luồng mass check-out này đọc dưới REPEATABLE READ có
            # thể không chờ khóa của luồng kia — vẫn thấy status="Checked In"
            # cũ và chạy tiếp, có nguy cơ ghi trùng giao dịch transfer City
            # Ledger/Group Master. Khóa ở đây để nhất quán với check_out_guest()
            # và với mass_check_in() (đã có for_update=True) trong cùng file.
            doc = frappe.get_doc("Hotel Reservation", r.name, for_update=True)
            doc.process_check_out()
            count += 1
        except Exception as e:
            frappe.db.rollback(save_point='group_rate_checkout')
            err_msg = str(e) or _("Unknown error")
            errors.append(f"<b>{r.name}</b>: {err_msg}")
            frappe.log_error(f"Failed to check out {r.name}: {err_msg}", "Mass Check-out Error")

    res_msg = _("Successfully Checked Out {0} guests.").format(count)
    if errors:
        res_msg += "<br><br>" + _("<b>Failures:</b>") + "<br><ul><li>" + "</li><li>".join(errors) + "</li></ul>"
            
    return {"message": res_msg, "success_count": count, "error_count": len(errors)}
    
@frappe.whitelist()
def bulk_reserve_rooms(group_booking, guest, rooms, arrival_date, departure_date, discount_type=None, discount_value=0):
    """
    Creates multiple Hotel Reservation records for a guest under a group booking.
    rooms: JSON list of room names
    """
    # TRƯỚC ĐÂY: không có kiểm tra quyền RIÊNG (chỉ dựa vào quyền "create"
    # ngầm định của res.insert() bên dưới) — khác với các hàm cùng file
    # (create_master_folio/add_rooms_to_group/mass_check_in/out đều có
    # frappe.has_permission("Hotel Reservation", "write") tường minh). Hàm
    # này còn cho phép set discount_value tùy ý (tới 100%) khi tạo hàng loạt
    # đặt phòng, nên cần chốt chặn rõ ràng như các hàm khác.
    if not frappe.has_permission("Hotel Reservation", "write"):
        frappe.throw(_("Not permitted to create reservations."), frappe.PermissionError)

    import json
    room_list = json.loads(rooms)

    group_doc = frappe.get_doc("Hotel Group Booking", group_booking)
    
    # Comprehensive Availability Verification
    check_bulk_availability(room_list, arrival_date, departure_date)

    created_reservations = []
    errors = []
    
    for room in room_list:
        try:
            # Create Hotel Reservation
            res = frappe.new_doc("Hotel Reservation")
            res.guest = guest
            res.room = room
            # Get room type
            res.room_type = frappe.db.get_value("Hotel Room", room, "room_type")
            res.arrival_date = arrival_date
            res.departure_date = departure_date
            res.group_booking = group_booking
            res.is_group_guest = 1
            res.company = group_doc.master_payer
            
            # --- EXTRACT FROM TABLE ---
            # Look for this room in the group booking's rooms child table
            row = next((r for r in group_doc.get("rooms", []) if r.room == room), None)
            
            if row:
                res.rate_plan = row.rate_plan
                res.discount_type = row.discount_type or group_doc.discount_type
                res.discount_value = row.discount_value if row.discount_type else group_doc.discount_value
            else:
                # Fallback to Group Level
                res.discount_type = group_doc.discount_type
                res.discount_value = group_doc.discount_value
            
            # Override with Dialog Values if explicitly provided (optional, let's prioritize table)
            if discount_type:
                res.discount_type = discount_type
                res.discount_value = float(discount_value) if discount_value else 0
            
            # Validation will happen on insert (availability check etc.)
            res.insert()
            
            # Link to master folio via routing if master folio exists
            if res.folio and group_doc.master_folio:
                try:
                    routing = frappe.new_doc("Reservation Routing")
                    routing.reservation = res.name
                    routing.source_folio = res.folio
                    routing.target_folio = group_doc.master_folio
                    routing.percentage = 100  # Route all charges to master
                    routing.insert(ignore_permissions=True)
                except Exception as routing_error:
                    # Log but don't fail the reservation creation
                    frappe.log_error(f"Failed to create routing for {res.name}: {str(routing_error)}", "Bulk Reserve Routing Error")
            
            created_reservations.append(res.name)
        except Exception as e:
            err_msg = str(e) or _("Unknown error")
            errors.append(f"<b>Room {room}</b>: {err_msg}")
        
    return {
        "created": created_reservations,
        "errors": errors
    }