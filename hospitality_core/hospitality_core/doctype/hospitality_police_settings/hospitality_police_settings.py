# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document
import re

class HospitalityPoliceSettings(Document):
    def validate(self):
        self.validate_establishment_info()
        self.validate_tax_id()
        self.validate_portal_url()

    def validate_establishment_info(self):
        """Kiểm tra tên và mã cơ sở lưu trú."""
        if not (self.establishment_name or "").strip():
            frappe.throw(_("Tên cơ sở lưu trú không được phép để trống."))

        code = (self.establishment_code or "").strip().upper()
        if not code:
            frappe.throw(_("Mã cơ sở lưu trú do Công an cấp không được để trống (ví dụ: TCG-QN-01)."))

        # Mã cơ sở không được chứa dấu cách hoặc ký tự đặc biệt nguy hiểm
        if not re.match(r"^[A-Z0-9_\-]+$", code):
            frappe.throw(_("Mã cơ sở lưu trú ({0}) chỉ được chứa chữ cái in hoa, chữ số, dấu gạch nối (-) hoặc gạch dưới (_).").format(code))

        self.establishment_code = code

    def validate_tax_id(self):
        """Kiểm tra tính hợp lệ của Mã số thuế doanh nghiệp Việt Nam."""
        mst = (self.tax_id or "").strip()
        if not mst:
            frappe.throw(_("Mã số thuế doanh nghiệp không được để trống."))

        # MST chuẩn: 10 số (5702169704) hoặc 13 số có gạch nối (5702169704-001)
        cleaned_mst = mst.replace(" ", "")
        if not re.match(r"^\d{10}(-\d{3})?$", cleaned_mst):
            frappe.throw(
                _("Mã số thuế ({0}) không đúng định dạng MST Việt Nam. Mã hợp lệ phải gồm 10 chữ số (hoặc 13 chữ số có dấu gạch ngang phân cách chi nhánh).").format(
                    mst
                )
            )
        self.tax_id = cleaned_mst

    def validate_portal_url(self):
        """Kiểm tra đường dẫn Cổng dịch vụ công xuất nhập cảnh."""
        url = (self.immigration_portal_url or "").strip()
        if url:
            if not (url.startswith("http://") or url.startswith("https://")):
                frappe.throw(_("Đường dẫn Cổng XNC ({0}) phải bắt đầu bằng http:// hoặc https://").format(url))
            self.immigration_portal_url = url

