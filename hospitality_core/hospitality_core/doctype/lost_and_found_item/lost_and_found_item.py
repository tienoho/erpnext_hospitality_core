import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

# TRƯỚC ĐÂY: class LostAndFoundItem — SAI. Đã xác minh trực tiếp
# frappe/model/base_document.py's import_controller(): tên class Frappe tìm
# = doctype.replace(" ", "").replace("-", "") — CHỈ bỏ khoảng trắng/gạch
# ngang, KHÔNG viết hoa từng chữ. Với DocType "Lost and Found Item" (chữ
# "and" viết thường theo đúng ngữ pháp tiêu đề tiếng Anh), tên class ĐÚNG
# phải là "LostandFoundItem" (giữ nguyên "and" thường), không phải
# "LostAndFoundItem". Lỗi này khiến get_controller() ném ImportError —
# CHƯA TỪNG bị phát hiện suốt phiên review vì chỉ lộ ra khi thực sự
# bench install-app/migrate trên site thật (bench tự xóa DocType này coi là
# "orphan" mỗi lần chạy migrate, vì không tìm thấy class khớp tên).
class LostandFoundItem(Document):
    def validate(self):
        self.validate_dates()
        self.validate_claim()

    def validate_dates(self):
        if getdate(self.found_date) > getdate(nowdate()):
            frappe.throw(_("Found Date cannot be in the future."))

    def validate_claim(self):
        if self.status == "Claimed":
            if not self.claimant_info:
                frappe.throw(_("Please enter Claimant Info before marking as Claimed."))
            
            if not self.claimed_date:
                self.claimed_date = nowdate()
            
            if getdate(self.claimed_date) < getdate(self.found_date):
                frappe.throw(_("Claimed Date cannot be before Found Date."))