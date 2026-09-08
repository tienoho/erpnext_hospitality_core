import frappe
from frappe import _
from frappe.model.document import Document


class HotelRoomType(Document):
    def validate(self):
        if self.max_adults is not None and self.max_adults < 1:
            frappe.throw(_("Max Adults must be at least 1."))
        if self.max_children is not None and self.max_children < 0:
            frappe.throw(_("Max Children cannot be negative."))
        if self.default_rate is not None and self.default_rate <= 0:
            frappe.throw(_("Default Rate must be greater than zero."))
