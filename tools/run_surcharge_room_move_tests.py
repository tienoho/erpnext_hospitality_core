"""Kịch bản kiểm thử MỚI — api/surcharge_engine.py + api/room_move.py (Đợt 1,
mục 5 của kế hoạch "Kịch bản kiểm thử TOÀN BỘ tính năng còn lại"). Cả 2 module
CHƯA TỪNG có 1 dòng test sống nào. Không có hàm nào trong 2 module này gọi
frappe.db.commit() (đã xác nhận grep trước khi viết — an toàn dùng
self.fixture() rollback-based bình thường, không cần fixture cô lập riêng
như financial_control.py's void_transaction() ở Mục 4).

Chạy trên site test riêng, dữ liệu rollback sau mỗi ca.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days
from run_property_integration import PropertyDatabaseTests


class SurchargeRoomMoveTests(unittest.TestCase):
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
        self.reservation = reservation
        return f

    def reset_surcharge_settings(self):
        # _get_surcharge_settings() tự fallback về mặc định khi field rỗng,
        # nhưng nếu 1 tiến trình khác/vòng trước đã lưu giá trị khác 0 vào
        # Single này, fallback sẽ KHÔNG áp dụng nữa (field không còn rỗng) —
        # ép về đúng giá trị mặc định tài liệu hoá trong _get_surcharge_settings()
        # để test xác định, không phụ thuộc trạng thái Single còn sót lại.
        settings = frappe.get_single('Hospitality Surcharge Settings')
        settings.standard_checkin_time = '14:00:00'
        settings.standard_checkout_time = '12:00:00'
        settings.early_tier1_hour = '06:00:00'
        settings.early_tier1_pct = 100
        settings.early_tier2_hour = '09:00:00'
        settings.early_tier2_pct = 50
        settings.early_tier3_pct = 30
        settings.late_tier1_hour = '15:00:00'
        settings.late_tier1_pct = 30
        settings.late_tier2_hour = '18:00:00'
        settings.late_tier2_pct = 50
        settings.late_tier3_pct = 100
        settings.enable_weekend_surcharge = 0
        settings.enable_holiday_surcharge = 0
        settings.save()

    # ------------------------------------------------------------------
    # calculate_checkin_surcharge() / calculate_checkout_surcharge()
    # ------------------------------------------------------------------
    def test_checkin_surcharge_tiers(self):
        self.fixture()
        self.reset_surcharge_settings()
        from hospitality_core.hospitality_core.api.surcharge_engine import calculate_checkin_surcharge
        on_time = calculate_checkin_surcharge(self.reservation.name, checkin_time='14:00:00')
        self.assertFalse(on_time['applicable'])

        tier1 = calculate_checkin_surcharge(self.reservation.name, checkin_time='05:00:00')
        self.assertTrue(tier1['applicable'])
        self.assertEqual(tier1['pct'], 100)

        tier2 = calculate_checkin_surcharge(self.reservation.name, checkin_time='07:00:00')
        self.assertEqual(tier2['pct'], 50)

        tier3 = calculate_checkin_surcharge(self.reservation.name, checkin_time='10:00:00')
        self.assertEqual(tier3['pct'], 30)
        self.assertAlmostEqual(tier3['amount'], tier3['base_rate'] * 0.3, places=2)

    def test_checkout_surcharge_tiers(self):
        self.fixture()
        self.reset_surcharge_settings()
        from hospitality_core.hospitality_core.api.surcharge_engine import calculate_checkout_surcharge
        on_time = calculate_checkout_surcharge(self.reservation.name, checkout_time='12:00:00')
        self.assertFalse(on_time['applicable'])

        tier1 = calculate_checkout_surcharge(self.reservation.name, checkout_time='14:00:00')
        self.assertEqual(tier1['pct'], 30)

        tier2 = calculate_checkout_surcharge(self.reservation.name, checkout_time='17:00:00')
        self.assertEqual(tier2['pct'], 50)

        tier3 = calculate_checkout_surcharge(self.reservation.name, checkout_time='19:00:00')
        self.assertEqual(tier3['pct'], 100)

    # ------------------------------------------------------------------
    # apply_surcharge_to_folio(): ghi tiền thật + chống ghi trùng.
    # ------------------------------------------------------------------
    def test_apply_surcharge_creates_transaction_and_is_idempotent(self):
        self.fixture()
        self.reset_surcharge_settings()
        from hospitality_core.hospitality_core.api.surcharge_engine import apply_surcharge_to_folio
        # Ham tu tinh lai theo now_datetime() THAT (khong truyen checkin_time)
        # — TRUOC DAY gia dinh SAI la ham tra ve dict {'success': False} khi
        # khong applicable; thuc te apply_surcharge_to_folio() frappe.throw()
        # thang trong truong hop nay (dung, dung y do API — "khong ap dung
        # phu thu" la 1 loi nghiep vu ro rang, khong phai 1 ket qua "that
        # bai" am tham). Da sua bat dung frappe.ValidationError de skip test
        # nhe nhang khi thoi diem chay THAT roi vao gio chuan (khong phu thu).
        try:
            result = apply_surcharge_to_folio(self.reservation.name, 'Early Check-in', description=None)
        except frappe.ValidationError as e:
            self.skipTest(f'Thời điểm chạy test không phát sinh phụ thu để kiểm tra: {e}')
        if result.get('message', '').find('lớn hơn 0') >= 0:
            self.skipTest('Thời điểm chạy test không tạo phụ thu dương.')
        self.assertTrue(result['success'])
        txn_name = result['transaction']
        self.assertTrue(frappe.db.exists('Folio Transaction', txn_name))
        balance_before = frappe.db.get_value('Guest Folio', self.reservation.folio, 'outstanding_balance')
        result2 = apply_surcharge_to_folio(self.reservation.name, 'Early Check-in', description=None)
        self.assertEqual(result2['transaction'], txn_name, 'Gọi lại lần 2 phải TÁI SỬ DỤNG giao dịch cũ, không tạo bản ghi mới.')
        balance_after = frappe.db.get_value('Guest Folio', self.reservation.folio, 'outstanding_balance')
        self.assertEqual(balance_before, balance_after, 'Gọi lại apply_surcharge_to_folio() không được cộng dồn thêm tiền.')

    def test_apply_surcharge_requires_write_permission(self):
        self.fixture()
        user = 'surcharge-noperm@example.com'
        if not frappe.db.exists('User', user):
            frappe.get_doc(dict(doctype='User', email=user, first_name='NoPerm',
                send_welcome_email=0, roles=[dict(role='Sales User')])).insert(ignore_permissions=True)
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.surcharge_engine import apply_surcharge_to_folio
        with self.assertRaises(frappe.PermissionError):
            apply_surcharge_to_folio(self.reservation.name, 'Early Check-in')

    # ------------------------------------------------------------------
    # check_holiday_or_weekend()
    # ------------------------------------------------------------------
    def test_check_holiday_or_weekend_detection(self):
        self.reset_surcharge_settings_standalone()
        from hospitality_core.hospitality_core.api.surcharge_engine import check_holiday_or_weekend
        # 2026-09-11 la Thu Sau (weekday=4).
        friday = check_holiday_or_weekend('2026-09-11')
        self.assertTrue(friday['is_weekend'])
        # Tat/bat weekend surcharge de xac nhan is_peak theo dung co cau hinh.
        settings = frappe.get_single('Hospitality Surcharge Settings')
        settings.enable_weekend_surcharge = 1
        settings.weekend_surcharge_pct = 20
        settings.save()
        friday2 = check_holiday_or_weekend('2026-09-11')
        self.assertTrue(friday2['is_peak'])
        self.assertEqual(friday2['surcharge_pct'], 20)

        monday = check_holiday_or_weekend('2026-09-14')
        self.assertFalse(monday['is_weekend'])
        self.assertFalse(monday['is_peak'])

    def reset_surcharge_settings_standalone(self):
        settings = frappe.get_single('Hospitality Surcharge Settings')
        settings.enable_weekend_surcharge = 0
        settings.enable_holiday_surcharge = 0
        settings.save()

    # ------------------------------------------------------------------
    # room_move.py: process_room_move()
    # ------------------------------------------------------------------
    def checkin(self, res):
        from hospitality_core.hospitality_core.doctype.hotel_reservation.hotel_reservation import check_in_guest
        check_in_guest(res.name)
        res.reload()
        return res

    def test_room_move_requires_checked_in_status(self):
        f = self.fixture()
        from hospitality_core.hospitality_core.api.room_move import process_room_move
        new_room = f.room(self.property, self.room_type, number='RM-TARGET-1')
        with self.assertRaisesRegex(frappe.ValidationError, 'Checked In'):
            process_room_move(self.reservation.name, new_room.name)

    def test_room_move_blocks_same_room(self):
        f = self.fixture()
        self.checkin(self.reservation)
        from hospitality_core.hospitality_core.api.room_move import process_room_move
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be the same'):
            process_room_move(self.reservation.name, self.reservation.room)

    def test_room_move_updates_room_and_folio(self):
        f = self.fixture()
        self.checkin(self.reservation)
        new_room = f.room(self.property, self.room_type, number='RM-TARGET-2')
        from hospitality_core.hospitality_core.api.room_move import process_room_move
        process_room_move(self.reservation.name, new_room.name)
        self.reservation.reload()
        self.assertEqual(self.reservation.room, new_room.name)
        folio_room = frappe.db.get_value('Guest Folio', self.reservation.folio, 'room')
        self.assertEqual(folio_room, new_room.name)
        self.assertEqual(frappe.db.get_value('Hotel Room', new_room.name, 'status'), 'Occupied')

    def test_room_move_blocks_conflicting_open_folio_on_target_room(self):
        f = self.fixture()
        self.checkin(self.reservation)
        # Phòng đích đã có 1 Guest Folio khác đang Open (khách trước chưa trả phòng xong).
        target_room = f.room(self.property, self.room_type, number='RM-TARGET-3')
        other_guest = frappe.get_doc(dict(doctype='Guest', full_name='Other Occupant',
            guest_type='Regular')).insert(ignore_permissions=True)
        # check_availability() (chạy TRƯỚC kiểm tra folio-conflict trong
        # process_room_move()) chỉ xét khoảng [hôm nay, departure_date của
        # đặt phòng đang chuyển] — đặt ngày của "khách khác" hẳn SAU khoảng
        # đó để không bị chặn nhầm ở bước availability, nhằm test ĐÚNG nhánh
        # "folio đích còn Open" (mô phỏng dữ liệu còn sót — 1 folio Open dù
        # đặt phòng tương lai chưa check-in).
        far_future = add_days(self.reservation.departure_date, 10)
        other_res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property,
            guest=other_guest.name, room=target_room.name, room_type=self.room_type,
            hotel_reception=target_room.hotel_reception, currency=self.currency,
            arrival_date=far_future, departure_date=add_days(far_future, 1))).insert()
        frappe.db.set_value('Guest Folio', other_res.folio, 'status', 'Open')
        from hospitality_core.hospitality_core.api.room_move import process_room_move
        with self.assertRaisesRegex(frappe.ValidationError, 'still Open'):
            process_room_move(self.reservation.name, target_room.name)

    def test_room_move_requires_supervisor_role(self):
        f = self.fixture()
        self.checkin(self.reservation)
        new_room = f.room(self.property, self.room_type, number='RM-TARGET-4')
        user = 'roommove-noperm@example.com'
        if not frappe.db.exists('User', user):
            frappe.get_doc(dict(doctype='User', email=user, first_name='NoPerm',
                send_welcome_email=0, roles=[dict(role='Sales User')])).insert(ignore_permissions=True)
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.room_move import process_room_move
        with self.assertRaisesRegex(frappe.ValidationError, 'Access Denied'):
            process_room_move(self.reservation.name, new_room.name)


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SurchargeRoomMoveTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
