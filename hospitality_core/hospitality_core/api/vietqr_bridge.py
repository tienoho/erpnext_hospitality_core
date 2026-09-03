# -*- coding: utf-8 -*-
"""
Module Sinh Mã Thanh Toán VietQR Động Chuẩn NAPAS 247 / EMVCo
Tuân thủ 100% nguyên tắc ZERO HARDCODE - Đọc cấu hình từ Hospitality Accounting Settings.
Hỗ trợ cả thuật toán EMVCo TLV Offline và Cloud Image API fallback.
"""

import frappe
from frappe import _
from frappe.utils import flt, cstr
import urllib.parse


def crc16_ccitt(data_bytes: bytes) -> str:
    """
    Tính mã kiểm tra CRC16-CCITT (Polynomial 0x1021, Initial 0xFFFF)
    theo đúng quy chuẩn EMVCo QR Code Specification.
    """
    crc = 0xFFFF
    for b in data_bytes:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _format_tlv(tag: str, value: str) -> str:
    """Format Tag-Length-Value (TLV) string."""
    val_str = str(value)
    length = f"{len(val_str.encode('utf-8')):02d}"
    return f"{tag}{length}{val_str}"


def build_emvco_vietqr(bank_bin: str, account_number: str, amount: float = 0, description: str = "", account_name: str = "") -> str:
    """
    Tạo chuỗi ký tự VietQR chuẩn EMVCo NAPAS 247 hoàn toàn Offline.
    """
    # 1. Consumer Account Information (Tag 38)
    sub_00 = _format_tlv("00", "A000000727")  # NAPAS AID
    sub_bank = _format_tlv("00", bank_bin) + _format_tlv("01", account_number)
    sub_01 = _format_tlv("01", sub_bank)
    sub_02 = _format_tlv("02", "QRIBFTTA")     # Chuyển nhanh Napas 247
    tag_38 = _format_tlv("38", sub_00 + sub_01 + sub_02)

    # 2. Transaction Currency (Tag 53): 704 = VND
    tag_53 = _format_tlv("53", "704")

    # 3. Country Code (Tag 58): VN
    tag_58 = _format_tlv("58", "VN")

    # 4. Point of Initiation: 12 (Dynamic QR with amount) or 11 (Static QR)
    point_init = "12" if amount > 0 else "11"
    tag_00 = _format_tlv("00", "01")
    tag_01 = _format_tlv("01", point_init)

    qr_payload = tag_00 + tag_01 + tag_38 + tag_53

    # 5. Amount (Tag 54)
    if amount > 0:
        amt_str = f"{int(round(amount))}"
        qr_payload += _format_tlv("54", amt_str)

    qr_payload += tag_58

    # 6. Additional Data Field Template (Tag 62)
    if description:
        # Giới hạn nội dung không dấu để tương thích tốt với mọi App ngân hàng
        clean_desc = urllib.parse.quote_plus(description).replace("+", " ")[:25]
        sub_desc = _format_tlv("08", clean_desc)
        qr_payload += _format_tlv("62", sub_desc)

    # 7. CRC16 Checksum (Tag 63)
    raw_for_crc = (qr_payload + "6304").encode("utf-8")
    crc_code = crc16_ccitt(raw_for_crc)
    
    return qr_payload + "6304" + crc_code


@frappe.whitelist()
def generate_vietqr_payload(folio_name=None, amount=None, description=None):
    """
    API sinh dữ liệu VietQR cho Folio hoặc số tiền thanh toán bất kỳ.
    100% Đọc cấu hình từ Hospitality Accounting Settings (Không hardcode).
    """
    settings = frappe.get_cached_doc("Hospitality Accounting Settings")
    
    if not getattr(settings, "enable_vietqr", 1):
        frappe.throw(_("Tính năng thanh toán VietQR chưa được kích hoạt trong Hospitality Accounting Settings."))

    bank_bin = (getattr(settings, "vietqr_bank_id", None) or "").strip()
    account_number = (getattr(settings, "vietqr_account_number", None) or "").strip()
    account_name = (getattr(settings, "vietqr_account_name", None) or "").strip()
    template = (getattr(settings, "vietqr_template", None) or "").strip() or "compact2"
    prefix = (getattr(settings, "vietqr_content_prefix", None) or "").strip()

    # Fallback động từ Company mặc định của hệ thống nếu chưa cấu hình tên chủ tài khoản
    default_company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.defaults.get_user_default("Company")
    if not account_name and default_company:
        account_name = default_company.upper()

    if not prefix:
        if default_company:
            prefix = "".join(w[0] for w in default_company.split() if w).upper()[:6]
        else:
            prefix = "PAY"

    if not bank_bin:
        frappe.throw(_("Chưa cấu hình Mã BIN Ngân hàng nhận thanh toán trong Hospitality Accounting Settings."))

    if not account_number:
        frappe.throw(_("Chưa cấu hình Số Tài Khoản Thụ Hưởng trong Hospitality Accounting Settings."))

    if not account_name:
        frappe.throw(_("Chưa cấu hình Tên chủ tài khoản thụ hưởng trong Hospitality Accounting Settings."))

    pay_amount = flt(amount or 0)
    room_no = ""

    if folio_name:
        folio = frappe.get_doc("Guest Folio", folio_name)
        if pay_amount <= 0:
            pay_amount = flt(folio.outstanding_balance or 0)
        room_no = folio.room or ""
        if not description:
            description = f"{prefix} {room_no} {folio_name}".strip()

    if not description:
        description = f"{prefix} THANHTOAN".strip()

    # Sinh link ảnh VietQR Cloud (chuẩn NAPAS QuickLink)
    clean_desc_url = urllib.parse.quote(description)
    clean_name_url = urllib.parse.quote(account_name)
    vietqr_url = f"https://api.vietqr.io/image/{bank_bin}-{account_number}-{template}.jpg?amount={int(round(pay_amount))}&addInfo={clean_desc_url}&accountName={clean_name_url}"

    # Sinh chuỗi EMVCo TLV thuần (Offline)
    emvco_string = build_emvco_vietqr(
        bank_bin=bank_bin,
        account_number=account_number,
        amount=pay_amount,
        description=description,
        account_name=account_name
    )

    return {
        "success": True,
        "bank_bin": bank_bin,
        "account_number": account_number,
        "account_name": account_name,
        "amount": pay_amount,
        "formatted_amount": frappe.format(pay_amount, {"fieldtype": "Currency"}),
        "description": description,
        "vietqr_image_url": vietqr_url,
        "emvco_string": emvco_string,
        "folio": folio_name,
        "room": room_no
    }
