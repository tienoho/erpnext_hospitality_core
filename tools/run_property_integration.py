"""Kiểm thử database trên site chung của bench (đã gộp theo yêu cầu người
dùng — trước đây dùng site test riêng 'hospitality-v2.test', nay hợp nhất về
'localhost' để tránh phân tán dữ liệu/site test)."""
import json
import sys
import unittest
from pathlib import Path

import frappe

SITE='localhost'
SITES=Path('/home/frappe/test-bench/sites')
if not SITES.exists() or not Path('/source/hospitality_core').exists():
    raise SystemExit('Cần container hospitality-v2-test và site test riêng.')
frappe.init(site=SITE,sites_path=str(SITES))
frappe.connect()
frappe.set_user('Administrator')
frappe.flags.in_test=True
frappe.conf.hospitality_v2_release_verified=1


class PropertyDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Dữ liệu chuẩn của setup wizard ERPNext, cần trước Company.on_update.
        if not frappe.db.exists('Warehouse Type', 'Transit'):
            frappe.get_doc(dict(doctype='Warehouse Type', name='Transit')).insert()
        for name,abbr in [('_Hospitality V2 A','HVA'),('_Hospitality V2 B','HVB')]:
            if not frappe.db.exists('Company',name):
                frappe.get_doc(dict(doctype='Company',company_name=name,abbr=abbr,country='Vietnam',
                    default_currency='VND',create_chart_of_accounts_based_on='Standard Template',
                    chart_of_accounts='Standard')).insert(ignore_permissions=True)
        for code,company in [('HV-A','_Hospitality V2 A'),('HV-B','_Hospitality V2 B')]:
            if not frappe.db.exists('Hospitality Property',code):
                frappe.get_doc(dict(doctype='Hospitality Property',property_code=code,property_name=code,
                    operating_company=company,currency='VND',timezone='Asia/Ho_Chi_Minh')).insert()
        frappe.db.commit()

    def setUp(self):
        frappe.set_user('Administrator')

    def tearDown(self):
        frappe.set_user('Administrator')
        # Savepoint không chạy rollback watchers của cache/default ERPNext.
        frappe.db.rollback()

    def room_type(self,prop):
        return frappe.get_doc(dict(doctype='Hotel Room Type',room_type_name='Integration Deluxe',
            property=prop,max_adults=2,max_children=1,default_rate=1500000,currency_rates=[
                dict(currency='VND',default_rate=1500000),dict(currency='USD',default_rate=100)])).insert()

    def room(self, prop, room_type=None, number='101'):
        reception = prop + '-Reception'
        if not frappe.db.exists('Hotel Reception', reception):
            frappe.get_doc(dict(doctype='Hotel Reception', reception_name=reception, property=prop)).insert()
        return frappe.get_doc(dict(doctype='Hotel Room', property=prop, room_number=number,
            room_type=room_type or self.room_type(prop).name, hotel_reception=reception,
            status='Available', is_enabled=1)).insert()

    def test_two_properties_same_labels(self):
        a=self.room_type('HV-A'); b=self.room_type('HV-B')
        rooms=[]
        for prop,rt in [('HV-A',a.name),('HV-B',b.name)]:
            rooms.append(self.room(prop, rt))
        self.assertNotEqual(rooms[0].name,rooms[1].name)
        self.assertNotEqual(a.name,b.name)
        with self.assertRaises(frappe.ValidationError):
            self.room_type('HV-A')

    def test_bulk_availability_uses_stable_room_id(self):
        from hospitality_core.hospitality_core.api.reservation import check_bulk_availability
        room = self.room('HV-A')
        self.assertNotEqual(room.name, room.room_number)
        self.assertTrue(check_bulk_availability([room.name], '2027-01-01', '2027-01-02'))

    def test_picker_filters_property_with_and_without_dates(self):
        from hospitality_core.hospitality_core.api.reservation import get_available_rooms_for_picker
        a = self.room('HV-A'); b = self.room('HV-B')
        for dates in [{}, dict(arrival_date='2027-01-01', departure_date='2027-01-02')]:
            rows = get_available_rooms_for_picker('Hotel Room', '', 'name', 0, 100,
                dict(property='HV-A', **dates))
            names = [row[0] for row in rows]
            self.assertIn(a.name, names)
            self.assertNotIn(b.name, names)

    def test_room_cannot_link_type_from_other_property(self):
        rt=self.room_type('HV-B')
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(dict(doctype='Hotel Room',property='HV-A',room_number='102',room_type=rt.name)).insert()

    def test_currency_prices_and_missing_pair(self):
        from hospitality_core.hospitality_core.api.rate_plan import snapshot_for
        rt=self.room_type('HV-A')
        self.assertEqual(snapshot_for(None,rt.name,'USD','HV-A')['default_rate'],100)
        self.assertEqual(snapshot_for(None,rt.name,'VND','HV-A')['default_rate'],1500000)
        with self.assertRaises(frappe.ValidationError):
            snapshot_for(None,rt.name,'EUR','HV-A')

    def test_plan_cannot_cross_property(self):
        a=self.room_type('HV-A'); b=self.room_type('HV-B')
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(dict(doctype='Room Rate Plan',plan_name='Cross Scope',property='HV-A',
                room_type=b.name,currency='VND',active=1)).insert()

    def test_query_conditions_do_not_grant_other_properties(self):
        from hospitality_core.hospitality_core.api.property_scope import allowed_properties,conditions,require_property
        user = self.property_user()
        frappe.set_user(user)
        self.assertEqual(allowed_properties(),['HV-A'])
        self.assertIn('HV-A',conditions(doctype='Hotel Reservation'))
        self.assertNotIn('HV-B',conditions(doctype='Hotel Reservation'))
        with self.assertRaises(frappe.PermissionError):
            require_property('HV-B')

    def property_user(self):
        user='hospitality-v2-test@example.test'
        if not frappe.db.exists('User',user):
            frappe.get_doc(dict(doctype='User',email=user,first_name='Property Test',send_welcome_email=0,
                roles=[dict(role='Hospitality User')])).insert(ignore_permissions=True)
        frappe.get_doc(dict(doctype='Hospitality Property Access',property='HV-A',user=user,enabled=1)).insert()
        frappe.db.set_value('Hospitality Property','HV-A','enabled',1)
        return user

    def test_folio_document_permission_checks_property(self):
        user = self.property_user()
        frappe.set_user(user)
        allowed = frappe.get_doc(dict(doctype='Guest Folio', name='TEST-FOLIO-A', property='HV-A'))
        forbidden = frappe.get_doc(dict(doctype='Guest Folio', name='TEST-FOLIO-B', property='HV-B'))
        allowed.check_permission('read')
        with self.assertRaises(frappe.PermissionError):
            forbidden.check_permission('read')

    def accounting_reservation(self, currency='VND', los=False):
        from frappe.utils import nowdate, add_days, getdate
        price_list = frappe.get_doc(dict(doctype='Price List', price_list_name='Integration Selling',
            selling=1, enabled=1, currency=currency)).insert()
        frappe.db.set_single_value('Selling Settings', 'selling_price_list', price_list.name)
        # Sau khi gộp bộ test sang site 'localhost' (đã qua Setup Wizard/cấu
        # hình thật, khác site test rỗng 'hospitality-v2.test' cũ), phát hiện
        # frappe.defaults.get_defaults()['selling_price_list'] tra ra
        # 'Standard Selling' — 1 default TOAN SITE luu trong bang
        # tabDefaultValue, HOAN TOAN doc lap voi field 'Selling Settings' Single
        # va KHONG bi anh huong boi clear-cache/FLUSHALL Redis (khac han loi
        # Redis cache staleness da biet truoc). frappe.new_doc()'s co che dien
        # gia tri mac dinh (get_new_doc() -> get_user_default_value()) uu tien
        # frappe.defaults truoc khi doc "Selling Settings" — set_single_value()
        # o tren khong du. Phai ghi de rieng qua set_default() de dam bao Sales
        # Invoice moi tao lay dung price list cua test.
        frappe.db.set_default('selling_price_list', price_list.name)
        preview = frappe.new_doc('Sales Invoice')
        self.assertEqual(preview.selling_price_list, price_list.name,
            dict(stored=frappe.db.get_single_value('Selling Settings', 'selling_price_list', cache=False),
                 cached=frappe.db.value_cache.get('Selling Settings')))
        if currency == 'USD':
            frappe.db.set_single_value('Accounts Settings',
                'allow_multi_currency_invoices_against_single_party_account', 1)
            frappe.get_doc(dict(doctype='Currency Exchange', date=nowdate(), from_currency='USD',
                to_currency='VND', exchange_rate=25000, for_selling=1, for_buying=1)).insert()
        company = frappe.get_doc('Company', '_Hospitality V2 A')
        def account(label, root_type):
            parent = frappe.db.get_value('Account', {'company': company.name, 'root_type': root_type,
                'is_group': 1}, 'name', order_by='lft')
            return frappe.get_doc(dict(doctype='Account', account_name=label, parent_account=parent,
                company=company.name, account_currency='VND')).insert().name
        unbilled = account('Integration Unbilled', 'Asset')
        tax_account = account('Integration Tax', 'Liability')
        income = account('Integration Room Revenue', 'Income')
        expense = account('Integration FX Expense', 'Expense')
        tax = frappe.get_doc(dict(doctype='Sales Taxes and Charges Template', title='Integration 10 percent',
            company=company.name, taxes=[dict(charge_type='On Net Total', account_head=tax_account,
                description='Integration Tax', rate=10)])).insert()
        settings = frappe.get_doc(dict(doctype='Hospitality Company Accounting Settings',
            operating_company=company.name, receivable_account=company.default_receivable_account,
            unbilled_account=unbilled, income_account=income, exchange_difference_account=expense,
            round_off_account=expense, cost_center=company.cost_center, tax_template=tax.name, enabled=1)).insert()
        frappe.get_doc(dict(doctype='Hospitality Property Settings', property='HV-A')).insert()
        prop = frappe.get_doc('Hospitality Property', 'HV-A')
        prop.flags.hospitality_service = True
        prop.update(dict(enabled=1, migration_verified=1, accept_new_bookings=1, cutover_date=nowdate()))
        prop.save()
        year = str(getdate(nowdate()).year)
        if not frappe.db.exists('Fiscal Year', year):
            frappe.get_doc(dict(doctype='Fiscal Year', year=year, year_start_date=year+'-01-01',
                year_end_date=year+'-12-31')).insert()
        else:
            # Site 'localhost' (sau khi gop bo test ve day) da co san Fiscal
            # Year nam nay nhung bi GIOI HAN theo 1 danh sach company THAT cua
            # Tap doan Tuan Chau (bang con 'companies') — khac han site test
            # rong 'hospitality-v2.test' truoc day (Fiscal Year luon khong bi
            # gioi han). Neu bang con nay KHONG RONG (dang o che do gioi han),
            # phai them company cua fixture nay vao thi GL Entry moi khong bi
            # tu choi "not in any active Fiscal Year". Khong dong vao neu bang
            # con dang RONG (nghia la khong gioi han gi ca — them 1 dong vao
            # se VO TINH bat dau gioi han, thay doi hanh vi cho MOI company
            # khac dang dua vao "rong = khong gioi han").
            fy = frappe.get_doc('Fiscal Year', year)
            existing_companies = {d.company for d in (fy.get('companies') or [])}
            if existing_companies and company.name not in existing_companies:
                fy.append('companies', dict(company=company.name))
                fy.save(ignore_permissions=True)
        if not frappe.db.exists('Item Group', 'Services'):
            root = frappe.db.get_value('Item Group', {'is_group': 1}, 'name', order_by='lft')
            frappe.get_doc(dict(doctype='Item Group', item_group_name='Services', parent_item_group=root)).insert()
        # is_group=0 (khong phai 1) — Customer.validate_customer_group() cua
        # ERPNext CAM chon 1 Customer Group/Territory kieu NHOM (group) lam
        # gia tri truc tiep, chi chap nhan nhom LA (leaf). Tren site test
        # rong 'hospitality-v2.test' truoc day, get_value(is_group=1) thuong
        # tra ve None (khong co fixture Customer Group/Territory nao ca) nen
        # loi nay khong lo ra; sau khi gop sang 'localhost' (co du fixture
        # chuan ERPNext nhu "All Customer Groups"/"All Territories" la group
        # goc) thi loi nay moi that su kich hoat — sua dung ca 2 site.
        customer = frappe.get_doc(dict(doctype='Customer', customer_name='Integration Guest',
            customer_type='Individual', customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
            territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert()
        guest = frappe.get_doc(dict(doctype='Guest', full_name='Integration Guest', customer=customer.name)).insert()
        room = self.room('HV-A')
        plan = None
        if los:
            plan = frappe.get_doc(dict(doctype='Room Rate Plan', plan_name='Integration LOS', property='HV-A',
                currency=currency, room_type=room.room_type, active=1,
                seasons=[dict(season_name='Integration', valid_from=nowdate(), valid_to=add_days(nowdate(), 30),
                    weekday_rate=1500000, weekend_rate=1500000)],
                los_discounts=[dict(min_nights=3, discount_percent=10)])).insert().name
        reservation = frappe.get_doc(dict(doctype='Hotel Reservation', property='HV-A', currency=currency, rate_plan=plan,
            guest=guest.name, billing_customer=customer.name, room=room.name, room_type=room.room_type,
            hotel_reception=room.hotel_reception, arrival_date=nowdate(), departure_date=add_days(nowdate(), 2))).insert()
        frappe.db.set_value('Guest Folio', reservation.folio, 'status', 'Open')
        return reservation, settings

    def test_daily_revenue_invoice_preserves_single_income(self):
        from hospitality_core.hospitality_core.api.rate_plan import post_daily_charge
        from hospitality_core.hospitality_core.api.property_accounting import create_invoice
        reservation, settings = self.accounting_reservation()
        self.assertEqual(reservation.accounting_version, 'Property v2')
        self.assertTrue(post_daily_charge(reservation, reservation.arrival_date))
        self.assertFalse(post_daily_charge(reservation, reservation.arrival_date))
        posting = frappe.get_doc('Hospitality Charge Posting', {'reservation': reservation.name})
        self.assertEqual(posting.net_amount, 1500000)
        self.assertEqual(posting.gross_amount, 1650000)
        self.assertEqual(frappe.db.get_value('Journal Entry', posting.journal_entry, 'docstatus'), 1)
        folio = frappe.get_doc('Guest Folio', reservation.folio)
        self.assertEqual(folio.outstanding_balance, 1650000)
        invoice = frappe.get_doc('Sales Invoice', create_invoice(folio.name))
        self.assertEqual(invoice.docstatus, 0)
        invoice.submit()
        self.assertEqual(invoice.grand_total, 1650000)
        entries = frappe.db.sql('''SELECT account, SUM(debit-credit) balance FROM `tabGL Entry`
            WHERE company=%s AND is_cancelled=0 GROUP BY account''', reservation.operating_company, as_dict=True)
        balances = {r.account: r.balance for r in entries}
        self.assertEqual(balances[settings.income_account], -1500000)
        self.assertEqual(balances[settings.unbilled_account], 0)
        self.assertEqual(balances[settings.receivable_account], 1650000)

    def test_los_no_change_does_not_remove_tax(self):
        from hospitality_core.hospitality_core.api.rate_plan import post_daily_charge, reconcile_los
        reservation, settings = self.accounting_reservation()
        post_daily_charge(reservation, reservation.arrival_date)
        reconcile_los(reservation)
        self.assertEqual(frappe.db.get_value('Guest Folio', reservation.folio, 'outstanding_balance'), 1650000)
        self.assertEqual(frappe.db.count('Folio Transaction', {'parent': reservation.folio}), 1)

    def test_usd_invoice_payment_in_vnd(self):
        from hospitality_core.hospitality_core.api.rate_plan import post_daily_charge
        from hospitality_core.hospitality_core.api.property_accounting import create_invoice, receive_payment
        reservation, settings = self.accounting_reservation(currency='USD')
        post_daily_charge(reservation, reservation.arrival_date)
        invoice = frappe.get_doc('Sales Invoice', create_invoice(reservation.folio))
        invoice.submit()
        self.assertEqual(invoice.grand_total, 110)
        self.assertEqual(invoice.base_grand_total, 2750000)
        bank = frappe.db.get_value('Account', {'company': reservation.operating_company,
            'account_type': 'Cash', 'is_group': 0}, 'name')
        payment = receive_payment(reservation.folio, bank, 1375000, 'integration-half', invoice=invoice.name)
        self.assertEqual(frappe.db.get_value('Payment Entry', payment, 'docstatus'), 1)
        self.assertEqual(frappe.db.get_value('Sales Invoice', invoice.name, 'outstanding_amount'), 1375000)
        self.assertEqual(frappe.db.get_value('Guest Folio', reservation.folio, 'outstanding_balance'), 55)
        self.assertEqual(receive_payment(reservation.folio, bank, 1375000, 'integration-half', invoice=invoice.name), payment)

    def test_los_adjustment_posts_revenue_and_is_idempotent(self):
        from frappe.utils import add_days
        from hospitality_core.hospitality_core.api.rate_plan import post_daily_charge, reconcile_los
        from hospitality_core.hospitality_core.api.property_accounting import create_invoice
        reservation, settings = self.accounting_reservation(los=True)
        post_daily_charge(reservation, reservation.arrival_date)
        reservation.departure_date = add_days(reservation.arrival_date, 3)
        reconcile_los(reservation)
        reconcile_los(reservation)
        self.assertEqual(frappe.db.get_value('Guest Folio', reservation.folio, 'outstanding_balance'), 1485000)
        self.assertEqual(frappe.db.count('Hospitality Charge Posting', {'reservation': reservation.name}), 2)
        invoice = frappe.get_doc('Sales Invoice', create_invoice(reservation.folio))
        invoice.submit()
        self.assertEqual(invoice.grand_total, 1485000)
        income = frappe.db.sql('''SELECT SUM(credit-debit) FROM `tabGL Entry`
            WHERE account=%s AND is_cancelled=0''', settings.income_account)[0][0]
        self.assertEqual(income, 1350000)

    def test_invoice_rejects_financial_source_tampering(self):
        from hospitality_core.hospitality_core.api.rate_plan import post_daily_charge
        from hospitality_core.hospitality_core.api.property_accounting import create_invoice
        reservation, _ = self.accounting_reservation()
        post_daily_charge(reservation, reservation.arrival_date)
        name = create_invoice(reservation.folio)
        for change in ['folio', 'tax', 'discount']:
            with self.subTest(change=change):
                frappe.db.savepoint('invoice_tamper')
                try:
                    invoice = frappe.get_doc('Sales Invoice', name)
                    if change == 'folio':
                        invoice.hospitality_folio = None
                    elif change == 'tax':
                        invoice.taxes[0].rate = 20
                    else:
                        invoice.additional_discount_percentage = 10
                    with self.assertRaises(frappe.ValidationError):
                        invoice.save()
                finally:
                    frappe.db.rollback(save_point='invoice_tamper')

    def test_missing_stored_exchange_does_not_use_external_fallback(self):
        from unittest.mock import patch
        from hospitality_core.hospitality_core.api.property_accounting import exchange
        with patch('erpnext.setup.utils.get_exchange_rate', return_value=25000):
            with self.assertRaises(frappe.ValidationError):
                exchange('USD', 'VND', '2000-01-01')


if __name__ == "__main__":
    try:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PropertyDatabaseTests))
        print(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
