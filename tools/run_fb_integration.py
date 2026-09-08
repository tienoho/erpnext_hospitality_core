"""Chỉ chạy trên container/site test riêng, rollback dữ liệu mỗi ca."""
import unittest
import frappe
from frappe.utils import nowdate, add_days, get_datetime
from run_property_integration import PropertyDatabaseTests
from hospitality_core.api.composite_item_utils import (
    process_composite_items_in_invoice, get_bom_ingredients,
)
from erpnext.stock.utils import get_stock_balance


class FBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def setup_stock(self):
        for purpose in ['Material Receipt', 'Material Issue', 'Material Consumption for Manufacture']:
            if not frappe.db.exists('Stock Entry Type', purpose):
                frappe.get_doc(dict(doctype='Stock Entry Type', name=purpose, purpose=purpose, is_standard=1)).insert()
        fixture = PropertyDatabaseTests()
        self.reservation, self.settings = fixture.accounting_reservation()
        self.company = self.reservation.operating_company
        self.warehouse = frappe.db.get_value('Warehouse', {'company': self.company, 'is_group': 0}, 'name')
        for uom in ['FB kg', 'FB g', 'FB portion']:
            if not frappe.db.exists('UOM', uom):
                frappe.get_doc(dict(doctype='UOM', uom_name=uom)).insert()
        self.raw = frappe.get_doc(dict(doctype='Item', item_code='FB-RAW', item_name='FB raw',
            item_group='Services', stock_uom='FB kg', is_stock_item=1,
            uoms=[dict(uom='FB kg', conversion_factor=1), dict(uom='FB g', conversion_factor=0.001)])).insert()
        self.dish = frappe.get_doc(dict(doctype='Item', item_code='FB-DISH', item_name='FB dish',
            item_group='Services', stock_uom='FB portion', is_stock_item=0, is_composite_item=1)).insert()
        self.receipt = self.stock_entry(10, add_days(nowdate(), -1))
        self.bom = frappe.get_doc(dict(doctype='BOM', item=self.dish.name, quantity=2,
            uom='FB portion', company=self.company, currency='VND', is_active=1, is_default=1,
            items=[dict(item_code=self.raw.name, qty=500, uom='FB g', conversion_factor=0.001,
                        rate=100)])).insert()
        self.bom.submit()

    def stock_entry(self, qty, date):
        from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
        return make_stock_entry(item_code=self.raw.name, qty=qty,
            to_warehouse=self.warehouse, company=self.company, basic_rate=100000,
            posting_date=date, posting_time='00:00:00', set_posting_time=1)

    def invoice(self):
        frappe.db.set_single_value('Selling Settings', 'allow_multiple_items', 1)
        inv = frappe.get_doc(dict(doctype='Sales Invoice', company=self.company,
            customer=self.reservation.billing_customer, currency='VND', conversion_rate=1,
            selling_price_list='Integration Selling', posting_date=nowdate(),
            items=[dict(item_code=self.dish.name, qty=qty, rate=100000, warehouse=self.warehouse,
                income_account=self.settings.income_account, cost_center=self.settings.cost_center)
                for qty in (2, 3)])).insert()
        return inv

    def test_two_lines_conversion_retry_cancel(self):
        self.setup_stock()
        ingredients = get_bom_ingredients(self.bom.name, 2)
        self.assertEqual(ingredients[0]['qty'] * ingredients[0]['conversion_factor'], 0.5)
        inv = self.invoice()
        inv.submit()
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 8.75)
        sources = frappe.get_all('Stock Entry', filters={'custom_source_invoice': inv.name, 'docstatus': 1},
            fields=['name', 'custom_source_invoice_item'])
        self.assertEqual(len(sources), 2)
        self.assertEqual({s.custom_source_invoice_item for s in sources}, {r.name for r in inv.items})
        process_composite_items_in_invoice(inv)
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 8.75)
        inv.cancel()
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 10)

    def test_eod_uses_cutoff_and_deduplicates_warehouse(self):
        from unittest.mock import patch
        self.setup_stock()
        self.stock_entry(5, nowdate())
        report = frappe.get_doc(dict(doctype='Sales Report', company=self.company,
            to_date_time=add_days(nowdate(), -1)+' 23:59:59'))
        original = frappe.db.get_value
        def get_value(dt=None, name=None, field=None, *args, **kwargs):
            if dt is None:
                return original(*args, **kwargs)
            if dt == 'POS Profile' and name in ['FB-POS-A', 'FB-POS-B']:
                return self.warehouse
            return original(dt, name, field, *args, **kwargs)
        with patch.object(frappe.db, 'get_value', side_effect=get_value):
            report.aggregate_stock_balances([frappe._dict(pos_profile=p) for p in ['FB-POS-A','FB-POS-B']])
        self.assertEqual(len(report.eod_stock_balance), 1)
        self.assertEqual(report.eod_stock_balance[0].balance_qty, 10)
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 15)

    def test_sale_uom_consumes_stock_quantity(self):
        self.setup_stock()
        frappe.get_doc(dict(doctype='UOM', uom_name='FB pack')).insert()
        self.dish.reload()
        self.dish.append('uoms', dict(uom='FB pack', conversion_factor=2))
        self.dish.save()
        inv = self.invoice()
        inv.set('items', [inv.items[0]])
        inv.items[0].update(dict(qty=1, uom='FB pack', conversion_factor=2))
        inv.save()
        inv.submit()
        self.assertEqual(inv.items[0].stock_qty, 2)
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 9.5)
        inv.cancel()
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 10)

    def test_cancel_after_composite_flag_removed(self):
        self.setup_stock()
        inv = self.invoice()
        inv.submit()
        self.dish.reload()
        self.dish.is_composite_item = 0
        self.dish.save()
        inv.cancel()
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 10)
        self.assertFalse(frappe.db.exists('Stock Entry', {
            'custom_source_invoice': inv.name, 'docstatus': 1}))

    def legacy_folio(self):
        folio = frappe.get_doc('Guest Folio', self.reservation.folio)
        frappe.db.set_value('Guest Folio', folio.name, 'accounting_version', 'Legacy')
        folio.reload()
        return folio

    def test_existing_folio_service_cannot_become_stock(self):
        self.setup_stock()
        service = frappe.get_doc(dict(doctype='Item', item_code='FB-SERVICE', item_name='Service',
            item_group='Services', stock_uom='FB portion', is_stock_item=0)).insert()
        folio = self.legacy_folio()
        folio.append('transactions', dict(item=service.name, qty=1, amount=100000,
            posting_date=nowdate(), bill_to='Guest'))
        folio.save()
        folio.reload()
        row = next(r for r in folio.transactions if r.item == service.name)
        row.item = self.raw.name
        with self.assertRaisesRegex(frappe.ValidationError, 'POS'):
            folio.save()

    def test_folio_stock_requires_ledger_and_preserves_source(self):
        self.setup_stock()
        inv = self.invoice()
        inv.set('items', [inv.items[0]])
        inv.items[0].update(dict(item_code=self.raw.name, qty=1, uom='FB kg',
            stock_uom='FB kg', conversion_factor=1))
        inv.update_stock = 0
        inv.save()
        inv.submit()
        folio = self.legacy_folio()
        fields = dict(item=self.raw.name, qty=1, amount=100000, posting_date=nowdate(),
            bill_to='Guest', reference_doctype='Sales Invoice', reference_name=inv.name)
        folio.append('transactions', fields)
        with self.assertRaisesRegex(frappe.ValidationError, 'POS'):
            folio.save()
        inv.cancel()
        issued = frappe.copy_doc(inv)
        issued.amended_from = inv.name
        issued.update_stock = 1
        issued.insert()
        issued.submit()
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 9)
        folio.reload()
        fields['reference_name'] = issued.name
        row = folio.append('transactions', fields)
        folio.save()
        folio.reload()
        folio.save()  # Lưu lại dòng không đổi vẫn hợp lệ.
        folio.reload()
        row = next(r for r in folio.transactions if r.reference_name == issued.name)
        row.qty = 2
        with self.assertRaisesRegex(frappe.ValidationError, 'Không sửa'):
            folio.save()

    def test_recipe_cost_and_missing_uom(self):
        from hospitality_core.hospitality_core.doctype.item_recipe.item_recipe import estimate_recipe_cost, get_uom_conversion_factor
        self.setup_stock()
        recipe = frappe.get_doc(dict(doctype='Item Recipe', name=self.dish.name, item=self.dish.name,
            quantity=2, uom='FB portion', is_active=1, bom=self.bom.name,
            ingredients=[dict(ingredient_item=self.raw.name, qty=500, uom='FB g')]))
        # Lưu fixture không chạy sync BOM để giữ BOM đã submit của ca.
        recipe.db_insert()
        for row in recipe.ingredients:
            row.db_insert()
        result = estimate_recipe_cost(recipe.name, self.warehouse, nowdate()+' 23:59:59')
        self.assertEqual(result['batch_cost'], 50000)
        self.assertEqual(result['unit_cost'], 25000)
        self.assertEqual(result['currency'], 'VND')
        with self.assertRaises(frappe.ValidationError):
            get_uom_conversion_factor(self.raw.name, 'FB portion', 'FB kg')

    def test_folio_accepts_delivery_note_stock_source(self):
        self.setup_stock()
        delivery = frappe.get_doc(dict(doctype='Delivery Note', company=self.company,
            customer=self.reservation.billing_customer, currency='VND', conversion_rate=1,
            selling_price_list='Integration Selling', posting_date=nowdate(),
            items=[dict(item_code=self.raw.name, qty=1, rate=100000, warehouse=self.warehouse,
                cost_center=self.settings.cost_center)])).insert()
        delivery.submit()
        inv = self.invoice()
        inv.set('items', [inv.items[0]])
        inv.items[0].update(dict(item_code=self.raw.name, qty=1, uom='FB kg',
            stock_uom='FB kg', conversion_factor=1, delivery_note=delivery.name,
            dn_detail=delivery.items[0].name))
        inv.update_stock = 0
        inv.save()
        inv.submit()
        folio = self.legacy_folio()
        folio.append('transactions', dict(item=self.raw.name, qty=1, amount=100000,
            posting_date=nowdate(), bill_to='Guest', reference_doctype='Sales Invoice', reference_name=inv.name))
        folio.save()
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 9)

    def test_direct_folio_stock_requires_source(self):
        self.setup_stock()
        folio = frappe.get_doc('Guest Folio', self.reservation.folio)
        # Kiểm tra luồng legacy còn cho phép bảng con trực tiếp.
        frappe.db.set_value('Guest Folio', folio.name, 'accounting_version', 'Legacy')
        folio.reload()
        fields = dict(item=self.raw.name, qty=1, amount=100000, posting_date=nowdate(), bill_to='Guest')
        row = frappe.get_doc(dict(doctype='Folio Transaction', parent=folio.name,
            parenttype='Guest Folio', parentfield='transactions', **fields))
        with self.assertRaisesRegex(frappe.ValidationError, 'POS'):
            row.insert(ignore_permissions=True)
        folio.append('transactions', fields)
        with self.assertRaisesRegex(frappe.ValidationError, 'POS'):
            folio.save()


if __name__ == '__main__':
    try:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FBTests))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
