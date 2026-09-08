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
		{"label": _("Kênh OTA"), "fieldname": "ota_platform", "fieldtype": "Data", "width": 150},
		{"label": _("Số Đặt Phòng"), "fieldname": "bookings", "fieldtype": "Int", "width": 110},
		{"label": _("Doanh Thu Phòng"), "fieldname": "revenue", "fieldtype": "Currency", "width": 150},
		{"label": _("Tỷ Lệ Hoa Hồng (%)"), "fieldname": "commission_percent", "fieldtype": "Percent", "width": 140},
		{"label": _("Hoa Hồng Phải Trả"), "fieldname": "commission_amount", "fieldtype": "Currency", "width": 150},
	]


def get_commission_rate_map():
	"""
	Đọc bảng cấu hình % hoa hồng theo kênh từ Hospitality Channel Manager
	Settings — kênh chưa có dòng cấu hình thì mặc định 0% (chưa xác nhận hợp
	đồng với đối tác đó), KHÔNG suy đoán một con số bất kỳ.
	"""
	settings = frappe.get_single("Hospitality Channel Manager Settings")
	return {row.ota_platform: flt(row.commission_percent) for row in (settings.ota_commission_rates or [])}


def get_data(filters):
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	ota_platform = filters.get("ota_platform")

	# Chỉ tính hoa hồng trên doanh thu Room Rent (đúng thông lệ hợp đồng OTA —
	# hoa hồng tính trên giá phòng, không tính dịch vụ/F&B phát sinh tại
	# khách sạn). TRƯỚC ĐÂY: chỉ lọc item='ROOM-RENT', bỏ sót các dòng
	# DISCOUNT/COMPLIMENTARY (item_group='Services' — khác item_group nên bị
	# loại) khiến doanh thu tính hoa hồng là GIÁ GỘP trước giảm giá, không
	# phải doanh thu THỰC THU — hoa hồng bị tính cao hơn thực tế bất cứ khi
	# nào có giảm giá LOS/thủ công áp dụng cho khách OTA. Nay cộng gộp cả
	# DISCOUNT/COMPLIMENTARY vào SUM để ra đúng doanh thu ròng.
	# Loại Master Folio (CẢ công ty lẫn ĐOÀN — is_company_master=0 chỉ loại
	# được Master Folio công ty; Master Folio của Hotel Group Booking không hề
	# set is_company_master=1, nên phải loại riêng qua NOT EXISTS) để tránh
	# đếm trùng giao dịch đã mirror. Loại luôn chính các bản mirror còn sót
	# (mirror_source) làm chốt chặn thứ 2, khớp quy ước authoritative của
	# accounting.py/folio.py.
	conditions = """
		ft.is_void = 0 AND gf.is_company_master = 0
		AND COALESCE(ft.mirror_source, '') = ''
		AND NOT EXISTS (SELECT 1 FROM `tabHotel Group Booking` hgb WHERE hgb.master_folio = gf.name)
		AND res.booking_source = 'OTA'
		AND ft.posting_date BETWEEN %(from_date)s AND %(to_date)s
	"""
	params = {"from_date": from_date, "to_date": to_date}

	if ota_platform:
		conditions += " AND res.ota_platform = %(ota_platform)s"
		params["ota_platform"] = ota_platform

	allowed_properties = allowed_properties_for_report()
	if allowed_properties is not None:
		conditions += " AND ft.property IN %(_properties)s"
		params["_properties"] = allowed_properties or [""]

	rows = frappe.db.sql(f"""
		SELECT
			res.ota_platform as ota_platform,
			COUNT(DISTINCT res.name) as bookings,
			SUM(ft.amount) as revenue
		FROM `tabFolio Transaction` ft
		JOIN `tabGuest Folio` gf ON ft.parent = gf.name
		JOIN `tabHotel Reservation` res ON gf.reservation = res.name
		JOIN `tabItem` item ON ft.item = item.name
		WHERE
			(item.item_code IN ('ROOM-RENT', 'DISCOUNT', 'COMPLIMENTARY') OR item.item_group = 'Accommodation')
			AND {conditions}
		GROUP BY res.ota_platform
		ORDER BY revenue DESC
	""", params, as_dict=True)

	rate_map = get_commission_rate_map()
	for r in rows:
		r["ota_platform"] = r.ota_platform or _("(Chưa xác định)")
		r["commission_percent"] = rate_map.get(r.ota_platform, 0)
		r["commission_amount"] = flt(r.revenue) * flt(r["commission_percent"]) / 100.0

	return rows
