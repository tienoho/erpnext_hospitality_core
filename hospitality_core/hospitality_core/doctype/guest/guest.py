import frappe
from frappe import _
from frappe.model.document import Document

class Guest(Document):
    def validate(self):
        if not self.customer:
            customer = frappe.new_doc("Customer")
            customer.customer_name = self.full_name
            customer.customer_type = "Individual"
            customer.flags.ignore_permissions = True
            customer.insert()
            self.customer = customer.name

@frappe.whitelist()
def get_guest_stats(guest):
    from hospitality_core.hospitality_core.api.guest_crm import get_profile
    profile = get_profile(guest)
    return dict(profile.get('stats', {}), spend_by_currency=profile.get('spend_by_currency', {}))
