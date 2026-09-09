"""Kịch bản kiểm thử MỚI — api/housekeeping_mobile.py + page/housekeeping_view/
housekeeping_view.py + doctype/hotel_maintenance_request (Đợt 2, mục 2 của kế
hoạch "Kịch bản kiểm thử TOÀN BỘ tính năng còn lại"). Cả 3 module CHƯA TỪNG có
1 dòng test sống nào, dù đã qua nhiều vòng fix tĩnh (mobile thiếu khóa row so
với desktop, Maintenance Request "Cancelled" làm kẹt Out of Order vĩnh viễn).

Không có hàm nào trong các module này gọi frappe.db.commit() (đã grep trước
khi viết) — an toàn dùng self.fixture() rollback-based bình thường.

Chạy trên site test riêng, dữ liệu rollback sau mỗi ca.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days
from run_property_integration import PropertyDatabaseTests


class HousekeepingTests(unittest.TestCase):
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

    def checkin_room(self, f, number):
        room = f.room(self.property, self.room_type, number=number)
        guest = frappe.get_doc(dict(doctype='Guest', full_name=f'HK Guest {number}',
            guest_type='Regular')).insert(ignore_permissions=True)
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property, guest=guest.name,
            room=room.name, room_type=self.room_type, hotel_reception=room.hotel_reception,
            currency=self.currency, arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        from hospitality_core.hospitality_core.doctype.hotel_reservation.hotel_reservation import check_in_guest
        check_in_guest(res.name)
        res.reload()
        return room, res

    # ------------------------------------------------------------------
    # housekeeping_mobile.py: update_room_status()
    # ------------------------------------------------------------------
    def test_mobile_update_status_normal_transition_and_logs(self):
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='HK-1')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import update_room_status
        result = update_room_status(room.name, 'Cleaning')
        self.assertEqual(result, 'Cleaning')
        self.assertEqual(frappe.db.get_value('Hotel Room', room.name, 'status'), 'Cleaning')
        log = frappe.get_all('Housekeeping Room Status Log', filters={'room': room.name}, fields=['previous_status', 'new_status'])
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0].new_status, 'Cleaning')

    def test_mobile_update_status_rejects_invalid_status(self):
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='HK-2')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import update_room_status
        with self.assertRaisesRegex(frappe.ValidationError, 'Invalid status'):
            update_room_status(room.name, 'Sparkling Clean')

    def test_mobile_update_status_guards_available_and_inspected_when_occupied(self):
        f = self.fixture()
        room, res = self.checkin_room(f, 'HK-3')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import update_room_status
        r1 = update_room_status(room.name, 'Available')
        self.assertEqual(r1, 'Occupied', 'Khong duoc phep tra "trong" 1 phong dang co khach Checked In.')
        r2 = update_room_status(room.name, 'Inspected')
        self.assertEqual(r2, 'Occupied', 'Cung phai chan tuong tu cho "Inspected" (mobile da fix ca 2 nhanh).')

    def test_mobile_update_status_accepts_room_number_not_just_docname(self):
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='HK-BY-NUMBER')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import update_room_status
        update_room_status('HK-BY-NUMBER', 'Dirty')
        self.assertEqual(frappe.db.get_value('Hotel Room', room.name, 'status'), 'Dirty')

    # ------------------------------------------------------------------
    # housekeeping_view.py: set_room_status() / batch_set_room_status()
    # ------------------------------------------------------------------
    def test_desktop_set_status_guards_available_when_occupied(self):
        f = self.fixture()
        room, res = self.checkin_room(f, 'HK-4')
        from hospitality_core.hospitality_core.page.housekeeping_view.housekeeping_view import set_room_status
        result = set_room_status(room.name, 'Available')
        self.assertEqual(result['status'], 'Occupied')

    def test_desktop_set_status_guards_inspected_when_occupied(self):
        # PHÁT HIỆN THẬT, ĐÃ FIX: set_room_status() (desktop) trước đây CHỈ
        # ép "Available" về "Occupied" khi phòng còn khách Checked In, KHÔNG
        # ép "Inspected" — khác với update_room_status() (mobile) đã ép cả 2
        # nhánh từ 1 vòng review trước. Đã đồng bộ desktop theo mobile.
        f = self.fixture()
        room, res = self.checkin_room(f, 'HK-5')
        from hospitality_core.hospitality_core.page.housekeeping_view.housekeeping_view import set_room_status
        result = set_room_status(room.name, 'Inspected')
        self.assertEqual(result['status'], 'Occupied',
            'Phai dong bo voi ban mobile: khong duoc de "Inspected" ghi de 1 phong dang co khach that.')

    def test_batch_set_room_status_isolates_individual_failures(self):
        f = self.fixture()
        room1 = f.room(self.property, self.room_type, number='HK-BATCH-1')
        room2 = f.room(self.property, self.room_type, number='HK-BATCH-2')
        from hospitality_core.hospitality_core.page.housekeeping_view.housekeeping_view import batch_set_room_status
        result = batch_set_room_status([room1.name, 'NON-EXISTENT-ROOM-XYZ', room2.name], 'Cleaning')
        self.assertEqual(result['updated_count'], 2, '1 phong loi (khong ton tai) khong duoc lam dung ca 2 phong con lai.')
        self.assertEqual(frappe.db.get_value('Hotel Room', room1.name, 'status'), 'Cleaning')
        self.assertEqual(frappe.db.get_value('Hotel Room', room2.name, 'status'), 'Cleaning')

    # ------------------------------------------------------------------
    # housekeeping_mobile.py: log_minibar_consumption()
    # ------------------------------------------------------------------
    def test_log_minibar_consumption_posts_folio_transaction(self):
        f = self.fixture()
        room, res = self.checkin_room(f, 'HK-MINIBAR-1')
        item = 'HK-MINIBAR-ITEM'
        if not frappe.db.exists('Item', item):
            frappe.get_doc(dict(doctype='Item', item_code=item, item_name=item, item_group='Services',
                stock_uom='Nos', is_stock_item=0, is_sales_item=1)).insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.api.housekeeping_mobile import log_minibar_consumption
        balance_before = frappe.db.get_value('Guest Folio', res.folio, 'outstanding_balance')
        posted = log_minibar_consumption(room.name, [dict(item=item, qty=1, amount=50000)])
        self.assertEqual(len(posted), 1)
        balance_after = frappe.db.get_value('Guest Folio', res.folio, 'outstanding_balance')
        self.assertEqual(balance_after, (balance_before or 0) + 50000)

    def test_log_minibar_consumption_requires_checked_in_folio(self):
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='HK-MINIBAR-2')  # Chua check-in, chua co folio mo.
        item = 'HK-MINIBAR-ITEM'
        if not frappe.db.exists('Item', item):
            frappe.get_doc(dict(doctype='Item', item_code=item, item_name=item, item_group='Services',
                stock_uom='Nos', is_stock_item=0, is_sales_item=1)).insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.api.housekeeping_mobile import log_minibar_consumption
        with self.assertRaisesRegex(frappe.ValidationError, 'Không tìm thấy đặt phòng'):
            log_minibar_consumption(room.name, [dict(item=item, qty=1, amount=50000)])

    def test_log_minibar_consumption_skips_non_positive_amounts(self):
        f = self.fixture()
        room, res = self.checkin_room(f, 'HK-MINIBAR-3')
        item = 'HK-MINIBAR-ITEM'
        if not frappe.db.exists('Item', item):
            frappe.get_doc(dict(doctype='Item', item_code=item, item_name=item, item_group='Services',
                stock_uom='Nos', is_stock_item=0, is_sales_item=1)).insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.api.housekeeping_mobile import log_minibar_consumption
        posted = log_minibar_consumption(room.name, [dict(item=item, qty=1, amount=0), dict(item=item, qty=1, amount=-5)])
        self.assertEqual(posted, [], 'So tien <=0 phai bi bo qua, khong tao Folio Transaction rac.')

    # ------------------------------------------------------------------
    # create_lost_and_found_report() / report_maintenance_issue()
    # ------------------------------------------------------------------
    def test_create_lost_and_found_report(self):
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='HK-LF-1')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import create_lost_and_found_report
        name = create_lost_and_found_report('Sac tay mau den', room.name)
        doc = frappe.get_doc('Lost and Found Item', name)
        self.assertEqual(doc.status, 'Found')
        self.assertEqual(doc.found_location, room.name)

    def test_report_maintenance_issue_marks_room_out_of_order(self):
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='HK-MAINT-1')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import report_maintenance_issue
        name = report_maintenance_issue(room.name, 'Plumbing', 'Voi nuoc bi ro')
        self.assertEqual(frappe.db.get_value('Hotel Room', room.name, 'status'), 'Out of Order')
        doc = frappe.get_doc('Hotel Maintenance Request', name)
        self.assertEqual(doc.status, 'Reported')

    def test_maintenance_cancelled_releases_room_from_out_of_order(self):
        # Xac nhan song dong fix da lam o vong review tinh truoc: "Cancelled"
        # (khac "Completed") CUNG phai giai phong phong, khong duoc de ket
        # "Out of Order" vinh vien.
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='HK-MAINT-2')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import report_maintenance_issue
        name = report_maintenance_issue(room.name, 'Electrical', 'Den hong')
        self.assertEqual(frappe.db.get_value('Hotel Room', room.name, 'status'), 'Out of Order')
        doc = frappe.get_doc('Hotel Maintenance Request', name)
        doc.status = 'Cancelled'
        doc.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value('Hotel Room', room.name, 'status'), 'Dirty',
            'Huy yeu cau bao tri phai giai phong phong ve Dirty, khong ket Out of Order vinh vien.')

    def test_maintenance_completed_requires_resolution_notes(self):
        f = self.fixture()
        room = f.room(self.property, self.room_type, number='HK-MAINT-3')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import report_maintenance_issue
        name = report_maintenance_issue(room.name, 'HVAC', 'Dieu hoa khong lanh')
        doc = frappe.get_doc('Hotel Maintenance Request', name)
        doc.status = 'Completed'
        with self.assertRaisesRegex(frappe.ValidationError, 'Resolution Notes'):
            doc.save(ignore_permissions=True)

    def test_maintenance_does_not_overwrite_occupied_room(self):
        # Neu phong dang co khach Checked In, bao cao bao tri KHONG duoc de
        # de "Out of Order" (khach van dang o, khong the khoa phong).
        f = self.fixture()
        room, res = self.checkin_room(f, 'HK-MAINT-4')
        from hospitality_core.hospitality_core.api.housekeeping_mobile import report_maintenance_issue
        report_maintenance_issue(room.name, 'Furniture', 'Ghe bi gay')
        self.assertEqual(frappe.db.get_value('Hotel Room', room.name, 'status'), 'Occupied',
            'Khong duoc de nhap yeu cau bao tri lam mat trang thai Occupied that.')


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(HousekeepingTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
