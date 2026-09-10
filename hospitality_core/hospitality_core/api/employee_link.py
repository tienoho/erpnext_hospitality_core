import frappe


def resolve_employees(user_ids):
	"""Resolve 1 danh sách User -> thông tin Employee tương ứng (nếu có), qua
	đúng field `Employee.user_id` (Link User) — mẫu tra cứu an toàn giống hệt
	`erpnext/erpnext/startup/boot.py`'s cách lấy Employee của user hiện tại.

	Trả về dict {user_id: {"employee_name":.., "department":.., "designation":..}}
	— CHỈ chứa các user_id thực sự resolve được Employee. User không có Employee
	(Administrator, tài khoản hệ thống/API, nhân viên chưa tạo hồ sơ Employee)
	sẽ KHÔNG có mặt trong dict trả về; nơi gọi tự fallback hiển thị nguyên
	user_id gốc thay vì coi đây là lỗi.

	Dùng đúng 1 câu truy vấn cho toàn bộ danh sách (không N+1) — nơi gọi nên
	thu thập hết user_id cần resolve trong 1 lượt báo cáo rồi gọi hàm này 1 lần.
	"""
	unique_ids = sorted({u for u in (user_ids or []) if u})
	if not unique_ids:
		return {}

	rows = frappe.get_all(
		"Employee",
		filters={"user_id": ["in", unique_ids]},
		fields=["user_id", "employee_name", "department", "designation"],
	)
	return {
		row.user_id: {
			"employee_name": row.employee_name,
			"department": row.department,
			"designation": row.designation,
		}
		for row in rows
	}
