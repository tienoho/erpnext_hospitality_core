# -*- coding: utf-8 -*-
"""
Module Quản Trị Công Nợ Đại Lý Lữ Hành (City Ledger) & Chính Sách Phòng FOC
Tuân thủ 100% nguyên tắc ZERO HARDCODE:
- Đọc hạn mức tín dụng động từ Customer (ERPNext Core).
- Đọc tỷ lệ phòng FOC động từ Hospitality Surcharge Settings.
"""

import frappe
from frappe import _
from frappe.utils import flt
import math


def _get_foc_rules():
    """Đọc cấu hình tỷ lệ phòng FOC từ Hospitality Surcharge Settings."""
    try:
        settings = frappe.get_cached_doc("Hospitality Surcharge Settings")
    except Exception:
        settings = None

    return {
        "enable_foc_policy": bool(getattr(settings, "enable_foc_policy", 1)),
        "rooms_per_foc": int(getattr(settings, "rooms_per_foc", 15) or 15)
    }


@frappe.whitelist()
def get_agent_credit_status(customer_name, company=None):
    """
    Kiểm tra hạn mức công nợ và số dư nợ thực tế của Đại lý lữ hành.
    Tái sử dụng các trường và hàm tính toán nợ chuẩn của ERPNext.
    Trả về trạng thái 3 màu: GREEN (<80%), YELLOW (80-100%), RED (>100%).
    """
    if not customer_name:
        return {"status": "NO_CUSTOMER", "has_limit": False}

    # TRƯỚC ĐÂY: không hề kiểm tra quyền — bất kỳ user đã đăng nhập nào cũng
    # xem được hạn mức tín dụng/số dư nợ/tỷ lệ sử dụng của BẤT KỲ đại lý/công
    # ty nào chỉ cần biết tên Customer.
    if not frappe.has_permission("Customer", "read", doc=customer_name):
        frappe.throw(_("Not permitted to view credit status for {0}.").format(customer_name), frappe.PermissionError)

    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company") or "CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO"

    cust_doc = frappe.get_doc("Customer", customer_name)
    
    # Đọc hạn mức tín dụng từ bảng credit_limits của Customer hoặc trường credit_limit
    credit_limit = 0.0
    company_limit_found = False
    if hasattr(cust_doc, "credit_limits") and cust_doc.credit_limits:
        for cl in cust_doc.credit_limits:
            if cl.company == company:
                credit_limit = flt(cl.credit_limit)
                company_limit_found = True
                break
    if not company_limit_found and hasattr(cust_doc, "credit_limit"):
        credit_limit = flt(cust_doc.credit_limit)

    # Lấy tổng dư nợ hiện tại (Outstanding Amount)
    outstanding_amt = 0.0
    try:
        # Tận dụng hàm chuẩn ERPNext nếu có — TRƯỚC ĐÂY: get_dashboard_info()
        # thực ra trả về 1 DANH SÁCH (company_wise_info, mỗi phần tử là 1
        # dict riêng theo từng company), KHÔNG PHẢI 1 dict như code cũ giả
        # định — gọi .get() trên list luôn ném AttributeError, bị except bên
        # dưới nuốt ÂM THẦM, khiến nhánh "tận dụng hàm chuẩn ERPNext" không
        # bao giờ thực sự chạy được (dead code, luôn rơi về fallback). Đã
        # sửa duyệt đúng danh sách, lấy đúng phần tử khớp company.
        from erpnext.accounts.party import get_dashboard_info
        info_list = get_dashboard_info("Customer", customer_name) or []
        matched = next((row for row in info_list if row.get("company") == company), None)
        if matched is None:
            raise ValueError("Không có dữ liệu dashboard cho company này")
        outstanding_amt = flt(matched.get("total_unpaid", 0))
    except Exception:
        # Fallback query số dư nợ chưa thanh toán từ Sales Invoice — TRƯỚC
        # ĐÂY không lọc theo company, cộng dồn dư nợ TOÀN BỘ pháp nhân của
        # khách hàng rồi so với hạn mức CHỈ RIÊNG 1 company (credit_limit ở
        # trên đã lọc theo company) — sai lệch nếu khách hàng có giao dịch
        # với nhiều pháp nhân trong tập đoàn.
        res = frappe.db.sql("""
            SELECT SUM(outstanding_amount)
            FROM `tabSales Invoice`
            WHERE customer = %(customer)s AND company = %(company)s AND docstatus = 1 AND outstanding_amount > 0
        """, {"customer": customer_name, "company": company})
        outstanding_amt = flt(res[0][0]) if res and res[0][0] else 0.0

    available_credit = credit_limit - outstanding_amt if credit_limit > 0 else 0
    usage_pct = (outstanding_amt / credit_limit * 100.0) if credit_limit > 0 else 0.0

    status_level = "GREEN"
    status_label = _("An toàn")
    if credit_limit > 0:
        if usage_pct > 100.0 or available_credit < 0:
            status_level = "RED"
            status_label = _("Vượt trần tín dụng (Khóa đặt phòng)")
        elif usage_pct >= 80.0:
            status_level = "YELLOW"
            status_label = _("Cảnh báo hạn mức (> 80%)")

    return {
        "customer": customer_name,
        "customer_name": cust_doc.customer_name,
        "has_credit_limit": credit_limit > 0,
        "credit_limit": credit_limit,
        "formatted_credit_limit": frappe.format(credit_limit, {"fieldtype": "Currency"}),
        "outstanding_amount": outstanding_amt,
        "formatted_outstanding": frappe.format(outstanding_amt, {"fieldtype": "Currency"}),
        "available_credit": available_credit,
        "formatted_available": frappe.format(available_credit, {"fieldtype": "Currency"}),
        "usage_pct": round(usage_pct, 1),
        "status_level": status_level,
        "status_label": status_label
    }


@frappe.whitelist()
def calculate_group_foc_rooms(group_booking_name):
    """
    Tính toán số phòng FOC tặng Hướng dẫn viên cho đoàn lữ hành.
    Công thức: Số phòng FOC = floor(Tổng số phòng trả tiền / rooms_per_foc).
    """
    foc_conf = _get_foc_rules()
    if not foc_conf["enable_foc_policy"]:
        return {"policy_enabled": False, "foc_rooms_eligible": 0}

    # Đếm tổng số phòng của đoàn không bị hủy
    reservations = frappe.get_all("Hotel Reservation",
        filters={"group_booking": group_booking_name, "status": ["!=", "Cancelled"]},
        fields=["name", "room", "is_complimentary"]
    )

    total_rooms = len(reservations)
    current_foc_rooms = [r for r in reservations if r.is_complimentary]

    rooms_per_foc = foc_conf["rooms_per_foc"]
    foc_eligible = math.floor(total_rooms / rooms_per_foc)

    return {
        "policy_enabled": True,
        "total_rooms": total_rooms,
        "rooms_per_foc": rooms_per_foc,
        "foc_eligible": foc_eligible,
        "current_foc_count": len(current_foc_rooms),
        "current_foc_reservations": [r.name for r in current_foc_rooms],
        "remaining_foc_quota": max(0, foc_eligible - len(current_foc_rooms))
    }


@frappe.whitelist()
def apply_foc_to_reservation(group_booking_name, reservation_name):
    """
    Áp dụng chính sách phòng FOC (Miễn phí) cho phòng của Hướng dẫn viên.
    """
    # Reuse the same supervisor-level role check as the other privileged folio
    # actions (Split/Merge Folio, Room Move) instead of the generic doctype
    # write-permission check, which any ordinary reservation-editing role passes.
    from hospitality_core.hospitality_core.api.folio_operations import _check_supervisor
    _check_supervisor()

    calc = calculate_group_foc_rooms(group_booking_name)
    if not calc.get("policy_enabled"):
        frappe.throw(_("Chính sách phòng FOC đang bị tắt trong Hospitality Surcharge Settings."))

    res = frappe.get_doc("Hotel Reservation", reservation_name)
    if res.group_booking != group_booking_name:
        frappe.throw(_("Đặt phòng {0} không thuộc đoàn {1}.").format(reservation_name, group_booking_name))

    if not res.is_complimentary and calc.get("remaining_foc_quota", 0) <= 0:
        frappe.throw(_("Đã sử dụng hết hạn mức phòng FOC ({0} phòng/đoàn) cho đoàn {1}.").format(
            calc.get("foc_eligible", 0), group_booking_name
        ))

    res.is_complimentary = 1
    res.discount_type = "Percentage"
    res.discount_value = 100.0
    res.add_comment("Info", _("Áp dụng phòng FOC cho Hướng dẫn viên theo chính sách đoàn ({0}:1).").format(calc["rooms_per_foc"]))
    res.save(ignore_permissions=True)

    return {
        "success": True,
        "reservation": reservation_name,
        "message": _("Đã gắn cờ FOC (Miễn phí 100%) cho đặt phòng {0}.").format(reservation_name)
    }
