import frappe
from frappe import _
from frappe.utils import flt
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 100},
		{"label": _("Room Type"), "fieldname": "room_type", "fieldtype": "Link", "options": "Hotel Room Type", "width": 180},
		{"label": _("Room Nights Sold"), "fieldname": "room_nights", "fieldtype": "Int", "width": 130},
		{"label": _("Room Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 150},
		{"label": _("Avg Rate / Night"), "fieldname": "avg_rate", "fieldtype": "Currency", "width": 140},
	]


def get_data(filters):
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	room_type = filters.get("room_type")

	# TRƯỚC ĐÂY: chỉ SUM(ft.amount) cho các dòng item='ROOM-RENT'/'Accommodation'
	# — bỏ sót hoàn toàn các dòng DISCOUNT/COMPLIMENTARY (item_group='Services',
	# khác item_group nên bị lọc loại), khiến "Room Revenue" là doanh thu GỘP
	# (giá niêm yết trước giảm giá), không phải doanh thu THỰC THU — sai lệch
	# bất cứ khi nào có giảm giá LOS/thủ công/miễn phí áp dụng. Đối chiếu với
	# quy ước ĐÚNG đã dùng trong room_only_sales.py (amount = room_rent -
	# discount): nay cộng gộp cả DISCOUNT/COMPLIMENTARY (luôn là số âm) vào
	# cùng SUM để ra đúng doanh thu ròng.
	# Loại bỏ Master Folio để tránh đếm trùng — các giao dịch đã được mirror
	# sang đó từ Guest Folio gốc (giống quy ước của gross_revenue_report).
	# QUAN TRỌNG: is_company_master=0 CHỈ loại được Master Folio của CÔNG TY —
	# Master Folio của ĐOÀN (Hotel Group Booking.master_folio) không hề được
	# gán is_company_master=1 khi tạo (xem create_folio() trong reservation.py),
	# nên nếu chỉ lọc is_company_master, doanh thu của MỌI khách đi đoàn sẽ bị
	# đếm 2 lần: 1 lần từ Guest Folio gốc, 1 lần nữa từ bản mirror trên Master
	# Folio của đoàn (mà join qua reservation "ảo" nên còn bị gắn nhầm vào
	# room_type "Virtual"). Phải loại riêng qua NOT EXISTS. Đồng thời loại trừ
	# chính các bản SAO MIRROR còn sót lại trên Guest Folio gốc (không nên xảy
	# ra bình thường, nhưng COALESCE(mirror_source,'')='' là chốt chặn an toàn
	# khớp với accounting.py/folio.py's quy ước authoritative).
	conditions = """ft.is_void = 0 AND gf.is_company_master = 0
		AND NOT EXISTS (SELECT 1 FROM `tabHotel Group Booking` hgb WHERE hgb.master_folio = gf.name)
		AND COALESCE(ft.mirror_source, '') = ''
		AND ft.posting_date BETWEEN %(from_date)s AND %(to_date)s"""
	params = {"from_date": from_date, "to_date": to_date}

	if room_type:
		conditions += " AND room.room_type = %(room_type)s"
		params["room_type"] = room_type

	# Lọc theo property được phép xem — xem report_scope.py để biết lý do
	# (permission_query_conditions của property_scope.py không tự áp dụng cho
	# SQL thô). None nghĩa là không cần lọc (hệ thống property chưa
	# cài/chưa kích hoạt/user là quản trị).
	allowed_properties = allowed_properties_for_report()
	if allowed_properties is not None:
		conditions += " AND ft.property IN %(_properties)s"
		params["_properties"] = allowed_properties or [""]

	# LUU Y: JOIN duoi day dung "res.room = room.name" (khong phai
	# room.room_number) — Hotel Room dung autoname='hash', ten ban ghi la
	# chuoi hash ngau nhien khong lien quan room_number. res.room (Link
	# field) luon la TEN ban ghi; noi voi room.room_number se LUON tra ve 0
	# dong (da tung la loi that o day + gross_revenue_report.py, da fix).
	rows = frappe.db.sql(f"""
		SELECT
			DATE_FORMAT(ft.posting_date, '%%Y-%%m') as month,
			room.room_type as room_type,
			COUNT(CASE WHEN item.item_code = 'ROOM-RENT' OR item.item_group = 'Accommodation' THEN 1 END) as room_nights,
			SUM(ft.amount) as revenue
		FROM `tabFolio Transaction` ft
		JOIN `tabGuest Folio` gf ON ft.parent = gf.name
		JOIN `tabHotel Reservation` res ON gf.reservation = res.name
		JOIN `tabHotel Room` room ON res.room = room.name
		JOIN `tabItem` item ON ft.item = item.name
		WHERE
			(item.item_code IN ('ROOM-RENT', 'DISCOUNT', 'COMPLIMENTARY') OR item.item_group = 'Accommodation')
			AND {conditions}
		GROUP BY month, room.room_type
		ORDER BY month, room.room_type
	""", params, as_dict=True)

	for r in rows:
		r["avg_rate"] = (flt(r.revenue) / r.room_nights) if r.room_nights else 0

	return rows
