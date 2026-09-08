# -*- coding: utf-8 -*-
"""
Module Động Tính Phụ Thu Khách Sạn (Dynamic Surcharges Engine)
Tuân thủ 100% nguyên tắc ZERO HARDCODE - Đọc cấu hình từ Hospitality Surcharge Settings.
Tái sử dụng 100% hàm định giá night_audit.get_rate() và quy trình hạch toán Folio Transaction.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, get_time, nowdate, getdate
from datetime import datetime, time


def _get_surcharge_settings():
    """
    Đọc cấu hình động từ Hospitality Surcharge Settings.
    Nếu chưa có, trả về fallback an toàn.
    """
    try:
        settings = frappe.get_cached_doc("Hospitality Surcharge Settings")
    except Exception:
        settings = None

    return {
        "standard_checkin_time": get_time(getattr(settings, "standard_checkin_time", None) or "14:00:00"),
        "standard_checkout_time": get_time(getattr(settings, "standard_checkout_time", None) or "12:00:00"),
        "early_tier1_hour": get_time(getattr(settings, "early_tier1_hour", None) or "06:00:00"),
        "early_tier1_pct": flt(getattr(settings, "early_tier1_pct", 100)),
        "early_tier2_hour": get_time(getattr(settings, "early_tier2_hour", None) or "09:00:00"),
        "early_tier2_pct": flt(getattr(settings, "early_tier2_pct", 50)),
        "early_tier3_pct": flt(getattr(settings, "early_tier3_pct", 30)),
        "late_tier1_hour": get_time(getattr(settings, "late_tier1_hour", None) or "15:00:00"),
        "late_tier1_pct": flt(getattr(settings, "late_tier1_pct", 30)),
        "late_tier2_hour": get_time(getattr(settings, "late_tier2_hour", None) or "18:00:00"),
        "late_tier2_pct": flt(getattr(settings, "late_tier2_pct", 50)),
        "late_tier3_pct": flt(getattr(settings, "late_tier3_pct", 100)),
        "child_free_max_age": int(getattr(settings, "child_free_max_age", 5)),
        "child_surcharge_rate": flt(getattr(settings, "child_surcharge_rate", 200000)),
        "extra_bed_rate": flt(getattr(settings, "extra_bed_rate", 500000)),
        "enable_foc_policy": bool(getattr(settings, "enable_foc_policy", 1)),
        "rooms_per_foc": int(getattr(settings, "rooms_per_foc", 15) or 15),
        "enable_weekend_surcharge": bool(getattr(settings, "enable_weekend_surcharge", 0)),
        "weekend_surcharge_pct": flt(getattr(settings, "weekend_surcharge_pct", 0)),
        "enable_holiday_surcharge": bool(getattr(settings, "enable_holiday_surcharge", 0)),
        "holiday_surcharge_pct": flt(getattr(settings, "holiday_surcharge_pct", 0))
    }


@frappe.whitelist()
def get_surcharge_rules():
    """Trả về toàn bộ quy tắc phụ thu cấu hình cho Frontend."""
    conf = _get_surcharge_settings()
    return {
        k: str(v) if isinstance(v, time) else v
        for k, v in conf.items()
    }


def _get_base_room_rate(res, target_date=None):
    """Phụ thu tính trên giá trước LOS của ngày phát sinh, theo căn cứ giá đã lưu."""
    from hospitality_core.hospitality_core.api.rate_plan import quote_reservation
    return quote_reservation(res, target_date or nowdate(), apply_los=False, apply_manual=False)['base_rate']


@frappe.whitelist()
def calculate_checkin_surcharge(reservation_name, checkin_time=None):
    """
    Tính phụ thu nhận phòng sớm (Early Check-in) theo cấu hình động.
    """
    res = frappe.get_doc("Hotel Reservation", reservation_name)
    res.check_permission("read")
    conf = _get_surcharge_settings()

    if not checkin_time:
        cur_dt = now_datetime()
        t = cur_dt.time()
    else:
        if isinstance(checkin_time, str):
            t = datetime.strptime(checkin_time[:8], "%H:%M:%S").time()
        else:
            t = checkin_time

    std_checkin = conf["standard_checkin_time"]

    # Nếu đến sau hoặc đúng giờ check-in chuẩn -> Không phụ thu
    if t >= std_checkin:
        return {"applicable": False, "pct": 0, "amount": 0, "reason": _("Nhận phòng đúng giờ chuẩn.")}

    base_rate = _get_base_room_rate(res)
    tier_pct = 0
    tier_label = ""

    if t < conf["early_tier1_hour"]:
        tier_pct = conf["early_tier1_pct"]
        tier_label = f"Trước {conf['early_tier1_hour'].strftime('%H:%M')} (100% tiền phòng)"
    elif t < conf["early_tier2_hour"]:
        tier_pct = conf["early_tier2_pct"]
        tier_label = f"{conf['early_tier1_hour'].strftime('%H:%M')} - {conf['early_tier2_hour'].strftime('%H:%M')} (50% tiền phòng)"
    else:
        tier_pct = conf["early_tier3_pct"]
        tier_label = f"{conf['early_tier2_hour'].strftime('%H:%M')} - {std_checkin.strftime('%H:%M')} (30% tiền phòng)"

    fee = flt(base_rate * (tier_pct / 100.0))

    return {
        "applicable": True,
        "checkin_time": t.strftime("%H:%M:%S"),
        "base_rate": base_rate,
        "pct": tier_pct,
        "amount": fee,
        "formatted_amount": frappe.format(fee, {"fieldtype": "Currency"}),
        "tier_label": tier_label,
        "surcharge_type": "Early Check-in",
        "description": f"Phụ thu nhận phòng sớm ({t.strftime('%H:%M')} - {tier_pct}%)"
    }


@frappe.whitelist()
def calculate_checkout_surcharge(reservation_name, checkout_time=None):
    """
    Tính phụ thu trả phòng muộn (Late Check-out) theo cấu hình động.
    """
    res = frappe.get_doc("Hotel Reservation", reservation_name)
    res.check_permission("read")
    conf = _get_surcharge_settings()

    if not checkout_time:
        cur_dt = now_datetime()
        t = cur_dt.time()
    else:
        if isinstance(checkout_time, str):
            t = datetime.strptime(checkout_time[:8], "%H:%M:%S").time()
        else:
            t = checkout_time

    std_checkout = conf["standard_checkout_time"]

    # Nếu trả trước hoặc đúng giờ check-out chuẩn -> Không phụ thu
    if t <= std_checkout:
        return {"applicable": False, "pct": 0, "amount": 0, "reason": _("Trả phòng đúng giờ chuẩn.")}

    base_rate = _get_base_room_rate(res)
    tier_pct = 0
    tier_label = ""

    if t <= conf["late_tier1_hour"]:
        tier_pct = conf["late_tier1_pct"]
        tier_label = f"{std_checkout.strftime('%H:%M')} - {conf['late_tier1_hour'].strftime('%H:%M')} (30% tiền phòng)"
    elif t <= conf["late_tier2_hour"]:
        tier_pct = conf["late_tier2_pct"]
        tier_label = f"{conf['late_tier1_hour'].strftime('%H:%M')} - {conf['late_tier2_hour'].strftime('%H:%M')} (50% tiền phòng)"
    else:
        tier_pct = conf["late_tier3_pct"]
        tier_label = f"Sau {conf['late_tier2_hour'].strftime('%H:%M')} (100% tiền phòng)"

    fee = flt(base_rate * (tier_pct / 100.0))

    return {
        "applicable": True,
        "checkout_time": t.strftime("%H:%M:%S"),
        "base_rate": base_rate,
        "pct": tier_pct,
        "amount": fee,
        "formatted_amount": frappe.format(fee, {"fieldtype": "Currency"}),
        "tier_label": tier_label,
        "surcharge_type": "Late Check-out",
        "description": f"Phụ thu trả phòng muộn ({t.strftime('%H:%M')} - {tier_pct}%)"
    }


@frappe.whitelist()
def apply_surcharge_to_folio(reservation_name, surcharge_type, amount=None, description=None):
    """
    Ghi nhận phụ thu vào Guest Folio tương ứng thông qua Folio Transaction.
    Số tiền luôn được tính lại ở server theo thời điểm áp dụng thực tế — tham số
    `amount` do client gửi (nếu có) chỉ được dùng để đối chiếu cảnh báo, không
    được tin tưởng trực tiếp, để tránh phụ thu bị lệch tier hoặc bị giả mạo.
    """
    res = frappe.get_doc("Hotel Reservation", reservation_name)
    # TRƯỚC ĐÂY: không hề kiểm tra quyền — hàm này GHI TIỀN THẬT vào Folio bất
    # kỳ đặt phòng nào, bất kỳ user đã đăng nhập nào cũng gọi được (dù insert
    # dùng ignore_permissions=True bên dưới, hàm không hề tự kiểm tra trước).
    res.check_permission("write")
    if not res.folio:
        frappe.throw(_("Đặt phòng này chưa có Guest Folio."))

    if surcharge_type == "Early Check-in":
        calc = calculate_checkin_surcharge(reservation_name)
    else:
        calc = calculate_checkout_surcharge(reservation_name)

    if not calc.get("applicable"):
        frappe.throw(calc.get("reason") or _("Không áp dụng phụ thu tại thời điểm hiện tại."))

    fee = flt(calc.get("amount"))
    if fee <= 0:
        return {"success": False, "message": _("Số tiền phụ thu phải lớn hơn 0.")}

    from hospitality_core.hospitality_core.api.folio import sync_folio_balance

    # Item code đại diện cho phụ thu
    item_code = "SURCHARGE-EARLY" if surcharge_type == "Early Check-in" else "SURCHARGE-LATE"
    if not description:
        description = f"Phụ thu {surcharge_type} phòng {res.room}"

    # Chốt chặn trùng lặp: chỉ mirror_to_company_folio()/mirror_to_group_folio()
    # trong folio.py có kiểm tra "đã ghi chưa", còn hàm này thì không — nếu
    # frm.call('check_in_guest') phía client bị lỗi mạng SAU KHI
    # apply_surcharge_to_folio() đã thành công, người dùng gọi lại toàn bộ quy
    # trình (dialog phụ thu hiện lại) sẽ ghi phụ thu này một lần nữa.
    existing = frappe.db.exists("Folio Transaction", {
        "parent": res.folio,
        "item": item_code,
        "is_void": 0
    })
    if existing:
        return {
            "success": True,
            "folio": res.folio,
            "transaction": existing,
            "amount": fee,
            "message": _("Phụ thu {0} đã được ghi nhận trước đó vào Folio {1} (giao dịch {2}), không tạo lại.").format(
                surcharge_type, res.folio, existing
            )
        }

    txn = frappe.get_doc({
        "doctype": "Folio Transaction",
        "parent": res.folio,
        "parenttype": "Guest Folio",
        "parentfield": "transactions",
        "posting_date": nowdate(),
        "item": item_code,
        "description": description,
        "qty": 1,
        "amount": fee,
        "bill_to": "Guest",
        "is_void": 0
    })
    # flags.hospitality_service=True — TRƯỚC ĐÂY thiếu: property_scope.py's
    # validate_document() bắt buộc 1 trong 3 flag nguồn gốc
    # (hospitality_service/from_rate_plan/from_folio_mirror) cho MỌI Folio
    # Transaction của folio đã cutover Property v2, nếu không sẽ throw. Thiếu
    # flag này nghĩa là TOÀN BỘ tính năng phụ thu check-in sớm/check-out muộn
    # sẽ ngừng hoạt động hoàn toàn (throw ngay) ngay khi property đầu tiên
    # kích hoạt Property v2 — không phải lỗi tính sai, mà là TÍNH NĂNG CHẾT
    # HẲN.
    txn.flags.hospitality_service = True
    txn.insert(ignore_permissions=True)

    sync_folio_balance(frappe.get_doc("Guest Folio", res.folio))

    return {
        "success": True,
        "folio": res.folio,
        "transaction": txn.name,
        "amount": fee,
        "message": _("Đã ghi nhận phụ thu {0} vào Folio {1}.").format(frappe.format(fee, {"fieldtype": "Currency"}), res.folio)
    }


@frappe.whitelist()
def check_holiday_or_weekend(target_date=None):
    """
    Tự động kiểm tra xem ngày chỉ định có rơi vào Cuối tuần (Thứ 6, Thứ 7)
    hoặc Ngày Lễ Tết (ERPNext Holiday List) để áp dụng phụ thu cao điểm.
    """
    if not target_date:
        target_date = nowdate()

    d = getdate(target_date)
    conf = _get_surcharge_settings()

    # 1. Kiểm tra cuối tuần (Thứ 6 = 4, Thứ 7 = 5 theo weekday() chuẩn Python)
    weekday = d.weekday()
    is_weekend = (weekday in (4, 5))

    # 2. Kiểm tra ngày Lễ Tết trong danh mục Holiday List của ERPNext
    is_holiday = False
    holiday_desc = ""
    try:
        holidays = frappe.db.get_all("Holiday", filters={"holiday_date": str(d)}, fields=["description"])
        if holidays:
            is_holiday = True
            holiday_desc = holidays[0].get("description") or _("Ngày Lễ Quốc Gia")
    except Exception:
        is_holiday = False

    surcharge_pct = 0.0
    reason = []

    if is_holiday and conf["enable_holiday_surcharge"]:
        surcharge_pct = max(surcharge_pct, conf["holiday_surcharge_pct"])
        reason.append(f"Ngày Lễ: {holiday_desc} (+{conf['holiday_surcharge_pct']}%)")
    elif is_weekend and conf["enable_weekend_surcharge"]:
        surcharge_pct = max(surcharge_pct, conf["weekend_surcharge_pct"])
        reason.append(f"Cuối tuần (+{conf['weekend_surcharge_pct']}%)")

    return {
        "date": str(d),
        "is_peak": (is_holiday and conf["enable_holiday_surcharge"]) or (is_weekend and conf["enable_weekend_surcharge"]),
        "is_weekend": is_weekend,
        "is_holiday": is_holiday,
        "holiday_description": holiday_desc,
        "surcharge_pct": surcharge_pct,
        "reason": " | ".join(reason) if reason else _("Ngày thường")
    }

