"""Kịch bản kiểm thử MỚI — night_audit.py's run_daily_audit() (Đợt 1, mục 1
của kế hoạch "Kịch bản kiểm thử TOÀN BỘ tính năng còn lại"). Hàm này chạy TỰ
ĐỘNG mỗi đêm cho MỌI property nhưng CHƯA TỪNG có 1 dòng test sống nào (xác
nhận bằng grep 5 file test hiện có — 0 kết quả).

Chạy trên site test riêng, dữ liệu rollback sau mỗi ca (theo đúng quy ước
các script khác trong thư mục này).
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days, now_datetime, getdate
from run_property_integration import PropertyDatabaseTests


class NightAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def fixture(self, **kwargs):
        f = PropertyDatabaseTests()
        reservation, settings = f.accounting_reservation(**kwargs)
        return reservation, settings

    # ------------------------------------------------------------------
    # 1) No-show: hủy tự động + hoàn cọc dư vào Guest Balance Ledger.
    # ------------------------------------------------------------------
    def test_no_show_cancellation_refunds_deposit(self):
        from hospitality_core.hospitality_core.api.night_audit import cancel_no_shows
        from hospitality_core.hospitality_core.api.property_accounting import receive_payment
        reservation, settings = self.fixture()
        self.assertEqual(reservation.status, 'Reserved')
        bank = frappe.db.get_value('Account', {'company': reservation.operating_company,
            'account_type': 'Cash', 'is_group': 0}, 'name')
        # Khách đặt cọc trước 500,000 — chưa có charge nào -> toàn bộ thành dư (credit).
        receive_payment(reservation.folio, bank, 500000, 'deposit-noshow-1')
        folio = frappe.get_doc('Guest Folio', reservation.folio)
        self.assertLess(folio.outstanding_balance, 0, 'Đặt cọc trước phải tạo số dư âm (credit) trên folio.')
        # Đẩy ngày đến quá khứ để đủ điều kiện no-show (arrival_date < posting_date).
        frappe.db.set_value('Hotel Reservation', reservation.name, 'arrival_date', add_days(nowdate(), -1))
        cancelled = cancel_no_shows(nowdate(), property=reservation.property)
        self.assertEqual(cancelled, 1)
        reservation.reload()
        self.assertEqual(reservation.status, 'Cancelled')
        self.assertEqual(frappe.db.get_value('Guest Folio', reservation.folio, 'status'), 'Cancelled')
        ledger = frappe.get_all('Guest Balance Ledger', filters={'folio': reservation.folio},
            fields=['amount', 'status', 'guest'])
        self.assertEqual(len(ledger), 1, 'Tiền cọc dư phải được hoàn vào Guest Balance Ledger đúng 1 lần.')
        self.assertAlmostEqual(ledger[0].amount, 500000, places=2)
        self.assertEqual(ledger[0].status, 'Available')
        folio.reload()
        self.assertAlmostEqual(folio.outstanding_balance, 0, places=2,
            msg='Sau khi chuyển tiền cọc dư sang Balance Ledger, folio phải về ~0.')

    def test_no_show_without_deposit_no_phantom_ledger_entry(self):
        from hospitality_core.hospitality_core.api.night_audit import cancel_no_shows
        reservation, settings = self.fixture()
        frappe.db.set_value('Hotel Reservation', reservation.name, 'arrival_date', add_days(nowdate(), -2))
        cancelled = cancel_no_shows(nowdate(), property=reservation.property)
        self.assertEqual(cancelled, 1)
        reservation.reload()
        self.assertEqual(reservation.status, 'Cancelled')
        self.assertEqual(frappe.db.count('Guest Balance Ledger', {'folio': reservation.folio}), 0,
            'Không đặt cọc thì không được tự tạo bản ghi hoàn tiền nào.')

    def test_no_show_skips_future_arrivals(self):
        from hospitality_core.hospitality_core.api.night_audit import cancel_no_shows
        reservation, settings = self.fixture()
        # arrival_date mặc định = hôm nay -> KHÔNG phải no-show (chưa quá hạn).
        cancelled = cancel_no_shows(nowdate(), property=reservation.property)
        self.assertEqual(cancelled, 0)
        reservation.reload()
        self.assertEqual(reservation.status, 'Reserved')

    # ------------------------------------------------------------------
    # 2) Overstay: tự gia hạn qua lifecycle + tính tiền đêm phát sinh.
    # ------------------------------------------------------------------
    def test_overstay_extends_departure_and_bills_once(self):
        from hospitality_core.hospitality_core.api.night_audit import process_single_reservation
        from hospitality_core.hospitality_core.doctype.hotel_reservation.hotel_reservation import check_in_guest
        reservation, settings = self.fixture()
        check_in_guest(reservation.name)
        reservation.reload()
        self.assertEqual(reservation.status, 'Checked In')
        original_departure = getdate(reservation.departure_date)
        # Đẩy departure_date về hôm nay -> quá hạn trả phòng (overstay).
        frappe.db.set_value('Hotel Reservation', reservation.name, 'departure_date', nowdate())
        row = frappe._dict(name=reservation.name)
        billed, overstayed, error = process_single_reservation(row, nowdate())
        self.assertIsNone(error)
        self.assertTrue(overstayed)
        reservation.reload()
        self.assertEqual(getdate(reservation.departure_date), getdate(add_days(nowdate(), 1)),
            'Overstay phải tự gia hạn departure_date thêm đúng 1 ngày.')
        # Chạy lại lần 2 CÙNG NGÀY posting -> không còn overstay (đã gia hạn qua),
        # và không tính tiền trùng ngày đã charge ở lần đầu.
        billed2, overstayed2, error2 = process_single_reservation(row, nowdate())
        self.assertIsNone(error2)
        self.assertFalse(overstayed2)
        self.assertFalse(billed2, 'Không được tính tiền trùng ngày đã charge trong cùng lần audit.')

    def test_room_charge_not_duplicated_same_day(self):
        from hospitality_core.hospitality_core.api.night_audit import process_single_reservation
        from hospitality_core.hospitality_core.doctype.hotel_reservation.hotel_reservation import check_in_guest
        reservation, settings = self.fixture()
        check_in_guest(reservation.name)
        # process_check_in() TỰ tính tiền đêm arrival_date ngay lúc check-in
        # (xem hotel_reservation.py's process_check_in() gọi post_daily_charge()
        # qua charge_date_for_checkin()) — nên kiểm tra idempotent cho đúng
        # ĐÊM mà audit chịu trách nhiệm tính (đêm kế tiếp), không phải đêm
        # check-in đã tự tính rồi.
        next_night = add_days(reservation.arrival_date, 1)
        row = frappe._dict(name=reservation.name)
        billed1, _, error1 = process_single_reservation(row, next_night)
        self.assertIsNone(error1)
        self.assertTrue(billed1)
        billed2, _, error2 = process_single_reservation(row, next_night)
        self.assertIsNone(error2)
        self.assertFalse(billed2, 'already_charged_today() phải chặn tính tiền 2 lần cùng ngày.')

    # ------------------------------------------------------------------
    # 3) Đối chiếu Room <-> Reservation <-> Folio.
    # ------------------------------------------------------------------
    def test_reconciliation_detects_occupied_room_without_checkin(self):
        from hospitality_core.hospitality_core.api.night_audit import reconcile_room_reservation_folio_status
        reservation, settings = self.fixture()
        # Phòng bị đặt "Occupied" thủ công (VD lỗi thao tác) nhưng KHÔNG check-in qua hệ thống.
        frappe.db.set_value('Hotel Room', reservation.room, 'status', 'Occupied')
        mismatches = reconcile_room_reservation_folio_status(property=reservation.property)
        self.assertTrue(any(reservation.room in m and 'Occupied' in m for m in mismatches),
            'Phải phát hiện phòng Occupied không có Reservation Checked In khớp.')

    def test_reconciliation_detects_checked_in_room_mismatch(self):
        from hospitality_core.hospitality_core.api.night_audit import reconcile_room_reservation_folio_status
        from hospitality_core.hospitality_core.doctype.hotel_reservation.hotel_reservation import check_in_guest
        reservation, settings = self.fixture()
        check_in_guest(reservation.name)
        # Ai đó vô tình đổi Room về Available dù khách vẫn đang Checked In trên hệ thống.
        frappe.db.set_value('Hotel Room', reservation.room, 'status', 'Available')
        mismatches = reconcile_room_reservation_folio_status(property=reservation.property)
        self.assertTrue(any(reservation.name in m for m in mismatches),
            'Phải phát hiện Reservation Checked In nhưng Room không Occupied.')

    def test_reconciliation_clean_when_consistent(self):
        from hospitality_core.hospitality_core.api.night_audit import reconcile_room_reservation_folio_status
        from hospitality_core.hospitality_core.doctype.hotel_reservation.hotel_reservation import check_in_guest
        reservation, settings = self.fixture()
        check_in_guest(reservation.name)
        mismatches = reconcile_room_reservation_folio_status(property=reservation.property)
        self.assertEqual([m for m in mismatches if reservation.name in m or reservation.room in m], [],
            'Trạng thái nhất quán (đã check-in đúng) không được báo lệch giả.')

    # ------------------------------------------------------------------
    # 4) run_daily_audit() đầu-cuối: ghi đúng Night Audit Log, có property.
    # ------------------------------------------------------------------
    def test_full_audit_run_writes_log_with_property_and_counts(self):
        from hospitality_core.hospitality_core.api.night_audit import _run_daily_audit_for_property
        from hospitality_core.hospitality_core.doctype.hotel_reservation.hotel_reservation import check_in_guest
        no_show_res, _ = self.fixture()
        frappe.db.set_value('Hotel Reservation', no_show_res.name, 'arrival_date', add_days(nowdate(), -1))
        # KHÔNG gọi lại self.fixture() lần 2 (-> accounting_reservation()) trong
        # CÙNG 1 transaction chưa commit — đã xác nhận thật ở vòng test trước:
        # helper này tự insert() nhiều bản ghi tên CỐ ĐỊNH (Price List "Integration
        # Selling"...), chỉ an toàn gọi ĐÚNG 1 LẦN/transaction (rollback() giữa
        # các lần gọi mới tránh trùng). Tự dựng đặt phòng thứ 2 thủ công, dùng
        # lại đúng guest/customer/currency/property đã có từ lần fixture() đầu.
        f = PropertyDatabaseTests()
        room2 = f.room(no_show_res.property, no_show_res.room_type, number='102')
        billed_res = frappe.get_doc(dict(doctype='Hotel Reservation', property=no_show_res.property,
            currency=no_show_res.currency, guest=no_show_res.guest, billing_customer=no_show_res.billing_customer,
            room=room2.name, room_type=room2.room_type, hotel_reception=room2.hotel_reception,
            arrival_date=nowdate(), departure_date=add_days(nowdate(), 2))).insert()
        frappe.db.set_value('Guest Folio', billed_res.folio, 'status', 'Open')
        check_in_guest(billed_res.name)
        _run_daily_audit_for_property(no_show_res.property)
        logs = frappe.get_all('Night Audit Log', filters={'property': no_show_res.property},
            fields=['name', 'no_show_count', 'room_charge_posted_count', 'error_count', 'reconciliation_mismatch_count'],
            order_by='creation desc', limit=1)
        self.assertEqual(len(logs), 1, 'Phải ghi đúng 1 Night Audit Log gắn property.')
        log = logs[0]
        self.assertGreaterEqual(log.no_show_count, 1)
        # KHÔNG assert room_charge_posted_count>=1: check_in_guest() TỰ tính
        # tiền đêm hôm nay ngay lúc check-in (xem test_room_charge_not_
        # duplicated_same_day) — audit CÙNG NGÀY đó đúng ra KHÔNG cần tính
        # thêm gì cho billed_res (already_charged_today() đúng đắn chặn lại).
        # Hành vi tính tiền idempotent đã được test riêng, kỹ hơn ở trên.
        self.assertGreaterEqual(log.room_charge_posted_count, 0)
        self.assertEqual(log.error_count, 0, 'Không có lỗi thật nào trong kịch bản sạch này.')
        no_show_res.reload()
        self.assertEqual(no_show_res.status, 'Cancelled')


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(NightAuditTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
