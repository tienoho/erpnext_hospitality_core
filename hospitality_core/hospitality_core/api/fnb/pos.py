"""Nối nguồn bếp vào hóa đơn; Folio và hóa đơn hợp nhất không xuất lại."""
import json
import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime
from .common import outlet, make_event, event_existing, load, save, positive
from .service import menu_item
from .recipes import select_recipe, ingredients
from .inventory import post_stock
from .guards import lock_warehouses


def invoice_outlet(doc):
    if doc.get('fnb_outlet'):
        return doc.fnb_outlet
    if doc.get('pos_profile'):
        mapped=frappe.db.get_value('FNB POS Mapping',{'pos_profile':doc.pos_profile},'parent')
        if mapped:
            return mapped
    whs={r.get('warehouse') for r in doc.items if r.get('warehouse')}
    candidates=frappe.get_all('FNB Outlet',filters={'warehouse':['in',list(whs)],'enabled':1},fields=['name','property']) if whs else []
    candidates=[r for r in candidates if frappe.db.get_value('FNB Settings',r.property,'enabled')]
    if len(candidates)>1:
        frappe.throw(_('Có nhiều outlet hợp lệ; cần chọn outlet F&B.'))
    if candidates:
        return candidates[0].name
    return None


def before_validate(doc, method=None):
    if not frappe.db.has_table('FNB Outlet'):
        return
    from hospitality_core.api.composite_item_utils import is_consolidated_pos_sales_invoice
    if is_consolidated_pos_sales_invoice(doc):
        validate_consolidation(doc)
        return
    name=invoice_outlet(doc)
    if not name:
        return
    out,cfg=outlet(name,active=False)
    if not cfg.enabled:
        return
    at=get_datetime(str(doc.posting_date)+' '+str(doc.get('posting_time') or '00:00:00'))
    old=doc.get_doc_before_save()
    if not doc.get('is_return') and (not old or not old.docstatus) and (out.get('paused') or cfg.get('paused')):
        frappe.throw(_('F&B đang tạm dừng; chưa được tạo hoặc submit hóa đơn mới.'))
    if not doc.flags.fnb_service:
        for field in ['fnb_approved_by','fnb_approval_hash','fnb_source_event','fnb_version']:
            if (doc.get(field) or '')!=((old.get(field) if old else '') or ''):
                frappe.throw(_('Không sửa nguồn hoặc phê duyệt F&B trực tiếp.'))
    if old and old.docstatus and old.get('fnb_version')!='FNB v1':
        return  # Chứng từ đã ghi trước cutover giữ đường lịch sử.
    if get_datetime(cfg.cutover_at)>at:
        frappe.throw(_('Ngày hóa đơn trước mốc chuyển đổi F&B.'))
    if not out.enabled or doc.company!=out.operating_company:
        frappe.throw(_('Outlet không hoạt động hoặc Company không khớp.'))
    if doc.get('hospitality_property') and doc.hospitality_property!=out.property:
        frappe.throw(_('Hóa đơn khác Property outlet.'))
    doc.flags.fnb_service=True
    doc.fnb_outlet=out.name
    doc.hospitality_property=out.property
    doc.fnb_version='FNB v1'
    if doc.get('is_return'):
        disposition=doc.get('fnb_return_disposition')
        if disposition not in ('Financial Only','Physical Return') or not doc.get('return_against'):
            frappe.throw(_('Hoàn F&B cần hóa đơn gốc và loại xử lý hàng.'))
        source=frappe.get_doc(doc.doctype,doc.return_against,for_update=True)
        source.check_permission('read')
        if source.docstatus!=1 or source.get('fnb_outlet')!=out.name:
            frappe.throw(_('Hóa đơn gốc không thuộc outlet hoặc chưa submit.'))
        if disposition=='Physical Return':
            if any(not frappe.get_cached_value('Item',r.item_code,'is_stock_item') for r in doc.items):
                frappe.throw(_('Phiếu hoàn vật lý chỉ gồm Item có tồn; không nhập lại nguyên liệu món đã chế biến.'))
            doc.update_stock=1
        else:
            doc.update_stock=0
        if doc.doctype=='POS Invoice':
            doc.update_stock=0  # SLE tức thời đi qua Stock Entry; POS hợp nhất không xuất lại.
        return
    byline={r.name:r for r in (old.items if old else [])}
    for row in doc.items:
        mode=menu_item(out,row.item_code)
        if doc.docstatus!=2 and bool(frappe.get_cached_value('Item',row.item_code,'is_stock_item'))!=(mode.stock_mode=='Stock'):
            frappe.throw(_('Item Master không còn khớp chế độ kho của outlet; cần xử lý cấu hình trước khi bán.'))
        if row.get('warehouse') and row.warehouse!=out.warehouse:
            frappe.throw(_('Kho dòng hóa đơn không khớp outlet.'))
        row.warehouse=out.warehouse
        previous=byline.get(row.name)
        if previous and old.get('fnb_outlet')==out.name and previous.item_code==row.item_code and previous.get('fnb_snapshot'):
            row.fnb_snapshot=previous.fnb_snapshot
            continue
        snapshot=dict(mode=mode.stock_mode,item=row.item_code,quantity=1,ingredients=[],cost_group=mode.cost_group)
        if mode.stock_mode=='Recipe':
            recipe,snapshot=select_recipe(out.name,row.item_code,at)
            snapshot.update(mode='Recipe',cost_group=mode.cost_group)
        row.fnb_snapshot=frappe.as_json(snapshot)
    stock_rows=[r for r in doc.items if menu_item(out,r.item_code).stock_mode=='Stock']
    if stock_rows:
        delivered=[bool(r.get('delivery_note') and r.get('dn_detail')) for r in stock_rows]
        if any(delivered) and not all(delivered):
            frappe.throw(_('Tách hóa đơn hàng đã giao qua Delivery Note và hàng xuất trực tiếp.'))
        doc.update_stock=0 if all(delivered) else 1
    if doc.doctype=='POS Invoice':
        doc.update_stock=0


def validate_consolidation(doc):
    """Chỉ nguồn POS thật trong Merge Log mới được bỏ qua xuất kho F&B."""
    references={r.get('pos_invoice') for r in doc.items if r.get('pos_invoice')}
    sources={name:frappe.get_doc('POS Invoice',name,for_update=True) for name in sorted(references)}
    is_fnb=any(s.get('fnb_version')=='FNB v1' for s in sources.values())
    if not is_fnb:
        if doc.get('fnb_version')=='FNB v1' or invoice_outlet(doc):
            frappe.throw(_('Hóa đơn hợp nhất F&B thiếu nguồn POS đã xác minh.'))
        return
    properties=set()
    outlets=set()
    expected={}
    for name,source in sources.items():
        source.check_permission('read')
        if source.docstatus!=1 or source.get('fnb_version')!='FNB v1' or source.company!=doc.company or source.currency!=doc.currency:
            frappe.throw(_('Không hợp nhất khác Company/currency hoặc trộn phiên bản xử lý F&B.'))
        if source.get('consolidated_invoice') and source.consolidated_invoice!=doc.name:
            frappe.throw(_('POS đã được hợp nhất vào hóa đơn khác.'))
        logs=frappe.db.sql('''SELECT m.name FROM `tabPOS Invoice Merge Log` m
            JOIN `tabPOS Invoice Reference` r ON r.parent=m.name
            WHERE m.docstatus=1 AND r.pos_invoice=%s
            AND (IFNULL(m.consolidated_invoice,'') IN ('',%s)
                 OR IFNULL(m.consolidated_credit_note,'')=%s) FOR UPDATE''',(name,doc.name,doc.name))
        if not logs:
            frappe.throw(_('Nguồn POS chưa có Merge Log được submit.'))
        properties.add(source.hospitality_property)
        outlets.add(source.fnb_outlet)
        expected.update({(name,r.name):r for r in source.items})
    if len(properties)!=1 or (doc.get('hospitality_property') and doc.hospitality_property not in properties):
        frappe.throw(_('Không hợp nhất POS khác Property.'))
    seen=set()
    for row in doc.items:
        key=(row.get('pos_invoice'),row.get('pos_invoice_item'))
        original=expected.get(key)
        if not original or key in seen or original.item_code!=row.item_code or abs(flt(original.qty)-flt(row.qty))>1e-9:
            frappe.throw(_('Dòng hợp nhất không khớp Item/lượng hoặc bị trùng nguồn POS.'))
        seen.add(key)
    if seen!=set(expected):
        frappe.throw(_('Hóa đơn hợp nhất thiếu dòng POS nguồn.'))
    doc.flags.fnb_service=True
    doc.fnb_version='FNB v1'
    doc.hospitality_property=next(iter(properties))
    doc.fnb_outlet=next(iter(outlets)) if len(outlets)==1 else None
    doc.update_stock=0
    doc.set('fnb_allocations',[])


def process_invoice(doc):
    if doc.get('fnb_version')!='FNB v1':
        return False
    from hospitality_core.api.composite_item_utils import is_consolidated_pos_sales_invoice
    if is_consolidated_pos_sales_invoice(doc):
        return True
    out,cfg=outlet(doc.fnb_outlet,active=False)
    lock_warehouses([out.warehouse],str(doc.posting_date)+' '+str(doc.get('posting_time') or '00:00:00'))
    if doc.docstatus==2:
        # Hoàn tiền không làm nguyên liệu đã chế biến trở lại kho.
        for event in frappe.get_all('FNB Inventory Event',filters={'source_doctype':doc.doctype,'source_name':doc.name,'event_type':'Allocate'},fields=['name','snapshot']):
            old,key,sig=event_existing(doc,'Release',event.name,dict(origin=event.name))
            if old:
                continue
            allocation=json.loads(event.snapshot)
            ticket=load('FNB Service Ticket',allocation['ticket'])
            line=next(r for r in ticket.items if r.name==allocation['ticket_line'])
            line.billed_qty-=allocation['stock_qty']
            ticket.status='Served'
            save(ticket)
            make_event(doc,'Release',key,sig,origin=event.name,snapshot=event.snapshot)
        return True
    if doc.get('is_return'):
        if doc.doctype=='POS Invoice' and doc.fnb_return_disposition=='Physical Return':
            post_pos_returns(doc,out,cfg)
        return True
    allocation_by_invoice={}
    for a in doc.get('fnb_allocations',[]):
        allocation_by_invoice.setdefault(a.invoice_line,[]).append(a)
    if set(allocation_by_invoice)-{r.name for r in doc.items}:
        frappe.throw(_('Phân bổ tham chiếu dòng không thuộc hóa đơn.'))
    for row in doc.items:
        snapshot=json.loads(row.fnb_snapshot or '{}')
        if not snapshot.get('mode'):
            frappe.throw(_('Thiếu snapshot xử lý kho F&B.'))
        allocations=allocation_by_invoice.get(row.name,[])
        total=sum(positive(a.stock_qty) for a in allocations)
        if allocations and abs(total-flt(row.stock_qty))>1e-9:
            frappe.throw(_('Phân bổ phiếu phục vụ phải khớp toàn bộ lượng của dòng hóa đơn.'))
        for a in allocations:
            payload=dict(ticket=a.ticket,ticket_line=a.ticket_line,stock_qty=flt(a.stock_qty),invoice_line=row.name)
            old,key,sig=event_existing(doc,'Allocate',a.name,payload)
            if old:
                continue
            ticket=load('FNB Service Ticket',a.ticket)
            if ticket.outlet!=out.name or ticket.purpose!='Sale' or ticket.status not in ('Sent','Prepared','Served','Reconciled'):
                frappe.throw(_('Phiếu phục vụ khác outlet hoặc không phải bán hàng.'))
            source=next((r for r in ticket.items if r.name==a.ticket_line),None)
            if not source or source.item!=row.item_code or source.served_qty-source.billed_qty+1e-9<a.stock_qty:
                frappe.throw(_('Lượng phân bổ vượt món đã phục vụ chưa thanh toán.'))
            make_event(doc,'Allocate',key,sig,source_line=row.name,quantity=a.stock_qty,snapshot=frappe.as_json(payload))
            source.billed_qty+=a.stock_qty
            if all(r.billed_qty+r.cancelled_qty>=r.stock_qty for r in ticket.items):
                ticket.status='Reconciled'
            save(ticket)
        if snapshot['mode']=='Session':
            session=load('FNB Service Session',doc.fnb_session,'read') if doc.get('fnb_session') else None
            if not session or session.outlet!=out.name or session.status not in ('Approved','Closed'):
                frappe.throw(_('Gói buffet/tiệc cần phiên phục vụ cùng outlet.'))
        if snapshot['mode']=='Recipe' and not allocations:
            old,key,sig=event_existing(doc,'Prepare',row.name,dict(item=row.item_code,qty=row.stock_qty,snapshot=snapshot))
            if old:
                continue
            event=make_event(doc,'Prepare',key,sig,source_line=row.name,quantity=row.stock_qty,purpose='Sale',
                posting_datetime=str(doc.posting_date)+' '+str(doc.get('posting_time') or '00:00:00'),snapshot=frappe.as_json(snapshot))
            post_stock(event,out,cfg,ingredients(snapshot,row.stock_qty))
        if snapshot['mode']=='Stock' and doc.doctype=='POS Invoice' and not (row.get('delivery_note') and row.get('dn_detail')):
            old,key,sig=event_existing(doc,'Issue',row.name,dict(item=row.item_code,qty=row.stock_qty))
            if not old:
                event=make_event(doc,'Issue',key,sig,source_line=row.name,quantity=row.stock_qty,purpose='Sale',
                    posting_datetime=str(doc.posting_date)+' '+str(doc.get('posting_time') or '00:00:00'),snapshot=frappe.as_json(snapshot))
                post_stock(event,out,cfg,[dict(item=row.item_code,qty=row.stock_qty,uom=row.stock_uom,batch_no=row.get('batch_no'))])
    return True


def prepare_pos_stock(doc,method=None):
    if doc.get('fnb_version')=='FNB v1':
        process_invoice(doc)


def check_reserved_stock(doc,method=None):
    if doc.get('fnb_version')!='FNB v1' or doc.get('is_return') or doc.get('is_consolidated'):
        return
    from .service import reserved_stock
    from erpnext.stock.utils import get_stock_balance
    out,cfg=outlet(doc.fnb_outlet)
    lock_warehouses([out.warehouse])
    quantities={}
    credit={}
    lines={r.name:r for r in doc.items}
    for row in doc.items:
        if json.loads(row.fnb_snapshot)['mode']=='Stock' and not row.get('delivery_note'):
            quantities[row.item_code]=quantities.get(row.item_code,0)+flt(row.stock_qty)
    # Khóa phiếu theo thứ tự cố định để hai hóa đơn không cùng dùng một phần giữ hàng.
    tickets={name:load('FNB Service Ticket',name,'read') for name in sorted({a.ticket for a in (doc.get('fnb_allocations') or [])})}
    by_source={}
    for a in (doc.get('fnb_allocations') or []):
        ticket=tickets[a.ticket]
        row=next((r for r in ticket.items if r.name==a.ticket_line),None)
        target=lines.get(a.invoice_line)
        if ticket.outlet!=out.name or ticket.purpose!='Sale' or not row or not target or row.item!=target.item_code:
            frappe.throw(_('Phân bổ giữ hàng không khớp phiếu và dòng hóa đơn.'))
        key=(ticket.name,row.name)
        by_source[key]=by_source.get(key,0)+positive(a.stock_qty)
        if by_source[key]>row.served_qty-row.billed_qty+1e-9:
            frappe.throw(_('Phân bổ vượt lượng đã phục vụ chưa thanh toán.'))
        credit[row.item]=credit.get(row.item,0)+a.stock_qty
    for item,qty in quantities.items():
        available=get_stock_balance(item,out.warehouse)-reserved_stock(out.warehouse,item)+credit.get(item,0)
        if qty>available+1e-9:
            frappe.throw(_('Không đủ tồn khả dụng; hàng đã được giữ cho phiếu phục vụ khác.'))


@frappe.whitelist()
def allocation_candidates(doctype,name):
    if doctype not in ('POS Invoice','Sales Invoice'):
        frappe.throw(_('Cần hóa đơn bán hàng.'))
    doc=frappe.get_doc(doctype,name)
    doc.check_permission('write')
    if doc.docstatus or doc.get('is_return') or doc.get('is_consolidated') or doc.get('fnb_version')!='FNB v1':
        frappe.throw(_('Chỉ phân bổ vào hóa đơn F&B nháp thông thường.'))
    out,cfg=outlet(doc.fnb_outlet)
    rows=[]
    names=frappe.get_list('FNB Service Ticket',filters={'outlet':out.name,'purpose':'Sale',
        'status':['in',['Sent','Prepared','Served']]},pluck='name',limit_page_length=200)
    for name in names:
        ticket=frappe.get_doc('FNB Service Ticket',name)
        for row in ticket.items:
            if row.item in {r.item_code for r in doc.items} and row.served_qty>row.billed_qty:
                rows.append(dict(ticket=name,ticket_line=row.name,item=row.item,remaining=row.served_qty-row.billed_qty,
                    uom=frappe.get_cached_value('Item',row.item,'stock_uom'),table_number=ticket.table_number,room=ticket.room))
    return rows


def post_pos_returns(doc,out,cfg):
    original=frappe.get_doc('POS Invoice',doc.return_against,for_update=True)
    for row in doc.items:
        quantity=abs(flt(row.stock_qty))
        old,key,sig=event_existing(doc,'Return',row.name,dict(item=row.item_code,qty=quantity,source=original.name))
        if old:
            continue
        original_line=next((r for r in original.items if r.name==row.get('pos_invoice_item')),None)
        if not original_line or original_line.item_code!=row.item_code:
            frappe.throw(_('Hoàn kho cần mã dòng POS gốc đúng Item.'))
        sources=frappe.get_all('FNB Inventory Event',filters={'source_doctype':'POS Invoice','source_name':original.name,
            'source_line':original_line.name,'event_type':'Issue'},fields=['name','stock_entry','source_line'],order_by='creation')
        source_batches={r.batch_no for source in sources if source.stock_entry
            for r in frappe.get_doc('Stock Entry',source.stock_entry).items if r.item_code==row.item_code and r.batch_no}
        if len(source_batches)>1 and not row.get('batch_no'):
            frappe.throw(_('Dòng gốc có nhiều lô; chọn lô thực nhận và tách dòng hoàn theo lô.'))
        if row.get('batch_no') and row.batch_no not in source_batches:
            frappe.throw(_('Lô thực nhận không thuộc dòng POS gốc.'))
        remaining=quantity
        material=[]
        used=[]
        for source in sources:
            if not source.stock_entry:
                continue
            entry=frappe.get_doc('Stock Entry',source.stock_entry)
            for stockrow in entry.items:
                if stockrow.item_code!=row.item_code or (row.get('batch_no') and stockrow.batch_no!=row.batch_no):
                    continue
                prior=frappe.get_all('FNB Inventory Event',filters={'event_type':'Return','property':out.property},fields=['snapshot'])
                returned=0
                for event in prior:
                    for allocation in json.loads(event.snapshot or '{}').get('stock_sources',[]):
                        if allocation['stock_row']==stockrow.name:
                            returned+=allocation['qty']
                take=min(remaining,max(0,stockrow.transfer_qty-returned))
                if take:
                    material.append(dict(item=row.item_code,qty=take,uom=stockrow.stock_uom,
                        batch_no=stockrow.batch_no,rate=stockrow.basic_amount/stockrow.transfer_qty))
                    used.append(dict(stock_row=stockrow.name,qty=take,event=source.name))
                    remaining-=take
            if remaining<=1e-9:
                break
        if remaining>1e-9:
            frappe.throw(_('Lượng nhập lại vượt nguồn kho POS chưa hoàn.'))
        event=make_event(doc,'Return',key,sig,source_line=row.name,quantity=quantity,purpose='Sale',
            snapshot=frappe.as_json(dict(stock_sources=used)),posting_datetime=str(doc.posting_date)+' '+str(doc.get('posting_time') or '00:00:00'))
        post_stock(event,out,cfg,material,purpose='Material Receipt')


def validate_return_approval(doc,method=None):
    if doc.get('fnb_version')=='FNB v1' and doc.get('is_return') and doc.get('fnb_return_disposition')=='Physical Return':
        from .guards import signature
        if not doc.get('fnb_approved_by') or doc.fnb_approved_by==doc.owner or doc.fnb_approval_hash!=signature(doc):
            frappe.throw(_('Nhập lại hàng thực tế cần người khác duyệt đúng nội dung phiếu hoàn.'))


def prevent_physical_source_cancel(doc,method=None):
    if doc.get('fnb_version')!='FNB v1':
        return
    if frappe.db.exists('FNB Inventory Event',{'source_doctype':doc.doctype,'source_name':doc.name,
        'stock_entry':['is','set']}):
        frappe.throw(_('POS đã có xuất/nhập kho vật lý. Dùng chứng từ hoàn Financial Only hoặc Physical Return có nguồn; không hủy rồi xuất lại hàng đã giao.'))


def post_room_charge(doc):
    from .common import digest
    charged=sum(flt(r.amount) for r in doc.payments if r.mode_of_payment=='Guest Account')
    if not charged:
        return
    if not doc.get('hotel_room'):
        frappe.throw(_('Ghi phòng F&B cần chọn phòng tường minh.'))
    from hospitality_core.hospitality_core.doctype.hotel_room.hotel_room import resolve_hotel_room
    resolved_room = resolve_hotel_room(doc.hotel_room, doc.get('hospitality_property'))
    if doc.get('is_return'):
        source=frappe.get_doc(doc.doctype,doc.return_against)
        source.check_permission('read')
        original_rows=frappe.get_all('Folio Transaction',filters={'reference_doctype':doc.doctype,
            'reference_name':source.name,'fnb_pos_key':['is','set'],'is_void':0},fields=['parent'])
        rows=list({r.parent for r in original_rows})
        if len(rows)!=1:
            frappe.throw(_('Không xác định duy nhất Folio ghi phòng của POS gốc để hoàn tiền.'))
    else:
        rows=frappe.get_all('Guest Folio',filters={'room':resolved_room,'property':doc.hospitality_property,'status':'Open'},pluck='name')
    if len(rows)!=1:
        frappe.throw(_('Cần đúng một Folio đang mở trong cơ sở của POS.'))
    folio=frappe.get_doc('Guest Folio',rows[0],for_update=True)
    folio.check_permission('write')
    if folio.property!=doc.hospitality_property or folio.status!='Open':
        frappe.throw(_('Folio gốc đã đóng hoặc khác cơ sở; xử lý hoàn theo công nợ gốc, không ghi vào khách đang ở phòng.'))
    if folio.operating_company!=doc.company or folio.currency!=doc.currency:
        frappe.throw(_('Folio và POS phải cùng Company/currency.'))
    res=frappe.get_doc('Hotel Reservation',folio.reservation)
    if not res.allow_pos_posting:
        frappe.throw(_('Đặt phòng không cho phép ghi phí POS.'))
    if abs(charged)>abs(flt(doc.grand_total))+0.01:
        frappe.throw(_('Phần ghi phòng vượt tổng hóa đơn.'))
    bill_to='Company' if res.is_company_guest else ('Group' if res.is_group_guest else 'Guest')
    weights=[abs(flt(r.net_amount)) for r in doc.items]
    total=sum(weights)
    if not total:
        frappe.throw(_('Không có giá trị món để phân bổ tiền ghi phòng.'))
    remaining=charged
    for index,row in enumerate(doc.items):
        source_key=digest(['FNB POS',doc.name,row.name])
        amount=remaining if index==len(doc.items)-1 else flt(charged*weights[index]/total,doc.precision('grand_total'))
        remaining-=amount
        if frappe.db.exists('Folio Transaction',{'fnb_pos_key':source_key}):
            continue
        txn=frappe.get_doc(dict(doctype='Folio Transaction',parent=folio.name,parenttype='Guest Folio',
            parentfield='transactions',item=row.item_code,qty=row.qty,amount=amount,description=row.item_name,
            posting_date=doc.posting_date,posting_time=doc.posting_time,bill_to=bill_to,
            reference_doctype=doc.doctype,reference_name=doc.name,is_invoiced=1,fnb_pos_key=source_key))
        txn.flags.hospitality_service=True
        txn.insert(ignore_permissions=True)


def void_room_charge(doc):
    from hospitality_core.hospitality_core.api.folio import sync_folio_balance
    rows=frappe.get_all('Folio Transaction',filters={'reference_doctype':doc.doctype,'reference_name':doc.name},fields=['name','parent'])
    affected=set()
    for row in rows:
        folio=frappe.get_doc('Guest Folio',row.parent)
        if folio.property!=doc.hospitality_property:
            frappe.throw(_('Nguồn Folio khác cơ sở POS.'))
        folio.check_permission('write')
        for linked in [row]+frappe.get_all('Folio Transaction',filters={'reference_doctype':'Folio Transaction','reference_name':row.name},fields=['name','parent']):
            target=frappe.get_doc('Guest Folio',linked.parent)
            target.check_permission('write')
            if target.property!=doc.hospitality_property:
                frappe.throw(_('Bản tổng hợp Folio khác cơ sở.'))
            frappe.db.set_value('Folio Transaction',linked.name,dict(is_void=1,void_reason='Hủy POS '+doc.name))
            affected.add(linked.parent)
    for name in affected:
        sync_folio_balance(frappe.get_doc('Guest Folio',name))
