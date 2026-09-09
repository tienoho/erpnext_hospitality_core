"""Kịch bản kiểm thử MỚI — Đợt 4 (phần cuối): ~19 báo cáo vận hành ưu tiên
thấp hơn (không đụng POS Invoice/POS Closing Entry — an toàn với mô hình
rollback-per-test đã dùng xuyên suốt phiên này):
daily_arrivals, daily_departures, maintenance_log_report,
lost_and_found_register, hospitality_expense_report, guest_ledger,
folio_transaction_move_report, house_list, guest_list,
room_availability_report, reservations_report,
housekeeping_productivity_report, void_and_allowance_report,
discount_and_complimentary_report, folio_balance_summary,
daily_sales_consumption, hotel_performance_analytics,
point_of_sale_report, police_guest_registration_report.

3 báo cáo phụ thuộc POS (pos_sales_summary/financial_activity_summary/
frontdesk_end_of_day_report) KHÔNG nằm trong file này — xem
tools/run_pos_reports_tests.py + ghi chú "SỰ CỐ NGHIÊM TRỌNG" trong plan.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days, getdate, flt
from run_property_integration import PropertyDatabaseTests


class OperationalReportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def fixture(self):
        f = PropertyDatabaseTests()
        reservation, settings = f.accounting_reservation()
        self.reservation = reservation
        self.company_a = frappe.db.get_value('Hospitality Property', 'HV-A', 'operating_company')
        return f

    # ------------------------------------------------------------------
    # Helpers dùng chung
    # ------------------------------------------------------------------
    def make_charge(self, folio_name, item, amount, posting_date=None, is_void=0,
                     void_reason=None, mirror_source=None, bill_to='Guest'):
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists(item, item)
        txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=folio_name, parenttype='Guest Folio',
            parentfield='transactions', posting_date=posting_date or nowdate(), item=item,
            description=f'Test {item}', qty=1, amount=amount, bill_to=bill_to, is_void=is_void,
            void_reason=void_reason, mirror_source=mirror_source))
        txn.flags.hospitality_service = True
        if mirror_source:
            txn.flags.from_folio_mirror = True
        txn.insert(ignore_permissions=True)
        return txn

    def make_customer(self, name):
        if not frappe.db.exists('Customer', name):
            frappe.get_doc(dict(doctype='Customer', customer_name=name, customer_type='Company',
                customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert(ignore_permissions=True)
        return name

    def make_master_folio(self, is_company_master=1, open_date=None, outstanding_balance=100000, company=None):
        guest = frappe.get_doc(dict(doctype='Guest', full_name=f'Master Folio Guest {frappe.generate_hash(4)}',
            guest_type='Regular')).insert(ignore_permissions=True)
        folio = frappe.get_doc(dict(doctype='Guest Folio', property='HV-A', guest=guest.name,
            company=company or self.make_customer('Test Op Reports Agency'), is_company_master=is_company_master,
            status='Open', open_date=open_date or nowdate())).insert(ignore_permissions=True)
        frappe.db.set_value('Guest Folio', folio.name, {
            'outstanding_balance': outstanding_balance,
            'total_charges': outstanding_balance,
            'total_payments': 0,
        }, update_modified=False)
        folio.reload()
        return folio

    # ==================================================================
    # daily_arrivals.py
    # ==================================================================
    def test_daily_arrivals_includes_checked_in_today(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Checked In')
        from hospitality_core.hospitality_core.report.daily_arrivals.daily_arrivals import execute
        columns, data = execute({'date': nowdate()})
        names = {d.name for d in data}
        self.assertIn(self.reservation.name, names)

    def test_daily_arrivals_excludes_reserved_not_checked_in(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Reserved')
        from hospitality_core.hospitality_core.report.daily_arrivals.daily_arrivals import execute
        columns, data = execute({'date': nowdate()})
        names = {d.name for d in data}
        self.assertNotIn(self.reservation.name, names,
            'Dat phong chua Checked In/Checked Out khong duoc tinh la mot "arrival" that.')

    # ==================================================================
    # daily_departures.py
    # ==================================================================
    def test_daily_departures_includes_checked_out_with_folio_totals(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, {
            'status': 'Checked Out', 'departure_date': nowdate()})
        frappe.db.set_value('Guest Folio', self.reservation.folio, {
            'total_charges': 500000, 'total_payments': 500000}, update_modified=False)
        from hospitality_core.hospitality_core.report.daily_departures.daily_departures import execute
        columns, data = execute({'date': nowdate()})
        row = next((d for d in data if d.name == self.reservation.name), None)
        self.assertIsNotNone(row)
        self.assertEqual(flt(row.total_charges), 500000)
        self.assertEqual(flt(row.total_payments), 500000)

    def test_daily_departures_excludes_wrong_departure_date(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, {
            'status': 'Checked Out', 'departure_date': add_days(nowdate(), -3)})
        from hospitality_core.hospitality_core.report.daily_departures.daily_departures import execute
        columns, data = execute({'date': nowdate()})
        names = {d.name for d in data}
        self.assertNotIn(self.reservation.name, names)

    # ==================================================================
    # maintenance_log_report.py
    # ==================================================================
    def test_maintenance_log_lists_request_with_reporter_name(self):
        self.fixture()
        mr = frappe.get_doc(dict(doctype='Hotel Maintenance Request', room=self.reservation.room,
            issue_type='Other', status='Reported', description='Broken AC')).insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.report.maintenance_log_report.maintenance_log_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((d for d in data if d.name == mr.name), None)
        self.assertIsNotNone(row)
        self.assertEqual(row.reported_by_name, frappe.db.get_value('User', 'Administrator', 'full_name'))

    def test_maintenance_log_filters_by_status(self):
        self.fixture()
        mr = frappe.get_doc(dict(doctype='Hotel Maintenance Request', room=self.reservation.room,
            issue_type='Other', status='Reported', description='Leaking faucet')).insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.report.maintenance_log_report.maintenance_log_report import execute
        columns, data = execute({'status': 'Completed'})
        names = {d.name for d in data}
        self.assertNotIn(mr.name, names, 'Loc theo status khac phai loai bo yeu cau con o trang thai Reported.')

    # ==================================================================
    # lost_and_found_register.py
    # ==================================================================
    def test_lost_and_found_shows_finder_name_directly(self):
        self.fixture()
        item = frappe.get_doc(dict(doctype='Lost and Found Item', found_date=nowdate(),
            item_name='Sạc điện thoại', found_location=self.reservation.room,
            finder='Nguyễn Văn A', status='Found')).insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.report.lost_and_found_register.lost_and_found_register import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((d for d in data if d.name == item.name), None)
        self.assertIsNotNone(row)
        self.assertEqual(row.finder_name, 'Nguyễn Văn A',
            'Sau fix bo JOIN Employee sai, "Found By" phai hien dung ten nhap tay.')

    def test_lost_and_found_filters_by_date_range(self):
        self.fixture()
        item = frappe.get_doc(dict(doctype='Lost and Found Item', found_date=add_days(nowdate(), -30),
            item_name='Old item', found_location=self.reservation.room,
            finder='Someone', status='Found')).insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.report.lost_and_found_register.lost_and_found_register import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        names = {d.name for d in data}
        self.assertNotIn(item.name, names)

    # ==================================================================
    # hospitality_expense_report.py
    # ==================================================================
    def _ensure_expense_category(self):
        if not frappe.db.exists('Expense Category', 'Test Op Report Category'):
            expense_account = frappe.db.get_value('Account', {'company': self.company_a, 'root_type': 'Expense',
                'is_group': 0}, 'name')
            frappe.get_doc(dict(doctype='Expense Category', category_name='Test Op Report Category',
                default_expense_account=expense_account)).insert(ignore_permissions=True)
        return 'Test Op Report Category'

    def _ensure_mode_of_payment(self):
        cash = frappe.db.get_value('Account', {'company': self.company_a, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', 'Cash'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Cash', type='Cash',
                accounts=[dict(company=self.company_a, default_account=cash)])).insert(ignore_permissions=True)
        elif not frappe.db.exists('Mode of Payment Account', {'parent': 'Cash', 'company': self.company_a}):
            mop = frappe.get_doc('Mode of Payment', 'Cash')
            mop.append('accounts', dict(company=self.company_a, default_account=cash))
            mop.save(ignore_permissions=True)
        return 'Cash'

    def make_expense(self, amount=50000, submit=True):
        cost_center = frappe.db.get_value('Cost Center', {'company': self.company_a, 'is_group': 0}, 'name')
        expense = frappe.get_doc(dict(doctype='Hospitality Expense', expense_date=nowdate(),
            expense_category=self._ensure_expense_category(), paid_via=self._ensure_mode_of_payment(),
            company=self.company_a, amount=amount, grand_total=amount, cost_center=cost_center,
            property='HV-A')).insert(ignore_permissions=True)
        if submit:
            expense.submit()
        return expense

    def test_hospitality_expense_report_only_includes_submitted(self):
        self.fixture()
        submitted = self.make_expense(amount=50000, submit=True)
        draft = self.make_expense(amount=70000, submit=False)
        from hospitality_core.hospitality_core.report.hospitality_expense_report.hospitality_expense_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate(), 'company': self.company_a})
        names = {d.name for d in data}
        self.assertIn(submitted.name, names)
        self.assertNotIn(draft.name, names, 'Chi phi con Draft khong duoc tinh vao bao cao, khop dung frontdesk_end_of_day_report.')

    def test_hospitality_expense_report_filters_by_category(self):
        self.fixture()
        expense = self.make_expense(amount=30000, submit=True)
        from hospitality_core.hospitality_core.report.hospitality_expense_report.hospitality_expense_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate(), 'company': self.company_a,
            'expense_category': 'Some Other Category'})
        names = {d.name for d in data}
        self.assertNotIn(expense.name, names)

    # ==================================================================
    # guest_ledger.py
    # ==================================================================
    def test_guest_ledger_excludes_corporate_by_default(self):
        self.fixture()
        frappe.db.set_value('Guest Folio', self.reservation.folio, 'outstanding_balance', 200000, update_modified=False)
        company_folio = self.make_master_folio(is_company_master=1, outstanding_balance=300000)
        from hospitality_core.hospitality_core.report.guest_ledger.guest_ledger import execute
        columns, data = execute({})
        names = {d.get('name') for d in data if d.get('name')}
        self.assertIn(self.reservation.folio, names)
        self.assertNotIn(company_folio.name, names,
            'Mac dinh (show_corporate khong bat) chi hien Guest Ledger, khong hien City Ledger.')

    def test_guest_ledger_show_corporate_includes_unmasked_company_folio(self):
        self.fixture()
        agency = self.make_customer('Guest Ledger Test Agency')
        company_folio = self.make_master_folio(is_company_master=1, outstanding_balance=400000, company=agency)
        from hospitality_core.hospitality_core.report.guest_ledger.guest_ledger import execute
        columns, data = execute({'show_corporate': 1})
        names = {d.get('name') for d in data if d.get('name')}
        self.assertIn(company_folio.name, names)

    # ==================================================================
    # folio_transaction_move_report.py
    # ==================================================================
    def test_folio_transaction_move_report_logs_move(self):
        self.fixture()
        txn = self.make_charge(self.reservation.folio, 'MINIBAR', 80000)
        target = self.make_master_folio(is_company_master=1, outstanding_balance=0)
        from hospitality_core.hospitality_core.api.folio import move_transactions
        move_transactions([txn.name], target.name)
        from hospitality_core.hospitality_core.report.folio_transaction_move_report.folio_transaction_move_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((d for d in data if d.transaction_name == txn.name), None)
        self.assertIsNotNone(row, 'move_transactions() phai ghi 1 dong Folio Transaction Move Log doc duoc qua report nay.')
        self.assertEqual(row.source_folio, self.reservation.folio)
        self.assertEqual(row.target_folio, target.name)

    # ==================================================================
    # house_list.py
    # ==================================================================
    def test_house_list_includes_checked_in_guest_with_summary(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Checked In')
        from hospitality_core.hospitality_core.report.house_list.house_list import execute
        columns, data, _none, _none2, summary = execute({'date': nowdate()})
        names = {d.get('room') for d in data}
        self.assertIn(self.reservation.room, names)
        self.assertTrue(summary and summary[0]['value'] >= 1)

    def test_house_list_excludes_reserved_not_yet_checked_in(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Reserved')
        from hospitality_core.hospitality_core.report.house_list.house_list import execute
        columns, data, _none, _none2, summary = execute({'date': nowdate()})
        names = {d.get('room') for d in data}
        self.assertNotIn(self.reservation.room, names)

    # ==================================================================
    # guest_list.py
    # ==================================================================
    def test_guest_list_billing_type_company(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, {
            'status': 'Checked In', 'is_company_guest': 1, 'company': self.make_customer('Guest List Test Co')})
        from hospitality_core.hospitality_core.report.guest_list.guest_list import execute
        columns, data = execute({})
        row = next((d for d in data if d.reservation == self.reservation.name), None)
        self.assertIsNotNone(row)
        self.assertTrue(row.billing_type.startswith('Company - '))

    def test_guest_list_only_checked_in(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Confirmed')
        from hospitality_core.hospitality_core.report.guest_list.guest_list import execute
        columns, data = execute({})
        names = {d.reservation for d in data}
        self.assertNotIn(self.reservation.name, names)

    # ==================================================================
    # room_availability_report.py
    # ==================================================================
    def test_room_availability_counts_sold_and_available(self):
        f = self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Checked In')
        from hospitality_core.hospitality_core.report.room_availability_report.room_availability_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((d for d in data if d['room_type'] == self.reservation.room_type), None)
        self.assertIsNotNone(row)
        self.assertGreaterEqual(row['sold'], 1)
        self.assertEqual(row['total_rooms'] - row['ooo'] - row['sold'], row['available'])

    def test_room_availability_filters_by_room_type(self):
        f = self.fixture()
        other_rt = f.room_type('HV-B')
        from hospitality_core.hospitality_core.report.room_availability_report.room_availability_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate(), 'room_type': self.reservation.room_type})
        room_types = {d['room_type'] for d in data}
        self.assertEqual(room_types, {self.reservation.room_type})

    # ==================================================================
    # reservations_report.py
    # ==================================================================
    def test_reservations_report_arrivals_view(self):
        self.fixture()
        from hospitality_core.hospitality_core.report.reservations_report.reservations_report import get_data
        rows = get_data({'date': self.reservation.arrival_date, 'view_mode': 'Arrivals'})
        names = {r.name for r in rows}
        self.assertIn(self.reservation.name, names)

    def test_reservations_report_in_house_view(self):
        self.fixture()
        mid_stay = add_days(self.reservation.arrival_date, 1)
        from hospitality_core.hospitality_core.report.reservations_report.reservations_report import get_data
        rows = get_data({'date': mid_stay, 'view_mode': 'In-House'})
        names = {r.name for r in rows}
        self.assertIn(self.reservation.name, names)

    def test_reservations_report_billing_type_complimentary(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'is_complimentary', 1)
        from hospitality_core.hospitality_core.report.reservations_report.reservations_report import get_data
        rows = get_data({'date': self.reservation.arrival_date, 'view_mode': 'Arrivals'})
        row = next((r for r in rows if r.name == self.reservation.name), None)
        self.assertIsNotNone(row)
        self.assertEqual(row.billing_type, 'Complimentary')

    # ==================================================================
    # housekeeping_productivity_report.py
    # ==================================================================
    def test_housekeeping_productivity_counts_completed_session(self):
        self.fixture()
        from hospitality_core.hospitality_core.api.housekeeping_mobile import log_room_status_change
        log_room_status_change(self.reservation.room, 'Dirty', 'Cleaning')
        log_room_status_change(self.reservation.room, 'Cleaning', 'Inspected')
        from hospitality_core.hospitality_core.report.housekeeping_productivity_report.housekeeping_productivity_report import get_data
        rows = get_data({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((r for r in rows if r['staff'] == 'Administrator'), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['rooms_cleaned'], 1)
        self.assertEqual(row['interrupted_sessions'], 0)

    def test_housekeeping_productivity_flags_interrupted_session(self):
        self.fixture()
        from hospitality_core.hospitality_core.api.housekeeping_mobile import log_room_status_change
        log_room_status_change(self.reservation.room, 'Dirty', 'Cleaning')
        # log_room_status_change() bo qua ghi log neu previous_status ==
        # new_status (xem code) — de tao 2 dong 'Cleaning' lien tiep (mo
        # phong 2 nhan vien cung nhan 1 phong), truyen previous_status KHAC
        # 'Cleaning' o lan goi thu 2 (tham so nay chi la metadata ghi log,
        # khong doi chieu voi trang thai that cua phong trong DB).
        log_room_status_change(self.reservation.room, 'Occupied', 'Cleaning')
        log_room_status_change(self.reservation.room, 'Cleaning', 'Available')
        from hospitality_core.hospitality_core.report.housekeeping_productivity_report.housekeeping_productivity_report import get_data
        rows = get_data({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((r for r in rows if r['staff'] == 'Administrator'), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['interrupted_sessions'], 1,
            'Phien bi ghi de boi lan "Cleaning" thu 2 truoc khi hoan tat phai duoc tinh la bi gian doan.')

    # ==================================================================
    # void_and_allowance_report.py
    # ==================================================================
    def test_void_and_allowance_lists_void_transaction(self):
        self.fixture()
        txn = self.make_charge(self.reservation.folio, 'MINIBAR', 90000, is_void=1, void_reason='Guest complaint')
        from hospitality_core.hospitality_core.report.void_and_allowance_report.void_and_allowance_report import execute
        columns, data, _none, chart = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((d for d in data if d.get('parent') == self.reservation.folio and d.get('type') == 'Void'), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['void_reason'], 'Guest complaint')

    def test_void_and_allowance_lists_discount_excludes_mirror(self):
        self.fixture()
        original = self.make_charge(self.reservation.folio, 'DISCOUNT', -50000)
        master = self.make_master_folio(is_company_master=1, outstanding_balance=0)
        mirror = self.make_charge(master.name, 'DISCOUNT', -50000, mirror_source=original.name, bill_to='Company')
        from hospitality_core.hospitality_core.report.void_and_allowance_report.void_and_allowance_report import execute
        columns, data, _none, chart = execute({'from_date': nowdate(), 'to_date': nowdate()})
        matching = [d for d in data if d.get('type') == 'Discount' and d.get('amount') == -50000]
        self.assertEqual(len(matching), 1, 'Ban sao mirror tren Master Folio khong duoc dem lai lan 2.')

    # ==================================================================
    # discount_and_complimentary_report.py
    # ==================================================================
    def test_discount_complimentary_classifies_type(self):
        self.fixture()
        self.make_charge(self.reservation.folio, 'COMPLIMENTARY', -40000)
        from hospitality_core.hospitality_core.report.discount_and_complimentary_report.discount_and_complimentary_report import execute
        columns, data, _none, chart = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((d for d in data if d.get('parent') == self.reservation.folio), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['type'], 'Complimentary')
        self.assertEqual(flt(row['amount']), 40000, 'Bao cao hien thi so duong de de doc, du amount goc am.')

    def test_discount_complimentary_type_filter_via_having(self):
        self.fixture()
        self.make_charge(self.reservation.folio, 'COMPLIMENTARY', -20000)
        from hospitality_core.hospitality_core.report.discount_and_complimentary_report.discount_and_complimentary_report import execute
        columns, data, _none, chart = execute({'from_date': nowdate(), 'to_date': nowdate(), 'type': 'Discount'})
        names = {d.get('parent') for d in data}
        self.assertNotIn(self.reservation.folio, names,
            'Filter type=Discount phai loai tru dong Complimentary (HAVING tren alias tinh boi CASE).')

    # ==================================================================
    # folio_balance_summary.py
    # ==================================================================
    def test_folio_balance_summary_guest_ledger_bucket(self):
        self.fixture()
        frappe.db.set_value('Guest Folio', self.reservation.folio, 'outstanding_balance', 250000, update_modified=False)
        from hospitality_core.hospitality_core.report.folio_balance_summary.folio_balance_summary import execute
        columns, data, _none, chart = execute({})
        guest_row = next((d for d in data if d.get('ledger_type') == 'Guest Ledger'), None)
        self.assertIsNotNone(guest_row)
        self.assertGreaterEqual(flt(guest_row['balance']), 250000)

    def test_folio_balance_summary_city_ledger_counts_master_only(self):
        self.fixture()
        company_folio = self.make_master_folio(is_company_master=1, outstanding_balance=350000)
        from hospitality_core.hospitality_core.report.folio_balance_summary.folio_balance_summary import execute
        columns, data, _none, chart = execute({})
        city_row = next((d for d in data if d.get('ledger_type') == 'City Ledger'), None)
        self.assertIsNotNone(city_row)
        self.assertGreaterEqual(flt(city_row['balance']), 350000)

    # ==================================================================
    # daily_sales_consumption.py
    # ==================================================================
    def test_daily_sales_consumption_merges_discount_into_room_charge(self):
        self.fixture()
        self.make_charge(self.reservation.folio, 'ROOM-RENT', 1000000)
        self.make_charge(self.reservation.folio, 'DISCOUNT', -100000)
        from hospitality_core.hospitality_core.report.daily_sales_consumption.daily_sales_consumption import execute
        columns, charges = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((c for c in charges if c.get('item') == 'ROOM-RENT'), None)
        self.assertIsNotNone(row)
        self.assertEqual(flt(row['discount_amount']), 100000)
        self.assertEqual(flt(row['amount']), 900000)

    def test_daily_sales_consumption_excludes_company_master_by_default(self):
        self.fixture()
        company_folio = self.make_master_folio(is_company_master=1, outstanding_balance=0)
        self.make_charge(company_folio.name, 'MINIBAR', 60000, bill_to='Company')
        from hospitality_core.hospitality_core.report.daily_sales_consumption.daily_sales_consumption import execute
        columns, charges = execute({'from_date': nowdate(), 'to_date': nowdate()})
        parents = {c.get('room') for c in charges}
        # Master folio khong co room rieng (room field tren Guest Folio rong cho
        # master) — kiem tra gian tiep qua so dong khop item MINIBAR gan voi
        # folio nay bang cach dem tong so dong, dam bao khong co dong nao co
        # gross_amount=60000 tu company master khi khong bat include_non_revenue.
        matching = [c for c in charges if flt(c.get('gross_amount')) == 60000]
        self.assertFalse(matching, 'Mac dinh (include_non_revenue khong bat) phai loai Company Master Folio.')

    # ==================================================================
    # hotel_performance_analytics.py
    # ==================================================================
    def test_hotel_performance_analytics_computes_adr_revpar(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Checked In')
        self.make_charge(self.reservation.folio, 'ROOM-RENT', 1500000)
        from hospitality_core.hospitality_core.report.hotel_performance_analytics.hotel_performance_analytics import execute
        columns, data, _none, chart = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((d for d in data if d['date'] == str(getdate(nowdate()))), None)
        self.assertIsNotNone(row)
        self.assertGreaterEqual(row['occupied_rooms'], 1)
        self.assertEqual(flt(row['adr']), flt(row['revenue']) / row['occupied_rooms'])

    # ==================================================================
    # point_of_sale_report.py
    # ==================================================================
    def test_point_of_sale_report_requires_pos_profile(self):
        self.fixture()
        from hospitality_core.hospitality_core.report.point_of_sale_report.point_of_sale_report import execute
        columns, data = execute({})
        self.assertEqual(data, [], 'Khong co pos_profile phai tra ve rong, khong query gi ca.')

    def test_point_of_sale_report_no_matching_invoices_still_shows_zero_total(self):
        self.fixture()
        from hospitality_core.hospitality_core.report.point_of_sale_report.point_of_sale_report import execute
        columns, data = execute({'pos_profile': 'Nonexistent Test Profile XYZ'})
        total_row = next((d for d in data if 'Total' in str(d.get('item_name', ''))), None)
        self.assertIsNotNone(total_row)
        self.assertEqual(flt(total_row['amount']), 0)

    # ==================================================================
    # police_guest_registration_report.py
    # ==================================================================
    def test_police_guest_registration_includes_checked_in_and_flags_missing_id(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Checked In')
        from hospitality_core.hospitality_core.report.police_guest_registration_report.police_guest_registration_report import execute
        columns, data = execute({'target_date': nowdate()})
        row = next((d for d in data if d['reservation'] == self.reservation.name), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['warning'], 'THIẾU SỐ GIẤY TỜ',
            'Khach chua co so CCCD/ho chieu phai duoc gan canh bao ro rang, khong duoc bo qua am tham.')

    def test_police_guest_registration_company_is_plain_data_not_broken_link(self):
        self.fixture()
        frappe.db.set_value('Hotel Reservation', self.reservation.name, {
            'status': 'Checked In', 'company': self.make_customer('Police Report Test Agency')})
        from hospitality_core.hospitality_core.report.police_guest_registration_report.police_guest_registration_report import execute
        columns, data = execute({'target_date': nowdate()})
        col = next(c for c in columns if c['fieldname'] == 'company')
        self.assertEqual(col['fieldtype'], 'Data',
            'Sau fix: field "company" phai la Data (gia tri thuc su la Customer, khong phai Company) — khong con la Link hong.')
        row = next((d for d in data if d['reservation'] == self.reservation.name), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['company'], 'Police Report Test Agency')


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(OperationalReportsTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
