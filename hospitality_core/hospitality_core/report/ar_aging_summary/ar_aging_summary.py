import frappe
from frappe import _
from frappe.utils import getdate, date_diff, flt
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Loại"), "fieldname": "folio_type", "fieldtype": "Data", "width": 90},
		{"label": _("Master Folio"), "fieldname": "name", "fieldtype": "Link", "options": "Guest Folio", "width": 140},
		{"label": _("Open Since"), "fieldname": "open_date", "fieldtype": "Date", "width": 100},
		{"label": _("Age (Days)"), "fieldname": "age", "fieldtype": "Int", "width": 90},
		{"label": _("0-30 Ngày"), "fieldname": "bucket_0_30", "fieldtype": "Currency", "width": 130},
		{"label": _("31-60 Ngày"), "fieldname": "bucket_31_60", "fieldtype": "Currency", "width": 130},
		{"label": _("61-90 Ngày"), "fieldname": "bucket_61_90", "fieldtype": "Currency", "width": 130},
		{"label": _("Trên 90 Ngày"), "fieldname": "bucket_90_plus", "fieldtype": "Currency", "width": 130},
		{"label": _("Tổng Nợ"), "fieldname": "balance_due", "fieldtype": "Currency", "width": 130},
	]


def get_data(filters):
	"""
	AR Aging theo thông lệ 30/60/90 ngày. LƯU Ý VỀ MÔ HÌNH DỮ LIỆU: Guest
	Folio (Master/City Ledger) trong hệ thống này là 1 số dư LIÊN TỤC
	(continuous balance), không phải danh sách hóa đơn rời rạc từng cái có
	ngày phát sinh riêng — vì vậy "tuổi nợ" ở đây tính theo NGÀY MỞ FOLIO
	(open_date), giống hệt quy ước đã dùng trong city_ledger.py, rồi xếp
	TOÀN BỘ số dư còn nợ của folio đó vào đúng 1 bậc tuổi tương ứng. Đây
	không phải aging theo từng hóa đơn con (vì dữ liệu không có khái niệm
	đó) — nếu sau này Guest Folio được tách thành các hóa đơn con có ngày
	riêng, báo cáo này cần viết lại ở mức chi tiết hơn.
	"""
	as_of_date = getdate(filters.get("as_of_date"))
	company = filters.get("company")

	# TRƯỚC ĐÂY: chỉ lọc is_company_master=1 — bỏ sót hoàn toàn công nợ của
	# Master Folio ĐOÀN (Hotel Group Booking.master_folio không bao giờ được
	# gán is_company_master=1, xem create_folio() trong reservation.py), nên
	# aging report chỉ phản ánh 1 phần công nợ thật của khách sạn. Nay lấy cả
	# 2 loại, có cột "Loại" để phân biệt (khớp fix tương tự ở city_ledger.py).
	conditions = """gf.status = 'Open' AND gf.outstanding_balance > 0
		AND (gf.is_company_master = 1
		     OR EXISTS (SELECT 1 FROM `tabHotel Group Booking` hgb WHERE hgb.master_folio = gf.name))"""
	params = {"as_of_date": as_of_date}

	if company:
		conditions += " AND gf.company = %(company)s"
		params["company"] = company

	allowed_properties = allowed_properties_for_report()
	if allowed_properties is not None:
		conditions += " AND gf.property IN %(_properties)s"
		params["_properties"] = allowed_properties or [""]

	rows = frappe.db.sql(f"""
		SELECT
			gf.company,
			CASE WHEN gf.is_company_master = 1 THEN 'Công ty' ELSE 'Đoàn' END as folio_type,
			gf.name,
			gf.open_date,
			gf.outstanding_balance as balance_due
		FROM `tabGuest Folio` gf
		WHERE {conditions}
		ORDER BY gf.company, gf.open_date
	""", params, as_dict=True)

	result = []
	totals = {"bucket_0_30": 0.0, "bucket_31_60": 0.0, "bucket_61_90": 0.0, "bucket_90_plus": 0.0, "balance_due": 0.0}

	for r in rows:
		age = date_diff(as_of_date, r.open_date)
		r["age"] = age
		r["bucket_0_30"] = 0.0
		r["bucket_31_60"] = 0.0
		r["bucket_61_90"] = 0.0
		r["bucket_90_plus"] = 0.0

		if age <= 30:
			r["bucket_0_30"] = flt(r.balance_due)
		elif age <= 60:
			r["bucket_31_60"] = flt(r.balance_due)
		elif age <= 90:
			r["bucket_61_90"] = flt(r.balance_due)
		else:
			r["bucket_90_plus"] = flt(r.balance_due)

		for key in totals:
			totals[key] += r[key] if key != "balance_due" else flt(r.balance_due)

		result.append(r)

	if result:
		result.append({
			"company": f"<b>{_('TỔNG CỘNG')}</b>",
			**totals,
		})

	return result
