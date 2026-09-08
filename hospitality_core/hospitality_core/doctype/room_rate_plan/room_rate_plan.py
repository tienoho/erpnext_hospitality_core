import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, flt, cint

class RoomRatePlan(Document):
    def validate(self):
        self.validate_seasons()
        self.validate_los_discounts()

    def validate_seasons(self):
        """
        TRƯỚC ĐÂY: Room Rate Plan chỉ có 1 giá cố định cho 1 khoảng ngày duy
        nhất (rate/valid_from/valid_to ở cấp cha) — không hỗ trợ nhiều mùa vụ
        khác giá nhau (Tết/hè/thấp điểm) trong CÙNG 1 rate plan, và không có
        khái niệm giá cuối tuần khác ngày thường. Nay mỗi dòng trong bảng con
        `seasons` là 1 mùa vụ độc lập — validate ở đây chỉ đảm bảo tính nhất
        quán NỘI BỘ của chính rate plan này (không cần so sánh chéo giữa các
        rate plan khác nhau, vì mỗi Hotel Reservation chỉ neo vào ĐÚNG 1 rate
        plan cụ thể — không có khái niệm 2 rate plan "tranh nhau" áp dụng cho
        cùng 1 đặt phòng).
        """
        seen = []
        for row in (self.seasons or []):
            if getdate(row.valid_from) > getdate(row.valid_to):
                frappe.throw(_(
                    "Mùa vụ '{0}' (dòng {1}): Từ Ngày không được sau Đến Ngày."
                ).format(row.season_name, row.idx))

            if flt(row.weekday_rate) < 0:
                frappe.throw(_("Mùa vụ '{0}' (dòng {1}): Giá Ngày Thường không thể là số âm.").format(row.season_name, row.idx))

            if flt(row.weekend_rate) < 0:
                frappe.throw(_("Mùa vụ '{0}' (dòng {1}): Giá Cuối Tuần không thể là số âm.").format(row.season_name, row.idx))

            for other in seen:
                if getdate(row.valid_from) <= getdate(other.valid_to) and getdate(row.valid_to) >= getdate(other.valid_from):
                    frappe.throw(_(
                        "Mùa vụ '{0}' (dòng {1}) trùng khoảng ngày với mùa vụ '{2}' (dòng {3}) trong CÙNG rate "
                        "plan này — mỗi ngày chỉ được thuộc đúng 1 mùa vụ để tránh không rõ giá nào áp dụng."
                    ).format(row.season_name, row.idx, other.season_name, other.idx))
            seen.append(row)

    def validate_los_discounts(self):
        thresholds = set()
        for row in (self.los_discounts or []):
            if cint(row.min_nights) in thresholds:
                frappe.throw(_("Không được có hai bậc LOS cùng số đêm tối thiểu."))
            thresholds.add(cint(row.min_nights))
            if cint(row.min_nights) < 1:
                frappe.throw(_("Bậc giảm giá LOS (dòng {0}): Số Đêm Tối Thiểu phải >= 1.").format(row.idx))
            if flt(row.discount_percent) < 0 or flt(row.discount_percent) > 100:
                frappe.throw(_("Bậc giảm giá LOS (dòng {0}): Giảm Giá (%) phải trong khoảng 0-100.").format(row.idx))
