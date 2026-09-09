"""Database regressions for the September F&B review; test site only, rollback per case."""
import sys
import unittest
from unittest.mock import patch
import frappe
from frappe.utils import nowdate, now_datetime, add_days
from run_fnb_procurement_costing_tests import ProcurementCostingTests
from erpnext.stock.utils import get_stock_balance


class ReviewTests(ProcurementCostingTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.reload_doc('hospitality_core', 'doctype', 'fnb_waste_record')
        frappe.db.commit()

    def test_stock_read_permissions_and_reports(self):
        self.setup_control()
        user = 'fnb.review.scope@example.test'
        frappe.get_doc(dict(doctype='User', email=user, first_name='Review Scope', send_welcome_email=0,
            roles=[dict(role='Stock User'), dict(role='FNB Operator')])).insert()
        frappe.get_doc(dict(doctype='Hospitality Property Access', user=user, property='HV-B', enabled=1)).insert()
        sle = frappe.db.get_value('Stock Ledger Entry', {'warehouse': self.warehouse}, 'name')
        bin_name = frappe.db.get_value('Bin', {'warehouse': self.warehouse, 'item_code': self.raw.name}, 'name')
        frappe.set_user(user)
        for dt, name in [('Stock Ledger Entry', sle), ('Bin', bin_name)]:
            self.assertFalse(frappe.has_permission(dt, 'read', doc=name))
            self.assertNotIn(name, frappe.get_list(dt, pluck='name'))
        from hospitality_core.hospitality_core.api.fnb.stock_reports import validate_scope
        for report in ['Stock Balance', 'Stock Projected Qty', 'Stock Ageing', 'Stock Analytics']:
            with self.assertRaises(frappe.PermissionError):
                validate_scope(report, {})
        frappe.set_user('Administrator')
        frappe.get_doc(dict(doctype='Hospitality Property Access', user=user, property=self.out.property, enabled=1)).insert()
        frappe.set_user(user)
        validate_scope('Stock Balance', {'warehouse': self.warehouse, 'company': self.company})

    def test_delivered_pos_line_does_not_issue(self):
        self.setup_control()
        from hospitality_core.hospitality_core.api.fnb.pos import process_invoice
        doc = frappe.get_doc(dict(doctype='POS Invoice', name='REVIEW-DELIVERED', company=self.company,
            hospitality_property=self.out.property, fnb_outlet=self.out.name, fnb_version='FNB v1',
            posting_date=nowdate(), docstatus=1, items=[dict(item_code=self.raw.name, stock_qty=1,
                delivery_note='DN-SOURCE', dn_detail='DN-LINE', fnb_snapshot='{"mode":"Stock"}')]))
        # Isolate the consumption branch; ERPNext validates Delivery Note links itself.
        with patch('hospitality_core.hospitality_core.api.fnb.pos.post_stock') as post:
            self.assertTrue(process_invoice(doc))
            post.assert_not_called()
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 10)

    def test_repost_worker_checks_closed_period(self):
        self.setup_control()
        from hospitality_core.hospitality_core.api.fnb.reposting import validate_repost
        frappe.db.set_value('FNB Warehouse Control', self.warehouse, 'closed_through', now_datetime())
        doc = frappe.get_doc(dict(doctype='Repost Item Valuation', company=self.company,
            based_on='Item and Warehouse', item_code=self.raw.name, warehouse=self.warehouse,
            posting_date=add_days(nowdate(), -1), posting_time='00:00:00'))
        with self.assertRaisesRegex(frappe.ValidationError, 'chốt kỳ'):
            validate_repost(doc)
        with self.assertRaisesRegex(frappe.ValidationError, 'chốt kỳ'):
            doc.set_status('In Progress')
        doc.posting_date = add_days(nowdate(), 1)
        validate_repost(doc)

    def test_receipt_aggregate_and_recheck(self):
        self.setup_control()
        po = self.make_po(qty=10)
        pr = self.make_pr(po, qty=6)
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.procurement import validate_receipt_tolerance
        duplicate = pr.items[0].as_dict()
        duplicate.pop('name', None)
        pr.append('items', duplicate)
        with self.assertRaisesRegex(frappe.ValidationError, 'dung sai'):
            validate_receipt_tolerance(pr, self.config)
        pr.set('items', [pr.items[0]])
        validate_receipt_tolerance(pr, self.config)
        frappe.db.set_value('Purchase Order Item', po.items[0].name, 'received_qty', 5)
        with self.assertRaisesRegex(frappe.ValidationError, 'dung sai'):
            validate_receipt_tolerance(pr, self.config)

    def test_return_uom_rate_normalization(self):
        self.setup_control()
        po = self.make_po(qty=10, rate=100000)
        pr = self.make_pr(po, qty=1)
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.procurement import validate_receipt_tolerance
        pr.is_return = 1
        pr.items[0].update(dict(qty=-1000, uom='FB g', conversion_factor=0.001, rate=100))
        validate_receipt_tolerance(pr, self.config)
        pr.items[0].rate=110
        with self.assertRaisesRegex(frappe.ValidationError, 'dung sai'):
            validate_receipt_tolerance(pr, self.config)

    def test_pause_allows_drain_but_not_deactivate(self):
        self.test_transfer_partial_receive()
        from hospitality_core.hospitality_core.api.fnb.configuration import set_paused, deactivate
        from hospitality_core.hospitality_core.api.fnb.procurement import receive_transfer
        from hospitality_core.hospitality_core.api.fnb.common import outlet
        frappe.set_user('Administrator')
        entry = frappe.get_doc('Stock Entry', frappe.db.get_value('Stock Entry',
            {'fnb_outlet': self.out.name, 'add_to_transit': 1, 'docstatus': 1}, 'name'))
        set_paused('FNB Outlet', self.out.name, 1, 'Review pause')
        with self.assertRaises(frappe.ValidationError):
            outlet(self.out.name)
        outlet(self.out.name, allow_paused=True)
        with self.assertRaisesRegex(frappe.ValidationError, 'trung chuyển'):
            deactivate('FNB Outlet', self.out.name, 'Review close')
        frappe.set_user(self.operator)
        receive_transfer(entry.name, {entry.items[0].name: 2}, 'drain')
        self.assertEqual(get_stock_balance(self.raw.name, self.config.transit_warehouse), 0)
        frappe.set_user('Administrator')
        deactivate('FNB Outlet', self.out.name, 'Review close')
        doc = frappe.get_doc('FNB Outlet', self.out.name)
        doc.enabled = 1
        with self.assertRaisesRegex(frappe.ValidationError, 'kích hoạt'):
            doc.save()

    def test_mapping_immutable_and_reactivation(self):
        self.setup_control()
        from hospitality_core.hospitality_core.api.fnb.configuration import set_paused, deactivate, activate_outlet
        set_paused('FNB Outlet', self.out.name, 1, 'Review')
        doc = frappe.get_doc('FNB Outlet', self.out.name)
        doc.warehouse = self.config.main_warehouse
        with self.assertRaisesRegex(frappe.ValidationError, 'ánh xạ'):
            doc.save()
        deactivate('FNB Outlet', self.out.name, 'Review')
        activate_outlet(self.out.name)
        self.assertEqual(frappe.db.get_value('FNB Outlet', self.out.name, 'enabled'), 1)

    def test_count_found_item(self):
        self.setup_control()
        item = frappe.get_doc(dict(doctype='Item', item_code='REVIEW-FOUND', item_name='Found',
            item_group='Services', stock_uom='FB kg', is_stock_item=1)).insert()
        frappe.set_user(self.operator)
        count = frappe.get_doc(dict(doctype='FNB Stock Count', property=self.out.property, outlet=self.out.name,
            warehouse=self.warehouse, posting_datetime=now_datetime(), reason='Found stock')).insert()
        from hospitality_core.hospitality_core.api.fnb.counts import start_count, add_found_item, record_count, approve_count
        start_count(count.name)
        add_found_item(count.name, item.name, 'Physical discovery')
        add_found_item(count.name, item.name, 'Physical discovery')
        count.reload()
        self.assertEqual(len([r for r in count.items if r.item == item.name]), 1)
        values = {r.name: (2 if r.item == item.name else 10) for r in count.items}
        record_count(count.name, values)
        frappe.set_user('Administrator')
        record_count(count.name, values, recount=True)
        approve_count(count.name, 'found-count', {r.name: 100000 for r in count.items if r.item == item.name})
        self.assertEqual(get_stock_balance(item.name, self.warehouse), 2)

    def test_explicit_batch_aggregate(self):
        self.setup_control()
        frappe.db.set_single_value('Stock Settings', 'enable_serial_and_batch_no_for_item', 1)
        frappe.clear_document_cache('Stock Settings', 'Stock Settings')
        from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
        item = frappe.get_doc(dict(doctype='Item', item_code='REVIEW-BATCH', item_name='Batch',
            item_group='Services', stock_uom='FB kg', is_stock_item=1, has_batch_no=1, create_new_batch=0)).insert()
        batch = frappe.get_doc(dict(doctype='Batch', batch_id='REVIEW-BATCH', item=item.name,
            expiry_date=add_days(nowdate(), 10))).insert()
        seed = make_stock_entry(item_code=item.name, qty=5, to_warehouse=self.warehouse,
            company=self.company, basic_rate=100, batch_no=batch.name, use_serial_batch_fields=1, do_not_submit=True)
        seed.flags.fnb_service=True
        seed.submit()
        from hospitality_core.hospitality_core.api.fnb.common import make_event
        from hospitality_core.hospitality_core.api.fnb.inventory import post_stock
        event = make_event(self.out, 'Issue', 'review-batch-key', 'review', purpose='Sale')
        with self.assertRaisesRegex(frappe.ValidationError, 'Tổng lượng'):
            post_stock(event, self.out, self.config, [dict(item=item.name, qty=3, batch_no=batch.name)] * 2)
        self.assertEqual(get_stock_balance(item.name, self.warehouse), 5)

    def test_paused_pos_return_and_physical_correction(self):
        self.test_native_pos_issues_once_with_native_tax()
        source = frappe.db.get_value('POS Invoice', {'fnb_outlet': self.out.name, 'is_return': 0, 'docstatus': 1}, 'name')
        from hospitality_core.hospitality_core.api.fnb.configuration import set_paused
        from erpnext.accounts.doctype.pos_invoice.pos_invoice import make_sales_return
        from hospitality_core.hospitality_core.api.fnb.procurement import approve_native
        from hospitality_core.hospitality_core.api.fnb.service import approve_waste
        set_paused('FNB Outlet', self.out.name, 1, 'Review')
        returned = make_sales_return(source)
        returned.fnb_return_disposition = 'Physical Return'
        frappe.set_user(self.operator)
        returned.insert()
        frappe.set_user('Administrator')
        approve_native('POS Invoice', returned.name)
        returned.reload()
        returned.submit()
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 10)
        origin = frappe.db.get_value('FNB Inventory Event', {'source_doctype': 'POS Invoice',
            'source_name': returned.name, 'event_type': 'Return'}, 'name')
        frappe.set_user(self.operator)
        waste = frappe.get_doc(dict(doctype='FNB Waste Record', property=self.out.property, outlet=self.out.name,
            posting_datetime=now_datetime(), disposition='Return Correction', source_event=origin,
            reason='Nhập nhầm lượng', items=[dict(item=self.raw.name, qty=0.5, uom='FB kg')])).insert()
        with self.assertRaisesRegex(frappe.ValidationError, 'tự duyệt'):
            approve_waste(waste.name, 'correct-return')
        frappe.set_user('Administrator')
        event = approve_waste(waste.name, 'correct-return')
        self.assertEqual(approve_waste(waste.name, 'correct-return'), event)
        self.assertEqual(get_stock_balance(self.raw.name, self.warehouse), 9.5)
        self.assertEqual(frappe.db.get_value('POS Invoice', returned.name, 'docstatus'), 1)
        frappe.set_user(self.operator)
        second = frappe.get_doc(dict(doctype='FNB Waste Record', property=self.out.property, outlet=self.out.name,
            posting_datetime=now_datetime(), disposition='Return Correction', source_event=origin,
            reason='Vượt nguồn', items=[dict(item=self.raw.name, qty=0.6, uom='FB kg')])).insert()
        frappe.set_user('Administrator')
        with self.assertRaisesRegex(frappe.ValidationError, 'vượt'):
            approve_waste(second.name, 'over-correction')


if __name__ == '__main__':
    names = sys.argv[1:] or [n for n in ReviewTests.__dict__ if n.startswith('test_')]
    try:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(ReviewTests(n) for n in names))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
