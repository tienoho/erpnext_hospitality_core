# -*- coding: utf-8 -*-
"""
Module Quét & Nhận Diện Giấy Tờ Tùy Thân (CCCD / Hộ Chiếu)
Tuần Châu Resort Hạ Long - CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO

Hỗ trợ Lễ tân quét/chụp ảnh giấy tờ tùy thân của khách lưu trú:
1. Bóc tách số thẻ CCCD (12 chữ số), Họ và tên, Ngày sinh, Giới tính, Quê quán, Địa chỉ.
2. Bóc tách vùng đọc máy hộ chiếu MRZ (Machine Readable Zone - 2 dòng chuẩn ICAO 9303).
3. Tự động trả về JSON để điền tự động vào Form Đặt phòng (Hotel Reservation) hoặc Hồ sơ Khách (Guest).
Tuân thủ đầy đủ chuẩn kiến trúc Frappe v16 và phân quyền RBAC.
"""

try:
    import frappe
    from frappe import _
except ImportError:
    frappe = None
    _ = lambda x: x

import re
import json

ALLOWED_ROLES = [
    "System Manager",
    "Hospitality Manager",
    "Hospitality User",
    "Frontdesk Supervisor",
    "Frontdesk User"
]

def check_scanner_permission():
    if frappe and hasattr(frappe, 'session') and frappe.session.user:
        if frappe.session.user == "Guest":
            frappe.throw(_("Vui lòng đăng nhập để sử dụng tính năng quét giấy tờ tùy thân."), frappe.PermissionError)
        
        user_roles = frappe.get_roles(frappe.session.user)
        has_role = any(r in ALLOWED_ROLES for r in user_roles)
        if not has_role and not frappe.has_permission("Guest", "write"):
            frappe.throw(_("Bạn không có quyền sử dụng tính năng quét giấy tờ tùy thân."), frappe.PermissionError)

def whitelist_decorator(func):
    if frappe and hasattr(frappe, 'whitelist'):
        return frappe.whitelist()(func)
    return func

@whitelist_decorator
def parse_id_document(raw_text=None, mrz_lines=None, image_data=None):
    """
    Bóc tách thông tin từ chuỗi OCR hoặc mã vạch / QR Code / MRZ của CCCD & Hộ chiếu.
    """
    check_scanner_permission()

    result = {
        "success": False,
        "document_type": "Unknown",
        "full_name": "",
        "id_number": "",
        "date_of_birth": "",
        "gender": "Nam",
        "nationality": "Việt Nam",
        "address": "",
        "is_alien": 0,
        "message": ""
    }

    if not raw_text and not mrz_lines:
        return {"success": False, "message": "Không có dữ liệu văn bản hoặc ảnh để nhận diện."}

    text = (raw_text or "").strip()

    # 1. Kiểm tra định dạng MRZ của Hộ chiếu quốc tế (2 dòng x 44 ký tự bắt đầu bằng P<)
    if mrz_lines or "P<" in text:
        mrz_text = mrz_lines if mrz_lines else text
        lines = [line.strip() for line in mrz_text.split('\n') if line.strip()]
        for idx, line in enumerate(lines):
            if line.startswith("P<") and len(lines) > idx + 1:
                line1 = line
                line2 = lines[idx + 1]
                
                # Parse Line 1: P<COUNTRY<SURNAME<<GIVEN_NAMES...
                match_country = line1[2:5]
                names_part = line1[5:].replace('<', ' ').strip()
                
                # Parse Line 2: PASSPORT_NO + NATIONALITY + DOB + EXPIRY
                passport_no = line2[0:9].replace('<', '').strip()
                nat = line2[10:13]
                dob_raw = line2[13:19] # YYMMDD
                gender_char = line2[20] # M/F

                result["document_type"] = "Passport"
                result["full_name"] = names_part
                result["id_number"] = passport_no
                result["nationality"] = nat if nat != "VNM" else "Việt Nam"
                result["is_alien"] = 1 if nat != "VNM" else 0
                result["gender"] = "Nữ" if gender_char == 'F' else "Nam"
                if len(dob_raw) == 6:
                    year_prefix = "19" if int(dob_raw[:2]) > 30 else "20"
                    result["date_of_birth"] = f"{year_prefix}{dob_raw[:2]}-{dob_raw[2:4]}-{dob_raw[4:6]}"
                result["success"] = True
                result["message"] = "Nhận diện Hộ chiếu quốc tế thành công qua mã MRZ."
                return result

    # 2. Kiểm tra định dạng Căn cước công dân Việt Nam (CCCD 12 số)
    cccd_match = re.search(r'\b(0\d{11})\b', text)
    if cccd_match:
        result["document_type"] = "CCCD"
        result["id_number"] = cccd_match.group(1)
        result["nationality"] = "Việt Nam"
        result["is_alien"] = 0

        # Trích xuất Họ và tên (không lấy xuống dòng)
        name_match = re.search(r'(?:Họ và tên|Full name|Họ tên)[:\s]*([^\n\r\t]+)', text, re.IGNORECASE)
        if name_match:
            cand_name = name_match.group(1).strip()
            cand_name = re.sub(r'[\/\:\-\.]', '', cand_name).strip()
            result["full_name"] = cand_name
        else:
            upper_lines = [l.strip() for l in text.split('\n') if l.strip().isupper() and len(l.strip().split()) >= 2]
            if upper_lines:
                result["full_name"] = upper_lines[0]

        # Trích xuất Ngày sinh (DD/MM/YYYY)
        dob_match = re.search(r'(?:Ngày sinh|Date of birth|Sinh ngày)[:\s]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})', text, re.IGNORECASE)
        if dob_match:
            dob_str = dob_match.group(1).replace('.', '/').replace('-', '/')
            parts = dob_str.split('/')
            if len(parts) == 3:
                result["date_of_birth"] = f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"

        # Trích xuất Giới tính
        if re.search(r'\b(Nữ|Female|F)\b', text, re.IGNORECASE):
            result["gender"] = "Nữ"
        else:
            result["gender"] = "Nam"

        # Trích xuất Địa chỉ thường trú
        addr_match = re.search(r'(?:Nơi thường trú|Nơi cư trú|Address)[:\s]*([^\n\r]+)', text, re.IGNORECASE)
        if addr_match:
            result["address"] = addr_match.group(1).strip()

        result["success"] = True
        result["message"] = "Nhận diện Căn cước công dân (CCCD) thành công."
        return result

    return {
        "success": False,
        "message": "Không tìm thấy số định danh CCCD hoặc Hộ chiếu hợp lệ trong văn bản."
    }
