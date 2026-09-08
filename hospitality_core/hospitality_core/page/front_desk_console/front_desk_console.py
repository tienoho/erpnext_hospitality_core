import frappe
from frappe import _
from frappe.utils import nowdate, flt, getdate
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

@frappe.whitelist()
def get_console_data(target_date=None):
    if not frappe.has_permission("Hotel Reservation", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    if not target_date:
        target_date = nowdate()

    # TRƯỚC ĐÂY: mọi truy vấn dưới đây (raw SQL + frappe.db.count) hoàn toàn
    # không lọc property — permission_query_conditions/has_permission (khung
    # phân quyền Property v2) CHỈ áp dụng cho frappe.get_list(), không áp
    # dụng cho raw SQL/frappe.get_all()/frappe.db.count() (frappe.get_all()
    # đặt ignore_permissions=True, khiến build_match_conditions() — nơi gọi
    # permission_query_conditions — bị bỏ qua hoàn toàn, xem
    # frappe/model/db_query.py dòng ~676). Front Desk Console là công cụ vận
    # hành chính lễ tân dùng CẢ NGÀY — khi property thứ 2 kích hoạt, lễ tân
    # cơ sở A sẽ thấy trộn lẫn cả arrivals/departures/số phòng của cơ sở B.
    allowed_properties = allowed_properties_for_report()
    property_condition = ""
    property_filter = {}
    if allowed_properties is not None:
        property_condition = "AND res.property IN %(_properties)s"
        property_filter = {"property": ["in", allowed_properties or [""]]}

    # 1. Fetch Arrivals for specific date
    # Include 'Checked Out' in arrivals list if they arrived AND left on the target date (Day Use)
    arrivals = frappe.db.sql(f"""
        SELECT res.name, g.full_name as guest_name, res.status, COALESCE(r.room_number, res.room) as room, res.room_type, res.arrival_date, r.status as room_hk_status
        FROM `tabHotel Reservation` res
        LEFT JOIN `tabGuest` g ON res.guest = g.name
        LEFT JOIN `tabHotel Room` r ON res.room = r.name
        WHERE res.arrival_date = %(target_date)s
        AND res.status IN ('Reserved', 'Checked In', 'Checked Out')
        {property_condition}
        ORDER BY res.status DESC, g.full_name ASC
    """, {"target_date": target_date, "_properties": allowed_properties or [""]}, as_dict=True)

    # 2. Fetch Departures for specific date
    departures = frappe.db.sql(f"""
        SELECT res.name, g.full_name as guest_name, res.status, COALESCE(r.room_number, res.room) as room, res.room_type, res.departure_date, r.status as room_hk_status
        FROM `tabHotel Reservation` res
        LEFT JOIN `tabGuest` g ON res.guest = g.name
        LEFT JOIN `tabHotel Room` r ON res.room = r.name
        WHERE res.departure_date = %(target_date)s
        AND res.status IN ('Checked In', 'Checked Out')
        {property_condition}
        ORDER BY res.status ASC, COALESCE(r.room_number, res.room) ASC
    """, {"target_date": target_date, "_properties": allowed_properties or [""]}, as_dict=True)

    # 3. Stats Calculation (Date Sensitive)
    total_rooms = frappe.db.count("Hotel Room", {"is_enabled": 1, **property_filter})

    # Calculate In-House (Night Occupancy)
    # Logic: Arrived <= Today AND Departing > Today.
    # This captures:
    #   - Old Check-ins (Stayovers)
    #   - New Check-ins (Arrivals)
    # It Excludes:
    #   - Due Outs (Departing Today) -> These rooms are considered available for tonight once vacated.
    in_house_count = frappe.db.count("Hotel Reservation", {
        "arrival_date": ["<=", target_date],
        "departure_date": [">", target_date],
        "status": "Checked In",
        **property_filter,
    })

    # Arrivals Pending (Reserved for this date)
    # These represent potential In-House guests for tonight who haven't arrived yet.
    arrivals_pending = len([a for a in arrivals if a.status == 'Reserved'])

    # Departures Pending (Checked In with departure on this date)
    # These are guests physically present right now but expected to leave.
    departures_pending = len([d for d in departures if d.status == 'Checked In'])

    available_today_departures = len([d for d in departures if d.status == 'Checked Out'])

    # Available Rooms Calculation
    # Logic: Total - (Currently In House for Night + Reserved Arrivals) - OOO
    # Note: A room that checks out today is available for a new arrival tonight.
    ooo_rooms = frappe.db.count("Hotel Room", {"status": "Out of Order", "is_enabled": 1, **property_filter})
    
    # Committed Rooms = People staying tonight + People arriving tonight
    committed_rooms = in_house_count + arrivals_pending
    
    available = total_rooms - committed_rooms - ooo_rooms
    if available < 0: available = 0

    occupancy_pct = 0
    if total_rooms > 0:
        occupancy_pct = flt((in_house_count / total_rooms) * 100, 1)

    return {
        "arrivals": arrivals,
        "departures": departures,
        "stats": {
            "total_rooms": total_rooms,
            "in_house": in_house_count,
            "occupancy_pct": occupancy_pct,
            "arrivals_pending": arrivals_pending,
            "departures_pending": departures_pending,
            "available": available
        }
    }