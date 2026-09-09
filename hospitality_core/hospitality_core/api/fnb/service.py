import json
import frappe
from frappe import _
from frappe.utils import flt, now_datetime
from .common import (load, save, outlet, positive, approve_actor, event_existing, make_event, atomic, role, parse_payload)
from .recipes import select_recipe, ingredients
from .inventory import post_stock, rows_from_doc
from .guards import lock_warehouses


def menu_item(out, item):
    row=next((r for r in out.menu if r.item==item),None)
    if not row:
        frappe.throw(_('Món chưa được cấu hình tại outlet.'))
    return row


def reserved_stock(warehouse,item):
    return flt(frappe.db.sql('''SELECT COALESCE(SUM(GREATEST(0,l.stock_qty-l.cancelled_qty-
        CASE WHEN t.purpose='Sale' THEN l.billed_qty ELSE l.prepared_qty END)),0)
        FROM `tabFNB Service Line` l JOIN `tabFNB Service Ticket` t ON t.name=l.parent
        JOIN `tabFNB Outlet` o ON o.name=t.outlet
        WHERE o.warehouse=%s AND l.item=%s AND t.status IN ('Sent','Prepared','Served')''',
        (warehouse,item))[0][0])


def ticket_status(doc):
    # TRƯỚC ĐÂY: so sánh >= không dung sai — prepared_qty/served_qty/
    # cancelled_qty được cộng dồn qua nhiều lần xác nhận từng phần
    # (confirm_ticket's row.xxx_qty += qty), có thể lệch phần triệu do
    # cộng dồn số thực (VD served_qty=2.9999999999997 thay vì 3.0) — khiến
    # điều kiện >= không bao giờ đúng dù phiếu đã thực sự hoàn tất, kẹt vĩnh
    # viễn ở trạng thái cũ. Các chỗ khác trong cùng file (kiểm tra "vượt
    # lượng còn lại") đã dùng dung sai +1e-9, riêng hàm này thì chưa — thêm
    # cho nhất quán.
    if all(r.cancelled_qty+1e-9>=r.stock_qty for r in doc.items):
        return 'Cancelled'
    if all(r.served_qty+r.cancelled_qty+1e-9>=r.stock_qty for r in doc.items):
        if doc.purpose!='Sale' or all(r.billed_qty+r.cancelled_qty+1e-9>=r.stock_qty for r in doc.items):
            return 'Reconciled'
        return 'Served'
    if all(r.prepared_qty+r.cancelled_qty+1e-9>=r.stock_qty for r in doc.items):
        return 'Prepared'
    return 'Sent'


@frappe.whitelist()
def preparation_batches(name, line):
    doc=load('FNB Service Ticket',name,'read')
    row=next((r for r in doc.items if r.name==line),None)
    if not row or not row.snapshot:
        frappe.throw(_('Dòng chưa có snapshot chế biến.'))
    return [r['item'] for r in json.loads(row.snapshot).get('ingredients',[])
            if frappe.get_cached_value('Item',r['item'],'has_batch_no')]


@frappe.whitelist(methods=['POST'])
@atomic
def send_ticket(name):
    doc=load('FNB Service Ticket',name)
    if doc.status!='Draft':
        return doc.name
    out,cfg=outlet(doc.outlet)
    lock_warehouses([out.warehouse],doc.posting_datetime)
    if not doc.items:
        frappe.throw(_('Phiếu phục vụ chưa có món.'))
    if doc.purpose!='Sale':
        approve_actor(doc)
        if not doc.beneficiary:
            frappe.throw(_('Cần người/bộ phận hưởng suất.'))
        doc.approved_by=frappe.session.user
        doc.approved_at=now_datetime()
    requested={}
    for row in doc.items:
        mode=menu_item(out,row.item)
        if mode.stock_mode=='Session':
            frappe.throw(_('Món buffet/gói sự kiện phải lập phiên phục vụ.'))
        snapshot=dict(mode=mode.stock_mode,item=row.item,quantity=1,ingredients=[],cost_group=mode.cost_group)
        if mode.stock_mode=='Recipe':
            recipe,snapshot=select_recipe(out.name,row.item,doc.posting_datetime)
            row.recipe=recipe.name
            snapshot.update(mode='Recipe',cost_group=mode.cost_group)
        row.snapshot=frappe.as_json(snapshot)
        if mode.stock_mode=='Stock':
            requested[row.item]=requested.get(row.item,0)+row.stock_qty
    from erpnext.stock.utils import get_stock_balance
    for item,qty in requested.items():
        if get_stock_balance(item,out.warehouse)-reserved_stock(out.warehouse,item)+1e-9<qty:
            frappe.throw(_('Không đủ tồn khả dụng sau giữ chỗ.'))
    doc.status='Sent'
    save(doc)
    return doc.name


@frappe.whitelist(methods=['POST'])
@atomic
def confirm_ticket(name, line, quantity, action, request_id, batches=None):
    if action not in ('Prepare','Serve','Cancel'):
        frappe.throw(_('Thao tác phiếu phục vụ không hợp lệ.'))
    doc=load('FNB Service Ticket',name)
    qty=positive(quantity)
    batches=parse_payload(batches, dict, empty=dict, label='Danh sách lô hàng')
    payload=dict(line=line,quantity=qty,action=action,batches=batches)
    existing,key,signature=event_existing(doc,action,request_id,payload)
    if existing:
        return existing.name
    if doc.status not in ('Sent','Prepared','Served'):
        frappe.throw(_('Phiếu chưa gửi bếp hoặc đã kết thúc.'))
    out,cfg=outlet(doc.outlet)
    lock_warehouses([out.warehouse],now_datetime())
    row=next((r for r in doc.items if r.name==line),None)
    if not row:
        frappe.throw(_('Dòng không thuộc phiếu.'))
    snapshot=json.loads(row.snapshot)
    if action=='Prepare':
        if qty>row.stock_qty-row.prepared_qty-row.cancelled_qty+1e-9:
            frappe.throw(_('Vượt lượng chưa chế biến.'))
    elif action=='Serve':
        if qty>row.prepared_qty-row.served_qty+1e-9:
            frappe.throw(_('Vượt lượng đã chế biến chưa phục vụ.'))
    elif qty>row.stock_qty-row.prepared_qty-row.cancelled_qty+1e-9:
        frappe.throw(_('Món đã chế biến cần ghi phiếu hủy món, không hoàn nguyên liệu.'))
    event=make_event(doc,action,key,signature,posting_datetime=now_datetime(),source_line=line,
        quantity=qty,purpose=doc.purpose,snapshot=frappe.as_json(dict(recipe=snapshot,batches=batches)))
    if action=='Prepare':
        if snapshot['mode']=='Recipe':
            material=ingredients(snapshot,qty)
            for r in material:
                r['batch_no']=batches.get(r['item'])
            post_stock(event,out,cfg,material)
        elif snapshot['mode']=='Stock' and doc.purpose!='Sale':
            post_stock(event,out,cfg,[dict(item=row.item,qty=qty,
                uom=frappe.get_cached_value('Item',row.item,'stock_uom'),batch_no=batches.get(row.item))])
        row.prepared_qty+=qty
    elif action=='Serve':
        row.served_qty+=qty
    else:
        row.cancelled_qty+=qty
    doc.status=ticket_status(doc)
    save(doc)
    return event.name


@frappe.whitelist(methods=['POST'])
@atomic
def produce(name, request_id):
    doc=load('FNB Production Batch',name)
    existing,key,sig=event_existing(doc,'Produce',request_id,dict(recipe=doc.recipe,qty=doc.output_qty,items=rows_from_doc(doc)))
    if existing:
        return existing.name
    if doc.status!='Draft':
        frappe.throw(_('Mẻ đã được ghi nhận.'))
    approve_actor(doc)
    out,cfg=outlet(doc.outlet)
    recipe,snapshot=select_recipe(out.name,frappe.db.get_value('FNB Recipe Version',doc.recipe,'item'),doc.posting_datetime)
    if recipe.name!=doc.recipe:
        frappe.throw(_('Mẻ phải dùng công thức hiệu lực tại thời điểm ghi nhận.'))
    if not doc.items:
        frappe.throw(_('Cần nguyên liệu thực dùng.'))
    expected={r['item'] for r in snapshot['ingredients']}
    if {r.item for r in doc.items}!=expected:
        frappe.throw(_('Nguyên liệu thực dùng phải khớp công thức; thay thế cần phiên bản được duyệt.'))
    if frappe.get_cached_value('Item',recipe.item,'has_batch_no'):
        if not doc.output_batch:
            if not doc.expiry_date:
                frappe.throw(_('Cần hạn dùng để tạo lô thành phẩm.'))
            batch=frappe.get_doc(dict(doctype='Batch',batch_id='FNB-'+frappe.generate_hash(length=12),
                item=recipe.item,expiry_date=doc.expiry_date))
            batch.insert(ignore_permissions=True)
            doc.output_batch=batch.name
        elif doc.expiry_date and str(frappe.db.get_value('Batch',doc.output_batch,'expiry_date'))!=str(doc.expiry_date):
            frappe.throw(_('Hạn dùng của mẻ không khớp lô thành phẩm.'))
    event=make_event(doc,'Produce',key,sig,quantity=positive(doc.output_qty),snapshot=frappe.as_json(snapshot),purpose='Production')
    entry=post_stock(event,out,cfg,rows_from_doc(doc),purpose='Manufacture',output=dict(item=recipe.item,qty=doc.output_qty,batch_no=doc.output_batch))
    doc.stock_entry=entry.name
    doc.snapshot=frappe.as_json(snapshot)
    doc.status='Approved'
    doc.approved_by=frappe.session.user
    doc.approved_at=now_datetime()
    save(doc)
    return event.name


@frappe.whitelist(methods=['POST'])
@atomic
def approve_waste(name, request_id):
    doc=load('FNB Waste Record',name)
    payload=dict(disposition=doc.disposition,source=doc.source_event,items=rows_from_doc(doc))
    existing,key,sig=event_existing(doc,'Return' if doc.disposition=='Physical Return' else 'Waste',request_id,payload)
    if existing:
        return existing.name
    if doc.status!='Draft' or not doc.reason or not doc.items:
        frappe.throw(_('Phiếu cần ở trạng thái nháp, có số lượng và lý do.'))
    approve_actor(doc)
    out,cfg=outlet(doc.outlet, allow_paused=True)
    origin=None
    if doc.disposition!='Inventory Loss':
        origin=load('FNB Inventory Event',doc.source_event,'read')
        if origin.property!=doc.property or origin.outlet!=doc.outlet:
            frappe.throw(_('Nguồn khác cơ sở/outlet.'))
    action='Return' if doc.disposition=='Physical Return' else 'Waste'
    event=make_event(doc,action,key,sig,origin=origin.name if origin else None,purpose='Waste',snapshot=frappe.as_json(payload))
    if doc.disposition=='Physical Return':
        event.purpose=origin.purpose
    if doc.disposition=='Inventory Loss':
        post_stock(event,out,cfg,rows_from_doc(doc))
    elif doc.disposition=='Return Correction':
        if origin.event_type != 'Return' or origin.source_doctype != 'POS Invoice' or not origin.stock_entry:
            frappe.throw(_('Điều chỉnh nhập sai cần sự kiện hoàn kho POS gốc.'))
        entry = frappe.get_doc('Stock Entry', origin.stock_entry)
        if entry.docstatus != 1:
            frappe.throw(_('Chứng từ nhập nguồn phải còn submit.'))
        remaining = {}
        for row in entry.items:
            k = (row.item_code, row.batch_no or None)
            remaining[k] = remaining.get(k, 0) + row.transfer_qty
        for prior in frappe.get_all('FNB Inventory Event', filters={'origin': origin.name,
                'event_type': 'Waste', 'name': ['!=', event.name]}, fields=['snapshot']):
            data = json.loads(prior.snapshot or '{}')
            if data.get('disposition') == 'Return Correction':
                for row in data['items']:
                    k = (row['item'], row.get('batch_no') or None)
                    remaining[k] = remaining.get(k, 0) - row['qty']
        for row in payload['items']:
            k = (row['item'], row.get('batch_no') or None)
            remaining[k] = remaining.get(k, 0) - row['qty']
            if remaining[k] < -1e-9:
                frappe.throw(_('Lượng điều chỉnh vượt phần nhập nguồn chưa điều chỉnh.'))
        event.purpose = origin.purpose
        event.quantity = sum(row['qty'] for row in payload['items'])
        post_stock(event, out, cfg, payload['items'])
    elif doc.disposition=='Prepared Waste':
        if origin.event_type!='Prepare' or origin.source_doctype!='FNB Service Ticket':
            frappe.throw(_('Chỉ phân loại món đã chế biến có phiếu nguồn.'))
        ticket=load('FNB Service Ticket',origin.source_name)
        row=next(r for r in ticket.items if r.name==origin.source_line)
        qty=sum(r.stock_qty for r in doc.items)
        if len(doc.items)!=1 or doc.items[0].item!=row.item or qty>origin.quantity+1e-9 or qty>row.prepared_qty-row.served_qty+1e-9:
            frappe.throw(_('Vượt lượng món đã làm chưa phục vụ.'))
        prior=frappe.db.sql('SELECT COALESCE(SUM(quantity),0) FROM `tabFNB Inventory Event` WHERE origin=%s AND event_type=\'Waste\'',origin.name)[0][0]
        if qty+flt(prior)>origin.quantity:
            frappe.throw(_('Món nguồn đã ghi hủy.'))
        event.quantity=qty
        snapshot=json.loads(row.snapshot)
        if snapshot.get('mode')=='Stock' and not origin.stock_entry:
            # Hàng bán trực tiếp chưa qua POS vẫn còn trên sổ, phải xuất lượng thực bỏ.
            post_stock(event,out,cfg,rows_from_doc(doc))
        # Giữ dấu vết chế biến ở event; dòng phiếu giải phóng phần không phục vụ.
        row.prepared_qty-=qty
        row.cancelled_qty+=qty
        ticket.status=ticket_status(ticket)
        save(ticket)
    else:
        if origin.event_type!='Issue' or origin.source_doctype!='FNB Service Session' or not origin.stock_entry:
            frappe.throw(_('Chỉ thu hồi Item tồn đã cấp vào phiên phục vụ; không hoàn nguyên liệu món đã chế biến.'))
        entry=frappe.get_doc('Stock Entry',origin.stock_entry)
        return_rows=rows_from_doc(doc)
        previous=frappe.get_all('FNB Inventory Event',filters={'origin':origin.name,'event_type':'Return','name':['!=',event.name]},fields=['snapshot'])
        returned={}
        for prior in previous:
            for r in json.loads(prior.snapshot)['items']:
                k=(r['item'],r.get('batch_no'))
                returned[k]=returned.get(k,0)+r['qty']
        for r in return_rows:
            sources=[s for s in entry.items if s.item_code==r['item'] and (s.batch_no or None)==(r.get('batch_no') or None)]
            limit=sum(s.transfer_qty for s in sources)-returned.get((r['item'],r.get('batch_no')),0)
            if not sources or r['qty']>limit+1e-9:
                frappe.throw(_('Lượng hoàn vượt nguồn thực cấp.'))
            r['rate']=sum(s.basic_amount for s in sources)/sum(s.transfer_qty for s in sources)
            returned[(r['item'],r.get('batch_no'))]=returned.get((r['item'],r.get('batch_no')),0)+r['qty']
        post_stock(event,out,cfg,return_rows,purpose='Material Receipt')
    save(event)
    doc.stock_entry=event.stock_entry
    doc.status='Approved'
    doc.approved_by=frappe.session.user
    doc.approved_at=now_datetime()
    save(doc)
    return event.name


@frappe.whitelist(methods=['POST'])
@atomic
def session_action(name, action, request_id, items=None, actual_covers=None):
    doc=load('FNB Service Session',name)
    if action not in ('Approve','Issue','Close'):
        frappe.throw(_('Thao tác phiên phục vụ không hợp lệ.'))
    # TRƯỚC ĐÂY: 'Approve' và 'Close' (chuyển trạng thái, không cấp/phục vụ gì)
    # đều bị gắn chung event_type='Serve' — trộn lẫn với sự kiện phục vụ thật
    # trong FNB Inventory Event, và khiến 1 request_id vô tình dùng lại cho cả
    # Approve lẫn Close (cùng action_string 'Serve' trong digest chống trùng)
    # bị báo "khóa chống trùng đã dùng với nội dung khác" dù là 2 nghiệp vụ
    # khác nhau. Đã thêm option Approve/Close vào Select event_type, dùng đúng
    # tên hành động thay vì gộp vào 'Serve'.
    event_type=action if action in ('Approve','Issue','Close') else 'Serve'
    parsed=parse_payload(items, list, empty=list, label='Danh sách hàng cấp')
    existing,key,sig=event_existing(doc,event_type,request_id,
        dict(action=action,items=parsed,actual_covers=actual_covers))
    if existing:
        return existing.name
    out,cfg=outlet(doc.outlet)
    if action=='Approve':
        if doc.status!='Draft':
            frappe.throw(_('Chỉ duyệt phiên nháp.'))
        approve_actor(doc)
        positive(doc.expected_covers,'Số khách')
        positive(doc.budget,'Ngân sách',zero=True)
        if not doc.menu:
            frappe.throw(_('Cần thực đơn và lượng chuẩn mỗi suất trước khi duyệt phiên.'))
        if doc.service_type in ('Staff','Complimentary') and not doc.beneficiary:
            frappe.throw(_('Cần người/bộ phận hưởng suất.'))
        for row in doc.menu:
            recipe,snapshot=select_recipe(out.name,row.item,doc.posting_datetime)
            row.recipe=recipe.name
            row.snapshot=frappe.as_json(snapshot)
        doc.status='Approved'
        doc.approved_by=frappe.session.user
        doc.approved_at=now_datetime()
    elif doc.status!='Approved':
        frappe.throw(_('Phiên chưa duyệt hoặc đã chốt.'))
    event=make_event(doc,event_type,key,sig,purpose=doc.service_type,
        snapshot=frappe.as_json(dict(action=action,items=parsed,actual_covers=actual_covers)))
    if action=='Issue':
        if not parsed:
            frappe.throw(_('Cần lượng thực cấp.'))
        normalized=[]
        from .common import stock_quantity
        for row in parsed:
            if not isinstance(row,dict) or not row.get('item') or not row.get('qty') or not row.get('uom'):
                frappe.throw(_('Danh sách hàng cấp không hợp lệ; mỗi dòng cần item/qty/uom.'))
            qty,conversion_factor,uom=stock_quantity(row['item'],row['qty'],row['uom'])
            normalized.append(dict(item=row['item'],qty=qty,uom=uom,batch_no=row.get('batch_no')))
        post_stock(event,out,cfg,normalized)
        event.snapshot=frappe.as_json(dict(action=action,items=normalized))
        save(event)
    if action=='Close':
        role()
        covers=positive(actual_covers,'Khách thực dùng',zero=True)
        if covers!=int(covers):
            frappe.throw(_('Số khách phải là số nguyên.'))
        used=frappe.db.sql("SELECT COALESCE(SUM(quantity),0) FROM `tabFNB Inventory Event` WHERE source_doctype='FNB Service Session' AND source_name=%s AND event_type='Benefit'",doc.name)[0][0]
        if covers<flt(used):
            frappe.throw(_('Số khách thực dùng nhỏ hơn số quyền lợi đã xác nhận.'))
        doc.actual_covers=covers
        doc.status='Closed'
    save(doc)
    return event.name


@frappe.whitelist(methods=['POST'])
@atomic
def use_breakfast(name, entitlement, quantity, request_id):
    session=load('FNB Service Session',name)
    qty=positive(quantity)
    if qty!=int(qty):
        frappe.throw(_('Số suất phải nguyên.'))
    existing,key,sig=event_existing(session,'Benefit',request_id,dict(entitlement=entitlement,quantity=qty))
    if existing:
        return existing.name
    if session.service_type!='Breakfast' or session.status!='Approved':
        frappe.throw(_('Cần phiên bữa sáng đã duyệt đang mở.'))
    benefit=frappe.get_doc('Guest Benefit Entitlement',entitlement,for_update=True)
    benefit.check_permission('read')
    if benefit.property!=session.property or benefit.benefit_type!='Breakfast' or str(benefit.benefit_date)!=str(session.business_date) or benefit.status!='Confirmed':
        frappe.throw(_('Quyền lợi không khớp cơ sở, ngày phục vụ hoặc đã hết hiệu lực.'))
    # TRƯỚC ĐÂY: chỉ lọc property+event_type — quét TOÀN BỘ lịch sử "Benefit"
    # của cả cơ sở (không giới hạn ngày), càng vận hành lâu càng chậm dần.
    # `entitlement` không phải field riêng trên FNB Inventory Event (nằm
    # trong snapshot JSON) nên vẫn cần lọc lại bằng Python, nhưng benefit_date
    # của entitlement đã bắt buộc khớp đúng business_date của phiên (dòng
    # kiểm tra ngay phía trên) — mọi lần dùng entitlement này chỉ có thể ghi
    # nhận trong đúng business_date đó, nên thu hẹp truy vấn về đúng 1 ngày
    # là an toàn, không bỏ sót.
    previous=frappe.get_all('FNB Inventory Event',
        filters={'property':session.property,'event_type':'Benefit','business_date':session.business_date},
        fields=['quantity','snapshot'])
    used=sum(r.quantity for r in previous if json.loads(r.snapshot).get('entitlement')==entitlement)
    if qty+used>benefit.quantity+1e-9:
        frappe.throw(_('Vượt số suất bữa sáng còn lại.'))
    event=make_event(session,'Benefit',key,sig,quantity=qty,purpose='Breakfast',
        snapshot=frappe.as_json(dict(entitlement=entitlement,quantity=qty)))
    if qty+used>=benefit.quantity-1e-9:
        benefit.status='Used'
        benefit.flags.hospitality_service=True
        benefit.save(ignore_permissions=True)
    return event.name
