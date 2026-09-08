import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, add_days
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Nhân Viên"), "fieldname": "staff", "fieldtype": "Link", "options": "User", "width": 200},
		{"label": _("Ngày"), "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": _("Số Phòng Đã Dọn"), "fieldname": "rooms_cleaned", "fieldtype": "Int", "width": 130},
		{"label": _("Tổng Thời Gian Dọn (Phút)"), "fieldname": "total_minutes", "fieldtype": "Float", "width": 170, "precision": 1},
		{"label": _("TB Phút / Phòng"), "fieldname": "avg_minutes", "fieldtype": "Float", "width": 130, "precision": 1},
		{"label": _("Phiên Bị Gián Đoạn"), "fieldname": "interrupted_sessions", "fieldtype": "Int", "width": 130},
		{"label": _("Sự Cố Phát Hiện"), "fieldname": "maintenance_flagged", "fieldtype": "Int", "width": 130},
	]


def get_data(filters):
	"""
	Năng suất buồng phòng theo nhân viên — trước đây KHÔNG THỂ xây báo cáo này
	vì `set_room_status()`/`update_room_status()` chỉ ghi đè trực tiếp
	Hotel Room.status, không lưu ai đổi/lúc nào (đã bổ sung DocType
	"Housekeeping Room Status Log" + nối dây ghi log vào cả 2 luồng để có dữ
	liệu này). Thời gian dọn phòng = khoảng cách giữa lúc 1 phòng chuyển sang
    "Cleaning" và lần chuyển tiếp theo sang "Inspected"/"Available"/"Occupied"
	CỦA CHÍNH PHÒNG ĐÓ — không có khái niệm phiên làm việc (session) tường
	minh trong dữ liệu, đây là suy luận tốt nhất có thể từ chuỗi log tuần tự.
	"Sự Cố Phát Hiện" chỉ là suy luận gần đúng theo (nhân viên báo cáo, ngày
	báo cáo) của Hotel Maintenance Request — dữ liệu hiện có KHÔNG có liên kết
	trực tiếp giữa 1 phiên dọn phòng cụ thể và 1 yêu cầu bảo trì cụ thể.
	"""
	from_date = getdate(filters.get("from_date"))
	to_date = getdate(filters.get("to_date"))
	staff_filter = filters.get("staff")

	# Mở rộng cửa sổ truy vấn 1 ngày về mỗi phía so với khoảng lọc thật —
	# TRƯỚC ĐÂY chỉ query đúng [from_date, to_date]: 1 phiên dọn phòng bắt đầu
	# 23:58 ngày to_date nhưng hoàn tất 00:05 hôm sau (rất phổ biến vì ca dọn
	# phòng thường chạy quanh nửa đêm) bị RỚT HOÀN TOÀN khỏi báo cáo — không
	# tính cho ai, không có dấu hiệu bất thường nào, làm lệch số liệu năng
	# suất một cách có hệ thống ở biên ngày. Nay query rộng hơn rồi lọc lại
	# theo NGÀY BẮT ĐẦU dọn (s["date"]) ở bước tổng hợp bên dưới.
	query_from = add_days(from_date, -1)
	query_to = add_days(to_date, 1)

	log_params = {"query_from": query_from, "query_to": query_to}
	property_condition = ""
	allowed_properties = allowed_properties_for_report()
	if allowed_properties is not None:
		property_condition = "AND property IN %(_properties)s"
		log_params["_properties"] = allowed_properties or [""]

	logs = frappe.db.sql(f"""
		SELECT room, new_status, changed_by, changed_on
		FROM `tabHousekeeping Room Status Log`
		WHERE DATE(changed_on) BETWEEN %(query_from)s AND %(query_to)s
		{property_condition}
		ORDER BY room, changed_on ASC
	""", log_params, as_dict=True)

	completion_statuses = {"Inspected", "Available", "Occupied"}
	pending_by_room = {}
	sessions = []

	for row in logs:
		if row.new_status == "Cleaning":
			existing = pending_by_room.get(row.room)
			if existing:
				# Phòng được đánh dấu "Cleaning" LẦN NỮA trước khi phiên trước
				# đó hoàn tất (2 nhân viên cùng nhận 1 phòng, hoặc 1 người bị
				# gián đoạn giữa chừng) — TRƯỚC ĐÂY phiên cũ bị ghi đè và MẤT
				# HẲN, không tính cho ai. Nay tính phiên cũ là "bị gián đoạn":
				# vẫn cộng thời gian đã dọn (tới lúc bị ghi đè) cho đúng nhân
				# viên gốc, và đếm riêng để quản lý biết mà kiểm tra thủ công
				# thay vì số liệu biến mất không dấu vết.
				duration_minutes = (get_datetime(row.changed_on) - get_datetime(existing.changed_on)).total_seconds() / 60.0
				if duration_minutes >= 0:
					sessions.append({
						"staff": existing.changed_by,
						"date": getdate(existing.changed_on),
						"duration": duration_minutes,
						"interrupted": True,
					})
			pending_by_room[row.room] = row
		elif row.new_status in completion_statuses and row.room in pending_by_room:
			start_row = pending_by_room.pop(row.room)
			duration_minutes = (get_datetime(row.changed_on) - get_datetime(start_row.changed_on)).total_seconds() / 60.0
			if duration_minutes >= 0:
				sessions.append({
					"staff": start_row.changed_by,
					"date": getdate(start_row.changed_on),
					"duration": duration_minutes,
					"interrupted": False,
				})

	agg = {}
	for s in sessions:
		if staff_filter and s["staff"] != staff_filter:
			continue
		# Chỉ giữ phiên có NGÀY BẮT ĐẦU nằm trong khoảng lọc thật — phiên bắt
		# đầu trước from_date (dù hoàn tất trong khoảng) vẫn thuộc về ngày
		# trước đó nên bị loại ở đây, đúng quy ước "tính theo ngày bắt đầu".
		if s["date"] < from_date or s["date"] > to_date:
			continue
		key = (s["staff"], s["date"])
		if key not in agg:
			agg[key] = {"staff": s["staff"], "date": s["date"], "rooms_cleaned": 0, "total_minutes": 0.0, "interrupted_sessions": 0}
		agg[key]["rooms_cleaned"] += 1
		agg[key]["total_minutes"] += s["duration"]
		if s["interrupted"]:
			agg[key]["interrupted_sessions"] += 1

	maint_params = {"from_date": from_date, "to_date": to_date}
	maint_property_condition = ""
	if allowed_properties is not None:
		maint_property_condition = "AND property IN %(_properties)s"
		maint_params["_properties"] = allowed_properties or [""]

	maint_rows = frappe.db.sql(f"""
		SELECT reported_by, DATE(creation) as report_date, COUNT(*) as cnt
		FROM `tabHotel Maintenance Request`
		WHERE DATE(creation) BETWEEN %(from_date)s AND %(to_date)s
		{maint_property_condition}
		GROUP BY reported_by, DATE(creation)
	""", maint_params, as_dict=True)
	maint_map = {(m.reported_by, m.report_date): m.cnt for m in maint_rows}

	result = []
	for key, val in agg.items():
		val["avg_minutes"] = (val["total_minutes"] / val["rooms_cleaned"]) if val["rooms_cleaned"] else 0
		val["maintenance_flagged"] = maint_map.get(key, 0)
		result.append(val)

	result.sort(key=lambda r: (r["date"], r["staff"] or ""))
	return result
