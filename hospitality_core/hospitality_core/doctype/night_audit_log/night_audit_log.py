import frappe
from frappe.model.document import Document
from hospitality_core.hospitality_core.api.employee_link import resolve_employees


class NightAuditLog(Document):
	@property
	def run_by_employee_name(self):
		"""Virtual field — resolve tên nhân viên thật qua Employee.user_id nếu
		`run_by` là 1 nhân viên có hồ sơ Employee. Trả None (hiển thị rỗng)
		nếu `run_by` là tài khoản hệ thống (VD Administrator chạy tự động qua
		scheduler) — đây là trường hợp bình thường, không phải lỗi."""
		if not self.run_by:
			return None
		info = resolve_employees([self.run_by]).get(self.run_by)
		return info.get("employee_name") if info else None
