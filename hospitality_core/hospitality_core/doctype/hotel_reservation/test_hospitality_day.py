import frappe
from frappe.utils import nowdate, add_days, getdate
from unittest.mock import patch
from datetime import datetime

def execute():
    try:
        cleanup()
        setup()
        test_hospitality_day_logic()
    finally:
        cleanup()

def cleanup():
    # Use db.delete for hard cleanup ignoring hooks
    frappe.db.delete("Guest Folio", {"guest": "Date Test Guest"})
    frappe.db.delete("Folio Transaction", {"parent": ["in", frappe.get_all("Guest Folio", filters={"guest": "Date Test Guest"}, pluck="name")]})
    
    frappe.db.delete("Hotel Reservation", {"guest": "Date Test Guest"})
    frappe.db.delete("Guest", {"full_name": "Date Test Guest"})
    frappe.db.delete("Hotel Room", {"room_number": "DT1"})

def setup():
    # Helper Data
    if not frappe.db.exists("Hotel Room Type", "Test Single"):
        doc = frappe.new_doc("Hotel Room Type")
        doc.room_type_name = "Test Single"
        doc.default_rate = 100
        doc.insert()
    
    if not frappe.db.exists("Hotel Room", "DT1"):
        doc = frappe.new_doc("Hotel Room")
        doc.room_number = "DT1"
        doc.room_type = "Test Single"
        doc.status = "Available"
        doc.insert()

    if not frappe.db.exists("Room Rate Plan", "Standard Test"):
        doc = frappe.new_doc("Room Rate Plan")
        doc.plan_name = "Standard Test"
        doc.room_type = "Test Single"
        doc.append("seasons", {
            "season_name": "Test Season",
            "valid_from": add_days(nowdate(), -10),
            "valid_to": add_days(nowdate(), 10),
            "weekday_rate": 150,
            "weekend_rate": 150
        })
        doc.insert()
        
    if not frappe.db.exists("Guest", "Date Test Guest"):
        g = frappe.new_doc("Guest")
        g.full_name = "Date Test Guest"
        g.guest_type = "Regular"
        g.insert()

def create_reservation():
    res = frappe.new_doc("Hotel Reservation")
    res.guest = "Date Test Guest"
    res.room_type = "Test Single"
    res.room = "DT1"
    res.arrival_date = add_days(nowdate(), -1) # Arrived yesterday (technically)
    res.departure_date = add_days(nowdate(), 1)
    res.rate_plan = "Standard Test"
    res.status = "Reserved"
    res.insert()
    return res

def test_hospitality_day_logic():
    print("Testing Check-In Date Logic...")
    
    # CASE 1: Before 8 AM (e.g., 07:00) -> Should charge for YESTERDAY
    print("\n--- Test Case 1: 07:00 AM Check-In ---")
    res1 = create_reservation()
    
    # Mock datetime to be Today 07:00 AM
    mock_now = datetime.now().replace(hour=7, minute=0, second=0)
    
    with patch('hospitality_core.hospitality_core.doctype.hotel_reservation.hotel_reservation.now_datetime') as mock_dt:
        mock_dt.return_value = mock_now
        
        res1.process_check_in()
        
        # Verify Charge Date
        res1.reload()
        folio_name = res1.folio
        
        # We expect a charge for YESTERDAY
        expected_date = add_days(nowdate(), -1)
        
        txn = frappe.db.get_value("Folio Transaction", {
            "parent": folio_name,
            "item": "ROOM-RENT",
            "posting_date": expected_date
        }, "amount")
        
        if txn:
            print(f"SUCCESS: Found charge for Yesterday ({expected_date}). Amount: {txn}")
        else:
            print(f"FAILURE: Did NOT find charge for Yesterday ({expected_date}).")
            
    # CASE 2: After 8 AM (e.g., 09:00) -> Should charge for TODAY
    # Cleanup Res 1
    frappe.db.set_value("Hotel Room", "DT1", "status", "Available")
    
    # Clear transactions to allow deletion
    fol = frappe.get_doc("Guest Folio", folio_name)
    fol.transactions = []
    fol.save()
    frappe.delete_doc("Guest Folio", folio_name)
    
    frappe.delete_doc("Hotel Reservation", res1.name)
    
    print("\n--- Test Case 2: 09:00 AM Check-In ---")
    res2 = create_reservation()
    res2.arrival_date = nowdate() # Arriving today
    res2.save() # Update arrival
    
    mock_now_2 = datetime.now().replace(hour=9, minute=0, second=0)
    
    with patch('hospitality_core.hospitality_core.doctype.hotel_reservation.hotel_reservation.now_datetime') as mock_dt_2:
        mock_dt_2.return_value = mock_now_2
        
        res2.process_check_in()
        
        res2.reload()
        folio_name_2 = res2.folio
        
        # We expect a charge for TODAY
        expected_date_2 = nowdate()
        
        txn_2 = frappe.db.get_value("Folio Transaction", {
            "parent": folio_name_2,
            "item": "ROOM-RENT",
            "posting_date": expected_date_2
        }, "amount")
        
        if txn_2:
             print(f"SUCCESS: Found charge for Today ({expected_date_2}). Amount: {txn_2}")
        else:
             print(f"FAILURE: Did NOT find charge for Today ({expected_date_2}).")

        # Final Cleanup for Res 2
        fol2 = frappe.get_doc("Guest Folio", folio_name_2)
        fol2.transactions = []
        fol2.save()
        frappe.delete_doc("Guest Folio", folio_name_2)
        frappe.delete_doc("Hotel Reservation", res2.name)
