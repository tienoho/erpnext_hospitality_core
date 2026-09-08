import frappe
from frappe import _
from frappe.utils import getdate, date_diff, nowdate

def check_availability(room, arrival_date, departure_date, ignore_reservation=None):
    """
    Checks if a room is available for the given date range.
    Returns True if available, raises ValidationError if not.
    """
    if not room or not arrival_date or not departure_date:
        return

    # Khóa dòng Hotel Room (SELECT ... FOR UPDATE) trước khi đọc các đặt phòng
    # đang trùng lịch — nếu không, 2 request tạo/duyệt Hotel Reservation đồng
    # thời cho CÙNG MỘT phòng (2 quầy lễ tân, hoặc kéo-thả trùng lúc trên Tape
    # Chart) đều có thể đọc thấy "chưa ai đặt" trước khi request kia commit,
    # rồi cả hai cùng lưu thành công — double-booking. create_folio() trong
    # cùng file này đã dùng đúng mẫu khóa này cho Hotel Reservation, chỉ chưa
    # áp dụng cho tài nguyên khan hiếm thật sự là Hotel Room.
    frappe.db.sql("SELECT name FROM `tabHotel Room` WHERE name=%s FOR UPDATE", room)

    # 1. Check if Room is Enabled (Maintenance check)
    room_status = frappe.db.get_value("Hotel Room", room, ["status", "is_enabled", "property"], as_dict=True)
    if not room_status:
        frappe.throw(_("Room {0} does not exist.").format(room))
    if room_status.property:
        from hospitality_core.hospitality_core.api.property_scope import require_property
        require_property(room_status.property)
    if not room_status.is_enabled:
        frappe.throw(_("Room {0} is currently disabled/under maintenance.").format(room))
    
    if room_status.status == "Out of Order":
        frappe.throw(_("Room {0} is marked Out of Order.").format(room))

    # 2. Check Overlapping Reservations
    # Logic: New Arrival < Existing Departure AND New Departure > Existing Arrival
    filters = {
        "room": room,
        "status": ["in", ["Reserved", "Checked In"]],
        "name": ["!=", ignore_reservation] if ignore_reservation else ["is", "set"]
    }
    
    existing_bookings = frappe.get_all("Hotel Reservation", 
        filters=filters,
        fields=["name", "arrival_date", "departure_date", "guest"]
    )

    for booking in existing_bookings:
        # Check for date overlap
        if (getdate(arrival_date) < getdate(booking.departure_date)) and \
           (getdate(departure_date) > getdate(booking.arrival_date)):
             frappe.throw(
                _("Room {0} is already booked by {1} from {2} to {3} (Reservation: {4})").format(
                    room, booking.guest, booking.arrival_date, booking.departure_date, booking.name
                )
             )
    
    return True

def check_bulk_availability(rooms, arrival_date, departure_date, ignore_reservation=None):
    """
    Checks if a list of rooms is available for the given date range.
    Collects ALL conflicts and raises a single ValidationError.
    """
    if not rooms or not arrival_date or not departure_date:
        return

    conflicts = []

    rooms = sorted(set(rooms))
    frappe.db.sql("SELECT name FROM `tabHotel Room` WHERE name IN %(rooms)s ORDER BY name FOR UPDATE",
                  {"rooms": rooms})

    # 1. Check Room Maintenance Status for all rooms in batch
    room_data = frappe.get_all("Hotel Room", 
        filters={"name": ["in", rooms]},
        fields=["name", "room_number", "status", "is_enabled", "property"]
    )

    from hospitality_core.hospitality_core.api.property_scope import require_property
    for prop in {r.property for r in room_data if r.property}:
        require_property(prop)
    room_map = {r.name: r for r in room_data}

    for room_num in rooms:
        r = room_map.get(room_num)
        if not r:
            conflicts.append(_("Room {0} does not exist.").format(room_num))
            continue
            
        if not r.is_enabled:
            conflicts.append(_("Room {0} is currently disabled/under maintenance.").format(room_num))
        elif r.status == "Out of Order":
            conflicts.append(_("Room {0} is marked Out of Order.").format(room_num))

    # 2. Check Overlapping Reservations for all rooms in batch
    # Logic: New Arrival < Existing Departure AND New Departure > Existing Arrival
    existing_bookings = frappe.get_all("Hotel Reservation", 
        filters={
            "room": ["in", rooms],
            "status": ["in", ["Reserved", "Checked In"]],
            "name": ["!=", ignore_reservation] if ignore_reservation else ["is", "set"]
        },
        fields=["name", "arrival_date", "departure_date", "guest", "room"]
    )

    for booking in existing_bookings:
        # Check for date overlap
        if (getdate(arrival_date) < getdate(booking.departure_date)) and \
           (getdate(departure_date) > getdate(booking.arrival_date)):
             conflicts.append(
                _("Room {0} is already booked by {1} from {2} to {3} (Reservation: {4})").format(
                    booking.room, booking.guest, booking.arrival_date, booking.departure_date, booking.name
                )
             )

    if conflicts:
        message = _("The following availability issues were found:") + "<br><br>"
        message += "<div class='alert alert-danger'>"
        message += "<ul>"
        for conflict in conflicts:
            message += f"<li>{conflict}</li>"
        message += "</ul>"
        message += "</div>"
        frappe.throw(message, title=_("Room Availability Conflict"))

    return True

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_available_rooms_for_picker(doctype, txt, searchfield, start, page_len, filters):
    """
    Search picker for rooms that are available for the selected dates.
    Filters: arrival_date, departure_date, room_type, ignore_reservation
    """
    filters = frappe.parse_json(filters) or {}
    arrival = filters.get("arrival_date")
    departure = filters.get("departure_date")
    room_type = filters.get("room_type")
    ignore = filters.get("ignore_reservation")
    from hospitality_core.hospitality_core.api.property_scope import resolve
    property = filters.get('property')
    if property or frappe.db.exists('Hospitality Property'):
        scope = resolve(property, linked=('Hotel Room Type', room_type) if room_type else None)
        property = scope.property
    if ignore:
        ignored = frappe.get_doc('Hotel Reservation', ignore)
        ignored.check_permission('read')
        if (ignored.get('property') or None) != (property or None):
            frappe.throw(_('Đặt phòng bỏ qua không thuộc cơ sở đã chọn.'))
    if arrival and departure and getdate(departure) <= getdate(arrival):
        frappe.throw(_('Ngày trả phòng phải sau ngày đến.'))

    return frappe.db.sql("""
        SELECT r.name, r.room_type, r.status, r.room_number
        FROM `tabHotel Room` r
        WHERE r.is_enabled = 1 AND r.status != 'Out of Order'
        AND (%(room_type)s IS NULL OR r.room_type = %(room_type)s)
        AND (%(property)s IS NULL OR r.property = %(property)s)
        AND (r.name LIKE %(txt)s OR r.room_number LIKE %(txt)s)
        AND (%(arrival)s IS NULL OR %(departure)s IS NULL OR NOT EXISTS (
            SELECT 1 FROM `tabHotel Reservation` b
            WHERE b.room = r.name AND b.status IN ('Reserved', 'Checked In')
            AND b.name != %(ignore)s
            AND b.arrival_date < %(departure)s AND b.departure_date > %(arrival)s
        ))
        ORDER BY r.room_number, r.name
        LIMIT %(start)s, %(page_len)s
    """, dict(room_type=room_type or None, property=property or None, txt=f"%{txt}%",
              arrival=arrival or None, departure=departure or None, ignore=ignore or '',
              start=start, page_len=page_len))

def create_folio(reservation_doc):
    """
    Creates a 'Provisional' Guest Folio linked to this reservation.
    """
    # Lock this reservation's row so two concurrent calls (double-click check-in,
    # a retried request) serialize here instead of both passing the exists-check
    # before either has committed its Guest Folio insert.
    frappe.db.sql(
        "SELECT name FROM `tabHotel Reservation` WHERE name=%s FOR UPDATE",
        reservation_doc.name
    )

    if frappe.db.exists("Guest Folio", {"reservation": reservation_doc.name, "status": ["!=", "Cancelled"]}):
        return

    folio = frappe.new_doc("Guest Folio")
    folio.guest = reservation_doc.guest
    folio.reservation = reservation_doc.name
    folio.room = reservation_doc.room
    folio.status = "Provisional"
    folio.company = reservation_doc.company # If corporate booking
    folio.hotel_reception = reservation_doc.hotel_reception
    folio.reserved_by = reservation_doc.reserved_by
    folio.open_date = nowdate()
    for field in ('property', 'operating_company', 'currency', 'billing_customer'):
        folio.set(field, reservation_doc.get(field))
    
    # Save the Folio
    folio.insert(ignore_permissions=True)
    
    # Link Folio back to Reservation
    reservation_doc.db_set("folio", folio.name)
    frappe.msgprint(_("Guest Folio {0} created successfully.").format(folio.name))

    # Transfer existing balances from the Guest Balance Ledger
    from hospitality_core.hospitality_core.api.folio import transfer_existing_balances
    transfer_existing_balances(folio)

@frappe.whitelist()
def get_room_rate(room=None, rate_plan=None, room_type=None, arrival_date=None, departure_date=None,
                  discount_type=None, discount_value=None, is_complimentary=None, reservation_name=None,
                  property=None, currency=None, membership=None, guest=None):
    from hospitality_core.hospitality_core.api.rate_plan import snapshot_for, reservation_snapshot, charge_date_for_checkin
    from hospitality_core.hospitality_core.api.rate_calculation import quote_day, quote_stay
    from frappe.utils import cint
    if room:
        room_type = frappe.db.get_value('Hotel Room', room, 'room_type')
    if not room_type or not arrival_date or not departure_date:
        return dict(nightly_rates=[], nights=0, total=0)
    saved = None
    if reservation_name:
        saved = frappe.get_doc('Hotel Reservation', reservation_name)
        saved.check_permission('read')
        if property and saved.get('property') != property or currency and saved.get('currency') and saved.currency != currency:
            frappe.throw(_('Không thay đổi cơ sở hoặc tiền tệ của đặt phòng đã lưu.'))
    if saved and saved.room_type == room_type and (saved.rate_plan or None) == (rate_plan or None) and (
            not guest or (saved.get('membership') or None) == (membership or None)):
        snapshot = reservation_snapshot(saved)
    else:
        snapshot = snapshot_for(rate_plan, room_type, currency, property)
        if snapshot.get('property') and membership and guest:
            from hospitality_core.hospitality_core.api.guest_loyalty import snapshot as loyalty_snapshot
            policy = loyalty_snapshot(frappe._dict(membership=membership, guest=guest,
                operating_company=snapshot['operating_company']))
            snapshot.update(vip_percent=policy.get('vip_percent', 0), loyalty=policy)
    discounts = dict(discount_type=discount_type, discount_value=discount_value,
                     complimentary=bool(cint(is_complimentary)))
    try:
        result = quote_stay(snapshot, arrival_date, departure_date, **discounts)
        result.update(result['nightly_rates'][0])  # Tương thích caller cũ, nhưng UI dùng toàn bộ từng đêm.
        result['nights'] = len(result['nightly_rates'])
        if getdate(arrival_date) <= getdate(nowdate()) and (not saved or saved.status == 'Reserved'):
            result['checkin_charge'] = quote_day(snapshot, charge_date_for_checkin(),
                                               arrival_date, departure_date, **discounts)
        result['snapshot_locked'] = bool(saved and saved.get('rate_snapshot') and snapshot.get('rate_plan') == saved.rate_plan)
        return result
    except ValueError as error:
        frappe.throw(str(error))
