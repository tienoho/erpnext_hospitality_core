"""Khóa kho dùng chung cho API nghiệp vụ và chứng từ ERPNext."""
import frappe
from frappe import _
from frappe.utils import get_datetime
from .common import require_property, digest

NATIVE = {'Stock Entry','Stock Reconciliation','Purchase Receipt','Purchase Invoice','Delivery Note',
          'POS Invoice','Sales Invoice','Material Request','Purchase Order','Landed Cost Voucher'}
STOCK_READ = {'Stock Ledger Entry', 'Bin', 'Stock Reservation Entry', 'Serial and Batch Bundle'}
WAREHOUSE_FIELDS = ('warehouse','s_warehouse','t_warehouse','from_warehouse','to_warehouse','rejected_warehouse',
                    'set_warehouse','set_from_warehouse','set_target_warehouse','source_warehouse','target_warehouse')


def warehouses(doc):
    found = {doc.get(f) for f in WAREHOUSE_FIELDS if doc.get(f)}
    for row in (doc.get('items') or []):
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
    values={k:doc.get(k) for k in ['company','fnb_outlet','material_request_type',
        'transaction_date','supplier','currency','conversion_rate','is_return','return_against','fnb_return_disposition',
        'taxes_and_charges','apply_discount_on','additional_discount_percentage','discount_amount',
        'cost_center','set_warehouse','update_stock','debit_to','credit_to','rounding_adjustment']}
    # TRƯỚC ĐÂY: posting_date/posting_time nằm thẳng trong danh sách hash vô
    # điều kiện — xác nhận THẬT qua test sống trên Docker (approve_native() rồi
    # submit() ngay sau, cùng 1 test, KHÔNG sửa gì) vẫn bị stock_gate() từ chối
    # "Chứng từ F&B cần người khác duyệt nội dung hiện tại". Nguyên nhân gốc:
    # erpnext/utilities/transaction_base.py's validate_posting_time() — chạy ở
    # MỌI lần validate() của Purchase Receipt/Purchase Order/Material Request/
    # Sales Invoice/POS Invoice — ghi đè VÔ ĐIỀU KIỆN posting_date/posting_time
    # thành thời điểm HIỆN TẠI mỗi lần, TRỪ KHI set_posting_time=1 được tick
    # tường minh. Vì approve_native()'s doc.save() và submit() sau đó là 2 lần
    # validate() KHÁC THỜI ĐIỂM, 2 trường này LUÔN đổi giữa 2 lần — khiến MỌI
    # chứng từ duyệt-rồi-submit-sau (đúng luồng bình thường, không phải edge
    # case) đều lệch chữ ký, chặn nhầm submit dù không ai sửa nội dung tài
    # chính gì. Chỉ đưa posting_date/posting_time vào hash khi set_posting_time
    # THẬT SỰ được tick (lúc đó ERPNext không tự ghi đè nữa — 2 trường mới ổn
    # định và có ý nghĩa "nội dung người dùng chọn" đáng bảo vệ).
    values['set_posting_time']=doc.get('set_posting_time')
    if doc.get('set_posting_time'):
        values['posting_date']=doc.get('posting_date')
        values['posting_time']=doc.get('posting_time')
    values['items']=[{k:r.get(k) for k in ['item_code','qty','uom','conversion_factor','rate','warehouse',
        'from_warehouse','schedule_date','purchase_order','purchase_order_item','rejected_qty','rejected_warehouse',
        'batch_no','serial_no','serial_and_batch_bundle','use_serial_batch_fields','expense_account','income_account',
        'cost_center','item_tax_template','discount_percentage','discount_amount','pos_invoice_item','sales_invoice_item']}
        for r in doc.get('items',[])]
    values['taxes']=[{k:r.get(k) for k in ['charge_type','account_head','row_id','rate','tax_amount',
        'included_in_print_rate','included_in_paid_amount','cost_center','category','add_deduct_tax']} for r in (doc.get('taxes') or [])]
    bundles=sorted({r.get('serial_and_batch_bundle') for r in doc.get('items',[]) if r.get('serial_and_batch_bundle')})
    values['bundles']={name:frappe.get_all('Serial and Batch Entry',filters={'parent':name},
        fields=['batch_no','serial_no','qty','warehouse'],order_by='idx') for name in bundles}
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
    if doc.doctype=='Landed Cost Voucher':
        for row in (doc.get('purchase_receipts') or []):
            source=frappe.get_doc(row.receipt_document_type,row.receipt_document)
            source_at=str(source.posting_date)+' '+str(source.get('posting_time') or '00:00:00')
            lock_warehouses(warehouses(source),source_at)
    if method=='before_submit' and active and doc.doctype=='Purchase Invoice' and doc.get('update_stock'):
        frappe.throw(_('Kho F&B nhận/trả hàng qua Purchase Receipt đã duyệt; Purchase Invoice chỉ ghi nhận công nợ.'))
    if method=='before_submit' and active and doc.doctype in {'Stock Entry','Stock Reconciliation'} and not doc.flags.fnb_service:
        if not doc.get('fnb_source_event'):
            frappe.throw(_('Kho F&B đã kích hoạt: tạo chứng từ qua nghiệp vụ có nguồn, không ghi kho trực tiếp.'))
    if method=='before_submit' and active and doc.doctype in {'Material Request','Purchase Order','Purchase Receipt'}:
        if not doc.flags.fnb_service and (not doc.get('fnb_approved_by') or doc.fnb_approval_hash!=signature(doc)):
            frappe.throw(_('Chứng từ F&B cần người khác duyệt nội dung hiện tại trước khi submit.'))
        if doc.doctype == 'Purchase Receipt':
            from .common import outlet
            from .procurement import validate_receipt_tolerance
            # Khong dung ten '_' o day - no shadow bien module-level `from frappe import _`
            # (ham dich thuat) cho toan bo stock_gate(), gay UnboundLocalError o dong throw ben tren.
            _outlet_doc, config = outlet(doc.fnb_outlet, allow_paused=bool(doc.get('is_return')))
            validate_receipt_tolerance(doc, config)
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
    if doc.doctype in NATIVE | STOCK_READ and frappe.db.has_table('FNB Warehouse Control'):
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
    if doctype not in NATIVE | STOCK_READ:
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
