import frappe


@frappe.whitelist()
def get_guest_details(guest):
    from hospitality_core.hospitality_core.api.guest_crm import get_profile
    return get_profile(guest)
