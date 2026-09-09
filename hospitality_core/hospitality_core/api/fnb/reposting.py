"""Keep ERPNext valuation jobs outside F&B counts and closed periods."""
import frappe
from frappe.utils import get_datetime
from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import RepostItemValuation
from .guards import lock_warehouses


def validate_repost(doc, method=None):
    if not frappe.db.has_table('FNB Warehouse Control'):
        return
    company = doc.company
    count = None
    at = get_datetime(str(doc.posting_date) + ' ' + str(doc.posting_time or '00:00:00'))
    if doc.get('voucher_type') and doc.get('voucher_no'):
        source = frappe.get_doc(doc.voucher_type, doc.voucher_no)
        company = source.company
        source_at = get_datetime(str(source.posting_date) + ' ' + str(source.get('posting_time') or '00:00:00'))
        at = min(at, source_at)
        if source.doctype == 'Stock Reconciliation' and source.get('fnb_source_event'):
            event = frappe.get_doc('FNB Inventory Event', source.fnb_source_event)
            if event.event_type == 'Count' and event.source_doctype == 'FNB Stock Count':
                count = event.source_name
    # Revaluation follows dependent transfers/production across warehouses.
    # Closing already requires all Company reposts to finish; use the same scope.
    names = frappe.get_all('FNB Warehouse Control', filters={'operating_company': company}, pluck='name')
    lock_warehouses(names, at, count=count)


class ScopedRepostItemValuation(RepostItemValuation):
    def set_status(self, status=None, write=True):
        if status == 'In Progress':
            validate_repost(self)
        return super().set_status(status=status, write=write)
