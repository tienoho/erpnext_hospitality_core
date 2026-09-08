import frappe
from frappe import _
from frappe.utils import flt, nowdate
from .common import load, outlet, approve_actor, atomic, stock_quantity, role, event_existing, make_event, save, positive
from .guards import signature, warehouses, lock_warehouses


@frappe.whitelist()
def suggest_request(outlet_name,session=None):
    out,cfg=outlet(outlet_name)
    from erpnext.stock.utils import get_stock_balance
    from .service import reserved_stock
    from .recipes import select_recipe,ingredients
    targets={row.item:row.par_qty for row in out.menu if row.stock_mode=='Stock' and row.par_qty>0}
    demand={}
    if session:
        service=load('FNB Service Session',session,'read')
        if service.outlet!=out.name or service.status not in ('Draft','Approved'):
            frappe.throw(_('Cần phiên dự kiến hoặc đã duyệt cùng outlet.'))
        for row in service.menu:
            snapshot=frappe.parse_json(row.snapshot) if row.snapshot else select_recipe(out.name,row.item,service.posting_datetime)[1]
            for raw in ingredients(snapshot,row.stock_qty*positive(service.expected_covers)):
                demand[raw['item']]=demand.get(raw['item'],0)+raw['qty']
    rows=[]
    for item in sorted(set(targets)|set(demand)):
        available=get_stock_balance(item,out.warehouse)-reserved_stock(out.warehouse,item)
        # ERPNext giữ ordered_qty theo stock UOM; hàng đang giao được thể hiện riêng.
        pending=flt(frappe.db.sql('''SELECT COALESCE(SUM(GREATEST(0,i.stock_qty-i.ordered_qty)),0)
            FROM `tabMaterial Request Item` i JOIN `tabMaterial Request` m ON m.name=i.parent
            WHERE m.docstatus=1 AND m.status NOT IN ('Stopped','Cancelled') AND m.material_request_type='Material Transfer'
            AND i.warehouse=%s AND i.item_code=%s''',(out.warehouse,item))[0][0])
        transit=flt(frappe.db.sql('''SELECT COALESCE(SUM(GREATEST(0,i.transfer_qty-i.transferred_qty)),0)
            FROM `tabStock Entry Detail` i JOIN `tabStock Entry` s ON s.name=i.parent
            JOIN `tabMaterial Request Item` m ON m.name=i.material_request_item
            WHERE s.docstatus=1 AND s.add_to_transit=1 AND m.warehouse=%s AND i.item_code=%s''',(out.warehouse,item))[0][0])
        main=get_stock_balance(item,cfg.main_warehouse)
        required=max(0,targets.get(item,0)+demand.get(item,0)-available-pending-transit)
        rows.append(dict(item=item,uom=frappe.get_cached_value('Item',item,'stock_uom'),
            available=available,par_qty=targets.get(item,0),planned_qty=demand.get(item,0),pending_request_qty=pending,in_transit_qty=transit,
            required_qty=required,main_available=main,purchase_shortage=max(0,required-main)))
    return rows


@frappe.whitelist(methods=['POST'])
@atomic
def create_request(outlet_name, items, required_date, purpose,request_id,request_type='Material Transfer'):
    out,cfg=outlet(outlet_name)
    if request_type not in ('Material Transfer','Purchase'):
        frappe.throw(_('Chỉ lập yêu cầu chuyển kho hoặc mua hàng.'))
    if not purpose:
        frappe.throw(_('Cần mục đích cấp hàng.'))
    items=frappe.parse_json(items) if isinstance(items,str) else items
    if not items:
        frappe.throw(_('Cần danh sách hàng.'))
    payload=dict(items=items,required_date=str(required_date),purpose=purpose,request_type=request_type)
    existing,key,sig=event_existing(out,'Request',request_id,payload)
    if existing:
        return frappe.parse_json(existing.snapshot)['request']
    doc=frappe.get_doc(dict(doctype='Material Request',material_request_type=request_type,
        company=out.operating_company,transaction_date=nowdate(),schedule_date=required_date,
        fnb_outlet=out.name,hospitality_property=out.property,remarks=purpose))
    for row in items:
        stock_qty,factor,stock_uom=stock_quantity(row['item'],row['qty'],row['uom'])
        doc.append('items',dict(item_code=row['item'],qty=row['qty'],uom=row['uom'],conversion_factor=factor,
            warehouse=out.warehouse if request_type=='Material Transfer' else cfg.main_warehouse,
            from_warehouse=cfg.main_warehouse if request_type=='Material Transfer' else None,schedule_date=required_date))
    doc.insert()  # Giữ quyền Material Request chuẩn ERPNext.
    event=make_event(out,'Request',key,sig,snapshot=frappe.as_json(dict(request=doc.name,**payload)))
    event.outlet=out.name
    save(event)
    return doc.name


@frappe.whitelist(methods=['POST'])
@atomic
def approve_native(doctype, name):
    if doctype not in {'Material Request','Purchase Order','Purchase Receipt','POS Invoice','Sales Invoice'}:
        frappe.throw(_('Loại chứng từ không thuộc quy trình duyệt F&B.'))
    doc=frappe.get_doc(doctype,name,for_update=True)
    doc.check_permission('write')
    if doc.docstatus!=0 or not doc.get('fnb_outlet'):
        frappe.throw(_('Cần chứng từ nháp có outlet F&B.'))
    out,cfg=outlet(doc.fnb_outlet)
    approve_actor(doc)
    if doctype in {'POS Invoice','Sales Invoice'} and (not doc.is_return or doc.fnb_return_disposition!='Physical Return'):
        frappe.throw(_('Chỉ duyệt hóa đơn hoàn hàng vật lý trong nghiệp vụ này.'))
    if doc.company!=out.operating_company:
        frappe.throw(_('Company không khớp outlet.'))
    lock_warehouses(warehouses(doc))
    if doctype=='Purchase Receipt':
        if not cfg.allow_direct_receipt and any(r.warehouse!=cfg.main_warehouse for r in doc.items if r.qty>0):
            frappe.throw(_('Chưa cho phép nhận mua trực tiếp vào bếp/bar.'))
        for row in doc.items:
            if not row.purchase_order_item:
                frappe.throw(_('Nhận hàng F&B cần dòng Purchase Order đã duyệt.'))
            source=frappe.db.get_value('Purchase Order Item',row.purchase_order_item,['rate','qty','received_qty','parent'],as_dict=True)
            if not source or frappe.db.get_value('Purchase Order',source.parent,'docstatus')!=1:
                frappe.throw(_('Đơn mua chưa submit.'))
            if abs(flt(row.rate)-flt(source.rate))>abs(flt(source.rate))*cfg.price_tolerance_percent/100+1e-9:
                frappe.throw(_('Giá nhận vượt dung sai; điều chỉnh và duyệt lại đơn mua.'))
            if flt(source.received_qty)+flt(row.qty)>flt(source.qty)*(1+cfg.quantity_tolerance_percent/100)+1e-9:
                frappe.throw(_('Lượng nhận vượt dung sai; điều chỉnh và duyệt lại đơn mua.'))
    doc.flags.fnb_service=True
    doc.fnb_approved_by=frappe.session.user
    doc.save()
    doc.fnb_approval_hash=signature(doc)
    doc.db_set('fnb_approval_hash',doc.fnb_approval_hash,update_modified=False)
    return doc.name


@frappe.whitelist(methods=['POST'])
@atomic
def dispatch_request(name, quantities, request_id):
    role({'FNB Storekeeper','FNB Cost Controller','System Manager'})
    doc=frappe.get_doc('Material Request',name,for_update=True)
    doc.check_permission('read')
    out,cfg=outlet(doc.fnb_outlet)
    quantities=frappe.parse_json(quantities) if isinstance(quantities,str) else quantities
    existing,key,sig=event_existing(doc,'Transfer',request_id,quantities)
    if existing:
        return existing.name
    if doc.docstatus!=1 or doc.material_request_type!='Material Transfer' or not doc.fnb_approved_by:
        frappe.throw(_('Cần yêu cầu chuyển kho đã duyệt và submit.'))
    lock_warehouses([cfg.main_warehouse,cfg.transit_warehouse,out.warehouse])
    from erpnext.stock.doctype.material_request.material_request import make_stock_entry
    entry=make_stock_entry(doc.name)
    selected=[]
    for row in entry.items:
        if row.material_request_item not in quantities:
            continue
        qty=positive(quantities[row.material_request_item])
        if qty>row.qty+1e-9:
            frappe.throw(_('Lượng giao vượt phần yêu cầu còn lại.'))
        row.qty=qty*positive(row.conversion_factor,'Hệ số quy đổi')
        row.stock_uom=frappe.get_cached_value('Item',row.item_code,'stock_uom')
        row.uom=row.stock_uom
        row.conversion_factor=1
        row.s_warehouse=cfg.main_warehouse
        row.t_warehouse=cfg.transit_warehouse
        selected.append(row)
    if not selected or len(selected)!=len(quantities):
        frappe.throw(_('Dòng giao không thuộc phần yêu cầu còn lại.'))
    entry.set('items',selected)
    entry.add_to_transit=1
    entry.from_warehouse=cfg.main_warehouse
    entry.to_warehouse=cfg.transit_warehouse
    event=make_event(doc,'Transfer',key,sig,purpose='Transfer',snapshot=frappe.as_json(quantities))
    entry.fnb_outlet=out.name
    entry.fnb_source_event=event.name
    entry.fnb_version='FNB v1'
    entry.flags.fnb_service=True
    entry.insert()
    entry.submit()
    event.stock_entry=entry.name
    save(event)
    return event.name


@frappe.whitelist(methods=['POST'])
@atomic
def receive_transfer(stock_entry, quantities, request_id):
    doc=frappe.get_doc('Stock Entry',stock_entry,for_update=True)
    doc.check_permission('read')
    out,cfg=outlet(doc.fnb_outlet)
    quantities=frappe.parse_json(quantities) if isinstance(quantities,str) else quantities
    existing,key,sig=event_existing(doc,'Receive',request_id,quantities)
    if existing:
        return existing.name
    if doc.docstatus!=1 or not doc.add_to_transit or doc.owner==frappe.session.user:
        frappe.throw(_('Cần phiếu đang giao và người nhận khác người xuất.'))
    lock_warehouses([cfg.transit_warehouse,out.warehouse])
    from erpnext.stock.doctype.stock_entry.stock_entry import make_stock_in_entry
    entry=make_stock_in_entry(doc.name)
    if isinstance(entry,dict):
        entry=frappe.get_doc(entry)
    selected=[]
    for row in entry.items:
        if row.ste_detail not in quantities:
            continue
        qty=positive(quantities[row.ste_detail])
        if qty>row.qty+1e-9:
            frappe.throw(_('Lượng nhận vượt phần đang giao.'))
        row.qty=qty
        row.t_warehouse=out.warehouse
        selected.append(row)
    if not selected or len(selected)!=len(quantities):
        frappe.throw(_('Dòng nhận không thuộc phiếu giao.'))
    entry.set('items',selected)
    entry.to_warehouse=out.warehouse
    event=make_event(doc,'Receive',key,sig,purpose='Transfer',snapshot=frappe.as_json(quantities))
    entry.fnb_outlet=out.name
    entry.fnb_source_event=event.name
    entry.fnb_version='FNB v1'
    entry.flags.fnb_service=True
    entry.insert()
    entry.submit()
    event.stock_entry=entry.name
    save(event)
    return event.name


@frappe.whitelist()
def pending_transfer(doctype,name):
    if doctype not in ('Material Request','Stock Entry'):
        frappe.throw(_('Loại chứng từ cấp/nhận không hợp lệ.'))
    doc=frappe.get_doc(doctype,name)
    doc.check_permission('read')
    out,cfg=outlet(doc.fnb_outlet)
    if doc.docstatus!=1:
        frappe.throw(_('Cần chứng từ đã submit.'))
    if doctype=='Material Request':
        if doc.material_request_type!='Material Transfer':
            frappe.throw(_('Cần yêu cầu chuyển kho.'))
        from erpnext.stock.doctype.material_request.material_request import make_stock_entry
        pending=make_stock_entry(name)
        key='material_request_item'
    else:
        if not doc.add_to_transit:
            frappe.throw(_('Phiếu không qua kho trung chuyển.'))
        from erpnext.stock.doctype.stock_entry.stock_entry import make_stock_in_entry
        pending=make_stock_in_entry(name)
        if isinstance(pending,dict):
            pending=frappe.get_doc(pending)
        key='ste_detail'
    return dict(from_warehouse=cfg.main_warehouse if doctype=='Material Request' else cfg.transit_warehouse,
        to_warehouse=cfg.transit_warehouse if doctype=='Material Request' else out.warehouse,
        rows=[dict(line=r.get(key),item=r.item_code,uom=r.uom,remaining=r.qty) for r in pending.items if r.qty>0])
