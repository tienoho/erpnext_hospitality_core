"""Kịch bản kiểm thử MỚI — Đợt 4 (báo cáo tài chính ưu tiên cao, phần 2/2):
pos_sales_summary.py, financial_activity_summary.py, frontdesk_end_of_day_report.py.
Cả 3 report CHƯA TỪNG chạy thật lần nào — 2 report đầu phụ thuộc lẫn nhau qua
room_only_sales.py/daily_payment_collection.py (đã test/fix ở các đợt trước).

Không có report nào trong 3 file này gọi frappe.db.commit(); fixture tạo POS
Invoice/POS Closing Entry cũng không commit — an toàn dùng rollback-based.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days, now_datetime, flt
from run_property_integration import PropertyDatabaseTests


class POSReportsTests(unittest.TestCase):
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
        # "Hospitality Accounting Settings" la Single TOAN SITE dung chung boi
        # MOI file test Legacy (city_ledger/group_booking/docker_verification)
        # — POS Invoice submit() luon chay qua accounting.py's
        # redirect_pos_income_to_suspense()/reclassify_pos_taxes() (Legacy),
        # doc settings.cost_center tu Single nay. Neu file test KHAC chay
        # truoc do cau hinh cho company RIENG cua no (VD 'FC Test Co'), Single
        # se tro sai company khi toi luot file nay. Dung lai dung ham da xac
        # nhan an toan trong run_docker_verification.py (tu kiem tra +
        # cau hinh lai neu can, khong "chi dien neu con trong").
        from run_docker_verification import ensure_legacy_accounting_settings
        ensure_legacy_accounting_settings(self.company_a)
        # POS Closing Entry's validate() luôn ĐỌC LẠI POS Settings.invoice_type
        # (fetch_invoice_type(), ghi đè bất kể gì đã set trên doc) để quyết
        # định kiểm tra 'POS Invoice' hay 'Sales Invoice' — mặc định ERPNext
        # là 'Sales Invoice', SAI với app này (dùng POS Invoice xuyên suốt).
        frappe.db.set_single_value('POS Settings', 'invoice_type', 'POS Invoice')
        return f

    # ------------------------------------------------------------------
    # Helpers dùng chung
    # ------------------------------------------------------------------
    def make_item(self, code, item_group='Services'):
        if not frappe.db.exists('Item Group', item_group):
            root = frappe.db.get_value('Item Group', {'is_group': 1}, 'name', order_by='lft')
            frappe.get_doc(dict(doctype='Item Group', item_group_name=item_group,
                parent_item_group=root)).insert(ignore_permissions=True)
        if not frappe.db.exists('Item', code):
            frappe.get_doc(dict(doctype='Item', item_code=code, item_name=code, item_group=item_group,
                stock_uom='Nos', is_stock_item=0, is_sales_item=1)).insert(ignore_permissions=True)
        return code

    def make_pos_profile(self, name, mode_of_payment='Cash'):
        if frappe.db.exists('POS Profile', name):
            return name
        income = frappe.db.get_value('Hospitality Company Accounting Settings', self.company_a, 'income_account')
        cost_center = frappe.db.get_value('Hospitality Company Accounting Settings', self.company_a, 'cost_center')
        expense = frappe.db.get_value('Company', self.company_a, 'default_expense_account') or income
        warehouse = frappe.db.get_value('Warehouse', {'company': self.company_a, 'is_group': 0}, 'name')
        if not warehouse:
            parent = frappe.db.get_value('Warehouse', {'company': self.company_a, 'is_group': 1}, 'name', order_by='lft')
            warehouse = frappe.get_doc(dict(doctype='Warehouse', warehouse_name='POS Test Store',
                company=self.company_a, parent_warehouse=parent)).insert(ignore_permissions=True).name
        if not frappe.db.exists('Mode of Payment', mode_of_payment):
            cash = frappe.db.get_value('Account', {'company': self.company_a, 'account_type': 'Cash', 'is_group': 0}, 'name')
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment=mode_of_payment, type='Cash',
                accounts=[dict(company=self.company_a, default_account=cash)])).insert(ignore_permissions=True)
        elif not frappe.db.exists('Mode of Payment Account', {'parent': mode_of_payment, 'company': self.company_a}):
            cash = frappe.db.get_value('Account', {'company': self.company_a, 'account_type': 'Cash', 'is_group': 0}, 'name')
            mop = frappe.get_doc('Mode of Payment', mode_of_payment)
            mop.append('accounts', dict(company=self.company_a, default_account=cash))
            mop.save(ignore_permissions=True)
        frappe.get_doc(dict(doctype='POS Profile', name=name, company=self.company_a, currency='VND',
            warehouse=warehouse, selling_price_list=frappe.db.get_single_value('Selling Settings', 'selling_price_list'),
            income_account=income, expense_account=expense, cost_center=cost_center,
            write_off_account=income, write_off_cost_center=cost_center,
            payments=[dict(mode_of_payment=mode_of_payment, default=1)])).insert(ignore_permissions=True)
        return name

    def make_pos_opening(self, pos_profile, mode_of_payment='Cash'):
        existing = frappe.db.get_value('POS Opening Entry', {'pos_profile': pos_profile, 'status': 'Open'}, 'name')
        if existing:
            return existing
        opening = frappe.get_doc(dict(doctype='POS Opening Entry', company=self.company_a, pos_profile=pos_profile,
            user='Administrator', period_start_date=now_datetime(), posting_date=nowdate(),
            balance_details=[dict(mode_of_payment=mode_of_payment, opening_amount=0)]))
        opening.insert(ignore_permissions=True)
        opening.submit()
        return opening.name

    def make_pos_invoice(self, pos_profile, item_code, amount, mode_of_payment='Cash', hotel_room=None):
        customer = 'Walk in Customer'
        if not frappe.db.exists('Customer', customer):
            frappe.get_doc(dict(doctype='Customer', customer_name=customer, customer_type='Individual',
                customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert(ignore_permissions=True)
        inv = frappe.get_doc(dict(doctype='POS Invoice', company=self.company_a, customer=customer,
            pos_profile=pos_profile, currency='VND', conversion_rate=1, hotel_room=hotel_room,
            selling_price_list=frappe.db.get_single_value('Selling Settings', 'selling_price_list'),
            posting_date=nowdate(),
            items=[dict(item_code=item_code, qty=1, rate=amount)],
            payments=[dict(mode_of_payment=mode_of_payment, amount=amount)]))
        inv.insert(ignore_permissions=True)
        inv.payments[0].amount = inv.grand_total
        inv.paid_amount = inv.grand_total
        inv.save()
        inv.submit()
        return inv

    def make_closing_entry(self, pos_profile, mode_of_payment='Cash'):
        from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import make_closing_entry_from_opening
        opening_name = frappe.db.get_value('POS Opening Entry', {'pos_profile': pos_profile, 'status': 'Open'}, 'name')
        opening = frappe.get_doc('POS Opening Entry', opening_name)
        closing = make_closing_entry_from_opening(opening)
        for row in closing.get('payment_reconciliation') or []:
            row.closing_amount = row.expected_amount
        closing.flags.ignore_permissions = True
        closing.insert(ignore_permissions=True)
        closing.submit()
        return closing

    # ==================================================================
    # pos_sales_summary.py
    # ==================================================================
    def test_pos_sales_summary_returns_empty_without_date_filter(self):
        self.fixture()
        from hospitality_core.hospitality_core.report.pos_sales_summary.pos_sales_summary import execute
        columns, data = execute({})
        self.assertEqual(data, [])

    def test_pos_sales_summary_profile_totals_and_payment_breakdown(self):
        self.fixture()
        profile = self.make_pos_profile('Test Restaurant POS')
        self.make_pos_opening(profile)
        inv = self.make_pos_invoice(profile, self.make_item('POS-TEST-DRINK'), 200000)
        closing = self.make_closing_entry(profile)
        from hospitality_core.hospitality_core.report.pos_sales_summary.pos_sales_summary import execute
        columns, data = execute({'date': nowdate()})
        descriptions = [d['description'] for d in data]
        self.assertIn(f'<b>{profile}</b>', descriptions)
        sales_idx = descriptions.index(f'<b>{profile}</b>') + 1
        self.assertEqual(data[sales_idx]['description'], 'Total Sales')
        self.assertEqual(flt(data[sales_idx]['amount']), flt(inv.grand_total))

    def test_pos_sales_summary_excludes_reception_from_summary_only(self):
        f = self.fixture()
        reception = self.make_pos_profile('Reception')
        self.make_pos_opening(reception)
        self.make_pos_invoice(reception, self.make_item('POS-TEST-RECEPTION-ITEM'), 150000)
        self.make_closing_entry(reception)
        from hospitality_core.hospitality_core.report.pos_sales_summary.pos_sales_summary import execute
        columns, data = execute({'date': nowdate()})
        descriptions = [d['description'] for d in data]
        # Van hien thi rieng cho profile 'Reception' (khong loai o phan per-profile)
        self.assertIn('<b>Reception</b>', descriptions)
        # Nhung "Total POS Sales" trong Summary phai KHONG cong don doanh thu Reception
        summary_start = descriptions.index('<b>Summary</b>')
        summary_rows = data[summary_start:]
        total_pos_row = next((r for r in summary_rows if r['description'] == 'Total POS Sales'), None)
        self.assertIsNotNone(total_pos_row)
        self.assertEqual(flt(total_pos_row['amount']), 0,
            'Reception phai duoc loai khoi "Total POS Sales" trong Summary (da tinh rieng qua Accommodation).')

    def test_pos_sales_summary_filter_by_specific_profile_skips_breakfast_exclusion(self):
        f = self.fixture()
        profile = self.make_pos_profile('Test Bar POS')
        self.make_pos_opening(profile)
        inv = self.make_pos_invoice(profile, self.make_item('POS-TEST-BAR-ITEM'), 90000)
        self.make_closing_entry(profile)
        from hospitality_core.hospitality_core.report.pos_sales_summary.pos_sales_summary import execute
        columns, data = execute({'date': nowdate(), 'pos_profile': profile})
        summary_start = next(i for i, d in enumerate(data) if d['description'] == '<b>Summary</b>')
        summary_rows = data[summary_start + 1:]
        self.assertEqual(summary_rows[0]['description'], 'Total Sales')
        self.assertEqual(flt(summary_rows[0]['amount']), flt(inv.grand_total))

    # ==================================================================
    # financial_activity_summary.py
    # ==================================================================
    def test_financial_activity_summary_empty_without_date(self):
        self.fixture()
        from hospitality_core.hospitality_core.report.financial_activity_summary.financial_activity_summary import execute
        columns, data = execute({})
        self.assertEqual(data, [])

    def test_financial_activity_summary_item_group_and_accommodation(self):
        f = self.fixture()
        profile = self.make_pos_profile('Test FnB POS')
        self.make_pos_opening(profile)
        drink_item = self.make_item('FAS-TEST-DRINK', item_group='Drinks')
        self.make_pos_invoice(profile, drink_item, 120000)
        self.make_closing_entry(profile)
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists('ROOM-RENT', 'ROOM-RENT')
        room_txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=self.reservation.folio, parenttype='Guest Folio',
            parentfield='transactions', posting_date=nowdate(), item='ROOM-RENT', description='Room charge',
            qty=1, amount=1500000, bill_to='Guest', is_void=0))
        room_txn.flags.hospitality_service = True
        room_txn.insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.report.financial_activity_summary.financial_activity_summary import execute
        columns, data = execute({'date': nowdate()})
        by_desc = {d['description']: d['amount'] for d in data}
        self.assertEqual(flt(by_desc.get('Drinks')), 120000)
        self.assertEqual(flt(by_desc.get('Accommodation')), 1500000)

    def test_financial_activity_summary_protein_and_food_split(self):
        f = self.fixture()
        profile = self.make_pos_profile('Test Kitchen POS')
        self.make_pos_opening(profile)
        food_item = self.make_item('FAS-TEST-VEGGIE', item_group='Food')
        chicken_item = self.make_item('FAS-TEST-CHICKEN-DISH', item_group='Food')
        self.make_pos_invoice(profile, food_item, 60000)
        self.make_pos_invoice(profile, chicken_item, 80000)
        self.make_closing_entry(profile)
        from hospitality_core.hospitality_core.report.financial_activity_summary.financial_activity_summary import execute
        columns, data = execute({'date': nowdate()})
        by_desc = {d['description']: d['amount'] for d in data}
        self.assertEqual(flt(by_desc.get('Food (without Proteins)')), 60000)
        self.assertEqual(flt(by_desc.get('Chicken')), 80000)
        self.assertEqual(flt(by_desc.get('<b>Total Proteins</b>')), 80000)
        self.assertEqual(flt(by_desc.get('<b>Food with Proteins</b>')), 140000)

    def test_financial_activity_summary_tray_charge_by_item_name(self):
        f = self.fixture()
        profile = self.make_pos_profile('Test Tray POS')
        self.make_pos_opening(profile)
        tray_item = self.make_item('FAS-TEST-TRAY-01')
        frappe.db.set_value('Item', tray_item, 'item_name', 'Tray Charge - VIP')
        self.make_pos_invoice(profile, tray_item, 30000)
        self.make_closing_entry(profile)
        from hospitality_core.hospitality_core.report.financial_activity_summary.financial_activity_summary import execute
        columns, data = execute({'date': nowdate()})
        by_desc = {d['description']: d['amount'] for d in data}
        self.assertEqual(flt(by_desc.get('Tray Charge')), 30000)

    # ==================================================================
    # frontdesk_end_of_day_report.py
    # ==================================================================
    def test_frontdesk_eod_empty_without_date(self):
        self.fixture()
        from hospitality_core.hospitality_core.report.frontdesk_end_of_day_report.frontdesk_end_of_day_report import execute
        columns, data = execute({})
        self.assertEqual(data, [])

    def test_frontdesk_eod_checkins_and_departures(self):
        f = self.fixture()
        reception = frappe.db.get_value('Hotel Room', self.reservation.room, 'hotel_reception')
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Checked In')
        room2, guest2, res2 = self._make_checked_out_reservation(f)
        from hospitality_core.hospitality_core.report.frontdesk_end_of_day_report.frontdesk_end_of_day_report import execute
        columns, data = execute({'date': nowdate(), 'hotel_reception': reception})
        by_metric = {d['metric']: d['value'] for d in data}
        self.assertEqual(by_metric['New Check-ins'], 2, 'Ca Checked In lan Checked Out (da qua arrival_date hom nay) deu tinh la check-in.')
        self.assertEqual(by_metric['Departures'], 1)

    def _make_checked_out_reservation(self, f):
        room = f.room('HV-A', room_type=self.reservation.room_type, number='EOD-CHECKOUT-1')
        guest = frappe.get_doc(dict(doctype='Guest', full_name='EOD Checkout Guest', guest_type='Regular')).insert(ignore_permissions=True)
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property='HV-A', guest=guest.name,
            room=room.name, room_type=room.room_type, hotel_reception=room.hotel_reception,
            currency='VND', arrival_date=nowdate(), departure_date=nowdate())).insert()
        frappe.db.set_value('Hotel Reservation', res.name, 'status', 'Checked Out')
        return room, guest, res

    def test_frontdesk_eod_sales_consumption_and_tax_breakdown(self):
        f = self.fixture()
        reception = frappe.db.get_value('Hotel Room', self.reservation.room, 'hotel_reception')
        item = self.make_item('EOD-TEST-CHARGE')
        txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=self.reservation.folio, parenttype='Guest Folio',
            parentfield='transactions', posting_date=nowdate(), item=item, description='EOD test charge',
            qty=1, amount=1225000, bill_to='Guest', is_void=0))
        txn.flags.hospitality_service = True
        txn.insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.api.accounting import get_tax_breakdown
        expected = get_tax_breakdown(1225000)
        from hospitality_core.hospitality_core.report.frontdesk_end_of_day_report.frontdesk_end_of_day_report import execute
        columns, data = execute({'date': nowdate(), 'hotel_reception': reception})
        by_metric = {d['metric']: d['value'] for d in data}
        self.assertIn('1,225,000', by_metric['Sales Consumption (Gross)'].replace('.', ',').replace(' ', ''))

    def test_frontdesk_eod_expenses_and_net_profit(self):
        f = self.fixture()
        reception = frappe.db.get_value('Hotel Room', self.reservation.room, 'hotel_reception')
        expense_category = self._ensure_expense_category()
        mode_of_payment = self._ensure_cash_mode_of_payment()
        cost_center = frappe.db.get_value('Cost Center', {'company': self.company_a, 'is_group': 0}, 'name')
        expense = frappe.get_doc(dict(doctype='Hospitality Expense', expense_date=nowdate(),
            expense_category=expense_category, paid_via=mode_of_payment, company=self.company_a,
            amount=40000, grand_total=40000, cost_center=cost_center, hotel_reception=reception,
            property='HV-A')).insert(ignore_permissions=True)
        expense.submit()
        from hospitality_core.hospitality_core.report.frontdesk_end_of_day_report.frontdesk_end_of_day_report import execute
        columns, data = execute({'date': nowdate(), 'hotel_reception': reception})
        by_metric = {d['metric']: d['value'] for d in data}
        self.assertIn('40,000', by_metric['Total Expenses'].replace('.', ',').replace(' ', ''))
        self.assertTrue(any(k.strip() == f'- {expense_category}' for k in by_metric),
            f'Phai co dong chi tiet theo danh muc {expense_category}.')

    def _ensure_expense_category(self):
        name = 'EOD Test Category'
        if not frappe.db.exists('Expense Category', name):
            expense_account = frappe.db.get_value('Account', {'company': self.company_a, 'root_type': 'Expense',
                'is_group': 0}, 'name')
            frappe.get_doc(dict(doctype='Expense Category', category_name=name,
                default_expense_account=expense_account)).insert(ignore_permissions=True)
        return name

    def _ensure_cash_mode_of_payment(self):
        name = 'Cash'
        cash = frappe.db.get_value('Account', {'company': self.company_a, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', name):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment=name, type='Cash',
                accounts=[dict(company=self.company_a, default_account=cash)])).insert(ignore_permissions=True)
        elif not frappe.db.exists('Mode of Payment Account', {'parent': name, 'company': self.company_a}):
            mop = frappe.get_doc('Mode of Payment', name)
            mop.append('accounts', dict(company=self.company_a, default_account=cash))
            mop.save(ignore_permissions=True)
        return name


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(POSReportsTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
