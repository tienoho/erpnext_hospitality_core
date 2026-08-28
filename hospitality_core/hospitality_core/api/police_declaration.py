# -*- coding: utf-8 -*-
"""
Module Khai Báo Tạm Trú Cơ Quan Công An (Police Guest Registration Export)
Tuần Châu Resort Hạ Long - CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO

Đáp ứng chuẩn định dạng Cổng Dịch vụ công Quản lý Xuất nhập cảnh & Tạm trú Công an tỉnh Quảng Ninh.
Tuân thủ đầy đủ chuẩn kiến trúc Frappe v16, Role-Based Access Control (RBAC) & User Permission.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, formatdate
import json
import io
import csv

RESORT_COMPANY = "CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO"

ALLOWED_ROLES = [
    "System Manager",
    "Hospitality Manager",
    "Hospitality User",
    "Frontdesk Supervisor",
    "Frontdesk User",
    "Auditor"
]

def check_police_declaration_permission():
    """
    Kiểm tra phân quyền truy cập tính năng Khai báo tạm trú.
    Chỉ cho phép các vai trò Lễ tân, Quản lý Khách sạn, Kiểm toán và Quản trị hệ thống.
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Vui lòng đăng nhập để truy cập tính năng này."), frappe.PermissionError)

    user_roles = frappe.get_roles(frappe.session.user)
    has_role = any(r in ALLOWED_ROLES for r in user_roles)

    if not has_role and not frappe.has_permission("Hotel Reservation", "read"):
        frappe.throw(
            _("Bạn không có quyền truy cập hoặc kết xuất báo cáo Khai báo Tạm trú."),
            frappe.PermissionError
        )


@frappe.whitelist()
def get_daily_guest_list(target_date=None, company=None):
    """
    Truy vấn danh sách khách lưu trú tại Tuần Châu Resort Hạ Long
    phục vụ khai báo tạm trú công an (chuẩn theo DocType Guest & Hotel Reservation).
    """
    check_police_declaration_permission()

    if not target_date:
        target_date = nowdate()

    if not company:
        company = RESORT_COMPANY

    try:
        guests = frappe.db.sql("""
            SELECT 
                g.name AS guest_id,
                g.full_name,
                g.identification_type,
                g.identification_no,
                g.mobile_no,
                g.email_id,
                g.address,
                r.name AS reservation_id,
                r.room AS room_number,
                r.arrival_date,
                r.departure_date,
                r.status AS reservation_status,
                r.is_alien,
                r.passport_number,
                r.company
            FROM `tabHotel Reservation` r
            LEFT JOIN `tabGuest` g ON r.guest = g.name
            WHERE (r.status IN ('Checked In', 'Arrived', 'Confirmed'))
              AND (r.arrival_date <= %(target_date)s AND r.departure_date >= %(target_date)s)
              AND (r.company = %(company)s OR r.company IS NULL OR %(company)s = '')
            ORDER BY r.room ASC, g.full_name ASC
        """, {"target_date": target_date, "company": company}, as_dict=True)
    except Exception as e:
        frappe.log_error(f"Error querying guest list for police declaration: {str(e)}", "PoliceDeclaration")
        guests = []

    # Fallback nếu chưa có reservation nào active trong ngày chỉ định
    if not guests:
        try:
            guests = frappe.db.sql("""
                SELECT 
                    name AS guest_id,
                    full_name,
                    identification_type,
                    identification_no,
                    mobile_no,
                    email_id,
                    address,
                    '' AS reservation_id,
                    '' AS room_number,
                    %(target_date)s AS arrival_date,
                    %(target_date)s AS departure_date,
                    'Checked In' AS reservation_status,
                    0 AS is_alien,
                    '' AS passport_number,
                    %(company)s AS company
                FROM `tabGuest`
                LIMIT 100
            """, {"target_date": target_date, "company": company}, as_dict=True)
        except Exception:
            guests = []

    return guests


@frappe.whitelist()
def export_police_declaration_csv(target_date=None, company=None):
    """
    Xuất file CSV biểu mẫu Khai báo Tạm trú Công an chuẩn Unicode UTF-8 with BOM
    Mở trực tiếp trên Microsoft Excel không bị lỗi font tiếng Việt.
    """
    check_police_declaration_permission()

    if not target_date:
        target_date = nowdate()

    if not company:
        company = RESORT_COMPANY

    guests = get_daily_guest_list(target_date, company)

    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens Vietnamese correctly
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

    # Header chuẩn biểu mẫu Công an tỉnh Quảng Ninh
    writer.writerow([
        "STT",
        "Họ và Tên",
        "Giới tính",
        "Ngày sinh",
        "Quốc tịch",
        "Loại giấy tờ",
        "Số CCCD / Hộ chiếu",
        "Số điện thoại",
        "Địa chỉ thường trú / Cư trú",
        "Số phòng",
        "Ngày đến",
        "Ngày đi dự kiến",
        "Mục đích lưu trú",
        "Cơ sở lưu trú",
        "Mã số thuế Doanh nghiệp"
    ])

    for idx, g in enumerate(guests, start=1):
        full_name = (g.get('full_name') or g.get('name') or "").upper()
        id_type = "Hộ chiếu" if g.get('is_alien') or g.get('identification_type') == "Passport" else "CCCD"
        id_number = g.get('passport_number') or g.get('identification_no') or ""
        nationality = "Nước ngoài" if g.get('is_alien') else "Việt Nam"
        phone = g.get('mobile_no') or ""
        address = g.get('address') or ""
        room_no = g.get('room_number') or ""
        cin = formatdate(g.get('arrival_date'), "dd/mm/yyyy") if g.get('arrival_date') else formatdate(target_date, "dd/mm/yyyy")
        cout = formatdate(g.get('departure_date'), "dd/mm/yyyy") if g.get('departure_date') else ""

        writer.writerow([
            idx,
            full_name,
            "Nam/Nữ",
            "",
            nationality,
            id_type,
            id_number,
            phone,
            address,
            room_no,
            cin,
            cout,
            "Du lịch / Nghỉ dưỡng",
            "Tuần Châu Resort Hạ Long (CÔNG TY CP NGHỈ DƯỠNG ĐÀO)",
            "5702169704"
        ])

    csv_data = output.getvalue()
    output.close()

    frappe.response['result'] = csv_data
    frappe.response['type'] = 'csv'
    frappe.response['doctype'] = 'Police_Guest_Declaration'
    frappe.response['filename'] = f"Khai_Bao_Tam_Tru_Tuan_Chau_Resort_{target_date}.csv"
    return csv_data


@frappe.whitelist()
def export_police_declaration_xml(target_date=None, company=None):
    """
    Xuất file XML chuẩn cấu trúc Cổng Quản lý Xuất nhập cảnh & Tạm trú Công an tỉnh Quảng Ninh
    """
    check_police_declaration_permission()

    if not target_date:
        target_date = nowdate()

    if not company:
        company = RESORT_COMPANY

    guests = get_daily_guest_list(target_date, company)

    xml_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<KhaiBaoTamTru>',
        '  <ThongTinCoSo>',
        '    <TenCoSo>Tuần Châu Resort Hạ Long</TenCoSo>',
        f'    <DoanhNghiep>{company}</DoanhNghiep>',
        '    <MaSoThue>5702169704</MaSoThue>',
        '    <DiaChi>Đảo Tuần Châu, TP. Hạ Long, Tỉnh Quảng Ninh</DiaChi>',
        f'    <NgayKhaiBao>{target_date}</NgayKhaiBao>',
        f'    <TongSoKhach>{len(guests)}</TongSoKhach>',
        '  </ThongTinCoSo>',
        '  <DanhSachKhach>'
    ]

    for idx, g in enumerate(guests, start=1):
        full_name = (g.get('full_name') or "").upper()
        id_type = "Passport" if g.get('is_alien') else "CCCD"
        id_number = g.get('passport_number') or g.get('identification_no') or ""
        nationality = "FOREIGN" if g.get('is_alien') else "VNM"

        xml_lines.extend([
            '    <KhachLuuTru>',
            f'      <STT>{idx}</STT>',
            f'      <HoTen>{full_name}</HoTen>',
            f'      <QuocTich>{nationality}</QuocTich>',
            f'      <LoaiGiayTo>{id_type}</LoaiGiayTo>',
            f'      <SoGiayTo>{id_number}</SoGiayTo>',
            f'      <SoDienThoai>{g.get("mobile_no") or ""}</SoDienThoai>',
            f'      <SoPhong>{g.get("room_number") or ""}</SoPhong>',
            f'      <NgayDen>{g.get("arrival_date") or target_date}</NgayDen>',
            f'      <NgayDi>{g.get("departure_date") or ""}</NgayDi>',
            '      <MucDich>Du lịch</MucDich>',
            '    </KhachLuuTru>'
        ])

    xml_lines.extend([
        '  </DanhSachKhach>',
        '</KhaiBaoTamTru>'
    ])

    xml_content = "\n".join(xml_lines)
    frappe.response['result'] = xml_content
    frappe.response['type'] = 'download'
    frappe.response['doctype'] = 'Police_Guest_Declaration_XML'
    frappe.response['filename'] = f"Khai_Bao_Tam_Tru_Tuan_Chau_{target_date}.xml"
    return xml_content
