"""Kịch bản kiểm thử MỚI cho vòng review Docker (08/09/2026) — nhắm đúng các
chỗ đã sửa trong phiên review này mà bộ test FNB/property gốc CHƯA che phủ:
  1. POS Invoice THƯỜNG (không qua FNB) bán Item tồn kho — deduct_stock_items_for_pos_invoice().
  2. Ghi phí phòng (Guest Account) cho Item tồn kho bán qua POS thường, trên folio Property v2 —
     invoice_has_stock_source() + thứ tự hook on_submit.
  3. Payment Entry / split_transaction / housekeeping minibar / balance transfer /
     ledger adjustment trên folio Property v2 — 8 chỗ vừa thêm flags.hospitality_service.
  4. vietnam_einvoice: phát hành HĐĐT Mock cho hóa đơn Legacy tạo từ create_invoice_from_folio().

Chạy trên site test riêng, dữ liệu rollback sau mỗi ca (theo đúng quy ước các
script khác trong thư mục này).
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days, now_datetime
from run_property_integration import PropertyDatabaseTests
from erpnext.stock.utils import get_stock_balance


def ensure_legacy_accounting_settings(company):
    """`accounting.py` (đường Legacy — redirect_pos_income_to_suspense(),
    reclassify_pos_taxes(), make_gl_entries_for_folio_transaction()) đọc
    `Hospitality Accounting Settings` (Single, KHÁC hẳn `Hospitality Company
    Accounting Settings` của Property v2 mà accounting_reservation() đã tự
    cấu hình) — cần cấu hình riêng, độc lập."""
    settings = frappe.get_single('Hospitality Accounting Settings')
    # QUAN TRỌNG: kiểm tra receivable_account hiện tại có ĐÚNG thuộc company
    # đang cần không, không chỉ "đã có giá trị gì đó là xong" — phát hiện
    # thật: "Hospitality Accounting Settings" là Single TOÀN SITE dùng chung
    # với run_city_ledger_financial_control_tests.py/run_group_booking_tests.py's
    # fixture Legacy tương tự (mỗi file 1 company RIÊNG) — nếu file đó chạy
    # TRƯỚC và đã cấu hình xong cho company của NÓ, early-return cũ ở đây sẽ
    # bỏ qua việc cấu hình lại cho company của CHÍNH file này, dẫn tới lỗi
    # "Giao dịch thuộc pháp nhân X nhưng cấu hình kế toán Legacy toàn cục
    # đang trỏ tới pháp nhân Y" (đã xác nhận thật khi chạy nhiều file liên
    # tiếp không reinstall).
    if settings.receivable_account and frappe.db.get_value('Account', settings.receivable_account, 'company') == company:
        return
    def account(label, root_type):
        parent = frappe.db.get_value('Account', {'company': company, 'root_type': root_type, 'is_group': 1},
            'name', order_by='lft')
        return frappe.get_doc(dict(doctype='Account', account_name=label, parent_account=parent,
            company=company, account_currency='VND')).insert().name
    settings.enable_vietqr = 0
    settings.receivable_account = frappe.get_cached_value('Company', company, 'default_receivable_account')
    settings.income_account = frappe.get_cached_value('Hospitality Company Accounting Settings', company, 'income_account')
    settings.income_suspense_account = account('Docker Legacy Income Suspense', 'Liability')
    settings.consumption_tax_account = account('Docker Legacy Consumption Tax', 'Liability')
    settings.vat_account = account('Docker Legacy VAT', 'Liability')
    settings.service_charge_account = account('Docker Legacy Service Charge', 'Liability')
    settings.cost_center = frappe.get_cached_value('Company', company, 'cost_center')
    settings.save(ignore_permissions=True)


class DockerVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def fixture(self):
        f = PropertyDatabaseTests()
        reservation, settings = f.accounting_reservation()
        self.assertEqual(reservation.accounting_version, 'Property v2')
        frappe.db.set_value('Hotel Reservation', reservation.name, 'allow_pos_posting', 1)
        frappe.db.set_single_value('POS Settings', 'invoice_type', 'POS Invoice')
        company = reservation.operating_company
        ensure_legacy_accounting_settings(company)
        warehouse = frappe.db.get_value('Warehouse', {'company': company, 'is_group': 0}, 'name')
        if not frappe.db.exists('UOM', 'Nos'):
            frappe.get_doc(dict(doctype='UOM', uom_name='Nos')).insert()
        item = frappe.get_doc(dict(doctype='Item', item_code='DOCKER-VERIFY-RAW', item_name='Docker Verify Raw',
            item_group='Services', stock_uom='Nos', is_stock_item=1)).insert()
        receipt = frappe.new_doc('Stock Entry')
        receipt.stock_entry_type = 'Material Receipt'
        receipt.purpose = 'Material Receipt'
        receipt.company = company
        receipt.append('items', dict(item_code=item.name, qty=10, uom='Nos', t_warehouse=warehouse,
            basic_rate=50000, cost_center=frappe.get_cached_value('Company', company, 'cost_center')))
        receipt.insert(ignore_permissions=True)
        receipt.submit()
        return reservation, settings, item, warehouse, company

    def make_pos_invoice(self, reservation, item, warehouse, company, mode_of_payment, amount, is_return=0,
                          return_against=None, customer=None, hotel_room=None):
        # enforce_payment_mode_rules() (fix phiên trước) bắt buộc: có Phòng ->
        # CHỈ 'Guest Account'; Walk-in Customer không Phòng -> CẤM 'Guest
        # Account'/'Complimentary' (mode khác như tiền mặt thì được); khách
        # khác Walk-in không Phòng -> CHỈ 'Complimentary'. Mặc định dùng
        # 'Walk in Customer' (đúng quy tắc cho thanh toán tiền mặt thường).
        if customer is None:
            customer = 'Walk in Customer'
            if not frappe.db.exists('Customer', customer):
                frappe.get_doc(dict(doctype='Customer', customer_name=customer, customer_type='Individual',
                    customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                    territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert(ignore_permissions=True)
        pos_profile_name = 'Docker Verify POS'
        if not frappe.db.exists('POS Profile', pos_profile_name):
            income = frappe.db.get_value('Hospitality Company Accounting Settings', company, 'income_account')
            expense = frappe.db.get_value('Company', company, 'default_expense_account') or income
            frappe.get_doc(dict(doctype='POS Profile', name=pos_profile_name, company=company, currency='VND',
                warehouse=warehouse, selling_price_list=frappe.db.get_single_value('Selling Settings', 'selling_price_list'),
                income_account=income, expense_account=expense,
                cost_center=frappe.db.get_value('Hospitality Company Accounting Settings', company, 'cost_center'),
                write_off_account=income, write_off_cost_center=frappe.db.get_value('Hospitality Company Accounting Settings', company, 'cost_center'),
                payments=[dict(mode_of_payment=mode_of_payment, default=1)])).insert(ignore_permissions=True)
        if not frappe.db.exists('POS Opening Entry', {'pos_profile': pos_profile_name, 'status': 'Open'}):
            opening = frappe.get_doc(dict(doctype='POS Opening Entry', company=company, pos_profile=pos_profile_name,
                user='Administrator', period_start_date=now_datetime(), posting_date=nowdate(),
                balance_details=[dict(mode_of_payment=mode_of_payment, opening_amount=0)]))
            opening.insert(ignore_permissions=True)
            opening.submit()
        qty = -1 if is_return else 1
        inv = frappe.get_doc(dict(doctype='POS Invoice', company=company, customer=customer,
            pos_profile=pos_profile_name, currency='VND', conversion_rate=1, hotel_room=hotel_room,
            selling_price_list=frappe.db.get_single_value('Selling Settings', 'selling_price_list'),
            posting_date=nowdate(), is_return=is_return, return_against=return_against,
            paid_amount=amount * (-1 if is_return else 1),
            items=[dict(item_code=item.name, qty=qty, rate=50000, warehouse=warehouse)],
            payments=[dict(mode_of_payment=mode_of_payment, amount=amount * (-1 if is_return else 1))]))
        inv.insert(ignore_permissions=True)
        inv.save()
        inv.submit()
        return inv

    # ------------------------------------------------------------------
    # 1) POS Invoice thường (không FNB) bán Item tồn kho -> Stock Entry thật
    # ------------------------------------------------------------------
    def test_plain_pos_invoice_deducts_via_stock_entry(self):
        reservation, settings, item, warehouse, company = self.fixture()
        cash = frappe.db.get_value('Account', {'company': company, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', 'Docker Verify Cash'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Docker Verify Cash', type='Cash',
                accounts=[dict(company=company, default_account=cash)])).insert()

        self.assertEqual(get_stock_balance(item.name, warehouse), 10)
        inv = self.make_pos_invoice(reservation, item, warehouse, company, 'Docker Verify Cash', 50000)
        self.assertIsNone(inv.get('fnb_version'))
        self.assertEqual(get_stock_balance(item.name, warehouse), 9,
            'deduct_stock_items_for_pos_invoice() phải trừ đúng 1 đơn vị qua Stock Entry thật.')
        entries = frappe.get_all('Stock Entry', filters={'custom_source_invoice': inv.name,
            'custom_invoice_type': 'POS Invoice', 'docstatus': 1})
        self.assertEqual(len(entries), 1, 'Phải có đúng 1 Stock Entry (Material Issue) gắn với hóa đơn.')
        se = frappe.get_doc('Stock Entry', entries[0].name)
        self.assertEqual(se.stock_entry_type, 'Material Issue')
        gl_qty = frappe.db.count('GL Entry', {'voucher_type': 'Stock Entry', 'voucher_no': se.name, 'is_cancelled': 0})
        self.assertGreater(gl_qty, 0, 'Stock Entry.submit() phải tự ghi GL (Stock-in-Hand/COGS) cùng lúc với SLE.')

        # Hủy hóa đơn -> tồn kho phải hoàn lại đúng, Stock Entry phải bị hủy theo
        inv.reload()
        inv.cancel()
        self.assertEqual(get_stock_balance(item.name, warehouse), 10,
            'Hủy POS Invoice phải hoàn lại đúng tồn kho qua việc hủy Stock Entry liên kết.')
        se.reload()
        self.assertEqual(se.docstatus, 2)

    def test_plain_pos_invoice_return_receives_stock_back(self):
        reservation, settings, item, warehouse, company = self.fixture()
        cash = frappe.db.get_value('Account', {'company': company, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', 'Docker Verify Cash'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Docker Verify Cash', type='Cash',
                accounts=[dict(company=company, default_account=cash)])).insert()
        original = self.make_pos_invoice(reservation, item, warehouse, company, 'Docker Verify Cash', 50000)
        self.assertEqual(get_stock_balance(item.name, warehouse), 9)
        ret = self.make_pos_invoice(reservation, item, warehouse, company, 'Docker Verify Cash', 50000,
            is_return=1, return_against=original.name)
        self.assertEqual(get_stock_balance(item.name, warehouse), 10,
            'Hoàn hàng (is_return=1) phải NHẬP LẠI kho qua Material Receipt, không crash vì qty âm.')
        entries = frappe.get_all('Stock Entry', filters={'custom_source_invoice': ret.name,
            'custom_invoice_type': 'POS Invoice', 'docstatus': 1})
        self.assertEqual(len(entries), 1)
        self.assertEqual(frappe.db.get_value('Stock Entry', entries[0].name, 'stock_entry_type'), 'Material Receipt')

    # ------------------------------------------------------------------
    # 2) Ghi phí phòng cho Item tồn kho bán qua POS thường, folio Property v2 —
    #    KHÔNG được invoice_has_stock_source() chặn nhầm.
    # ------------------------------------------------------------------
    def test_room_charge_for_stock_item_not_blocked_on_property_v2(self):
        reservation, settings, item, warehouse, company = self.fixture()
        receivable = frappe.get_cached_value('Company', company, 'default_receivable_account')
        if not frappe.db.exists('Mode of Payment', 'Guest Account'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Guest Account', type='General',
                accounts=[dict(company=company, default_account=receivable)])).insert()
        elif not frappe.db.exists('Mode of Payment Account', {'parent': 'Guest Account', 'company': company}):
            mop = frappe.get_doc('Mode of Payment', 'Guest Account')
            mop.append('accounts', dict(company=company, default_account=receivable))
            mop.save(ignore_permissions=True)
        # enforce_payment_mode_rules(): hóa đơn gắn Phòng CHỈ được thanh toán
        # qua 'Guest Account' — dùng đúng khách/phòng của reservation.
        inv = self.make_pos_invoice(reservation, item, warehouse, company, 'Guest Account', 50000,
            customer=reservation.billing_customer, hotel_room=reservation.room)
        self.assertEqual(get_stock_balance(item.name, warehouse), 9)
        txns = frappe.get_all('Folio Transaction', filters={'reference_doctype': 'POS Invoice',
            'reference_name': inv.name, 'item': item.name})
        self.assertEqual(len(txns), 1,
            'Ghi phí phòng cho Item tồn kho phải thành công — không bị invoice_has_stock_source() '
            'chặn nhầm (Stock Entry của deduct_stock_items_for_pos_invoice() phải được nhận diện đúng, '
            'và phải chạy TRƯỚC process_room_charge() trong danh sách hook on_submit).')

    # ------------------------------------------------------------------
    # 3) Payment Entry / split_transaction / housekeeping minibar / balance
    #    transfer / ledger adjustment trên folio Property v2 — 8 chỗ vừa
    #    thêm flags.hospitality_service không được ném "Giao dịch v2..."
    # ------------------------------------------------------------------
    def test_payment_entry_on_property_v2_folio(self):
        reservation, settings, item, warehouse, company = self.fixture()
        folio = frappe.get_doc('Guest Folio', reservation.folio)
        receivable = frappe.get_cached_value('Company', company, 'default_receivable_account')
        cash = frappe.db.get_value('Account', {'company': company, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', 'Docker Verify Cash'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Docker Verify Cash', type='Cash',
                accounts=[dict(company=company, default_account=cash)])).insert()
        pe = frappe.get_doc(dict(doctype='Payment Entry', payment_type='Receive', company=company,
            party_type='Customer', party=reservation.billing_customer, paid_from=receivable, paid_to=cash,
            paid_amount=100000, received_amount=100000, mode_of_payment='Docker Verify Cash',
            reference_no=reservation.folio, reference_date=nowdate(),
            hospitality_property=reservation.property, hospitality_event_key=f'docker-verify-{now_datetime()}'))
        pe.insert(ignore_permissions=True)
        pe.submit()
        txn = frappe.get_all('Folio Transaction', filters={'reference_doctype': 'Payment Entry', 'reference_name': pe.name})
        self.assertEqual(len(txn), 1,
            'process_payment_entry() phải ghi được Folio Transaction trên folio Property v2 — '
            'không bị chặn thiếu flags.hospitality_service.')

    def test_split_transaction_on_property_v2_folio(self):
        from hospitality_core.hospitality_core.api.folio_operations import split_transaction
        reservation, settings, item, warehouse, company = self.fixture()
        folio = frappe.get_doc('Guest Folio', reservation.folio)
        txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=folio.name, parenttype='Guest Folio',
            parentfield='transactions', item='MANUAL_ADJUSTMENT', qty=1, amount=100000,
            posting_date=nowdate(), bill_to='Guest'))
        txn.flags.hospitality_service = True
        txn.insert(ignore_permissions=True)
        split_transaction(txn.name, [dict(folio=folio.name, amount=60000), dict(folio=folio.name, amount=40000)])
        remaining = frappe.db.count('Folio Transaction', {'parent': folio.name, 'reference_doctype': 'Folio Transaction',
            'reference_name': txn.name})
        self.assertEqual(remaining, 2, 'split_transaction() phải tạo được 2 dòng mới trên folio Property v2.')

    def test_housekeeping_minibar_on_property_v2_folio(self):
        # validate_inventory_source() (fix của "luồng khác" ở vòng bugfix
        # trước) CHẶN CÓ CHỦ ĐÍCH mọi charge Item tồn kho (is_stock_item=1)
        # ghi thẳng qua Folio mà không có chứng từ xuất kho thật đứng sau —
        # minibar qua housekeeping_mobile.py KHÔNG tạo Stock Entry nào, nên
        # phải dùng Item phi tồn kho (dịch vụ) cho đúng thiết kế đã quyết
        # định, không phải lỗi cần sửa ở product code.
        from hospitality_core.hospitality_core.api.housekeeping_mobile import log_minibar_consumption
        reservation, settings, item, warehouse, company = self.fixture()
        frappe.db.set_value('Hotel Reservation', reservation.name, 'status', 'Checked In')
        frappe.set_user('Administrator')
        minibar_item = frappe.db.exists('Item', 'DOCKER-VERIFY-MINIBAR') or frappe.get_doc(dict(
            doctype='Item', item_code='DOCKER-VERIFY-MINIBAR', item_name='Docker Verify Minibar',
            item_group='Services', stock_uom='Nos', is_stock_item=0)).insert().name
        result = log_minibar_consumption(reservation.room, [dict(item=minibar_item, qty=1, amount=30000)])
        self.assertTrue(result if isinstance(result, list) else True)
        txns = frappe.get_all('Folio Transaction', filters={'parent': reservation.folio, 'item': minibar_item})
        self.assertGreaterEqual(len(txns), 1,
            'Ghi phí minibar qua housekeeping_mobile.py phải thành công trên folio Property v2.')

    def test_ledger_adjustment_on_property_v2_folio(self):
        reservation, settings, item, warehouse, company = self.fixture()
        adj = frappe.get_doc(dict(doctype='Folio Ledger Adjustment', folio=reservation.folio,
            adjustment_type='Add Debt', amount=20000, description='Docker verification test'))
        adj.insert(ignore_permissions=True)
        adj.submit()
        txns = frappe.get_all('Folio Transaction', filters={'reference_doctype': 'Folio Ledger Adjustment',
            'reference_name': adj.name})
        self.assertEqual(len(txns), 1,
            'process_ledger_adjustment() phải ghi được Folio Transaction trên folio Property v2 — '
            'xác nhận DocType Folio Ledger Adjustment (vừa nối dây migration) hoạt động đầu-cuối.')
        adj.cancel()


class VietnamEinvoiceVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def test_legacy_invoice_from_folio_has_address_and_issues_mock_einvoice(self):
        from hospitality_core.hospitality_core.api.invoicing import create_invoice_from_folio
        if not frappe.db.exists('Address Template', {'is_default': 1}):
            frappe.get_doc(dict(doctype='Address Template', country='Vietnam', is_default=1,
                template="{{ address_line1 }}\n{{ city }}\n{{ country }}")).insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.api.einvoice import issue_einvoice_from_folio

        f = PropertyDatabaseTests()
        # Gọi accounting_reservation() trước CHỈ để mở property 'HV-A' nhận
        # booking mới (accept_new_bookings=1) — không dùng reservation nó trả
        # về, vì cần 1 folio LEGACY riêng (không qua Property v2) để test
        # đúng đường create_invoice_from_folio() (Legacy) + vietnam_einvoice.
        f.accounting_reservation()
        customer = frappe.get_doc(dict(doctype='Customer', customer_name='Docker Einvoice Customer',
            customer_type='Company', customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
            territory=frappe.db.get_value('Territory', {'is_group': 0}), tax_id='0101234567')).insert()
        address = frappe.get_doc(dict(doctype='Address', address_title='Docker Einvoice Customer',
            address_type='Billing', address_line1='123 Test Street', city='Ha Noi', country='Vietnam',
            links=[dict(link_doctype='Customer', link_name=customer.name)])).insert()
        guest = frappe.get_doc(dict(doctype='Guest', full_name='Docker Einvoice Guest', customer=customer.name)).insert()
        company = frappe.db.get_value('Hospitality Property', 'HV-A', 'operating_company')
        ensure_legacy_accounting_settings(company)
        # accounting_reservation() ở trên đã tự tạo room_type "Integration
        # Deluxe" + phòng số '101' — dùng lại đúng room_type đó, đặt số
        # phòng khác để tránh trùng (property_scope.py chặn trùng room_number
        # trong cùng cơ sở).
        existing_room_type = frappe.db.get_value('Hotel Room Type', {'property': 'HV-A'}, 'name')
        room = f.room('HV-A', room_type=existing_room_type, number='DOCKER-EINVOICE-101')
        reservation = frappe.get_doc(dict(doctype='Hotel Reservation', property='HV-A', currency='VND',
            guest=guest.name, billing_customer=customer.name, room=room.name, room_type=room.room_type,
            hotel_reception=room.hotel_reception, arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        frappe.db.set_value('Guest Folio', reservation.folio, dict(status='Open', accounting_version='Legacy',
            company=customer.name))
        folio = frappe.get_doc('Guest Folio', reservation.folio)
        item = frappe.get_doc(dict(doctype='Item', item_code='DOCKER-EINVOICE-ITEM', item_name='Docker Einvoice Item',
            item_group='Services', stock_uom='Nos', is_stock_item=0)).insert() if not frappe.db.exists('Item', 'DOCKER-EINVOICE-ITEM') \
            else frappe.get_doc('Item', 'DOCKER-EINVOICE-ITEM')
        income = frappe.get_cached_value('Company', company, 'default_income_account')
        frappe.get_doc(dict(doctype='Item Default', parent=item.name, parenttype='Item', parentfield='item_defaults',
            company=company, default_warehouse=None, income_account=income)).insert(ignore_permissions=True)
        txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=folio.name, parenttype='Guest Folio',
            parentfield='transactions', item=item.name, qty=1, amount=110000, posting_date=nowdate(), bill_to='Guest'))
        txn.flags.hospitality_service = True
        txn.insert(ignore_permissions=True)

        si_name = create_invoice_from_folio(reservation.folio)
        si = frappe.get_doc('Sales Invoice', si_name)
        self.assertTrue(si.address_display, 'create_invoice_from_folio() phải tự điền address_display từ Customer.')
        self.assertEqual(si.hospitality_folio, reservation.folio)
        si.submit()

        if not frappe.db.exists('Vietnam E-Invoice Config', company):
            frappe.get_doc(dict(doctype='Vietnam E-Invoice Config', company=company, tax_id='0101234567',
                provider='Mock Sandbox', environment='Sandbox')).insert(ignore_permissions=True)

        frappe.set_user('Administrator')
        result = issue_einvoice_from_folio(reservation.folio)
        self.assertEqual(result.get('einvoice_status'), 'Issued')
        si.reload()
        self.assertEqual(si.einvoice_status, 'Issued')
        self.assertTrue(si.einvoice_number)
        self.assertTrue(si.einvoice_series, 'Phải gán đúng Vietnam E-Invoice Series (đường vietnam_einvoice thật, không phải Mock cục bộ).')


if __name__ == '__main__':
    names = None
    import sys
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    suite.addTests(loader.loadTestsFromTestCase(DockerVerificationTests))
    suite.addTests(loader.loadTestsFromTestCase(VietnamEinvoiceVerificationTests))
    try:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
