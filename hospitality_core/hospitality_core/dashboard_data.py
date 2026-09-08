import frappe
from frappe import _
from frappe.utils import flt, add_days, getdate, nowdate
from datetime import timedelta
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

@frappe.whitelist()
def get_hospitality_analytics_data(chart_name, from_date=None, to_date=None):
	if not ("Hospitality Manager" in frappe.get_roles() or "System Manager" in frappe.get_roles()):
		frappe.throw(_("Not authorized to view hospitality analytics."), frappe.PermissionError)

	if not from_date:
		from_date = add_days(nowdate(), -30)
	if not to_date:
		to_date = nowdate()

	if chart_name == "Occupancy Rate Trend":
		return get_occupancy_rate_trend(from_date, to_date)
	elif chart_name == "Average Daily Rate (ADR)":
		return get_adr_trend(from_date, to_date)
	elif chart_name == "RevPAR Trend":
		return get_revpar_trend(from_date, to_date)
	elif chart_name == "Guest Type Distribution":
		return get_guest_type_distribution(from_date, to_date)
	elif chart_name == "Revenue vs Expense Trend":
		return get_revenue_expense_trend(from_date, to_date)
	elif chart_name == "Expense Breakdown":
		return get_expense_breakdown(from_date, to_date)
	elif chart_name == "Sales by Reception":
		return get_sales_by_reception(from_date, to_date)
	elif chart_name == "Payment Mode Distribution":
		return get_payment_mode_distribution(from_date, to_date)
	elif chart_name == "Gross Profit Margin Trend":
		return get_gross_profit_margin_trend(from_date, to_date)
	elif chart_name == "Maintenance Cost by Room Type":
		return get_maintenance_cost_by_room_type(from_date, to_date)
	elif chart_name == "Today's Occupancy":
		return get_today_occupancy()
	elif chart_name == "Today's Revenue":
		return get_today_revenue()
	elif chart_name == "Today's Expenses":
		return get_today_expenses()

def get_occupancy_rate_trend(from_date, to_date):
	# Lọc theo property được phép xem — xem report_scope.py để biết lý do
	# (frappe.db.count()/frappe.db.sql() không tự áp dụng property_scope.py's
	# permission_query_conditions như get_list/get_all).
	allowed_properties = allowed_properties_for_report()
	room_filters = {"is_enabled": 1}
	res_property_sql = ""
	res_property_params = ()
	if allowed_properties is not None:
		room_filters["property"] = ["in", allowed_properties or [""]]
		res_property_sql = "AND property IN %s"
		res_property_params = (tuple(allowed_properties or [""]),)
	total_rooms = frappe.db.count("Hotel Room", room_filters) or 1
	dates = []
	values = []

	curr = getdate(from_date)
	end = getdate(to_date)

	while curr <= end:
		d_str = curr.strftime("%Y-%m-%d")
		occ_count = frappe.db.sql(f"""
			SELECT COUNT(*)
			FROM `tabHotel Reservation`
			WHERE arrival_date <= %s AND departure_date > %s
			AND status NOT IN ('Cancelled', 'No Show')
			{res_property_sql}
		""", (d_str, d_str) + res_property_params)[0][0]

		dates.append(d_str)
		values.append(round((flt(occ_count) / total_rooms) * 100.0, 2))
		curr += timedelta(days=1)

	return {"labels": dates, "datasets": [{"name": "Occupancy %", "values": values}]}

def get_adr_trend(from_date, to_date):
	allowed_properties = allowed_properties_for_report()
	ft_property_sql = ""
	res_property_sql = ""
	property_params = ()
	if allowed_properties is not None:
		props = (tuple(allowed_properties or [""]),)
		ft_property_sql = "AND property IN %s"
		res_property_sql = "AND property IN %s"
		property_params = props

	dates = []
	values = []
	curr = getdate(from_date)
	end = getdate(to_date)

	while curr <= end:
		d_str = curr.strftime("%Y-%m-%d")
		# Total Revenue for the day
		rev = frappe.db.sql(f"""
			SELECT SUM(amount) FROM `tabFolio Transaction`
			WHERE posting_date = %s AND is_void = 0
			AND (reference_doctype != 'Payment Entry' OR reference_doctype IS NULL)
			AND COALESCE(mirror_source, '') = ''
			{ft_property_sql}
		""", (d_str,) + property_params)[0][0] or 0

		# Occupied rooms for the day
		occ_count = frappe.db.sql(f"""
			SELECT COUNT(*) FROM `tabHotel Reservation`
			WHERE arrival_date <= %s AND departure_date > %s
			AND status NOT IN ('Cancelled', 'No Show')
			{res_property_sql}
		""", (d_str, d_str) + property_params)[0][0] or 0

		dates.append(d_str)
		values.append(round(flt(rev) / occ_count, 2) if occ_count > 0 else 0)
		curr += timedelta(days=1)

	return {"labels": dates, "datasets": [{"name": "ADR", "values": values}]}

def get_revpar_trend(from_date, to_date):
	allowed_properties = allowed_properties_for_report()
	room_filters = {"is_enabled": 1}
	ft_property_sql = ""
	property_params = ()
	if allowed_properties is not None:
		room_filters["property"] = ["in", allowed_properties or [""]]
		ft_property_sql = "AND property IN %s"
		property_params = (tuple(allowed_properties or [""]),)
	total_rooms = frappe.db.count("Hotel Room", room_filters) or 1
	dates = []
	values = []
	curr = getdate(from_date)
	end = getdate(to_date)

	while curr <= end:
		d_str = curr.strftime("%Y-%m-%d")
		rev = frappe.db.sql(f"""
			SELECT SUM(amount) FROM `tabFolio Transaction`
			WHERE posting_date = %s AND is_void = 0
			AND (reference_doctype != 'Payment Entry' OR reference_doctype IS NULL)
			AND COALESCE(mirror_source, '') = ''
			{ft_property_sql}
		""", (d_str,) + property_params)[0][0] or 0

		dates.append(d_str)
		values.append(round(flt(rev) / total_rooms, 2))
		curr += timedelta(days=1)

	return {"labels": dates, "datasets": [{"name": "RevPAR", "values": values}]}

def get_guest_type_distribution(from_date, to_date):
	allowed_properties = allowed_properties_for_report()
	property_sql = ""
	property_params = ()
	if allowed_properties is not None:
		property_sql = "AND res.property IN %s"
		property_params = (tuple(allowed_properties or [""]),)
	data = frappe.db.sql(f"""
		SELECT guest_type, COUNT(*) as count
		FROM `tabHotel Reservation` res
		JOIN `tabGuest` g ON res.guest = g.name
		WHERE arrival_date BETWEEN %s AND %s
		{property_sql}
		GROUP BY guest_type
	""", (from_date, to_date) + property_params, as_dict=1)
	
	return {
		"labels": [d.guest_type for d in data],
		"datasets": [{"values": [d.count for d in data]}]
	}

def get_revenue_expense_trend(from_date, to_date):
	allowed_properties = allowed_properties_for_report()
	ft_property_sql = ""
	property_params = ()
	exp_filters_extra = {}
	if allowed_properties is not None:
		ft_property_sql = "AND property IN %s"
		property_params = (tuple(allowed_properties or [""]),)
		exp_filters_extra["property"] = ["in", allowed_properties or [""]]

	dates = []
	revenue = []
	expenses = []
	curr = getdate(from_date)
	end = getdate(to_date)

	while curr <= end:
		d_str = curr.strftime("%Y-%m-%d")
		rev = frappe.db.sql(f"""
			SELECT SUM(amount) FROM `tabFolio Transaction`
			WHERE posting_date = %s AND is_void = 0
			AND (reference_doctype != 'Payment Entry' OR reference_doctype IS NULL)
			AND COALESCE(mirror_source, '') = ''
			{ft_property_sql}
		""", (d_str,) + property_params)[0][0] or 0

		exp = frappe.db.get_value("Hospitality Expense", {"expense_date": d_str, "docstatus": 1, **exp_filters_extra}, "SUM(grand_total)") or 0

		dates.append(d_str)
		revenue.append(flt(rev))
		expenses.append(flt(exp))
		curr += timedelta(days=1)
		
	return {
		"labels": dates, 
		"datasets": [
			{"name": "Revenue", "values": revenue},
			{"name": "Expenses", "values": expenses}
		]
	}

def get_expense_breakdown(from_date, to_date):
	allowed_properties = allowed_properties_for_report()
	property_sql = ""
	property_params = ()
	if allowed_properties is not None:
		property_sql = "AND property IN %s"
		property_params = (tuple(allowed_properties or [""]),)
	data = frappe.db.sql(f"""
		SELECT expense_category, SUM(grand_total) as total
		FROM `tabHospitality Expense`
		WHERE expense_date BETWEEN %s AND %s AND docstatus = 1
		{property_sql}
		GROUP BY expense_category
	""", (from_date, to_date) + property_params, as_dict=1)
	
	return {
		"labels": [d.expense_category for d in data],
		"datasets": [{"values": [flt(d.total) for d in data]}]
	}

def get_sales_by_reception(from_date, to_date):
	allowed_properties = allowed_properties_for_report()
	property_sql = ""
	property_params = ()
	if allowed_properties is not None:
		property_sql = "AND ft.property IN %s"
		property_params = (tuple(allowed_properties or [""]),)
	data = frappe.db.sql(f"""
		SELECT room.hotel_reception, SUM(ft.amount) as total
		FROM `tabFolio Transaction` ft
		JOIN `tabGuest Folio` gf ON ft.parent = gf.name
		JOIN `tabHotel Reservation` res ON gf.reservation = res.name
		JOIN `tabHotel Room` room ON res.room = room.room_number
		WHERE ft.posting_date BETWEEN %s AND %s
		AND ft.is_void = 0
		AND (ft.reference_doctype != 'Payment Entry' OR ft.reference_doctype IS NULL)
		AND COALESCE(ft.mirror_source, '') = ''
		AND gf.is_company_master = 0
		AND NOT EXISTS (SELECT 1 FROM `tabHotel Group Booking` hgb WHERE hgb.master_folio = gf.name)
		{property_sql}
		GROUP BY room.hotel_reception
	""", (from_date, to_date) + property_params, as_dict=1)
	
	return {
		"labels": [d.hotel_reception or "Unknown" for d in data],
		"datasets": [{"values": [flt(d.total) for d in data]}]
	}

def get_payment_mode_distribution(from_date, to_date):
	# Payment Entry không có field "property" như doctype riêng của app này —
	# dùng "hospitality_property" (custom field do migrations/property_v2.py tạo).
	allowed_properties = allowed_properties_for_report()
	property_sql = ""
	property_params = ()
	if allowed_properties is not None:
		property_sql = "AND hospitality_property IN %s"
		property_params = (tuple(allowed_properties or [""]),)
	data = frappe.db.sql(f"""
		SELECT mode_of_payment, SUM(paid_amount) as total
		FROM `tabPayment Entry`
		WHERE posting_date BETWEEN %s AND %s AND docstatus = 1
		{property_sql}
		GROUP BY mode_of_payment
	""", (from_date, to_date) + property_params, as_dict=1)
	
	return {
		"labels": [d.mode_of_payment for d in data],
		"datasets": [{"values": [flt(d.total) for d in data]}]
	}

def get_maintenance_cost_by_room_type(from_date, to_date):
	allowed_properties = allowed_properties_for_report()
	property_sql = ""
	property_params = ()
	if allowed_properties is not None:
		property_sql = "AND exp.property IN %s"
		property_params = (tuple(allowed_properties or [""]),)
	data = frappe.db.sql(f"""
		SELECT room.room_type, SUM(exp.grand_total) as total
		FROM `tabHospitality Expense` exp
		JOIN `tabHotel Maintenance Request` mr ON exp.maintenance_request = mr.name
		JOIN `tabHotel Room` room ON mr.room = room.room_number
		WHERE exp.expense_date BETWEEN %s AND %s AND exp.docstatus = 1
		{property_sql}
		GROUP BY room.room_type
	""", (from_date, to_date) + property_params, as_dict=1)
	
	return {
		"labels": [d.room_type for d in data],
		"datasets": [{"values": [flt(d.total) for d in data]}]
	}
def get_gross_profit_margin_trend(from_date, to_date):
	allowed_properties = allowed_properties_for_report()
	ft_property_sql = ""
	property_params = ()
	exp_filters_extra = {}
	if allowed_properties is not None:
		ft_property_sql = "AND property IN %s"
		property_params = (tuple(allowed_properties or [""]),)
		exp_filters_extra["property"] = ["in", allowed_properties or [""]]

	dates = []
	values = []
	curr = getdate(from_date)
	end = getdate(to_date)

	while curr <= end:
		d_str = curr.strftime("%Y-%m-%d")
		rev = frappe.db.sql(f"""
			SELECT SUM(amount) FROM `tabFolio Transaction`
			WHERE posting_date = %s AND is_void = 0
			AND (reference_doctype != 'Payment Entry' OR reference_doctype IS NULL)
			AND COALESCE(mirror_source, '') = ''
			{ft_property_sql}
		""", (d_str,) + property_params)[0][0] or 0

		exp = frappe.db.get_value("Hospitality Expense", {"expense_date": d_str, "docstatus": 1, **exp_filters_extra}, "SUM(grand_total)") or 0

		dates.append(d_str)
		margin = round(((flt(rev) - flt(exp)) / flt(rev)) * 100.0, 2) if flt(rev) > 0 else 0
		values.append(margin)
		curr += timedelta(days=1)

	return {"labels": dates, "datasets": [{"name": "GP Margin %", "values": values}]}

@frappe.whitelist()
def get_today_occupancy():
	allowed_properties = allowed_properties_for_report()
	room_filters = {"is_enabled": 1}
	res_property_sql = ""
	res_property_params = ()
	if allowed_properties is not None:
		room_filters["property"] = ["in", allowed_properties or [""]]
		res_property_sql = "AND property IN %s"
		res_property_params = (tuple(allowed_properties or [""]),)
	total_rooms = frappe.db.count("Hotel Room", room_filters) or 1
	d_str = nowdate()
	occ_count = frappe.db.sql(f"""
		SELECT COUNT(*) FROM `tabHotel Reservation`
		WHERE arrival_date <= %s AND departure_date > %s
		AND status NOT IN ('Cancelled', 'No Show')
		{res_property_sql}
	""", (d_str, d_str) + res_property_params)[0][0] or 0
	return round((flt(occ_count) / total_rooms) * 100.0, 2)

@frappe.whitelist()
def get_today_revenue():
	allowed_properties = allowed_properties_for_report()
	property_sql = ""
	property_params = ()
	if allowed_properties is not None:
		property_sql = "AND property IN %s"
		property_params = (tuple(allowed_properties or [""]),)
	return frappe.db.sql(f"""
		SELECT SUM(amount) FROM `tabFolio Transaction`
		WHERE posting_date = %s AND is_void = 0
		AND (reference_doctype != 'Payment Entry' OR reference_doctype IS NULL)
		AND COALESCE(mirror_source, '') = ''
		{property_sql}
	""", (nowdate(),) + property_params)[0][0] or 0

@frappe.whitelist()
def get_today_expenses():
	allowed_properties = allowed_properties_for_report()
	filters = {"expense_date": nowdate(), "docstatus": 1}
	if allowed_properties is not None:
		filters["property"] = ["in", allowed_properties or [""]]
	return frappe.db.get_value("Hospitality Expense", filters, "SUM(grand_total)") or 0
