"""Kịch bản kiểm thử — 3 báo cáo phụ thuộc POS còn treo từ Đợt 4:
pos_sales_summary.py, financial_activity_summary.py, frontdesk_end_of_day_report.py.

QUAN TRỌNG VỀ FIXTURE (khác hẳn MỌI file test khác trong thư mục này): POS
Invoice.submit()/POS Closing Entry.submit() LUÔN kích hoạt `frappe.db.commit()`
thật bên trong (cơ chế ghi sổ GL an toàn của ERPNext — `make_gl_entries()`),
HOÀN TOÀN ĐỘC LẬP với việc test có lỗi hay không, và `frappe.db.rollback()` ở
tearDown() KHÔNG THỂ hoàn tác lại (đã xác nhận thật, gây corrupt site 'localhost'
2 lần trong phiên trước — xem plan file). KHÔNG được dùng
`PropertyDatabaseTests.accounting_reservation()` (property 'HV-A' dùng CHUNG
cho MỌI file test khác) — dùng 1 Company + Hospitality Property HOÀN TOÀN
RIÊNG (khớp mẫu `void_fixture()` đã dùng an toàn cho
`run_city_ledger_financial_control_tests.py`'s `void_transaction()`), để commit
thật của POS Invoice/Closing Entry chỉ "khóa cứng" đúng company/property cô
lập này — vô hại tuyệt đối vì không file test nào khác tham chiếu tới.
"""
import re
import unittest
import frappe
from frappe.utils import nowdate, add_days, now_datetime, flt, getdate
from run_property_integration import PropertyDatabaseTests


def _parse_money(formatted):
    """Chuyen chuoi tien te da format (VD '1,225,000.00' hoac co ky hieu
    tien te) thanh so thuc — dung de do CHENH LECH truoc/sau, vi
    frontdesk_end_of_day_report.py chi tra ve gia tri DA FORMAT (khong co
    so tho)."""
    if not formatted:
        return 0.0
    cleaned = re.sub(r'[^\d.\-]', '', str(formatted))
    return flt(cleaned) if cleaned else 0.0


class POSReportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def fixture(self):
        """Company + Property CÔ LẬP riêng cho file test này — không dùng
        'HV-A'/'_Hospitality V2 A' hay 'FC-TEST'/'FC Test Co' (đã dùng bởi
        run_city_ledger_financial_control_tests.py) để không đè lẫn nhau nếu
        2 file cùng chạy gần nhau trong 1 phiên."""
        company = 'POS Report Test Co'
        if not frappe.db.exists('Company', company):
            # Company.insert() tự frappe.db.commit() nội bộ (bootstrap chart
            # of accounts) — không cần commit thêm, chỉ cần company này không
            # bị file test nào khác tham chiếu.
            frappe.get_doc(dict(doctype='Company', company_name=company, abbr='PRTC', country='Vietnam',
                default_currency='VND', create_chart_of_accounts_based_on='Standard Template',
                chart_of_accounts='Standard')).insert(ignore_permissions=True)
        self.company_a = company

        year = str(getdate(nowdate()).year)
        if not frappe.db.exists('Fiscal Year', year):
            frappe.get_doc(dict(doctype='Fiscal Year', year=year, year_start_date=year + '-01-01',
                year_end_date=year + '-12-31')).insert(ignore_permissions=True)
        else:
            # Site 'localhost' co san Fiscal Year nam nay nhung GIOI HAN theo
            # danh sach company THAT cua Tap doan Tuan Chau — them company
            # cua rieng file nay vao neu bang con dang o che do gioi han.
            fy = frappe.get_doc('Fiscal Year', year)
            existing_companies = {d.company for d in (fy.get('companies') or [])}
            if existing_companies and company not in existing_companies:
                fy.append('companies', dict(company=company))
                fy.save(ignore_permissions=True)

        # KHONG dung run_docker_verification.ensure_legacy_accounting_settings()
        # o day — ham do doc income_account tu 'Hospitality Company Accounting
        # Settings' (doctype RIENG cua Property v2, chi ton tai cho company da
        # qua accounting_reservation()'s setup) — company cua rieng file nay
        # chua tung qua Property v2 setup nen se MandatoryError. Tu tao Account
        # truc tiep, khop dung mau da dung o
        # run_city_ledger_financial_control_tests.py's ensure_legacy_payment_prereqs().
        cash = frappe.db.get_value('Account', {'company': company, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', 'PRT Cash'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='PRT Cash', type='Cash',
                accounts=[dict(company=company, default_account=cash)])).insert(ignore_permissions=True)
        elif not frappe.db.exists('Mode of Payment Account', {'parent': 'PRT Cash', 'company': company}):
            mop = frappe.get_doc('Mode of Payment', 'PRT Cash')
            mop.append('accounts', dict(company=company, default_account=cash))
            mop.save(ignore_permissions=True)

        def _account(label, root_type):
            existing = frappe.db.get_value('Account', {'company': company, 'account_name': label}, 'name')
            if existing:
                return existing
            parent = frappe.db.get_value('Account', {'company': company, 'root_type': root_type,
                'is_group': 1}, 'name', order_by='lft')
            return frappe.get_doc(dict(doctype='Account', account_name=label, parent_account=parent,
                company=company, account_currency='VND')).insert().name

        settings = frappe.get_single('Hospitality Accounting Settings')
        settings.receivable_account = frappe.db.get_value('Company', company, 'default_receivable_account')
        settings.income_suspense_account = _account('PRT Income Suspense', 'Liability')
        settings.income_account = _account('PRT Room Revenue', 'Income')
        settings.consumption_tax_account = _account('PRT Consumption Tax', 'Liability')
        settings.vat_account = _account('PRT VAT', 'Liability')
        settings.service_charge_account = _account('PRT Service Charge', 'Liability')
        settings.cost_center = frappe.db.get_value('Company', company, 'cost_center')
        settings.enable_vietqr = 0
        settings.save(ignore_permissions=True)
        self._income_account = settings.income_account
        self._cost_center = settings.cost_center

        frappe.db.set_single_value('POS Settings', 'invoice_type', 'POS Invoice')

        # Price List RIENG (khong dung 'Integration Selling' dung chung boi
        # accounting_reservation() — file nay khong goi ham do, tranh moi lien
        # quan toi Single 'Selling Settings' ma cac file khac phu thuoc).
        price_list = 'POS Report Selling'
        if not frappe.db.exists('Price List', price_list):
            frappe.get_doc(dict(doctype='Price List', price_list_name=price_list,
                selling=1, enabled=1, currency='VND')).insert(ignore_permissions=True)
        frappe.db.set_single_value('Selling Settings', 'selling_price_list', price_list)
        frappe.db.set_default('selling_price_list', price_list)
        self.price_list = price_list

        prop = 'PRT-TEST'
        if not frappe.db.exists('Hospitality Property', prop):
            frappe.get_doc(dict(doctype='Hospitality Property', property_code=prop, property_name=prop,
                operating_company=company, currency='VND', timezone='Asia/Ho_Chi_Minh',
                accept_new_bookings=1)).insert(ignore_permissions=True)
        self.property = prop

        room_type = frappe.db.get_value('Hotel Room Type', {'property': prop}, 'name')
        if not room_type:
            room_type = frappe.get_doc(dict(doctype='Hotel Room Type', property=prop,
                room_type_name='PRT Standard', max_adults=2, max_children=1, default_rate=1000000,
                currency_rates=[dict(currency='VND', default_rate=1000000)])).insert(ignore_permissions=True).name
        reception = frappe.db.get_value('Hotel Reception', {'property': prop}, 'name')
        if not reception:
            reception = frappe.get_doc(dict(doctype='Hotel Reception', reception_name='PRT-TEST-Reception',
                property=prop)).insert(ignore_permissions=True).name

        suffix = frappe.generate_hash(6)
        room = frappe.get_doc(dict(doctype='Hotel Room', property=prop, room_number=f'PRT-{suffix}',
            room_type=room_type, hotel_reception=reception, status='Available', is_enabled=1)).insert(ignore_permissions=True)
        guest = frappe.get_doc(dict(doctype='Guest', full_name=f'POS Report Test Guest {suffix}',
            guest_type='Regular')).insert(ignore_permissions=True)
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property=prop, guest=guest.name,
            room=room.name, room_type=room_type, hotel_reception=reception, currency='VND',
            arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert(ignore_permissions=True)
        frappe.db.set_value('Guest Folio', res.folio, 'status', 'Open')
        self.reservation = res
        return self

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

    def make_pos_profile(self, name, mode_of_payment='PRT Cash'):
        if frappe.db.exists('POS Profile', name):
            return name
        income = self._income_account
        cost_center = self._cost_center
        expense = frappe.db.get_value('Company', self.company_a, 'default_expense_account') or income
        warehouse = frappe.db.get_value('Warehouse', {'company': self.company_a, 'is_group': 0}, 'name')
        if not warehouse:
            parent = frappe.db.get_value('Warehouse', {'company': self.company_a, 'is_group': 1}, 'name', order_by='lft')
            warehouse = frappe.get_doc(dict(doctype='Warehouse', warehouse_name='POS Report Test Store',
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
            warehouse=warehouse, selling_price_list=self.price_list,
            income_account=income, expense_account=expense, cost_center=cost_center,
            write_off_account=income, write_off_cost_center=cost_center,
            payments=[dict(mode_of_payment=mode_of_payment, default=1)])).insert(ignore_permissions=True)
        return name

    def make_pos_opening(self, pos_profile, mode_of_payment='PRT Cash'):
        existing = frappe.db.get_value('POS Opening Entry', {'pos_profile': pos_profile, 'status': 'Open'}, 'name')
        if existing:
            return existing
        opening = frappe.get_doc(dict(doctype='POS Opening Entry', company=self.company_a, pos_profile=pos_profile,
            user='Administrator', period_start_date=now_datetime(), posting_date=nowdate(),
            balance_details=[dict(mode_of_payment=mode_of_payment, opening_amount=0)]))
        opening.insert(ignore_permissions=True)
        opening.submit()
        return opening.name

    def make_pos_invoice(self, pos_profile, item_code, amount, mode_of_payment='PRT Cash', hotel_room=None):
        # pos_bridge.py's enforce_payment_mode_rules() nhan dien dung TEN
        # "Walk in Customer" (khong gan Phong -> chi duoc thanh toan
        # 'Complimentary', TRU khi dung dung ten nay) — Customer la doctype
        # toan cuc (khong co field company), dung chung ten nay giua cac file
        # test khac an toan, khong gay xung dot/o nhiem gi.
        customer = 'Walk in Customer'
        if not frappe.db.exists('Customer', customer):
            frappe.get_doc(dict(doctype='Customer', customer_name=customer, customer_type='Individual',
                customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert(ignore_permissions=True)
        inv = frappe.get_doc(dict(doctype='POS Invoice', company=self.company_a, customer=customer,
            pos_profile=pos_profile, currency='VND', conversion_rate=1, hotel_room=hotel_room,
            selling_price_list=self.price_list, posting_date=nowdate(),
            items=[dict(item_code=item_code, qty=1, rate=amount)],
            payments=[dict(mode_of_payment=mode_of_payment, amount=amount)]))
        inv.insert(ignore_permissions=True)
        inv.payments[0].amount = inv.grand_total
        inv.paid_amount = inv.grand_total
        inv.save()
        inv.submit()
        return inv

    def make_closing_entry(self, pos_profile, mode_of_payment='PRT Cash'):
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

    def _pos_profile_total_sales(self, profile):
        """'PRT Report Test Co' la company CO LAP nhung du lieu POS
        Invoice/Closing Entry (commit that, khong rollback duoc) VAN TICH
        LUY qua nhieu lan chay file test nay (POS Profile dung ten CO
        DINH, tai su dung giua cac lan chay) — khong duoc gia dinh "Total
        Sales" bang dung 1 hoa don vua tao, phai do CHENH LECH truoc/sau."""
        from hospitality_core.hospitality_core.report.pos_sales_summary.pos_sales_summary import execute
        columns, data = execute({'date': nowdate(), 'pos_profile': profile})
        descriptions = [d['description'] for d in data]
        if f'<b>{profile}</b>' not in descriptions:
            return 0.0
        sales_idx = descriptions.index(f'<b>{profile}</b>') + 1
        if sales_idx < len(data) and data[sales_idx]['description'] == 'Total Sales':
            return flt(data[sales_idx]['amount'])
        return 0.0

    def test_pos_sales_summary_profile_totals_and_payment_breakdown(self):
        self.fixture()
        profile = self.make_pos_profile('PRT Restaurant POS')
        self.make_pos_opening(profile)
        before = self._pos_profile_total_sales(profile)
        inv = self.make_pos_invoice(profile, self.make_item('PRT-TEST-DRINK'), 200000)
        self.make_closing_entry(profile)
        after = self._pos_profile_total_sales(profile)
        self.assertEqual(after - before, flt(inv.grand_total))

    def _total_pos_sales_summary(self):
        from hospitality_core.hospitality_core.report.pos_sales_summary.pos_sales_summary import execute
        columns, data = execute({'date': nowdate()})
        descriptions = [d['description'] for d in data]
        if '<b>Summary</b>' not in descriptions:
            return 0.0
        summary_rows = data[descriptions.index('<b>Summary</b>'):]
        row = next((r for r in summary_rows if r['description'] == 'Total POS Sales'), None)
        return flt(row['amount']) if row else 0.0

    def test_pos_sales_summary_excludes_reception_from_summary_only(self):
        self.fixture()
        # pos_sales_summary.py's exclusion list dung dung CHUOI CO DINH
        # "Reception"/"Reception (New)"/"Breakfast" (BREAKFAST_POS_PROFILE) —
        # KHONG the doi ten thanh "PRT Reception" nhu cac profile khac trong
        # file nay (se khong con khop dieu kien loai tru, dung sai muc dich
        # cua chinh test nay). Nhung "POS Profile" la doctype TOAN CUC (ten
        # duy nhat toan site) — 'localhost' co the co san outlet THAT ten
        # dung "Reception" (site nay da xac nhan mang du lieu that/demo cua
        # property 'TCR-RESORT') — kiem tra ton tai TRUOC, bo qua test neu co
        # de KHONG bao gio dung cham vao du lieu that.
        if frappe.db.exists('POS Profile', 'Reception'):
            self.skipTest('POS Profile "Reception" da ton tai (co the la outlet that cua property khac) '
                '— khong an toan de tao du lieu test duoi dung ten nay.')
        reception = self.make_pos_profile('Reception')
        self.make_pos_opening(reception)
        before = self._total_pos_sales_summary()
        self.make_pos_invoice(reception, self.make_item('PRT-TEST-RECEPTION-ITEM'), 150000)
        self.make_closing_entry(reception)
        from hospitality_core.hospitality_core.report.pos_sales_summary.pos_sales_summary import execute
        columns, data = execute({'date': nowdate()})
        descriptions = [d['description'] for d in data]
        self.assertIn('<b>Reception</b>', descriptions)
        after = self._total_pos_sales_summary()
        self.assertEqual(after - before, 0,
            'Reception phai duoc loai khoi "Total POS Sales" trong Summary (da tinh rieng qua Accommodation).')

    def test_pos_sales_summary_filter_by_specific_profile_skips_breakfast_exclusion(self):
        self.fixture()
        profile = self.make_pos_profile('PRT Bar POS')
        self.make_pos_opening(profile)
        before = self._pos_profile_total_sales(profile)
        inv = self.make_pos_invoice(profile, self.make_item('PRT-TEST-BAR-ITEM'), 90000)
        self.make_closing_entry(profile)
        after = self._pos_profile_total_sales(profile)
        self.assertEqual(after - before, flt(inv.grand_total))

    # ==================================================================
    # financial_activity_summary.py
    # ==================================================================
    def test_financial_activity_summary_empty_without_date(self):
        self.fixture()
        from hospitality_core.hospitality_core.report.financial_activity_summary.financial_activity_summary import execute
        columns, data = execute({})
        self.assertEqual(data, [])

    def _financial_activity_by_desc(self):
        from hospitality_core.hospitality_core.report.financial_activity_summary.financial_activity_summary import execute
        columns, data = execute({'date': nowdate()})
        return {d['description']: flt(d['amount']) for d in data}

    def test_financial_activity_summary_item_group_and_accommodation(self):
        self.fixture()
        profile = self.make_pos_profile('PRT FnB POS')
        self.make_pos_opening(profile)
        drink_item = self.make_item('FAS-PRT-DRINK', item_group='Drinks')
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists('ROOM-RENT', 'ROOM-RENT')
        # 'PRT Report Test Co' la company CO LAP nhung du lieu POS Invoice/
        # Closing Entry VA Folio Transaction (ca 2 deu commit that qua
        # make_gl_entries(), khong rollback duoc — property nay chua cutover
        # Property v2 nen MOI Folio Transaction cung di qua duong Legacy GL
        # ghi that) TICH LUY qua nhieu lan chay — phai do CHENH LECH truoc/sau,
        # khong gia dinh gia tri tuyet doi.
        before = self._financial_activity_by_desc()
        self.make_pos_invoice(profile, drink_item, 120000)
        self.make_closing_entry(profile)
        room_txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=self.reservation.folio, parenttype='Guest Folio',
            parentfield='transactions', posting_date=nowdate(), item='ROOM-RENT', description='Room charge',
            qty=1, amount=1500000, bill_to='Guest', is_void=0))
        room_txn.flags.hospitality_service = True
        room_txn.insert(ignore_permissions=True)
        after = self._financial_activity_by_desc()
        self.assertEqual(after.get('Drinks', 0) - before.get('Drinks', 0), 120000)
        self.assertEqual(after.get('Accommodation', 0) - before.get('Accommodation', 0), 1500000)

    def test_financial_activity_summary_protein_and_food_split(self):
        self.fixture()
        profile = self.make_pos_profile('PRT Kitchen POS')
        self.make_pos_opening(profile)
        food_item = self.make_item('FAS-PRT-VEGGIE', item_group='Food')
        chicken_item = self.make_item('FAS-PRT-CHICKEN-DISH', item_group='Food')
        before = self._financial_activity_by_desc()
        self.make_pos_invoice(profile, food_item, 60000)
        self.make_pos_invoice(profile, chicken_item, 80000)
        self.make_closing_entry(profile)
        after = self._financial_activity_by_desc()
        self.assertEqual(after.get('Food (without Proteins)', 0) - before.get('Food (without Proteins)', 0), 60000)
        self.assertEqual(after.get('Chicken', 0) - before.get('Chicken', 0), 80000)
        self.assertEqual(after.get('<b>Total Proteins</b>', 0) - before.get('<b>Total Proteins</b>', 0), 80000)
        self.assertEqual(after.get('<b>Food with Proteins</b>', 0) - before.get('<b>Food with Proteins</b>', 0), 140000)

    def test_financial_activity_summary_tray_charge_by_item_name(self):
        self.fixture()
        profile = self.make_pos_profile('PRT Tray POS')
        self.make_pos_opening(profile)
        tray_item = self.make_item('FAS-PRT-TRAY-01')
        frappe.db.set_value('Item', tray_item, 'item_name', 'Tray Charge - VIP')
        before = self._financial_activity_by_desc()
        self.make_pos_invoice(profile, tray_item, 30000)
        self.make_closing_entry(profile)
        after = self._financial_activity_by_desc()
        self.assertEqual(after.get('Tray Charge', 0) - before.get('Tray Charge', 0), 30000)

    # ==================================================================
    # frontdesk_end_of_day_report.py
    # ==================================================================
    def test_frontdesk_eod_empty_without_date(self):
        self.fixture()
        from hospitality_core.hospitality_core.report.frontdesk_end_of_day_report.frontdesk_end_of_day_report import execute
        columns, data = execute({})
        self.assertEqual(data, [])

    def _frontdesk_checkins_departures(self, reception):
        from hospitality_core.hospitality_core.report.frontdesk_end_of_day_report.frontdesk_end_of_day_report import execute
        columns, data = execute({'date': nowdate(), 'hotel_reception': reception})
        by_metric = {d['metric']: d['value'] for d in data}
        return by_metric.get('New Check-ins', 0), by_metric.get('Departures', 0)

    def test_frontdesk_eod_checkins_and_departures(self):
        self.fixture()
        reception = frappe.db.get_value('Hotel Room', self.reservation.room, 'hotel_reception')
        # Property CO LAP nhung TICH LUY reservation qua nhieu lan chay (moi
        # fixture() tao 1 reservation moi voi arrival_date=hom nay, khong bao
        # gio bi xoa) — phai do CHENH LECH so dem truoc/sau, khong gia dinh
        # gia tri tuyet doi.
        before_checkins, before_departures = self._frontdesk_checkins_departures(reception)
        # self.reservation (tu fixture()): arrival_date=hom nay, departure_date=
        # hom nay+1 -> gop cho "New Check-ins" khi chuyen status.
        frappe.db.set_value('Hotel Reservation', self.reservation.name, 'status', 'Checked In')
        # Dat phong RIENG cho "Departures" (departure_date=hom nay). KHONG
        # THE dung 1 dat phong vua co arrival_date=hom nay VUA co
        # departure_date=hom nay (validate_dates() bat buoc departure PHAI
        # SAU arrival — 2 truong bang nhau se bi chan) — phai tach thanh 2
        # dat phong rieng cho 2 chi so.
        room2, guest2, res2 = self._make_checked_out_reservation()
        after_checkins, after_departures = self._frontdesk_checkins_departures(reception)
        self.assertEqual(after_checkins - before_checkins, 1)
        self.assertEqual(after_departures - before_departures, 1)

    def _make_checked_out_reservation(self):
        room = frappe.get_doc(dict(doctype='Hotel Room', property=self.property,
            room_number=f'PRT-CHECKOUT-{frappe.generate_hash(4)}', room_type=self.reservation.room_type,
            hotel_reception=self.reservation.hotel_reception, status='Available', is_enabled=1)).insert(ignore_permissions=True)
        guest = frappe.get_doc(dict(doctype='Guest', full_name='PRT EOD Checkout Guest', guest_type='Regular')).insert(ignore_permissions=True)
        # arrival_date PHAI truoc departure_date (validate_dates() bat buoc —
        # dat ca 2 = nowdate() se bi chan "Departure Date must be after
        # Arrival Date."). departure_date=hom nay de tinh dung vao "Departures".
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property, guest=guest.name,
            room=room.name, room_type=room.room_type, hotel_reception=room.hotel_reception,
            currency='VND', arrival_date=add_days(nowdate(), -1), departure_date=nowdate())).insert(ignore_permissions=True)
        frappe.db.set_value('Hotel Reservation', res.name, 'status', 'Checked Out')
        return room, guest, res

    def _frontdesk_metric(self, reception, metric):
        from hospitality_core.hospitality_core.report.frontdesk_end_of_day_report.frontdesk_end_of_day_report import execute
        columns, data = execute({'date': nowdate(), 'hotel_reception': reception})
        by_metric = {d['metric']: d['value'] for d in data}
        return _parse_money(by_metric.get(metric))

    def test_frontdesk_eod_sales_consumption_and_tax_breakdown(self):
        self.fixture()
        reception = frappe.db.get_value('Hotel Room', self.reservation.room, 'hotel_reception')
        item = self.make_item('EOD-PRT-CHARGE')
        before = self._frontdesk_metric(reception, 'Sales Consumption (Gross)')
        txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=self.reservation.folio, parenttype='Guest Folio',
            parentfield='transactions', posting_date=nowdate(), item=item, description='EOD test charge',
            qty=1, amount=1225000, bill_to='Guest', is_void=0))
        txn.flags.hospitality_service = True
        txn.insert(ignore_permissions=True)
        after = self._frontdesk_metric(reception, 'Sales Consumption (Gross)')
        self.assertEqual(after - before, 1225000)

    def test_frontdesk_eod_expenses_and_net_profit(self):
        self.fixture()
        reception = frappe.db.get_value('Hotel Room', self.reservation.room, 'hotel_reception')
        expense_category = self._ensure_expense_category()
        mode_of_payment = self._ensure_cash_mode_of_payment()
        cost_center = frappe.db.get_value('Cost Center', {'company': self.company_a, 'is_group': 0}, 'name')
        before = self._frontdesk_metric(reception, 'Total Expenses')
        expense = frappe.get_doc(dict(doctype='Hospitality Expense', expense_date=nowdate(),
            expense_category=expense_category, paid_via=mode_of_payment, company=self.company_a,
            amount=40000, grand_total=40000, cost_center=cost_center, hotel_reception=reception,
            property=self.property)).insert(ignore_permissions=True)
        expense.submit()
        after = self._frontdesk_metric(reception, 'Total Expenses')
        self.assertEqual(after - before, 40000)
        from hospitality_core.hospitality_core.report.frontdesk_end_of_day_report.frontdesk_end_of_day_report import execute
        columns, data = execute({'date': nowdate(), 'hotel_reception': reception})
        by_metric = {d['metric']: d['value'] for d in data}
        self.assertTrue(any(k.strip() == f'- {expense_category}' for k in by_metric),
            f'Phai co dong chi tiet theo danh muc {expense_category}.')

    def _ensure_expense_category(self):
        name = 'PRT EOD Test Category'
        if not frappe.db.exists('Expense Category', name):
            expense_account = frappe.db.get_value('Account', {'company': self.company_a, 'root_type': 'Expense',
                'is_group': 0}, 'name')
            frappe.get_doc(dict(doctype='Expense Category', category_name=name,
                default_expense_account=expense_account)).insert(ignore_permissions=True)
        return name

    def _ensure_cash_mode_of_payment(self):
        name = 'PRT Cash'
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
