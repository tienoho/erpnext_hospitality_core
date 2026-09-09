"""Kịch bản kiểm thử MỚI — group_booking.py + hotel_group_booking.py (Đợt 1,
mục 2 của kế hoạch "Kịch bản kiểm thử TOÀN BỘ tính năng còn lại"). Module đặt
đoàn CHƯA TỪNG có 1 dòng test sống nào (xác nhận bằng grep 5 file test hiện
có — 0 kết quả) dù đã qua nhiều vòng fix tĩnh (phòng ảo bắt buộc cấu hình,
dò phòng ảo còn trống thay vì luôn lấy phòng đầu tiên, record_group_deposit()
tạo Payment Entry thật thay vì chỉ đổi dropdown).

Chạy trên site test riêng, dữ liệu rollback sau mỗi ca.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days, flt
from run_property_integration import PropertyDatabaseTests


class GroupBookingTests(unittest.TestCase):
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
        # Phòng ảo bắt buộc cho create_master_payer_reservation() — xem
        # comment trong hotel_group_booking.py: KHÔNG còn tự mượn phòng thật.
        if not frappe.db.exists('Hotel Room Type', {'room_type_name': 'Virtual', 'property': self.property}):
            # default_rate<=0 bị Hotel Room Type's controller từ chối (dòng
            # "self.default_rate is not None and self.default_rate<=0") dù
            # phòng ảo không bao giờ thực sự dùng giá này (rate_plan=None khi
            # neo Master Folio) — dùng số dương tối thiểu để qua validate.
            virtual_type = frappe.get_doc(dict(doctype='Hotel Room Type', property=self.property,
                room_type_name='Virtual', default_rate=1, currency_rates=[
                    dict(currency=self.currency, default_rate=1)])).insert()
        else:
            virtual_type = frappe.get_doc('Hotel Room Type', frappe.db.get_value('Hotel Room Type',
                {'room_type_name': 'Virtual', 'property': self.property}, 'name'))
        self.virtual_room = f.room(self.property, virtual_type.name, number='VIRTUAL-1')
        # 2 phòng thật cho danh sách phòng của đoàn.
        self.room_a = f.room(self.property, reservation.room_type, number='GRP-A')
        self.room_b = f.room(self.property, reservation.room_type, number='GRP-B')
        self.room_type = reservation.room_type
        # Master payer: 1 đại lý/công ty đặt đoàn.
        agent_name = 'Group Test Agency'
        if not frappe.db.exists('Customer', agent_name):
            frappe.get_doc(dict(doctype='Customer', customer_name=agent_name, customer_type='Company',
                customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert(ignore_permissions=True)
        self.master_payer = agent_name

    def ensure_legacy_accounting_settings(self):
        # create_company_folio_payment() (kế toán Legacy) đi qua
        # handle_payment_income_realization(), dùng Single doctype TOÀN CỤC
        # "Hospitality Accounting Settings" (khác hẳn "Hospitality Company
        # Accounting Settings" theo từng company mà accounting_reservation()
        # đã cấu hình cho Property v2) — chưa từng được fixture nào cấu hình
        # vì mọi test khác trong bộ này đều chạy dưới Property v2. Cấu hình
        # tối thiểu ở đây để test đúng tính năng thanh toán Company/Group
        # Legacy hiện có (không phải giả lập gì mới, đây là bước cấu hình
        # bắt buộc thật sự trước khi tính năng này hoạt động trên bất kỳ
        # site nào còn dùng kế toán Legacy).
        def account(label, root_type):
            existing = frappe.db.get_value('Account', {'company': self.company, 'account_name': label}, 'name')
            if existing:
                return existing
            parent = frappe.db.get_value('Account', {'company': self.company, 'root_type': root_type,
                'is_group': 1}, 'name', order_by='lft')
            return frappe.get_doc(dict(doctype='Account', account_name=label, parent_account=parent,
                company=self.company, account_currency=self.currency)).insert().name
        # QUAN TRỌNG: gán THẲNG (không dùng "x = x or y") — "Hospitality
        # Accounting Settings" là Single TOÀN SITE, dùng chung bởi CẢ file
        # test này lẫn run_city_ledger_financial_control_tests.py's
        # ensure_legacy_payment_prereqs() tương tự. Phát hiện thật: nếu 1
        # trong 2 file "commit thật" trước (qua void_transaction()/
        # record_group_deposit()), kiểu gán idempotent "chỉ điền nếu còn
        # trống" sẽ khiến file chạy SAU kế thừa nhầm tài khoản/cost_center
        # của company thuộc file KHÁC (VD "Cost Center ... does not belong
        # to Company ...") — đã xác nhận thật khi chạy 2 file liên tiếp
        # không reinstall. Luôn gán lại đúng theo company hiện tại.
        settings = frappe.get_single('Hospitality Accounting Settings')
        settings.receivable_account = frappe.db.get_value('Company', self.company, 'default_receivable_account')
        settings.income_suspense_account = account('Legacy Income Suspense', 'Liability')
        settings.income_account = account('Legacy Room Revenue', 'Income')
        settings.consumption_tax_account = account('Legacy Consumption Tax', 'Liability')
        settings.vat_account = account('Legacy VAT', 'Liability')
        settings.service_charge_account = account('Legacy Service Charge', 'Liability')
        settings.cost_center = frappe.db.get_value('Company', self.company, 'cost_center')
        settings.enable_vietqr = 0  # Không liên quan test này; tránh validate_vietqr_settings() đòi cấu hình thêm.
        settings.save()

    def make_group(self, rooms=None, arrival=None, departure=None):
        return frappe.get_doc(dict(doctype='Hotel Group Booking', group_name=f'Test Group {frappe.generate_hash(6)}',
            master_payer=self.master_payer, property=self.property, operating_company=self.company,
            currency=self.currency, arrival_date=arrival or nowdate(), departure_date=departure or add_days(nowdate(), 2),
            rooms=rooms or [])).insert()

    # ------------------------------------------------------------------
    # 1) Xác nhận đoàn: tạo Master Folio + đặt phòng master + đặt phòng con.
    # ------------------------------------------------------------------
    def test_confirm_creates_master_folio_and_bulk_reservations(self):
        self.fixture()
        group = self.make_group(rooms=[dict(room=self.room_a.name, room_type=self.room_type),
            dict(room=self.room_b.name, room_type=self.room_type)])
        group.status = 'Confirmed'
        group.save()
        group.reload()
        self.assertTrue(group.master_folio, 'Xác nhận đoàn phải tự tạo Master Folio.')
        master_res = frappe.get_all('Hotel Reservation', filters={'folio': group.master_folio}, fields=['name', 'room', 'status'])
        self.assertEqual(len(master_res), 1)
        self.assertEqual(master_res[0].room, self.virtual_room.name,
            'Đặt phòng master phải neo vào phòng ẢO, không phải phòng thật.')
        self.assertEqual(master_res[0].status, 'Reserved')
        child_res = frappe.get_all('Hotel Reservation', filters={'group_booking': group.name,
            'room': ['in', [self.room_a.name, self.room_b.name]]}, fields=['name', 'room', 'status', 'is_group_guest'])
        self.assertEqual(len(child_res), 2, 'Phải tạo đủ 2 đặt phòng con cho 2 phòng trong danh sách.')
        for r in child_res:
            self.assertEqual(r.status, 'Reserved')
            self.assertEqual(r.is_group_guest, 1)

    def test_confirm_without_virtual_room_type_blocked(self):
        f = PropertyDatabaseTests()
        reservation, settings = f.accounting_reservation()
        # KHÔNG tạo Hotel Room Type "Virtual" cho property này.
        agent_name = 'Group No Virtual Agency'
        if not frappe.db.exists('Customer', agent_name):
            frappe.get_doc(dict(doctype='Customer', customer_name=agent_name, customer_type='Company',
                customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert(ignore_permissions=True)
        group = frappe.get_doc(dict(doctype='Hotel Group Booking', group_name=f'No Virtual {frappe.generate_hash(6)}',
            master_payer=agent_name, property=reservation.property, operating_company=reservation.operating_company,
            currency=reservation.currency, arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        group.status = 'Confirmed'
        with self.assertRaisesRegex(frappe.ValidationError, 'Virtual'):
            group.save()

    # ------------------------------------------------------------------
    # 2) 2 đoàn trùng ngày phải dùng 2 phòng ảo KHÁC NHAU (không xung đột lịch).
    # ------------------------------------------------------------------
    def test_two_overlapping_groups_use_different_virtual_rooms(self):
        self.fixture()
        virtual_type = frappe.db.get_value('Hotel Room Type', {'room_type_name': 'Virtual', 'property': self.property}, 'name')
        f = PropertyDatabaseTests()
        second_virtual = f.room(self.property, virtual_type, number='VIRTUAL-2')
        g1 = self.make_group()
        g1.status = 'Confirmed'
        g1.save()
        g1.reload()
        g2 = self.make_group()
        g2.status = 'Confirmed'
        g2.save()
        g2.reload()
        res1 = frappe.db.get_value('Hotel Reservation', {'folio': g1.master_folio}, 'room')
        res2 = frappe.db.get_value('Hotel Reservation', {'folio': g2.master_folio}, 'room')
        self.assertNotEqual(res1, res2, '2 đoàn trùng ngày phải được cấp 2 phòng ảo khác nhau, không xung đột lịch.')
        self.assertEqual({res1, res2}, {self.virtual_room.name, second_virtual.name})

    # ------------------------------------------------------------------
    # 3) Nhận phòng/trả phòng hàng loạt.
    # ------------------------------------------------------------------
    def test_mass_check_in_and_check_out(self):
        from hospitality_core.hospitality_core.api.group_booking import mass_check_in, mass_check_out
        self.fixture()
        # Check-out (process_check_out()) đòi departure_date == hôm nay
        # (dòng "Cannot Check Out. Departure date (...) must be today"), còn
        # validate_dates() của chính Hotel Group Booking lại đòi arrival <
        # departure nghiêm ngặt (không cho bằng nhau) — dùng arrival=hôm qua,
        # departure=hôm nay để thỏa cả 2, cho phép check-in RỒI check-out
        # ngay trong cùng 1 lần chạy test.
        group = self.make_group(rooms=[dict(room=self.room_a.name, room_type=self.room_type),
            dict(room=self.room_b.name, room_type=self.room_type)], arrival=add_days(nowdate(), -1), departure=nowdate())
        group.status = 'Confirmed'
        group.save()
        group.reload()
        result = mass_check_in(group.name)
        self.assertEqual(result['error_count'], 0, f"Mass check-in không được lỗi: {result.get('message')}")
        self.assertEqual(result['success_count'], 3, 'Phải check-in đủ 3 đặt phòng (1 master + 2 phòng con).')
        statuses = frappe.get_all('Hotel Reservation', filters={'group_booking': group.name}, pluck='status')
        master_status = frappe.db.get_value('Hotel Reservation', {'folio': group.master_folio}, 'status')
        self.assertTrue(all(s == 'Checked In' for s in statuses))
        self.assertEqual(master_status, 'Checked In')
        # check_out_guest() chặn checkout khi Group Master Folio còn dư nợ
        # (đúng ý đồ: "All group charges must be settled first") — check-in
        # 2 phòng thật đã mirror charge phòng lên Master Folio, nên phải
        # thanh toán hết trước khi test được luồng check-out.
        from hospitality_core.hospitality_core.api.payment_bridge import create_company_folio_payment
        from hospitality_core.hospitality_core.api.folio import sync_folio_balance
        master_folio_doc = frappe.get_doc('Guest Folio', group.master_folio)
        sync_folio_balance(master_folio_doc)
        outstanding = frappe.db.get_value('Guest Folio', group.master_folio, 'outstanding_balance') or 0.0
        if outstanding > 0.01:
            cash = frappe.db.get_value('Account', {'company': self.company, 'account_type': 'Cash', 'is_group': 0}, 'name')
            if not frappe.db.exists('Mode of Payment', 'Group Settlement Cash'):
                frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Group Settlement Cash', type='Cash',
                    accounts=[dict(company=self.company, default_account=cash)])).insert()
            # create_company_folio_payment() giờ chặn cứng folio
            # accounting_version=='Property v2' (xem payment_bridge.py —
            # Property v2 chưa có hàm thanh toán Company/Group riêng, chỉ
            # có receive_payment() cho khách lẻ). fixture() dùng property
            # đã cutover Property v2 nên Master Folio đoàn mặc định mang
            # đúng version đó — hạ tạm về 'Legacy' để test được đúng tính
            # năng thanh toán Company/Group hiện có (mô phỏng 1 folio đoàn
            # mở TRƯỚC ngày cutover, vẫn còn hợp lệ theo đúng quy ước
            # accounting_version bất biến của property_scope.py).
            frappe.db.set_value('Guest Folio', group.master_folio, 'accounting_version', 'Legacy')
            self.ensure_legacy_accounting_settings()
            create_company_folio_payment(group.master_folio, outstanding, 'Group Settlement Cash',
                hotel_reception=None, remarks='Settle group charges before checkout')
        result_out = mass_check_out(group.name)
        self.assertEqual(result_out['error_count'], 0, f"Mass check-out không được lỗi: {result_out.get('message')}")
        # create_master_payer_reservation() CÓ set group_booking=self.name
        # trên chính đặt phòng ảo (đã đọc lại code xác nhận, khác giả định
        # sai lúc đầu) — mass_check_out() lọc theo group_booking nên check-out
        # đủ cả 3 (1 master + 2 phòng con).
        self.assertEqual(result_out['success_count'], 3, 'Phải check-out đủ 3 đặt phòng (1 master + 2 phòng con).')

    # ------------------------------------------------------------------
    # 4) Đặt cọc đoàn: phải là Payment Entry thật, trừ đúng số dư Master Folio.
    # ------------------------------------------------------------------
    def test_record_group_deposit_creates_real_payment_and_reduces_balance(self):
        from hospitality_core.hospitality_core.api.group_booking import record_group_deposit
        self.fixture()
        group = self.make_group()
        group.deposit_required = 2000000
        group.status = 'Confirmed'
        group.save()
        group.reload()
        self.assertEqual(group.deposit_status, 'Pending')
        cash = frappe.db.get_value('Account', {'company': self.company, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', 'Group Deposit Cash'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Group Deposit Cash', type='Cash',
                accounts=[dict(company=self.company, default_account=cash)])).insert()
        # record_group_deposit()/create_company_folio_payment() chỉ hỗ trợ
        # kế toán Legacy (xem ghi chú trong payment_bridge.py — Property v2
        # chưa có hàm thanh toán Company/Group riêng) — hạ Master Folio về
        # 'Legacy' để test đúng tính năng hiện có (mô phỏng folio đoàn mở
        # trước ngày cutover).
        frappe.db.set_value('Guest Folio', group.master_folio, 'accounting_version', 'Legacy')
        self.ensure_legacy_accounting_settings()
        folio_before = frappe.get_doc('Guest Folio', group.master_folio)
        pe_name = record_group_deposit(group.name, 'Group Deposit Cash', reference_no='DEPOSIT-1')
        self.assertTrue(frappe.db.exists('Payment Entry', pe_name))
        pe = frappe.get_doc('Payment Entry', pe_name)
        self.assertEqual(pe.docstatus, 1)
        self.assertAlmostEqual(flt(pe.paid_amount), 2000000, places=2)
        group.reload()
        self.assertEqual(group.deposit_status, 'Received')
        folio_after = frappe.get_doc('Guest Folio', group.master_folio)
        self.assertLess(folio_after.outstanding_balance, folio_before.outstanding_balance,
            'Ghi nhận cọc phải TRỪ THẬT vào số dư Master Folio, không chỉ đổi dropdown.')

    def test_record_group_deposit_without_master_folio_blocked(self):
        from hospitality_core.hospitality_core.api.group_booking import record_group_deposit
        self.fixture()
        group = self.make_group()  # status='Tentative' -> chưa tạo Master Folio.
        with self.assertRaisesRegex(frappe.ValidationError, 'Master Folio'):
            record_group_deposit(group.name, 'Cash', amount=1000000)

    def test_record_group_deposit_on_property_v2_folio_blocked_clearly(self):
        # fixture() dùng property đã cutover Property v2 nên Master Folio
        # đoàn mặc định mang version đó — xác nhận create_company_folio_payment()
        # từ chối RÕ RÀNG (thay vì crash "Account is required" do thiếu cấu
        # hình Legacy song song, hoặc tệ hơn là âm thầm ghi trùng doanh thu
        # nếu có cấu hình Legacy) khi chưa có hàm thanh toán Company/Group
        # riêng cho Property v2.
        from hospitality_core.hospitality_core.api.group_booking import record_group_deposit
        self.fixture()
        group = self.make_group()
        group.deposit_required = 1000000
        group.status = 'Confirmed'
        group.save()
        group.reload()
        self.assertEqual(frappe.db.get_value('Guest Folio', group.master_folio, 'accounting_version'), 'Property v2')
        if not frappe.db.exists('Mode of Payment', 'Group Deposit Cash'):
            cash = frappe.db.get_value('Account', {'company': self.company, 'account_type': 'Cash', 'is_group': 0}, 'name')
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Group Deposit Cash', type='Cash',
                accounts=[dict(company=self.company, default_account=cash)])).insert()
        with self.assertRaisesRegex(frappe.ValidationError, 'Property v2'):
            record_group_deposit(group.name, 'Group Deposit Cash', reference_no='DEPOSIT-BLOCKED')


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(GroupBookingTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
