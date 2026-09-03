# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_time

class HospitalitySurchargeSettings(Document):
    def validate(self):
        self.validate_hours()
        self.validate_rates_and_percentages()
        self.validate_child_ages()
        self.validate_foc_policy()

    def validate_hours(self):
        """Kiểm tra tính hợp lý của các mốc giờ quy chuẩn."""
        t_cin = get_time(self.standard_checkin_time)
        t_cout = get_time(self.standard_checkout_time)
        t_early1 = get_time(self.early_tier1_hour)
        t_early2 = get_time(self.early_tier2_hour)
        t_late1 = get_time(self.late_tier1_hour)
        t_late2 = get_time(self.late_tier2_hour)

        # 1. Giờ nhận phòng phải sau giờ trả phòng trong ngày
        if t_cin <= t_cout:
            frappe.throw(
                _("Giờ nhận phòng chuẩn ({0}) phải sau giờ trả phòng chuẩn ({1}) để đảm bảo thời gian dọn phòng (Housekeeping turn-around).").format(
                    self.standard_checkin_time, self.standard_checkout_time
                )
            )

        # 2. Thứ tự bậc nhận phòng sớm: Tier 1 < Tier 2 < Standard Check-in
        if not (t_early1 < t_early2 < t_cin):
            frappe.throw(
                _("Mốc giờ phụ thu nhận sớm không hợp lệ! Quy tắc bắt buộc: Mốc 1 ({0}) < Mốc 2 ({1}) < Giờ nhận phòng chuẩn ({2}).").format(
                    self.early_tier1_hour, self.early_tier2_hour, self.standard_checkin_time
                )
            )

        # 3. Thứ tự bậc trả phòng muộn: Standard Check-out < Tier 1 < Tier 2
        if not (t_cout < t_late1 < t_late2):
            frappe.throw(
                _("Mốc giờ phụ thu trả muộn không hợp lệ! Quy tắc bắt buộc: Giờ trả phòng chuẩn ({0}) < Mốc 1 ({1}) < Mốc 2 ({2}).").format(
                    self.standard_checkout_time, self.late_tier1_hour, self.late_tier2_hour
                )
            )

    def validate_rates_and_percentages(self):
        """Kiểm tra tỷ lệ % phụ thu và đơn giá dịch vụ."""
        pct_fields = [
            ("early_tier1_pct", _("Phụ thu nhận sớm Mốc 1")),
            ("early_tier2_pct", _("Phụ thu nhận sớm Mốc 2")),
            ("early_tier3_pct", _("Phụ thu nhận sớm Mốc 3")),
            ("late_tier1_pct", _("Phụ thu trả muộn Mốc 1")),
            ("late_tier2_pct", _("Phụ thu trả muộn Mốc 2")),
            ("late_tier3_pct", _("Phụ thu trả muộn Mốc 3")),
            ("weekend_surcharge_pct", _("Phụ thu cuối tuần")),
            ("holiday_surcharge_pct", _("Phụ thu ngày lễ tết")),
        ]

        for fld, label in pct_fields:
            val = flt(getattr(self, fld, 0))
            if val < 0 or val > 500:
                frappe.throw(_("Tỷ lệ {0} ({1}%) không hợp lệ. Giá trị phải nằm trong khoảng từ 0% đến 500%.").format(label, val))

        rate_fields = [
            ("child_surcharge_rate", _("Đơn giá phụ thu trẻ em")),
            ("extra_bed_rate", _("Đơn giá giường phụ (Extra Bed)"))
        ]

        for fld, label in rate_fields:
            val = flt(getattr(self, fld, 0))
            if val < 0:
                frappe.throw(_("{0} không được phép là số âm.").format(label))

    def validate_child_ages(self):
        """Kiểm tra tính nhất quán của độ tuổi trẻ em."""
        free_age = int(self.child_free_max_age or 0)
        surch_min = int(self.child_surcharge_min_age or 0)
        surch_max = int(self.child_surcharge_max_age or 0)

        if free_age < 0 or surch_min < 0 or surch_max < 0:
            frappe.throw(_("Độ tuổi trẻ em không được phép là số âm."))

        if free_age >= surch_max:
            frappe.throw(
                _("Độ tuổi miễn phí tối đa ({0} tuổi) phải nhỏ hơn độ tuổi phụ thu tối đa ({1} tuổi).").format(
                    free_age, surch_max
                )
            )

        if surch_min > surch_max:
            frappe.throw(
                _("Độ tuổi phụ thu tối thiểu ({0} tuổi) không thể lớn hơn độ tuổi tối đa ({1} tuổi).").format(
                    surch_min, surch_max
                )
            )

    def validate_foc_policy(self):
        """Kiểm tra chính sách tặng phòng FOC cho đoàn."""
        if self.enable_foc_policy:
            rpf = int(self.rooms_per_foc or 0)
            if rpf < 1:
                frappe.throw(_("Số phòng đoàn để tặng 1 phòng FOC phải lớn hơn hoặc bằng 1 (mặc định là 15 phòng)."))

