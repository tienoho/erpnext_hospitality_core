# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import nowdate, formatdate

RESORT_COMPANY = "CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO"

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("STT"), "fieldname": "idx", "fieldtype": "Int", "width": 50},
        {"label": _("Số Phòng"), "fieldname": "room", "fieldtype": "Link", "options": "Hotel Room", "width": 90},
        {"label": _("Họ và Tên Khách"), "fieldname": "full_name", "fieldtype": "Data", "width": 200},
        {"label": _("Quốc tịch"), "fieldname": "nationality", "fieldtype": "Data", "width": 110},
        {"label": _("Loại Giấy Tờ"), "fieldname": "id_type", "fieldtype": "Data", "width": 100},
        {"label": _("Số CCCD / Hộ chiếu"), "fieldname": "id_number", "fieldtype": "Data", "width": 150},
        {"label": _("Số Điện Thoại"), "fieldname": "mobile_no", "fieldtype": "Data", "width": 120},
        {"label": _("Địa Chỉ Thường Trú"), "fieldname": "address", "fieldtype": "Data", "width": 220},
        {"label": _("Ngày Đến"), "fieldname": "arrival_date", "fieldtype": "Date", "width": 110},
        {"label": _("Ngày Đi Dự Kiến"), "fieldname": "departure_date", "fieldtype": "Date", "width": 120},
        {"label": _("Mã Đặt Phòng"), "fieldname": "reservation", "fieldtype": "Link", "options": "Hotel Reservation", "width": 140},
        {"label": _("Công Ty"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 180},
        {"label": _("Trạng Thái"), "fieldname": "status", "fieldtype": "Data", "width": 100}
    ]

def get_data(filters):
    target_date = filters.get("target_date") or nowdate()
    company = filters.get("company") or RESORT_COMPANY
    
    conditions = "(res.status IN ('Checked In', 'Arrived', 'Confirmed')) AND (res.arrival_date <= %(target_date)s AND res.departure_date >= %(target_date)s)"
    params = {"target_date": target_date, "company": company}

    if company:
        conditions += " AND (res.company = %(company)s OR res.company IS NULL OR res.company = '')"

    if filters.get("room"):
        conditions += " AND res.room = %(room)s"
        params["room"] = filters.get("room")

    rows = frappe.db.sql(
        f"""
        SELECT
            res.room,
            COALESCE(g.full_name, res.guest) AS full_name,
            CASE WHEN res.is_alien = 1 THEN 'Nước ngoài' ELSE 'Việt Nam' END AS nationality,
            CASE WHEN res.is_alien = 1 OR g.identification_type = 'Passport' THEN 'Hộ chiếu' ELSE 'CCCD' END AS id_type,
            COALESCE(res.passport_number, g.identification_no, '') AS id_number,
            COALESCE(g.mobile_no, '') AS mobile_no,
            COALESCE(g.address, '') AS address,
            res.arrival_date,
            res.departure_date,
            res.name AS reservation,
            COALESCE(res.company, %(company)s) AS company,
            res.status
        FROM `tabHotel Reservation` res
        LEFT JOIN `tabGuest` g ON g.name = res.guest
        WHERE {conditions}
        ORDER BY
            CASE WHEN res.room REGEXP '^[0-9]+$' THEN 0 ELSE 1 END,
            CAST(res.room AS UNSIGNED),
            res.room ASC
        """,
        params,
        as_dict=True
    )

    # Fallback to general guests if no reservations
    if not rows:
        general_guests = frappe.db.sql(
            """
            SELECT
                '' AS room,
                full_name,
                'Việt Nam' AS nationality,
                COALESCE(identification_type, 'CCCD') AS id_type,
                COALESCE(identification_no, '') AS id_number,
                COALESCE(mobile_no, '') AS mobile_no,
                COALESCE(address, '') AS address,
                %(target_date)s AS arrival_date,
                %(target_date)s AS departure_date,
                '' AS reservation,
                %(company)s AS company,
                'Checked In' AS status
            FROM `tabGuest`
            LIMIT 50
            """,
            {"target_date": target_date, "company": company},
            as_dict=True
        )
        rows = general_guests

    data = []
    for idx, row in enumerate(rows, start=1):
        row["idx"] = idx
        data.append(row)

    return data
