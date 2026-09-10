"""Kịch bản kiểm thử MỚI — Đợt 4 (báo cáo tài chính ưu tiên cao, phần 1):
city_ledger.py, ar_aging_summary.py, monthly_revenue_by_room_type.py,
gross_revenue_report.py, ota_commission_report.py, taxes_and_charges_report.py.
Cả 6 report CHƯA TỪNG chạy thật lần nào, dù đã qua nhiều vòng fix tĩnh về đếm
trùng mirror/company-master/group-master.

Không có report nào trong 6 file này gọi frappe.db.commit() (đã grep trước
khi viết) — an toàn dùng self.fixture()/PropertyDatabaseTests rollback-based.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days, getdate, flt
from run_property_integration import PropertyDatabaseTests


class FinancialReportsTests(unittest.TestCase):
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
    def make_customer(self, name):
        # Guest Folio.company la Link toi Customer (dai ly/cong ty dat ho),
        # KHONG PHAI Link toi Company (phap nhan khach san) — dung quy uoc
        # da xac nhan nhieu lan trong phien nay (Hotel Reservation.company
        # cung vay).
        if not frappe.db.exists('Customer', name):
            frappe.get_doc(dict(doctype='Customer', customer_name=name, customer_type='Company',
                customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert(ignore_permissions=True)
        return name

    def make_master_folio(self, is_company_master=1, open_date=None, outstanding_balance=100000,
                           company=None, excess_payment=0):
        guest = frappe.get_doc(dict(doctype='Guest', full_name=f'Master Folio Guest {frappe.generate_hash(4)}',
            guest_type='Regular')).insert(ignore_permissions=True)
        folio = frappe.get_doc(dict(doctype='Guest Folio', property='HV-A', guest=guest.name,
            company=company or self.make_customer('Test City Ledger Agency'), is_company_master=is_company_master,
            status='Open', open_date=open_date or nowdate())).insert(ignore_permissions=True)
        # QUAN TRONG: khong duoc dat outstanding_balance/total_charges/... khi
        # insert() — folio.py's sync_folio_balance() (hook on_update, chay
        # ngay ca luc insert) tu tinh lai CAC FIELD NAY tu Folio Transaction
        # THAT, ghi de ve 0 vi khong co giao dich nao — phat hien duoc qua
        # debug song khi test bao cao nay lan dau (fixture tuong doi, khong
        # phai loi bao cao). Dung frappe.db.set_value() SAU insert de bo qua
        # hoan toan hook, giu dung gia tri da dinh cho muc dich test bao cao.
        frappe.db.set_value('Guest Folio', folio.name, {
            'outstanding_balance': outstanding_balance,
            'total_charges': outstanding_balance,
            'total_payments': 0,
            'excess_payment': excess_payment,
        }, update_modified=False)
        folio.reload()
        return folio

    def make_group_master_folio(self, open_date=None, outstanding_balance=100000):
        """Master Folio ĐOÀN — is_company_master=0, liên kết qua Hotel Group Booking.master_folio
        (không bao giờ set is_company_master=1, đúng quy ước create_folio() thật)."""
        folio = self.make_master_folio(is_company_master=0, open_date=open_date,
            outstanding_balance=outstanding_balance)
        gb = frappe.get_doc(dict(doctype='Hotel Group Booking', property='HV-A',
            group_name=f'Test Group {frappe.generate_hash(4)}', status='Tentative')).insert(ignore_permissions=True)
        frappe.db.set_value('Hotel Group Booking', gb.name, 'master_folio', folio.name, update_modified=False)
        return folio, gb

    def make_charge(self, folio_name, item, amount, posting_date=None):
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists(item, item)
        txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=folio_name, parenttype='Guest Folio',
            parentfield='transactions', posting_date=posting_date or nowdate(), item=item,
            description=f'Test {item}', qty=1, amount=amount, bill_to='Guest', is_void=0))
        txn.flags.hospitality_service = True
        txn.insert(ignore_permissions=True)
        return txn

    def make_user(self, email, roles):
        if not frappe.db.exists('User', email):
            frappe.get_doc(dict(doctype='User', email=email, first_name=email.split('@')[0],
                send_welcome_email=0, roles=[dict(role=r) for r in roles])).insert(ignore_permissions=True)
        return email

    # ==================================================================
    # city_ledger.py
    # ==================================================================
    def test_city_ledger_includes_company_and_group_master_folios(self):
        self.fixture()
        company_folio = self.make_master_folio(is_company_master=1, outstanding_balance=500000)
        group_folio, gb = self.make_group_master_folio(outstanding_balance=300000)
        from hospitality_core.hospitality_core.report.city_ledger.city_ledger import execute
        columns, data = execute({})
        by_name = {d.get('name'): d for d in data if d.get('name')}
        self.assertIn(company_folio.name, by_name)
        self.assertEqual(by_name[company_folio.name]['folio_type'], 'Công ty')
        self.assertIn(group_folio.name, by_name)
        self.assertEqual(by_name[group_folio.name]['folio_type'], 'Đoàn',
            'Master Folio doan (is_company_master=0, lien ket qua Hotel Group Booking) phai xuat hien voi loai "Doan".')

    def test_city_ledger_excludes_closed_and_zero_balance(self):
        self.fixture()
        closed_folio = self.make_master_folio(is_company_master=1, outstanding_balance=200000)
        frappe.db.set_value('Guest Folio', closed_folio.name, 'status', 'Closed', update_modified=False)
        zero_folio = self.make_master_folio(is_company_master=1, outstanding_balance=0)
        from hospitality_core.hospitality_core.report.city_ledger.city_ledger import execute
        columns, data = execute({})
        names = {d.get('name') for d in data if d.get('name')}
        self.assertNotIn(closed_folio.name, names)
        self.assertNotIn(zero_folio.name, names)

    def test_city_ledger_filters_by_company_and_totals_row(self):
        self.fixture()
        agency_a = self.make_customer('City Ledger Agency A')
        agency_b = self.make_customer('City Ledger Agency B')
        f1 = self.make_master_folio(is_company_master=1, outstanding_balance=100000, company=agency_a)
        f2 = self.make_master_folio(is_company_master=1, outstanding_balance=250000, company=agency_b)
        from hospitality_core.hospitality_core.report.city_ledger.city_ledger import execute
        columns, data = execute({'company': agency_a})
        names = {d.get('name') for d in data if d.get('name')}
        self.assertIn(f1.name, names)
        self.assertNotIn(f2.name, names, 'Filter theo company (Customer) phai loai bo folio cua Customer khac.')
        total_row = data[-1]
        self.assertIn('TOTAL', total_row['company'])
        self.assertEqual(flt(total_row['balance_due']), 100000)

    # ==================================================================
    # ar_aging_summary.py
    # ==================================================================
    def test_ar_aging_buckets_by_open_date(self):
        self.fixture()
        as_of = getdate(nowdate())
        f_10 = self.make_master_folio(open_date=add_days(as_of, -10), outstanding_balance=100000)
        f_45 = self.make_master_folio(open_date=add_days(as_of, -45), outstanding_balance=200000)
        f_75 = self.make_master_folio(open_date=add_days(as_of, -75), outstanding_balance=300000)
        f_100 = self.make_master_folio(open_date=add_days(as_of, -100), outstanding_balance=400000)
        from hospitality_core.hospitality_core.report.ar_aging_summary.ar_aging_summary import execute
        columns, data = execute({'as_of_date': as_of})
        by_name = {d.get('name'): d for d in data if d.get('name')}
        self.assertEqual(flt(by_name[f_10.name]['bucket_0_30']), 100000)
        self.assertEqual(flt(by_name[f_45.name]['bucket_31_60']), 200000)
        self.assertEqual(flt(by_name[f_75.name]['bucket_61_90']), 300000)
        self.assertEqual(flt(by_name[f_100.name]['bucket_90_plus']), 400000)
        for f, key in [(f_10, 'bucket_0_30'), (f_45, 'bucket_31_60'), (f_75, 'bucket_61_90'), (f_100, 'bucket_90_plus')]:
            row = by_name[f.name]
            for other_key in ('bucket_0_30', 'bucket_31_60', 'bucket_61_90', 'bucket_90_plus'):
                if other_key != key:
                    self.assertEqual(flt(row[other_key]), 0, f'{f.name}: chi 1 bac tuoi duoc co so tien, con lai phai la 0.')

    def test_ar_aging_includes_group_master_folio(self):
        self.fixture()
        folio, gb = self.make_group_master_folio(open_date=add_days(nowdate(), -5), outstanding_balance=150000)
        from hospitality_core.hospitality_core.report.ar_aging_summary.ar_aging_summary import execute
        columns, data = execute({})
        by_name = {d.get('name'): d for d in data if d.get('name')}
        self.assertIn(folio.name, by_name)
        self.assertEqual(by_name[folio.name]['folio_type'], 'Đoàn')

    def test_ar_aging_totals_row_sums_all_buckets(self):
        self.fixture()
        self.make_master_folio(open_date=add_days(nowdate(), -5), outstanding_balance=100000)
        self.make_master_folio(open_date=add_days(nowdate(), -50), outstanding_balance=200000)
        from hospitality_core.hospitality_core.report.ar_aging_summary.ar_aging_summary import execute
        columns, data = execute({})
        total_row = data[-1]
        self.assertEqual(flt(total_row['balance_due']), flt(total_row['bucket_0_30']) + flt(total_row['bucket_31_60'])
            + flt(total_row['bucket_61_90']) + flt(total_row['bucket_90_plus']))
        self.assertGreaterEqual(flt(total_row['balance_due']), 300000)

    # ==================================================================
    # monthly_revenue_by_room_type.py — sau fix JOIN res.room=room.name
    # ==================================================================
    def test_monthly_revenue_groups_by_room_type_with_net_amount(self):
        f = self.fixture()
        self.make_charge(self.reservation.folio, 'ROOM-RENT', 1500000)
        self.make_charge(self.reservation.folio, 'DISCOUNT', -150000)
        from hospitality_core.hospitality_core.report.monthly_revenue_by_room_type import monthly_revenue_by_room_type as mod
        rows = mod.get_data({'from_date': nowdate(), 'to_date': nowdate()})
        matching = [r for r in rows if r.room_type == self.reservation.room_type]
        self.assertTrue(matching, 'Sau khi fix JOIN res.room=room.name, phai tim thay it nhat 1 dong dung room_type.')
        row = matching[0]
        self.assertEqual(flt(row.revenue), 1350000, 'Doanh thu phai la NET (1,500,000 - 150,000), khong phai gop.')
        self.assertEqual(row.room_nights, 1)

    def test_monthly_revenue_filters_by_room_type(self):
        f = self.fixture()
        self.make_charge(self.reservation.folio, 'ROOM-RENT', 1000000)
        from hospitality_core.hospitality_core.report.monthly_revenue_by_room_type import monthly_revenue_by_room_type as mod
        rows_match = mod.get_data({'from_date': nowdate(), 'to_date': nowdate(), 'room_type': self.reservation.room_type})
        self.assertTrue(rows_match)
        other_rt = f.room_type('HV-B')
        rows_other = mod.get_data({'from_date': nowdate(), 'to_date': nowdate(), 'room_type': other_rt.name})
        self.assertFalse(rows_other, 'Filter room_type khac phai khong tra ve gi.')

    def test_monthly_revenue_excludes_group_master_mirror(self):
        f = self.fixture()
        original = self.make_charge(self.reservation.folio, 'ROOM-RENT', 900000)
        folio, gb = self.make_group_master_folio(outstanding_balance=900000)
        # mirror_source la Link toi CHINH Folio Transaction goc (khong phai
        # folio) — mo phong ban sao mirror tren Master Folio doan cua CUNG
        # charge (that su reference_doctype se bi ghi de thanh khac 'Folio
        # Transaction' khi xuat hoa don, nhung o day chi can xac nhan dong co
        # mirror_source KHONG duoc dem lai lan 2).
        mirror = frappe.get_doc(dict(doctype='Folio Transaction', parent=folio.name, parenttype='Guest Folio',
            parentfield='transactions', posting_date=nowdate(), item='ROOM-RENT', description='Mirror',
            qty=1, amount=900000, bill_to='Group', is_void=0, mirror_source=original.name))
        # from_folio_mirror: bo qua guard validate_pricing_evidence() (chi he
        # thong tinh gia/mirror moi duoc phep set cac field can cu gia).
        mirror.flags.hospitality_service = True
        mirror.flags.from_folio_mirror = True
        mirror.insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.report.monthly_revenue_by_room_type import monthly_revenue_by_room_type as mod
        rows = mod.get_data({'from_date': nowdate(), 'to_date': nowdate()})
        total_revenue = sum(flt(r.revenue) for r in rows if r.room_type == self.reservation.room_type)
        self.assertEqual(total_revenue, 900000, 'Ban sao mirror tren Master Folio doan khong duoc dem lai lan 2.')

    # ==================================================================
    # gross_revenue_report.py — sau fix JOIN res.room=room.name
    # ==================================================================
    def test_gross_revenue_group_by_room(self):
        f = self.fixture()
        self.make_charge(self.reservation.folio, 'ROOM-RENT', 2000000)
        from hospitality_core.hospitality_core.report.gross_revenue_report import gross_revenue_report as mod
        data = mod.get_data({'from_date': nowdate(), 'to_date': nowdate(), 'group_by': 'Room', 'company': self.company_a})
        matching = [r for r in data if r.get('room_number') == self.reservation.room]
        self.assertTrue(matching, 'Sau khi fix JOIN, phai tim thay dung phong cua dat phong test.')
        row = matching[0]
        self.assertEqual(flt(row['revenue']), 2000000)
        self.assertGreater(flt(row['net_revenue']), 0)
        self.assertEqual(flt(row['gross_profit']), flt(row['net_revenue']) - flt(row['expenses']))

    def test_gross_revenue_group_by_reception(self):
        f = self.fixture()
        self.make_charge(self.reservation.folio, 'ROOM-RENT', 1200000)
        from hospitality_core.hospitality_core.report.gross_revenue_report import gross_revenue_report as mod
        data = mod.get_data({'from_date': nowdate(), 'to_date': nowdate(), 'group_by': 'Reception', 'company': self.company_a})
        reception = frappe.db.get_value('Hotel Room', self.reservation.room, 'hotel_reception')
        matching = [r for r in data if r.get('hotel_reception') == reception]
        self.assertTrue(matching)
        self.assertEqual(flt(matching[0]['revenue']), 1200000)

    def test_gross_revenue_with_direct_room_expense(self):
        f = self.fixture()
        self.make_charge(self.reservation.folio, 'ROOM-RENT', 1000000)
        mr = frappe.get_doc(dict(doctype='Hotel Maintenance Request', room=self.reservation.room,
            issue_type='Other', status='Completed', description='Test maintenance',
            resolution_notes='Fixed')).insert(ignore_permissions=True)
        cost_center = frappe.db.get_value('Cost Center', {'company': self.company_a, 'is_group': 0}, 'name')
        expense = frappe.get_doc(dict(doctype='Hospitality Expense', expense_date=nowdate(),
            expense_category=self._ensure_expense_category(),
            paid_via=self._ensure_mode_of_payment(), company=self.company_a, amount=50000, grand_total=50000,
            cost_center=cost_center, maintenance_request=mr.name, property='HV-A')).insert(ignore_permissions=True)
        expense.submit()
        from hospitality_core.hospitality_core.report.gross_revenue_report import gross_revenue_report as mod
        data = mod.get_data({'from_date': nowdate(), 'to_date': nowdate(), 'group_by': 'Room', 'company': self.company_a})
        matching = [r for r in data if r.get('room_number') == self.reservation.room]
        self.assertTrue(matching)
        self.assertEqual(flt(matching[0]['expenses']), 50000,
            'Chi phi lien ket qua Hotel Maintenance Request phai duoc tinh truc tiep vao dung phong.')

    def test_hospitality_expense_cancel_zeroes_out_gl_balance(self):
        f = self.fixture()
        cost_center = frappe.db.get_value('Cost Center', {'company': self.company_a, 'is_group': 0}, 'name')
        expense = frappe.get_doc(dict(doctype='Hospitality Expense', expense_date=nowdate(),
            expense_category=self._ensure_expense_category(),
            paid_via=self._ensure_mode_of_payment(), company=self.company_a, amount=60000, grand_total=60000,
            cost_center=cost_center, property='HV-A')).insert(ignore_permissions=True)
        expense.submit()
        # TRUOC KHI FIX: expense.cancel() crash TypeError ('cancel' khong ton
        # tai trong chu ky create_expense_gl_entries()), va ngay ca khi bo
        # qua loi do, ban GL cu khong bao gio flip is_cancelled cua 3 dong
        # GOC — chi phi da huy van bi tinh nhu con hieu luc trong moi bao cao
        # loc is_cancelled=0.
        expense.cancel()
        rows = frappe.get_all('GL Entry', filters={'voucher_no': expense.name},
            fields=['debit', 'credit', 'is_cancelled'])
        self.assertTrue(rows)
        self.assertTrue(all(r.is_cancelled for r in rows),
            'Huy Hospitality Expense phai dat is_cancelled=1 cho CA cac dong GOC lan dong dao chieu.')
        net = sum(flt(r.debit) - flt(r.credit) for r in rows if not r.is_cancelled)
        self.assertEqual(net, 0, 'Sau khi huy, tong so du (loc is_cancelled=0) phai ve dung 0.')

    def _ensure_expense_category(self):
        if not frappe.db.exists('Expense Category', 'Test Maintenance Category'):
            expense_account = frappe.db.get_value('Account', {'company': self.company_a, 'root_type': 'Expense',
                'is_group': 0}, 'name')
            frappe.get_doc(dict(doctype='Expense Category', category_name='Test Maintenance Category',
                default_expense_account=expense_account)).insert(ignore_permissions=True)
        return 'Test Maintenance Category'

    def _ensure_mode_of_payment(self):
        # 'Cash' co the da ton tai do file test KHAC tao cho 1 company khac
        # (VD run_city_ledger_financial_control_tests.py's 'FC Test Co') —
        # chi kiem tra ton tai Mode of Payment la khong du, phai kiem tra
        # dung dong 'Mode of Payment Account' cho CHINH self.company_a.
        cash = frappe.db.get_value('Account', {'company': self.company_a, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', 'Cash'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Cash', type='Cash',
                accounts=[dict(company=self.company_a, default_account=cash)])).insert(ignore_permissions=True)
        elif not frappe.db.exists('Mode of Payment Account', {'parent': 'Cash', 'company': self.company_a}):
            mop = frappe.get_doc('Mode of Payment', 'Cash')
            mop.append('accounts', dict(company=self.company_a, default_account=cash))
            mop.save(ignore_permissions=True)
        return 'Cash'

    # ==================================================================
    # ota_commission_report.py
    # ==================================================================
    def make_ota_reservation(self, f, platform='Agoda', number='OTA-1'):
        room = f.room('HV-A', room_type=self.reservation.room_type, number=number)
        guest = frappe.get_doc(dict(doctype='Guest', full_name=f'OTA Guest {frappe.generate_hash(4)}',
            guest_type='Regular')).insert(ignore_permissions=True)
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property='HV-A', guest=guest.name,
            room=room.name, room_type=room.room_type, hotel_reception=room.hotel_reception,
            currency='VND', booking_source='OTA', ota_platform=platform,
            arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        frappe.db.set_value('Guest Folio', res.folio, 'status', 'Open')
        return res

    def _ota_row(self, platform):
        from hospitality_core.hospitality_core.report.ota_commission_report.ota_commission_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((r for r in data if r['ota_platform'] == platform), None)
        return (flt(row['revenue']), flt(row['commission_percent'])) if row else (0.0, 0.0)

    def test_ota_commission_calculates_from_configured_rate(self):
        f = self.fixture()
        # KHONG the gia dinh site sach: 'localhost' da co san du lieu OTA that
        # (VD property 'TCR-RESORT', ~40 dat phong OTA) — so sanh CHENH LECH
        # truoc/sau khi them fixture cua chinh test nay, thay vi kiem tra gia
        # tri tuyet doi cua bao cao (bao cao khong co tham so loc company de
        # co lap ket qua, dung y do — property scoping tra ve day du cho
        # Administrator).
        before_revenue, _ = self._ota_row('Agoda')
        res = self.make_ota_reservation(f, platform='Agoda')
        self.make_charge(res.folio, 'ROOM-RENT', 1000000)
        settings = frappe.get_single('Hospitality Channel Manager Settings')
        settings.set('ota_commission_rates', [dict(ota_platform='Agoda', commission_percent=15)])
        settings.save(ignore_permissions=True)
        after_revenue, after_commission_percent = self._ota_row('Agoda')
        self.assertEqual(after_revenue - before_revenue, 1000000)
        self.assertEqual(after_commission_percent, 15)
        self.assertEqual((after_revenue - before_revenue) * after_commission_percent / 100.0, 150000)

    def test_ota_commission_defaults_to_zero_when_unconfigured(self):
        f = self.fixture()
        res = self.make_ota_reservation(f, platform='Traveloka', number='OTA-2')
        self.make_charge(res.folio, 'ROOM-RENT', 500000)
        from hospitality_core.hospitality_core.report.ota_commission_report.ota_commission_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        row = next((r for r in data if r['ota_platform'] == 'Traveloka'), None)
        self.assertIsNotNone(row)
        self.assertEqual(flt(row['commission_percent']), 0,
            'Kenh chua cau hinh % hoa hong phai mac dinh 0%, khong tu suy doan.')
        self.assertEqual(flt(row['commission_amount']), 0)

    def test_ota_commission_excludes_non_ota_bookings(self):
        f = self.fixture()
        # So sanh CHENH LECH tong doanh thu truoc/sau (khong gia dinh site
        # sach — xem ghi chu o test_ota_commission_calculates_from_configured_rate).
        from hospitality_core.hospitality_core.report.ota_commission_report.ota_commission_report import execute
        before_total = sum(flt(r['revenue']) for r in execute({'from_date': nowdate(), 'to_date': nowdate()})[1])
        self.make_charge(self.reservation.folio, 'ROOM-RENT', 800000)
        after_total = sum(flt(r['revenue']) for r in execute({'from_date': nowdate(), 'to_date': nowdate()})[1])
        self.assertEqual(after_total - before_total, 0,
            'Dat phong khong phai OTA (booking_source mac dinh Direct) khong duoc tinh vao bao cao nay.')

    # ==================================================================
    # taxes_and_charges_report.py
    # ==================================================================
    def test_taxes_and_charges_handles_none_filters_without_crash(self):
        self.fixture()
        from hospitality_core.hospitality_core.report.taxes_and_charges_report.taxes_and_charges_report import execute
        columns, data = execute(None)
        self.assertIsInstance(data, list)

    def _make_tax_gl_entry(self, account, amount, voucher_no, posting_date=None):
        """Chèn thẳng 1 dòng GL Entry vào tài khoản thuế — kiểm tra ĐÚNG logic
        đọc/hiển thị của report, không phụ thuộc accounting_version của folio
        fixture (make_gl_entries_for_folio_transaction() sẽ no-op ngay cho
        folio Property v2 như self.reservation.folio, vì đây là hàm CHỈ
        dành cho đường Legacy — không phù hợp để test report bằng cách này).
        voucher_no PHẢI là 1 Guest Folio CÓ THẬT — GL Entry's voucher_no là
        Dynamic Link (theo voucher_type), Frappe validate_links() sẽ chặn
        ngay nếu dùng chuỗi tùy ý không khớp bản ghi thật nào."""
        company = frappe.db.get_value('Account', account, 'company')
        cost_center = frappe.db.get_value('Cost Center', {'company': company, 'is_group': 0}, 'name')
        return frappe.get_doc(dict(doctype='GL Entry', posting_date=posting_date or nowdate(), account=account,
            company=company, cost_center=cost_center, voucher_type='Guest Folio', voucher_no=voucher_no,
            debit=0, credit=amount, debit_in_account_currency=0, credit_in_account_currency=amount,
            hospitality_property='HV-A', remarks='Test tax report row')).insert(ignore_permissions=True)

    def test_taxes_and_charges_lists_gl_entries_for_configured_accounts(self):
        self.fixture()
        settings = frappe.get_single('Hospitality Accounting Settings')
        if not settings.consumption_tax_account:
            self.skipTest('Hospitality Accounting Settings chua cau hinh tai khoan thue — bo qua ca nay.')
        self._make_tax_gl_entry(settings.consumption_tax_account, 50000, voucher_no=self.reservation.folio)
        from hospitality_core.hospitality_core.report.taxes_and_charges_report.taxes_and_charges_report import execute
        columns, data = execute({'from_date': nowdate(), 'to_date': nowdate()})
        matching = [r for r in data if r['voucher_no'] == self.reservation.folio]
        self.assertTrue(matching, 'GL Entry ghi vao tai khoan Consumption Tax phai xuat hien trong bao cao thue.')
        self.assertEqual(flt(matching[0]['ct_amount']), 50000)

    def test_taxes_and_charges_filters_by_date_range(self):
        self.fixture()
        settings = frappe.get_single('Hospitality Accounting Settings')
        if not settings.consumption_tax_account:
            self.skipTest('Hospitality Accounting Settings chua cau hinh tai khoan thue — bo qua ca nay.')
        self._make_tax_gl_entry(settings.consumption_tax_account, 30000, voucher_no=self.reservation.folio)
        from hospitality_core.hospitality_core.report.taxes_and_charges_report.taxes_and_charges_report import execute
        past_date = add_days(nowdate(), -365)
        columns, data = execute({'from_date': past_date, 'to_date': past_date})
        matching = [r for r in data if r['voucher_no'] == self.reservation.folio]
        self.assertFalse(matching, 'Loc theo khoang ngay khong khop phai khong tra ve giao dich cua hom nay.')


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(FinancialReportsTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
