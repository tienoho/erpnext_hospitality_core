import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

# ─── Protein item name keywords (case-insensitive LIKE match) ─────────────────
PROTEIN_KEYWORDS = ["Goatmeat", "Catfish", "Turkey", "Chicken", "Beef"]

# ─── Item groups ──────────────────────────────────────────────────────────────
DRINKS_GROUP     = "Drinks"
FOOD_GROUP       = "Food"
GYM_GROUP        = "Gym"
LAUNDRY_GROUP    = "Laundry"
SWIMMING_GROUP   = "Swimming"
PHOTOSHOOT_GROUP = "Photoshoot"
TRAY_CHARGE_NAME = "Tray Charge"


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": _("Description"), "fieldname": "description", "fieldtype": "Data",     "width": 280},
        {"label": _("Amount"),      "fieldname": "amount",      "fieldtype": "Currency",  "width": 160},
    ]

    if not filters.get("date"):
        return columns, []

    date = filters["date"]
    closing_entry_names = _get_closing_entry_names(date)
    allowed_properties = allowed_properties_for_report()

    # ── 1. Accommodation ──────────────────────────────────────────────────────
    accommodation = _get_room_rent_total(date)

    # ── 2–10. POS Item category sales ─────────────────────────────────────────
    drinks            = _get_item_group_total(closing_entry_names, DRINKS_GROUP, allowed_properties)
    food_no_protein   = _get_food_without_proteins(closing_entry_names, allowed_properties)
    goatmeat          = _get_protein_total(closing_entry_names, "Goatmeat", allowed_properties)
    catfish           = _get_protein_total(closing_entry_names, "Catfish", allowed_properties)
    turkey            = _get_protein_total(closing_entry_names, "Turkey", allowed_properties)
    chicken           = _get_protein_total(closing_entry_names, "Chicken", allowed_properties)
    beef              = _get_protein_total(closing_entry_names, "Beef", allowed_properties)
    total_proteins    = goatmeat + catfish + turkey + chicken + beef
    food_with_protein = food_no_protein + total_proteins

    # ── 11–15. Other POS categories ───────────────────────────────────────────
    gym               = _get_item_group_total(closing_entry_names, GYM_GROUP, allowed_properties)
    laundry           = _get_item_group_total(closing_entry_names, LAUNDRY_GROUP, allowed_properties)
    swimming          = _get_item_group_total(closing_entry_names, SWIMMING_GROUP, allowed_properties)
    photoshoot        = _get_item_group_total(closing_entry_names, PHOTOSHOOT_GROUP, allowed_properties)
    tray_charge       = _get_item_name_total(closing_entry_names, TRAY_CHARGE_NAME, allowed_properties)

    total_sales = (
        accommodation + drinks + food_with_protein +
        gym + laundry + swimming + photoshoot + tray_charge
    )

    # ── Receipts ──────────────────────────────────────────────────────────────
    from hospitality_core.hospitality_core.report.pos_sales_summary.pos_sales_summary import (
        get_closing_entries as get_pos_closing_entries,
        get_payment_map,
        get_profile_totals,
        build_summary_section
    )
    
    closing_entries = get_pos_closing_entries({"date": date})
    payment_map = get_payment_map([e.name for e in closing_entries]) if closing_entries else {}
    profile_totals = get_profile_totals(closing_entries, payment_map)
    receipts_summary = build_summary_section({"date": date}, profile_totals, no_profile_filter=True)

    # ── Build rows ────────────────────────────────────────────────────────────
    data = [
        {"description": _("<b>SALES</b>"),                "amount": None},
        {"description": _("Accommodation"),               "amount": accommodation},
        {"description": _("Drinks"),                      "amount": drinks},
        {"description": _("Food (without Proteins)"),     "amount": food_no_protein},
        {"description": _("Goatmeat"),                    "amount": goatmeat},
        {"description": _("Catfish"),                     "amount": catfish},
        {"description": _("Turkey"),                      "amount": turkey},
        {"description": _("Chicken"),                     "amount": chicken},
        {"description": _("Beef"),                        "amount": beef},
        {"description": _("<b>Total Proteins</b>"),       "amount": total_proteins},
        {"description": _("<b>Food with Proteins</b>"),   "amount": food_with_protein},
        {"description": _("Gym"),                         "amount": gym},
        {"description": _("Laundry"),                     "amount": laundry},
        {"description": _("Swimming"),                    "amount": swimming},
        {"description": _("Photoshoot"),                  "amount": photoshoot},
        {"description": _("Tray Charge"),                 "amount": tray_charge},
        {"description": "",                               "amount": None},
        {"description": _("<b>Total Sales</b>"),          "amount": total_sales},
        {"description": "",                               "amount": None},
        {"description": _("<b>RECEIPTS</b>"),             "amount": None},
    ]
    
    data.extend(receipts_summary)

    return columns, data


# ─── Private helpers ──────────────────────────────────────────────────────────

def _get_closing_entry_names(date):
    """
    Trả về các POS Closing Entry có ca đóng (period_start_date/period_end_date)
    giao với ngày kinh doanh `date`.

    TRƯỚC ĐÂY: giả định MỌI ca đóng POS đều được submit vào NGÀY HÔM SAU
    (posting_date = date+1) — đúng với outlet phục vụ khuya (nhà hàng/bar
    đóng ca sau nửa đêm), nhưng SAI với outlet đóng ca sớm cùng ngày (VD
    cửa hàng lưu niệm/spa đóng trước nửa đêm, posting_date = date) — closing
    entry của outlet đó bị RỚT HOÀN TOÀN khỏi báo cáo (không tính cho ngày
    nào cả, vì ngày `date+1` của NÓ cũng không khớp query của báo cáo
    `date+1`, do posting_date thật của nó là `date`, không phải `date+1`).
    Đồng thời còn gây đếm trùng ở "ngày biên" giữa 2 báo cáo liền kề nếu 2
    outlet khác nhau đóng ca cùng lúc quanh nửa đêm. Dùng đúng khoảng thời
    gian THẬT của ca (period_start_date/period_end_date, Datetime) giao với
    cửa sổ [date 00:00, date+1 00:00) — không phụ thuộc outlet đóng ca sớm
    hay muộn, không đếm trùng vì mỗi ca chỉ giao với ĐÚNG 1 ngày kinh doanh.
    """
    window_start = getdate(date)
    window_end = add_days(window_start, 1)
    rows = frappe.db.sql(
        """
        SELECT name FROM `tabPOS Closing Entry`
        WHERE docstatus = 1
          AND period_start_date < %(window_end)s
          AND period_end_date > %(window_start)s
        """,
        {"window_start": window_start, "window_end": window_end},
        as_dict=True,
    )
    return [r.name for r in rows] if rows else []


def _get_room_rent_total(date):
    """
    Returns total room-only sales for the given date
    by calling the exact logic from the room_only_sales report.
    """
    from hospitality_core.hospitality_core.report.room_only_sales.room_only_sales import get_data as get_room_sales_data

    sales_rows = get_room_sales_data({"from_date": date, "to_date": date})
    # The last row is the total row if there are records
    return flt(sales_rows[-1]["amount"]) if sales_rows else 0.0


def _get_item_group_total(closing_entry_names, item_group, allowed_properties=None):
    """Sum POS invoice item amounts for a specific item group across closing entries."""
    if not closing_entry_names:
        return 0.0
    params = {"names": tuple(closing_entry_names), "group": item_group}
    property_condition = ""
    if allowed_properties is not None:
        property_condition = "AND pi.hospitality_property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]
    result = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(pii.amount), 0) AS total
        FROM `tabPOS Invoice Reference` pir
        INNER JOIN `tabPOS Invoice` pi ON pi.name = pir.pos_invoice
        INNER JOIN `tabPOS Invoice Item` pii ON pii.parent = pi.name
        LEFT JOIN `tabItem` it ON it.name = pii.item_code
        WHERE pir.parent IN %(names)s
          AND pi.docstatus = 1
          AND COALESCE(it.item_group, '') = %(group)s
          {property_condition}
        """,
        params,
        as_dict=True,
    )
    return flt(result[0].total) if result else 0.0


def _get_protein_total(closing_entry_names, keyword, allowed_properties=None):
    """Sum POS invoice item amounts where item_name contains the protein keyword."""
    if not closing_entry_names:
        return 0.0
    params = {"names": tuple(closing_entry_names), "keyword": f"%{keyword}%"}
    property_condition = ""
    if allowed_properties is not None:
        property_condition = "AND pi.hospitality_property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]
    result = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(pii.amount), 0) AS total
        FROM `tabPOS Invoice Reference` pir
        INNER JOIN `tabPOS Invoice` pi ON pi.name = pir.pos_invoice
        INNER JOIN `tabPOS Invoice Item` pii ON pii.parent = pi.name
        WHERE pir.parent IN %(names)s
          AND pi.docstatus = 1
          AND pii.item_name LIKE %(keyword)s
          {property_condition}
        """,
        params,
        as_dict=True,
    )
    return flt(result[0].total) if result else 0.0


def _get_food_without_proteins(closing_entry_names, allowed_properties=None):
    """
    Sum items in the Food item group that do NOT match any protein keyword.
    """
    if not closing_entry_names:
        return 0.0

    # Build exclusion conditions dynamically
    protein_conditions = " AND ".join(
        [f"pii.item_name NOT LIKE %(protein_{i})s" for i, _ in enumerate(PROTEIN_KEYWORDS)]
    )
    params = {"names": tuple(closing_entry_names), "group": FOOD_GROUP}
    for i, kw in enumerate(PROTEIN_KEYWORDS):
        params[f"protein_{i}"] = f"%{kw}%"
    property_condition = ""
    if allowed_properties is not None:
        property_condition = "AND pi.hospitality_property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    result = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(pii.amount), 0) AS total
        FROM `tabPOS Invoice Reference` pir
        INNER JOIN `tabPOS Invoice` pi ON pi.name = pir.pos_invoice
        INNER JOIN `tabPOS Invoice Item` pii ON pii.parent = pi.name
        LEFT JOIN `tabItem` it ON it.name = pii.item_code
        WHERE pir.parent IN %(names)s
          AND pi.docstatus = 1
          AND COALESCE(it.item_group, '') = %(group)s
          AND {protein_conditions}
          {property_condition}
        """,
        params,
        as_dict=True,
    )
    return flt(result[0].total) if result else 0.0


def _get_item_name_total(closing_entry_names, item_name_keyword, allowed_properties=None):
    """Sum items whose item_name contains the given keyword (e.g. 'Tray Charge')."""
    if not closing_entry_names:
        return 0.0
    params = {"names": tuple(closing_entry_names), "keyword": f"%{item_name_keyword}%"}
    property_condition = ""
    if allowed_properties is not None:
        property_condition = "AND pi.hospitality_property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]
    result = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(pii.amount), 0) AS total
        FROM `tabPOS Invoice Reference` pir
        INNER JOIN `tabPOS Invoice` pi ON pi.name = pir.pos_invoice
        INNER JOIN `tabPOS Invoice Item` pii ON pii.parent = pi.name
        WHERE pir.parent IN %(names)s
          AND pi.docstatus = 1
          AND pii.item_name LIKE %(keyword)s
          {property_condition}
        """,
        params,
        as_dict=True,
    )
    return flt(result[0].total) if result else 0.0


