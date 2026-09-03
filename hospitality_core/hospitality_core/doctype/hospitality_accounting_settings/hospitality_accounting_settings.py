# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document
import re

class HospitalityAccountingSettings(Document):
    def validate(self):
        self.validate_vietqr_settings()
        self.validate_pos_einvoice_settings()

    def validate_vietqr_settings(self):
        """Kiểm tra tài khoản thụ hưởng VietQR."""
        if self.enable_vietqr:
            bank_id = (self.vietqr_bank_id or "").strip()
            acc_no = (self.vietqr_account_number or "").strip()
            acc_name = (self.vietqr_account_name or "").strip()

            if not bank_id:
                frappe.throw(_("Vui lòng chọn hoặc nhập Mã BIN Ngân hàng nhận thanh toán VietQR (ví dụ: 970415 cho VietinBank)."))

            if not re.match(r"^\d{6}$", bank_id):
                frappe.throw(_("Mã BIN Ngân hàng ({0}) không hợp lệ. Mã BIN chuẩn Napas gồm đúng 6 chữ số.").format(bank_id))

            if not acc_no:
                frappe.throw(_("Vui lòng nhập Số tài khoản ngân hàng nhận thanh toán VietQR."))

            # Số tài khoản chỉ được chứa chữ cái và số, độ dài 6-24 ký tự
            if not re.match(r"^[A-Za-z0-9]{6,24}$", acc_no):
                frappe.throw(_("Số tài khoản ngân hàng ({0}) không hợp lệ. Phải từ 6 đến 24 ký tự, không chứa khoảng trắng hoặc ký tự đặc biệt.").format(acc_no))

            if not acc_name:
                frappe.throw(_("Vui lòng nhập Tên chủ tài khoản thụ hưởng VietQR (ví dụ: CONG TY CP NGHI DUONG DAO)."))

            self.vietqr_bank_id = bank_id
            self.vietqr_account_number = acc_no
            self.vietqr_account_name = acc_name.upper()

    def validate_pos_einvoice_settings(self):
        """Kiểm tra cấu hình Hóa đơn điện tử máy tính tiền."""
        if self.enable_pos_cash_register:
            tmpl = (self.pos_invoice_template or "").strip()
            if tmpl and len(tmpl) > 20:
                frappe.throw(_("Ký hiệu mẫu hóa đơn máy tính tiền ({0}) quá dài (tối đa 20 ký tự).").format(tmpl))

