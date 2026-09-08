import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate, flt
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
        {"label": _("Total Rooms"), "fieldname": "total_rooms", "fieldtype": "Int", "width": 100},
        {"label": _("Occupied"), "fieldname": "occupied_rooms", "fieldtype": "Int", "width": 100},
        {"label": _("Occupancy %"), "fieldname": "occupancy_pct", "fieldtype": "Percent", "width": 110},
        {"label": _("Room Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 130},
        {"label": _("ADR"), "fieldname": "adr", "fieldtype": "Currency", "width": 120, "description": "Average Daily Rate"},
        {"label": _("RevPAR"), "fieldname": "revpar", "fieldtype": "Currency", "width": 120, "description": "Revenue Per Available Room"}
    ]

    data = []
    
    start_date = getdate(filters.get("from_date"))
    end_date = getdate(filters.get("to_date"))
    reception = filters.get("hotel_reception")
    
    # Lọc theo property được phép xem — xem report_scope.py để biết lý do
    # (frappe.db.count() cũng là truy vấn cấp thấp, KHÔNG tự áp dụng
    # permission_query_conditions như get_list/get_all).
    allowed_properties = allowed_properties_for_report()

    # 1. Total Inventory (Count of enabled rooms)
    # Filter by reception if provided
    room_filters = {"is_enabled": 1}
    if reception:
        room_filters["hotel_reception"] = reception
    if allowed_properties is not None:
        room_filters["property"] = ["in", allowed_properties or [""]]

    total_rooms_count = frappe.db.count("Hotel Room", filters=room_filters)

    # 2. Fetch all Room Revenue Transactions in range
    # Grouped by Date
    revenue_map = {}
    
    # Base params
    params = {"start": start_date, "end": end_date}
    reception_condition = ""
    
    if reception:
        reception_condition = "AND gf.hotel_reception = %(reception)s"
        params["reception"] = reception

    if allowed_properties is not None:
        reception_condition += " AND ft.property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    rev_sql = f"""
        SELECT ft.posting_date, SUM(ft.amount) as total
        FROM `tabFolio Transaction` ft
        JOIN `tabGuest Folio` gf ON ft.parent = gf.name
        WHERE ft.posting_date BETWEEN %(start)s AND %(end)s
        AND ft.is_void = 0
        AND COALESCE(ft.mirror_source, '') = ''
        AND ft.reference_doctype != 'Folio Transaction'
        AND (gf.is_company_master = 0 OR gf.is_company_master IS NULL)
        AND NOT EXISTS (SELECT 1 FROM `tabHotel Group Booking` hgb WHERE hgb.master_folio = gf.name)
        AND (ft.item IN ('DISCOUNT', 'COMPLIMENTARY')
             OR ft.item IN (SELECT name FROM `tabItem` WHERE item_code='ROOM-RENT' OR item_group='Accommodation'))
        {reception_condition}
        GROUP BY ft.posting_date
    """
    rev_data = frappe.db.sql(rev_sql, params, as_dict=True)
    for r in rev_data:
        revenue_map[str(r.posting_date)] = flt(r.total)

    # 3. Loop through dates
    curr_date = start_date
    while curr_date <= end_date:
        str_date = curr_date.strftime("%Y-%m-%d")
        
        # Calculate Occupied
        # Count reservations where Date is within [Arrival, Departure)
        res_filters = {
            "arrival_date": ["<=", str_date],
            "departure_date": [">", str_date], 
            "status": ["in", ["Checked In", "Checked Out"]] 
        }
        if reception:
            res_filters["hotel_reception"] = reception
        if allowed_properties is not None:
            res_filters["property"] = ["in", allowed_properties or [""]]

        occupied_count = frappe.db.count("Hotel Reservation", res_filters)

        revenue = revenue_map.get(str_date, 0.0)
        
        # Calculations
        occupancy = (occupied_count / total_rooms_count * 100) if total_rooms_count else 0.0
        adr = (revenue / occupied_count) if occupied_count else 0.0
        revpar = (revenue / total_rooms_count) if total_rooms_count else 0.0

        data.append({
            "date": str_date,
            "total_rooms": total_rooms_count,
            "occupied_rooms": occupied_count,
            "occupancy_pct": flt(occupancy, 2),
            "revenue": revenue,
            "adr": flt(adr, 2),
            "revpar": flt(revpar, 2)
        })

        curr_date = add_days(curr_date, 1)

    # Chart Configuration
    chart = {
        "data": {
            "labels": [d["date"] for d in data],
            "datasets": [
                {"name": "Occupancy %", "values": [d["occupancy_pct"] for d in data]},
                {"name": "RevPAR", "values": [d["revpar"] for d in data]}
            ]
        },
        "type": "line",
        "colors": ["#7cd6fd", "#743ee2"]
    }

    return columns, data, None, chart