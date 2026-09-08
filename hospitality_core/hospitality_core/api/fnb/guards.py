"""Khóa kho dùng chung cho API nghiệp vụ và chứng từ ERPNext."""
import frappe
from frappe import _
from frappe.utils import get_datetime
from .common import require_property, digest

NATIVE = {'Stock Entry','Stock Reconciliation','Purchase Receipt','Purchase Invoice','Delivery Note',
          'POS Invoice','Sales Invoice','Material Request','Purchase Order','Landed Cost Voucher'}
WAREHOUSE_FIELDS = ('warehouse','s_warehouse','t_warehouse','from_warehouse','to_warehouse','rejected_warehouse',
                    'set_warehouse','set_from_warehouse','set_target_warehouse','source_warehouse','target_warehouse')


def warehouses(doc):
    found = {doc.get(f) for f in WAREHOUSE_FIELDS if doc.get(f)}
    for row in doc.get('items',[]):
        found.update(row.get(f) for f in WAREHOUSE_FIELDS if row.get(f))
    if doc.doctype=='Landed Cost Voucher':
        for row in doc.get('purchase_receipts',[]):
            found.update(warehouses(frappe.get_doc(row.receipt_document_type,row.receipt_document)))
    return sorted(found)


def lock_warehouses(names, at=None, count=None):
    controls = []
    for name in sorted(set(names)):
        rows = frappe.db.sql('SELECT name, property, active_count, closed_through FROM `tabFNB Warehouse Control` WHERE name=%s FOR UPDATE',name,as_dict=True)
        if not rows:
            continue
        control = rows[0]
        require_property(control.property)
        if control.active_count and control.active_count != count:
            frappe.throw(_('Kho {0} đang kiểm kê.').format(name))
        if at and control.closed_through and get_datetime(at)<=get_datetime(control.closed_through):
            frappe.throw(_('Kho đã chốt kỳ; không ghi hoặc hủy chứng từ trong kỳ đã khóa.'))
        controls.append(control)
    return controls


def signature(doc):
    values={k:doc.get(k) for k in ['company','fnb_outlet','material_request_type','posting_date',
        'transaction_date','supplier','currency','conversion_rate','is_return','return_against','fnb_return_disposition']}
    values['items']=[{k:r.get(k) for k in ['item_code','qty','uom','conversion_factor','rate','warehouse',
        'from_warehouse','schedule_date','purchase_order','purchase_order_item','rejected_qty','rejected_warehouse']}
        for r in doc.get('items',[])]
    return digest(values)


def native_validate(doc, method=None):
    if frappe.flags.in_migrate or frappe.flags.in_install or not frappe.db.has_table('FNB Warehouse Control'):
        return
    if doc.doctype not in NATIVE:
        return
    names = warehouses(doc)
    properties = set(frappe.get_all('FNB Warehouse Control',filters={'name':['in',names]},pluck='property')) if names else set()
    if doc.get('fnb_outlet'):
        properties.add(frappe.db.get_value('FNB Outlet',doc.fnb_outlet,'property'))
    properties.discard(None)
    if not properties:
        return
    companies = {require_property(p).operating_company for p in properties}
    if len(companies)!=1 or (doc.get('company') and doc.company not in companies):
        frappe.throw(_('Kho F&B không thuộc Company chứng từ; liên công ty phải dùng mua/bán.'))
    # Chứng từ một cơ sở có dimension header; chuyển liên cơ sở được kiểm tra cả hai đầu.
    if len(properties)==1:
        prop = next(iter(properties))
        if doc.get('hospitality_property') and doc.hospitality_property != prop:
            frappe.throw(_('Property giả mạo hoặc không khớp kho.'))
        doc.hospitality_property = prop
    if not doc.flags.fnb_service:
        old = doc.get_doc_before_save()
        for field in ['fnb_version','fnb_source_event','fnb_approved_by','fnb_approval_hash']:
            if (doc.get(field) or '') != ((old.get(field) if old else '') or ''):
                frappe.throw(_('Không sửa nguồn hoặc phê duyệt F&B trực tiếp.'))


def stock_gate(doc, method=None):
    if frappe.flags.in_migrate or frappe.flags.in_install or not frappe.db.has_table('FNB Warehouse Control'):
        return
    native_validate(doc)
    at = str(doc.get('posting_date') or doc.get('transaction_date') or frappe.utils.nowdate()) + ' ' + str(doc.get('posting_time') or '00:00:00')
    controls = lock_warehouses(warehouses(doc),at,count=doc.flags.get('fnb_count'))
    if not controls:
        return
    active=any(frappe.db.get_value('FNB Settings',r.property,'enabled') for r in controls)
    if method=='before_submit' and active and doc.doctype in {'Stock Entry','Stock Reconciliation'} and not doc.flags.fnb_service:
        if not doc.get('fnb_source_event'):
            frappe.throw(_('Kho F&B đã kích hoạt: tạo chứng từ qua nghiệp vụ có nguồn, không ghi kho trực tiếp.'))
    if method=='before_submit' and doc.doctype in {'Material Request','Purchase Order','Purchase Receipt'}:
        if not doc.flags.fnb_service and (not doc.get('fnb_approved_by') or doc.fnb_approval_hash!=signature(doc)):
            frappe.throw(_('Chứng từ F&B cần người khác duyệt nội dung hiện tại trước khi submit.'))
    if method=='before_cancel' and doc.get('fnb_source_event') and not doc.flags.fnb_service:
        frappe.throw(_('Dùng nghiệp vụ điều chỉnh nguồn F&B; không hủy riêng chứng từ kho.'))


def scoped_permission(doc,user=None,ptype=None,**kwargs):
    from hospitality_core.hospitality_core.api.property_scope import allowed_properties, has_permission
    if not has_permission(doc,user=user,ptype=ptype):
        return False
    if doc.doctype.startswith('FNB '):
        return doc.get('property') in allowed_properties(user)
    if doc.doctype=='Warehouse' and frappe.db.has_table('FNB Warehouse Control'):
        prop=frappe.db.get_value('FNB Warehouse Control',doc.name,'property')
        return not prop or prop in allowed_properties(user)
    if doc.doctype in NATIVE and frappe.db.has_table('FNB Warehouse Control'):
        props=frappe.get_all('FNB Warehouse Control',filters={'name':['in',warehouses(doc)]},pluck='property') if warehouses(doc) else []
        return set(props).issubset(set(allowed_properties(user)))
    return True


def conditions(user=None, doctype=None):
    from hospitality_core.hospitality_core.api.property_scope import conditions as base_conditions, allowed_properties, manager
    base=base_conditions(user=user,doctype=doctype)
    if manager(user) or not frappe.db.has_table('FNB Warehouse Control'):
        return base
    allowed=','.join(frappe.db.escape(p) for p in allowed_properties(user)) or "''"
    if doctype and doctype.startswith('FNB '):
        return f'`tab{doctype}`.property IN ({allowed})'
    if doctype=='Warehouse':
        guard=f'NOT EXISTS (SELECT 1 FROM `tabFNB Warehouse Control` wc WHERE wc.warehouse=`tabWarehouse`.name AND wc.property NOT IN ({allowed}))'
        return f'({base}) AND ({guard})' if base else guard
    if doctype not in NATIVE:
        return base
    meta=frappe.get_meta(doctype)
    table=f'`tab{doctype}`'
    alternatives=[f'wc.name={table}.`{field}`' for field in WAREHOUSE_FIELDS if meta.has_field(field)]
    item_field=meta.get_field('items')
    if item_field and item_field.fieldtype=='Table':
        child=frappe.get_meta(item_field.options)
        matches=[f'wc.name=i.`{field}`' for field in WAREHOUSE_FIELDS if child.has_field(field)]
        if matches:
            alternatives.append(f"EXISTS (SELECT 1 FROM `tab{child.name}` i WHERE i.parent={table}.name AND ({' OR '.join(matches)}))")
    if not alternatives:
        return base
    guard=f"NOT EXISTS (SELECT 1 FROM `tabFNB Warehouse Control` wc WHERE wc.property NOT IN ({allowed}) AND ({' OR '.join(alternatives)}))"
    return f'({base}) AND ({guard})' if base else guard
