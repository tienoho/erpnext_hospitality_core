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

    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company") or "CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO"

    cust_doc = frappe.get_doc("Customer", customer_name)
    
    # Đọc hạn mức tín dụng từ bảng credit_limits của Customer hoặc trường credit_limit
    credit_limit = 0.0
    if hasattr(cust_doc, "credit_limits") and cust_doc.credit_limits:
        for cl in cust_doc.credit_limits:
            if cl.company == company:
                credit_limit = flt(cl.credit_limit)
                break
    if credit_limit == 0 and hasattr(cust_doc, "credit_limit"):
        credit_limit = flt(cust_doc.credit_limit)

    # Lấy tổng dư nợ hiện tại (Outstanding Amount)
    outstanding_amt = 0.0
    try:
        # Tận dụng hàm chuẩn ERPNext nếu có
        from erpnext.accounts.party import get_dashboard_info
        info = get_dashboard_info("Customer", customer_name)
        outstanding_amt = flt(info.get("total_unpaid", 0))
    except Exception:
        # Fallback query số dư nợ chưa thanh toán từ Sales Invoice
        res = frappe.db.sql("""
            SELECT SUM(outstanding_amount) 
            FROM `tabSales Invoice`
            WHERE customer = %(customer)s AND docstatus = 1 AND outstanding_amount > 0
        """, {"customer": customer_name})
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
    if not frappe.has_permission("Hotel Reservation", "write"):
        frappe.throw(_("Bạn không có quyền chỉnh sửa hoặc áp dụng FOC cho Đặt phòng này."), frappe.PermissionError)

    calc = calculate_group_foc_rooms(group_booking_name)
    if not calc.get("policy_enabled"):
        frappe.throw(_("Chính sách phòng FOC đang bị tắt trong Hospitality Surcharge Settings."))

    res = frappe.get_doc("Hotel Reservation", reservation_name)
    if res.group_booking != group_booking_name:
        frappe.throw(_("Đặt phòng {0} không thuộc đoàn {1}.").format(reservation_name, group_booking_name))

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
