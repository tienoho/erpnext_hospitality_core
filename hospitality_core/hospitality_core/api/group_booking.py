import frappe
from frappe import _
from hospitality_core.hospitality_core.api.reservation import check_bulk_availability

@frappe.whitelist()
def create_master_folio(group_booking_name):
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
    # We don't link a specific room or reservation, but we flag it as a Group Master
    folio.status = "Open"
    folio.save(ignore_permissions=True)
    
    # Link back
    doc.db_set("master_folio", folio.name)
    
    return folio.name

@frappe.whitelist()
def add_rooms_to_group(group_booking, rooms):
    """
    rooms: JSON string list of room names or reservations
    Logic to mass-update reservations to link them to this group.
    """
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
    reservations = frappe.get_all("Hotel Reservation", 
        filters={"group_booking": group_booking, "status": "Reserved"},
        fields=["name"]
    )
    
    frappe.log_error(f"Group {group_booking}: Found {len(reservations)} reservations via group_booking field", "Mass Check-in Debug")
    
    # Also check for master payer reservation by folio if it exists
    if group_doc.master_folio:
        master_res = frappe.get_all("Hotel Reservation",
            filters={
                "folio": group_doc.master_folio,
                "status": "Reserved"
            },
            fields=["name"]
        )
        frappe.log_error(f"Group {group_booking}: Found {len(master_res)} reservations via master_folio", "Mass Check-in Debug")
        # Add master reservation if not already in list
        for m_res in master_res:
            if m_res not in reservations:
                reservations.append(m_res)
                frappe.log_error(f"Added master reservation {m_res.name} to check-in list", "Mass Check-in Debug")
    
    if not reservations:
        return {"message": _("No reserved bookings found for this group.")}
        
    count = 0
    errors = []
    for r in reservations:
        try:
            doc = frappe.get_doc("Hotel Reservation", r.name)
            frappe.log_error(f"Checking in {doc.name}: rate_plan={doc.rate_plan}, room_type={doc.room_type}, folio={doc.folio}", "Mass Check-in Debug")
            doc.process_check_in()
            count += 1
        except Exception as e:
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
    reservations = frappe.get_all("Hotel Reservation", 
        filters={"group_booking": group_booking, "status": "Checked In"},
        fields=["name"]
    )
    
    if not reservations:
        return {"message": _("No in-house guests found for this group to check out.")}
        
    count = 0
    errors = []
    for r in reservations:
        try:
            doc = frappe.get_doc("Hotel Reservation", r.name)
            doc.process_check_out()
            count += 1
        except Exception as e:
            err_msg = str(e) or _("Unknown error")
            errors.append(f"<b>{r.name}</b>: {err_msg}")
            
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