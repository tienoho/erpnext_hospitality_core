import frappe
from frappe import _
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Type"), "fieldname": "type", "fieldtype": "Data", "width": 120},
        {"label": _("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Hotel Room", "width": 80},
        {"label": _("Guest"), "fieldname": "guest_name", "fieldtype": "Data", "width": 150},
        {"label": _("Item Code"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 120},
        {"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 200},
        {"label": _("Amount (Credit)"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Folio"), "fieldname": "parent", "fieldtype": "Link", "options": "Guest Folio", "width": 140},
        {"label": _("Posted By"), "fieldname": "owner", "fieldtype": "Data", "width": 120}
    ]

    filters = filters or {}
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    report_type = filters.get("type")

    # Logic:
    # Find transactions where amount < 0 (Credits)
    # Exclude Payments (Cash, Card, Transfer)
    # Include Items named 'DISCOUNT', 'COMPLIMENTARY' or Descriptions containing 'Discount'
    
    sql = """
        SELECT
            ft.posting_date,
            CASE 
                WHEN ft.item = 'COMPLIMENTARY' OR ft.description LIKE '%%Complimentary%%' THEN 'Complimentary'
                ELSE 'Discount'
            END as type,
            gf.room,
            g.full_name as guest_name,
            ft.item,
            ft.description,
            -ft.amount as amount, -- Show as positive value for report legibility
            ft.parent,
            ft.owner
        FROM `tabFolio Transaction` ft
        JOIN `tabGuest Folio` gf ON ft.parent = gf.name
        LEFT JOIN `tabGuest` g ON gf.guest = g.name
        WHERE ft.posting_date BETWEEN %s AND %s
        AND ft.is_void = 0
        AND (ft.amount < 0 OR ft.item IN ('DISCOUNT', 'COMPLIMENTARY'))
        -- Loại bản SAO MIRROR trên Master Folio (công ty/đoàn) — nếu không,
        -- mỗi lần giảm giá/miễn phí cho khách bill-to-Company/Group sẽ bị
        -- đếm 2 lần: 1 lần từ Guest Folio gốc, 1 lần nữa từ bản mirror.
        AND COALESCE(ft.mirror_source, '') = ''
        AND ft.item NOT IN ('PAYMENT', 'PAYMENT-CASH', 'PAYMENT-CARD') -- Adjust based on your payment item codes
        AND (
            ft.item IN ('DISCOUNT', 'COMPLIMENTARY')
            OR ft.description LIKE '%%Discount%%'
        )
    """
    params = [from_date, to_date]

    allowed_properties = allowed_properties_for_report()
    if allowed_properties is not None:
        sql += " AND ft.property IN %s"
        params.append(allowed_properties or [""])

    # `type` là cột suy diễn qua CASE trong SELECT, không thể lọc bằng WHERE
    # (WHERE chạy trước khi alias được tính) — bộ lọc "Type" trên JS trước đây
    # không có tác dụng gì vì .py chưa từng đọc filters["type"]. Dùng HAVING để
    # lọc trên alias đã tính.
    if report_type in ("Discount", "Complimentary"):
        sql += " HAVING type = %s"
        params.append(report_type)

    sql += " ORDER BY ft.posting_date DESC"

    data = frappe.db.sql(sql, tuple(params), as_dict=True)

    # Chart Data
    comp_total = sum([d['amount'] for d in data if d['type'] == 'Complimentary'])
    disc_total = sum([d['amount'] for d in data if d['type'] == 'Discount'])

    chart = {
        "data": {
            "labels": ["Complimentary", "Discounts"],
            "datasets": [{"name": "Value Given", "values": [comp_total, disc_total]}]
        },
        "type": "bar",
        "colors": ["#e74c3c", "#f39c12"]
    }
    
    if data:
        data.append({
            "description": "<b>TOTAL GIVEN</b>",
            "amount": sum([d['amount'] for d in data])
        })

    return columns, data, None, chart