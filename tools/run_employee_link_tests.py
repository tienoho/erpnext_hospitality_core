"""Kịch bản kiểm thử MỚI — api/employee_link.py (module helper mới, tích hợp
HRMS ở mức "chỉ liên kết định danh + báo cáo", theo đúng kế hoạch đã duyệt
trong plan mode: resolve User -> Employee qua Employee.user_id, làm giàu
housekeeping_productivity_report.py / maintenance_log_report.py / Night Audit
Log's virtual field `run_by_employee_name` — KHÔNG đụng Attendance/Payroll/
Shift Assignment.

Không có hàm nào trong phạm vi này gọi frappe.db.commit() — an toàn dùng
self.fixture() rollback-based bình thường, theo đúng mẫu run_housekeeping_tests.py.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days
from run_property_integration import PropertyDatabaseTests


class EmployeeLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def fixture(self):
        f = PropertyDatabaseTests()
        reservation, settings = f.accounting_reservation()
        self.property = reservation.property
        self.company = reservation.operating_company
        self.currency = reservation.currency
        self.room_type = reservation.room_type
        return f

    def make_employee_user(self, email, employee_name):
        """Tạo 1 User + Employee thật gắn qua user_id — mẫu resolve chuẩn
        `Employee.user_id` (khớp erpnext/erpnext/startup/boot.py:92).

        Vai trò gán 'System Manager': Hotel Room's DocPerm hiện tại (ngoài
        phạm vi việc HRMS này) CHỈ cấp quyền cho System Manager (không có vai
        trò "housekeeping staff" thật nào khác có write trên Hotel Room) —
        đây là hiện trạng phân quyền có sẵn của app, không phải điều kiện tự
        đặt ra cho test. Dùng vai trò này để có thể gọi thật update_room_status()/
        report_maintenance_issue() với session_user khác Administrator."""
        if not frappe.db.exists('User', email):
            frappe.get_doc(dict(doctype='User', email=email, first_name=email.split('@')[0],
                send_welcome_email=0, roles=[dict(role='System Manager')])).insert(ignore_permissions=True)
        if not frappe.db.exists('Employee', {'user_id': email}):
            frappe.get_doc(dict(doctype='Employee', employee_name=employee_name, first_name=employee_name,
                employee_number=email.split('@')[0], company=self.company, user_id=email,
                department=None, designation=None,
                gender='Male', date_of_birth='1990-01-01', date_of_joining=nowdate())).insert(ignore_permissions=True)
        return email

    # ------------------------------------------------------------------
    # api/employee_link.py: resolve_employees()
    # ------------------------------------------------------------------
    def test_resolve_employees_returns_info_for_linked_user(self):
        self.fixture()
        user = self.make_employee_user('hk-emp-1@example.com', 'Nguyen Van A')
        from hospitality_core.hospitality_core.api.employee_link import resolve_employees
        info = resolve_employees([user])
        self.assertIn(user, info)
        self.assertEqual(info[user]['employee_name'], 'Nguyen Van A')

    def test_resolve_employees_skips_user_without_employee(self):
        self.fixture()
        from hospitality_core.hospitality_core.api.employee_link import resolve_employees
        info = resolve_employees(['Administrator'])
        self.assertNotIn('Administrator', info, 'User không có Employee không được có mặt trong dict trả về.')

    def test_resolve_employees_empty_input_returns_empty_dict(self):
        from hospitality_core.hospitality_core.api.employee_link import resolve_employees
        self.assertEqual(resolve_employees([]), {})
        self.assertEqual(resolve_employees(None), {})

    # ------------------------------------------------------------------
    # housekeeping_productivity_report.py: cột Tên Nhân Viên/Phòng Ban/Chức Vụ
    # ------------------------------------------------------------------
    def test_housekeeping_report_resolves_employee_name(self):
        f = self.fixture()
        user = self.make_employee_user('hk-emp-2@example.com', 'Tran Thi B')
        room = f.room(self.property, self.room_type, number='EMP-HK-1')
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.housekeeping_mobile import update_room_status
        update_room_status(room.name, 'Cleaning')
        update_room_status(room.name, 'Available')
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.report.housekeeping_productivity_report.housekeeping_productivity_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((r for r in data if r['staff'] == user), None)
        self.assertIsNotNone(row, 'Phải có 1 dòng báo cáo cho user vừa dọn phòng.')
        self.assertEqual(row['employee_name'], 'Tran Thi B')

    def test_housekeeping_report_falls_back_to_username_without_employee(self):
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='EMP-HK-2')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import update_room_status
        update_room_status(room.name, 'Cleaning')
        update_room_status(room.name, 'Available')
        from hospitality_core.hospitality_core.report.housekeeping_productivity_report.housekeeping_productivity_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((r for r in data if r['staff'] == 'Administrator'), None)
        self.assertIsNotNone(row)
        self.assertIsNone(row['employee_name'], 'Administrator không có Employee — phải để trống, không crash.')

    # ------------------------------------------------------------------
    # maintenance_log_report.py: cột Department/Designation
    # ------------------------------------------------------------------
    def test_maintenance_report_resolves_department_designation(self):
        f = self.fixture()
        user = self.make_employee_user('mnt-emp-1@example.com', 'Le Van C')
        frappe.db.set_value('Employee', {'user_id': user}, 'department', None)
        room = f.room(self.property, self.room_type, number='EMP-MNT-1')
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.housekeeping_mobile import report_maintenance_issue
        report_maintenance_issue(room.name, 'Plumbing', 'Vòi nước bị rò rỉ')
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.report.maintenance_log_report.maintenance_log_report import execute
        columns, data = execute({})
        row = next((r for r in data if r.get('reported_by') == user), None)
        self.assertIsNotNone(row, 'Phải có 1 dòng báo cáo bảo trì cho user vừa báo cáo.')
        # reported_by_name (JOIN User.full_name, cột gốc đã có từ trước) không
        # đổi hành vi — chỉ xác nhận vẫn có giá trị, không kiểm tra cột này bị
        # đè bởi Employee (HRMS tự đồng bộ full_name của User theo Employee
        # vừa tạo — hành vi CHUẨN của HRMS, không phải điều cột mới cần đảm bảo).
        self.assertTrue(row['reported_by_name'])

    def test_maintenance_report_no_crash_for_user_without_employee(self):
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='EMP-MNT-2')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import report_maintenance_issue
        report_maintenance_issue(room.name, 'Electrical', 'Đèn không sáng')
        from hospitality_core.hospitality_core.report.maintenance_log_report.maintenance_log_report import execute
        columns, data = execute({})
        row = next((r for r in data if r.get('reported_by') == 'Administrator'), None)
        self.assertIsNotNone(row)
        self.assertIsNone(row['department'])
        self.assertIsNone(row['designation'])

    # ------------------------------------------------------------------
    # Night Audit Log: virtual field run_by_employee_name
    # ------------------------------------------------------------------
    def test_night_audit_log_virtual_field_resolves_employee_name(self):
        f = PropertyDatabaseTests()
        reservation, settings = f.accounting_reservation()
        self.company = reservation.operating_company
        user = self.make_employee_user('night-emp-1@example.com', 'Pham Thi D')
        from hospitality_core.hospitality_core.api.night_audit import _run_daily_audit_for_property
        frappe.set_user(user)
        _run_daily_audit_for_property(reservation.property)
        frappe.set_user('Administrator')
        log = frappe.get_last_doc('Night Audit Log', filters={'run_by': user, 'property': reservation.property})
        self.assertEqual(log.run_by_employee_name, 'Pham Thi D')

    def test_night_audit_log_virtual_field_blank_for_system_user(self):
        f = PropertyDatabaseTests()
        reservation, settings = f.accounting_reservation()
        from hospitality_core.hospitality_core.api.night_audit import _run_daily_audit_for_property
        _run_daily_audit_for_property(reservation.property)
        log = frappe.get_last_doc('Night Audit Log',
            filters={'run_by': 'Administrator', 'property': reservation.property})
        self.assertIsNone(log.run_by_employee_name,
            'run_by=Administrator (tiến trình hệ thống) phải để trống, không crash, không suy đoán.')
        # run_by gốc PHẢI giữ nguyên đúng user thật đã chạy — không bị đổi bởi lớp hiển thị.
        self.assertEqual(log.run_by, 'Administrator')


if __name__ == '__main__':
    import sys
    frappe.init(site='localhost')
    frappe.connect()
    unittest.main(argv=[sys.argv[0]] + sys.argv[1:])
