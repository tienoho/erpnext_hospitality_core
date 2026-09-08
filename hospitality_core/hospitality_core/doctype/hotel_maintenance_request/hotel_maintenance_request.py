import frappe
from frappe import _
from frappe.model.document import Document

class HotelMaintenanceRequest(Document):
	def recalculate_total_expenses(self):
		total = frappe.db.sql("""
			SELECT SUM(grand_total) 
			FROM `tabHospitality Expense` 
			WHERE maintenance_request = %s AND docstatus = 1
		""", (self.name))[0][0] or 0.0
		self.db_set("total_expenses", total)

	def validate(self):
		if self.status == "Completed" and not self.resolution_notes:
			frappe.throw(_("Please enter Resolution Notes before marking as Completed."))

	def on_update(self):
		self.update_room_status()

	def update_room_status(self):
		# Only update room status if the room is currently enabled
		if not frappe.db.get_value("Hotel Room", self.room, "is_enabled"):
			return

		current_room_status = frappe.db.get_value("Hotel Room", self.room, "status")

		# Logic: If Request is Open/In Progress, block the room — but don't
		# overwrite an Occupied room; a guest is still checked in and the
		# room isn't up for new booking regardless of this flag.
		if self.status in ["Reported", "In Progress"]:
			if current_room_status not in ["Out of Order", "Occupied"]:
				frappe.db.set_value("Hotel Room", self.room, "status", "Out of Order")
				frappe.msgprint(_("Room {0} marked as 'Out of Order' due to maintenance request.").format(self.room))

		# Logic: If Request is Completed OR Cancelled, release the room to
		# Housekeeping — but only if no other Maintenance Request for this
		# room is still open.
		# TRƯỚC ĐÂY: chỉ xử lý "Completed" — "Cancelled" (giá trị hợp lệ của
		# Select field status, VD tạo nhầm yêu cầu rồi hủy thay vì hoàn tất)
		# không khớp nhánh nào cả, khiến phòng bị kẹt "Out of Order" VĨNH
		# VIỄN dù yêu cầu bảo trì đã bị hủy — không bán được phòng cho tới
		# khi ai đó tự sửa tay trạng thái phòng.
		elif self.status in ("Completed", "Cancelled"):
			if current_room_status == "Out of Order":
				other_open = frappe.db.exists("Hotel Maintenance Request", {
					"room": self.room,
					"status": ["in", ["Reported", "In Progress"]],
					"name": ["!=", self.name]
				})
				if not other_open:
					if self.status == "Completed":
						frappe.db.set_value("Hotel Room", self.room, "status", "Dirty")
						frappe.msgprint(_("Maintenance Completed. Room {0} marked as 'Dirty' for cleaning.").format(self.room))
					else:
						frappe.db.set_value("Hotel Room", self.room, "status", "Dirty")
						frappe.msgprint(_("Maintenance Request cancelled. Room {0} marked as 'Dirty' for cleaning before returning to sale.").format(self.room))