import json
import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, flt
from .common import (load, save, settings, check_warehouse, role, approve_actor, atomic,
                     positive, event_existing, make_event)
from .guards import lock_warehouses


@frappe.whitelist(methods=['POST'])
@atomic
def start_count(name):
    role({'FNB Storekeeper','FNB Cost Controller','System Manager'})
    doc=load('FNB Stock Count',name)
    if doc.status=='Counting':
        return doc.name
    if doc.status!='Draft':
        frappe.throw(_('Phiên kiểm kê không còn ở trạng thái nháp.'))
    cfg=settings(doc.property)
    check_warehouse(doc.warehouse,doc.property,doc.operating_company)
    controls=lock_warehouses([doc.warehouse],now_datetime())
    if not controls:
        frappe.throw(_('Kho chưa được ánh xạ F&B.'))
    pending=frappe.db.sql('''SELECT t.name FROM `tabFNB Service Ticket` t
        JOIN `tabFNB Service Line` l ON l.parent=t.name JOIN `tabItem` i ON i.name=l.item
        JOIN `tabFNB Outlet` o ON o.name=t.outlet
        WHERE o.warehouse=%s AND t.status IN ('Sent','Prepared','Served')
        AND i.is_stock_item=1 AND l.stock_qty>l.cancelled_qty+
        CASE WHEN t.purpose='Sale' THEN l.billed_qty ELSE l.prepared_qty END LIMIT 1''',doc.warehouse)
    if pending:
        frappe.throw(_('Còn hàng phục vụ chưa đối chiếu POS tại kho; xử lý trước khi đếm.'))
    from erpnext.stock.utils import get_stock_balance
    at=now_datetime()
    candidates=frappe.get_all('Bin',filters={'warehouse':doc.warehouse},pluck='item_code')
    snapshot=[]
    doc.set('items',[])
    for item in candidates:
        master=frappe.get_cached_doc('Item',item)
        if master.has_serial_no:
            frappe.throw(_('Item có serial nằm ngoài danh mục F&B; kiểm kê bằng ERPNext chuyên dụng.'))
        qty,rate=get_stock_balance(item,doc.warehouse,at.date(),at.time(),with_valuation_rate=True)
        if master.has_batch_no:
            from erpnext.stock.doctype.batch.batch import get_batch_qty
            from erpnext.stock.utils import get_incoming_rate
            batches=get_batch_qty(item_code=item,warehouse=doc.warehouse,posting_datetime=at,
                for_stock_levels=True,consider_negative_batches=True,do_not_check_future_batches=True)
            for batch in batches:
                batch_rate=get_incoming_rate(frappe._dict(item_code=item,warehouse=doc.warehouse,qty=-batch.qty,
                    batch_no=batch.batch_no,company=doc.operating_company,posting_date=at.date(),posting_time=at.time())) if batch.qty else rate
                snapshot.append(dict(item=item,batch_no=batch.batch_no,qty=batch.qty,rate=batch_rate,uom=master.stock_uom))
                doc.append('items',dict(item=item,batch_no=batch.batch_no,qty=1,uom=master.stock_uom))
        else:
            snapshot.append(dict(item=item,batch_no=None,qty=qty,rate=rate,uom=master.stock_uom))
            doc.append('items',dict(item=item,qty=1,uom=master.stock_uom))
    if not snapshot:
        frappe.throw(_('Kho chưa có mặt hàng để đếm.'))
    doc.count_snapshot=frappe.as_json(snapshot)
    doc.posting_datetime=at
    doc.status='Counting'
    save(doc)
    control=load('FNB Warehouse Control',doc.warehouse,'read')
    control.active_count=doc.name
    save(control)
    return doc.name


@frappe.whitelist(methods=['POST'])
@atomic
def record_count(name, values, recount=False):
    doc=load('FNB Stock Count',name)
    if doc.status!='Counting':
        frappe.throw(_('Kho chưa mở phiên đếm.'))
    role({'FNB Storekeeper','FNB Cost Controller','System Manager'})
    lock_warehouses([doc.warehouse],count=doc.name)
    from frappe.utils import cint
    recount=bool(cint(recount))
    values=frappe.parse_json(values) if isinstance(values,str) else values
    if not isinstance(values,dict):
        frappe.throw(_('Số đếm phải là ánh xạ mã dòng → số lượng.'))
    if recount and (not doc.counted_by or doc.counted_by==frappe.session.user):
        frappe.throw(_('Người đếm lại phải khác người đếm lần đầu.'))
    if not recount and doc.recounted_by:
        frappe.throw(_('Đã đếm lại; không sửa lần đếm đầu.'))
    actor=doc.recounted_by if recount else doc.counted_by
    if actor and actor!=frappe.session.user:
        frappe.throw(_('Mỗi lần đếm có một người chịu trách nhiệm.'))
    rows={r.name:r for r in doc.items}
    for key,qty in values.items():
        if key not in rows:
            frappe.throw(_('Dòng đếm không thuộc phiên.'))
        row=rows[key]
        row.set('recounted_qty' if recount else 'counted_qty',positive(qty,'Số đếm',zero=True))
        row.set('recount_entered' if recount else 'count_entered',1)
    doc.set('recounted_by' if recount else 'counted_by',frappe.session.user)
    save(doc)
    return doc.name


@frappe.whitelist(methods=['POST'])
@atomic
def approve_count(name, request_id):
    doc=load('FNB Stock Count',name)
    payload={r.name:[r.counted_qty,r.recounted_qty,r.count_entered,r.recount_entered] for r in doc.items}
    existing,key,sig=event_existing(doc,'Count',request_id,payload)
    if existing:
        return existing.name
    role({'FNB Cost Controller','FNB Finance Approver','System Manager'})
    approve_actor(doc)
    if doc.status!='Counting' or not doc.counted_by or not doc.recounted_by or not all(r.count_entered and r.recount_entered for r in doc.items):
        frappe.throw(_('Cần hoàn tất hai lượt đếm độc lập.'))
    if doc.counted_by==frappe.session.user:
        frappe.throw(_('Người đếm đầu không được duyệt chênh lệch.'))
    cfg=settings(doc.property)
    lock_warehouses([doc.warehouse],count=doc.name)
    at=get_datetime(doc.posting_datetime)
    original={(r['item'],r.get('batch_no') or None):r for r in json.loads(doc.count_snapshot)}
    event=make_event(doc,'Count',key,sig,snapshot=doc.count_snapshot,purpose='Count')
    reco=frappe.get_doc(dict(doctype='Stock Reconciliation',company=doc.operating_company,purpose='Stock Reconciliation',
        set_posting_time=1,posting_date=at.date(),posting_time=at.time(),expense_account=cfg.variance_account,
        cost_center=cfg.cost_center,hospitality_property=doc.property,fnb_outlet=doc.outlet,
        fnb_version='FNB v1',fnb_source_event=event.name))
    for row in doc.items:
        baseline=original[(row.item,row.batch_no or None)]
        if abs(flt(row.recounted_qty)-flt(baseline['qty']))>1e-9:
            if not doc.reason:
                frappe.throw(_('Cần lý do/phân tích chênh lệch kiểm kê.'))
            reco.append('items',dict(item_code=row.item,warehouse=doc.warehouse,qty=row.recounted_qty,
                valuation_rate=baseline['rate'],allow_zero_valuation_rate=int(not baseline['rate']),
                batch_no=row.batch_no,use_serial_batch_fields=int(bool(row.batch_no))))
    if reco.items:
        reco.flags.fnb_service=True
        reco.flags.fnb_count=doc.name
        reco.insert(ignore_permissions=True)
        reco.submit()
        event.stock_reconciliation=reco.name
        doc.stock_reconciliation=reco.name
        save(event)
    doc.status='Closed'
    doc.approved_by=frappe.session.user
    doc.approved_at=now_datetime()
    save(doc)
    control=load('FNB Warehouse Control',doc.warehouse,'read')
    control.active_count=None
    save(control)
    return event.name


@frappe.whitelist(methods=['POST'])
@atomic
def abort_count(name, reason):
    role({'FNB Cost Controller','FNB Finance Approver','System Manager'})
    doc=load('FNB Stock Count',name)
    if doc.status!='Counting' or not str(reason or '').strip():
        frappe.throw(_('Chỉ mở khóa phiên đang đếm và phải có lý do.'))
    lock_warehouses([doc.warehouse],count=doc.name)
    doc.reason=reason
    doc.status='Cancelled'
    save(doc)
    control=load('FNB Warehouse Control',doc.warehouse,'read')
    control.active_count=None
    save(control)
    return doc.name
