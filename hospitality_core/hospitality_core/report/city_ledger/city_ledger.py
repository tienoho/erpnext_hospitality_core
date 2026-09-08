import frappe
from frappe import _
from frappe.utils import nowdate, date_diff
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Customer", "width": 160},
        {"label": _("Loại"), "fieldname": "folio_type", "fieldtype": "Data", "width": 90},
        {"label": _("Master Folio"), "fieldname": "name", "fieldtype": "Link", "options": "Guest Folio", "width": 140},
        {"label": _("Open Since"), "fieldname": "open_date", "fieldtype": "Date", "width": 100},
        {"label": _("Age (Days)"), "fieldname": "age", "fieldtype": "Int", "width": 80},
        {"label": _("Guest Ref"), "fieldname": "guest_name", "fieldtype": "Data", "width": 150},
        {"label": _("Total Charges"), "fieldname": "total_charges", "fieldtype": "Currency", "width": 100},
        {"label": _("Payments/Credits"), "fieldname": "total_payments", "fieldtype": "Currency", "width": 100},
        {"label": _("Balance Due"), "fieldname": "balance_due", "fieldtype": "Currency", "width": 130},
        {"label": _("Credit Balance"), "fieldname": "excess_payment", "fieldtype": "Currency", "width": 130}
    ]

    # TRƯỚC ĐÂY: chỉ lọc is_company_master=1 — Master Folio của ĐOÀN (Hotel
    # Group Booking.master_folio) KHÔNG BAO GIỜ được gán is_company_master=1
    # (xem create_folio() trong reservation.py, dùng chung cho cả công ty lẫn
    # đoàn), nên công nợ của MỌI đoàn đang mở (chưa tất toán) hoàn toàn KHÔNG
    # xuất hiện trong City Ledger — một khoảng trống thật, không phải giới hạn
    # có chủ đích, vì City Ledger đúng nghĩa là "toàn bộ công nợ chưa thu của
    # bên thứ 3 chịu trách nhiệm thanh toán", đoàn cũng là 1 dạng bên thứ 3
    # như vậy. Nay lấy cả 2 loại Master Folio, có cột "Loại" để phân biệt.
    conditions = """gf.status = 'Open'
        AND (gf.is_company_master = 1
             OR EXISTS (SELECT 1 FROM `tabHotel Group Booking` hgb WHERE hgb.master_folio = gf.name))"""
    params = {}

    if filters.get("company"):
        conditions += " AND gf.company = %(company)s"
        params["company"] = filters.get("company")

    allowed_properties = allowed_properties_for_report()
    if allowed_properties is not None:
        conditions += " AND gf.property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    sql = f"""
        SELECT
            gf.company,
            CASE WHEN gf.is_company_master = 1 THEN 'Công ty' ELSE 'Đoàn' END as folio_type,
            gf.name,
            gf.open_date,
            DATEDIFF(CURDATE(), gf.open_date) as age,
            guest.full_name as guest_name,
            gf.total_charges,
            gf.total_payments,
            CASE WHEN gf.outstanding_balance > 0 THEN gf.outstanding_balance ELSE 0 END as balance_due,
            gf.excess_payment
        FROM
            `tabGuest Folio` gf
        LEFT JOIN
            `tabGuest` guest ON gf.guest = guest.name
        WHERE
            {conditions}
            AND gf.outstanding_balance != 0
        ORDER BY
            gf.company, gf.open_date
    """

    data = frappe.db.sql(sql, params, as_dict=True)
    
    # Add Total Row
    if data:
        total_due = sum(d.balance_due for d in data)
        total_credit = sum(d.excess_payment for d in data)
        data.append({
            "company": "<b>TOTAL CITY LEDGER</b>",
            "balance_due": total_due,
            "excess_payment": total_credit
        })
    
    return columns, data