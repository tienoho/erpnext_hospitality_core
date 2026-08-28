import frappe
from frappe import _

def after_install():
    create_roles()
    create_custom_fields()
    create_default_data()
    enable_vietnamese_language()

def enable_vietnamese_language():
    if frappe.db.exists("Language", "vi"):
        frappe.db.set_value("Language", "vi", "enabled", 1)

def create_roles():
    roles = ["Hospitality User", "Hospitality Manager", "Housekeeping Staff"]
    for role in roles:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()

def create_custom_fields():
    # Add 'Room Charge' to Mode of Payment if not exists
    if not frappe.db.exists("Mode of Payment", "Room Charge"):
        mode = frappe.new_doc("Mode of Payment")
        mode.mode_of_payment = "Room Charge"
        mode.type = "General"
        mode.insert()

    # Add 'hotel_room' field to POS Invoice if not exists
    if not frappe.db.exists("Custom Field", {"dt": "POS Invoice", "fieldname": "hotel_room"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice",
            "fieldname": "hotel_room",
            "label": "Hotel Room Number",
            "fieldtype": "Link",
            "options": "Hotel Room",
            "insert_after": "customer"
        }).insert()

def create_default_data():
    # Create default Allowance Reason Codes
    reasons = [
        {"code": "POST-ERR", "desc": "Posting Error", "mgr": 0},
        {"code": "GUEST-SAT", "desc": "Guest Satisfaction / Complaint", "mgr": 1},
        {"code": "MGMT-COMP", "desc": "Management Complementary", "mgr": 1}
    ]
    
    for r in reasons:
        if not frappe.db.exists("Allowance Reason Code", r["code"]):
            frappe.get_doc({
                "doctype": "Allowance Reason Code",
                "reason_code": r["code"],
                "description": r["desc"],
                "requires_manager_approval": r["mgr"]
            }).insert()

    # Determine default UOM
    uom = frappe.db.get_value("UOM", {"enabled": 1}, "name") or "Nos"
    if not frappe.db.exists("UOM", uom):
        try:
            frappe.get_doc({"doctype": "UOM", "uom_name": uom, "name": uom}).insert(ignore_permissions=True)
        except Exception:
            pass

    # Create Service Items
    items = [
        {"code": "ROOM-RENT", "name": "Room Rent"},
        {"code": "POS-CHARGE", "name": "POS Charge"},
        {"code": "PAYMENT", "name": "Payment Credit"}
    ]
    # Determine default Item Group
    target_item_group = "Services"
    if not frappe.db.exists("Item Group", "Services"):
        # Find the root item group
        root_item_group = frappe.db.get_value("Item Group", 
            {"parent_item_group": ["in", ["", None]], "is_group": 1}, "name")
        
        if not root_item_group:
             root_item_group = frappe.db.get_value("Item Group", {"is_group": 1}, "name")
        
        if not root_item_group:
            try:
                root_doc = frappe.get_doc({
                    "doctype": "Item Group",
                    "item_group_name": "All Item Groups",
                    "name": "All Item Groups",
                    "is_group": 1
                })
                root_doc.flags.ignore_links = True
                root_doc.flags.ignore_mandatory = True
                root_doc.insert(ignore_permissions=True)
                root_item_group = "All Item Groups"
            except Exception:
                pass

        if root_item_group:
            try:
                frappe.get_doc({
                    "doctype": "Item Group",
                    "item_group_name": "Services",
                    "name": "Services",
                    "parent_item_group": root_item_group,
                    "is_group": 0
                }).insert(ignore_permissions=True)
                target_item_group = "Services"
            except Exception:
                target_item_group = root_item_group
        else:
            target_item_group = frappe.db.get_value("Item Group", {}, "name") or "All Item Groups"
            
    for i in items:
        if not frappe.db.exists("Item", i["code"]):
            try:
                item = frappe.new_doc("Item")
                item.item_code = i["code"]
                item.item_name = i["name"]
                item.item_group = target_item_group
                item.stock_uom = uom
                item.is_stock_item = 0
                item.flags.ignore_links = True
                item.flags.ignore_mandatory = True
                item.insert(ignore_permissions=True)
            except Exception:
                pass