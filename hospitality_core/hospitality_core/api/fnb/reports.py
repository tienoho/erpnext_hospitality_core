import json
from datetime import timedelta
import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, flt, now_datetime
from .common import require_property, load, save, approve_actor, atomic, role, digest, business_boundary
from .guards import lock_warehouses


@frappe.whitelist()
def cost_summary(property, from_date, to_date, outlet=None):
    role({'FNB Cost Controller','FNB Finance Approver','System Manager'})
    prop=require_property(property)
    if getdate(to_date)<getdate(from_date):
        frappe.throw(_('Khoảng ngày không hợp lệ.'))
    if outlet and frappe.db.get_value('FNB Outlet',outlet,'property')!=property:
        frappe.throw(_('Outlet khác cơ sở.'))
    filters={'property':property,'business_date':['between',[from_date,to_date]]}
    if outlet:
        filters['outlet']=outlet
    events=frappe.get_all('FNB Inventory Event',filters=filters,
        fields=['name','event_type','purpose','stock_entry','stock_reconciliation','source_doctype','source_name','source_line','snapshot','quantity','origin'])
    totals={}
    exceptions=[]
    vouchers=set()
    for event in events:
        bucket=totals.setdefault(event.purpose or 'Other',dict(cost=0,stock_qty_by_item={}))
        if event.stock_entry:
            if frappe.db.get_value('Stock Entry',event.stock_entry,'docstatus')!=1:
                exceptions.append(dict(event=event.name,problem='Chứng từ kho không còn submit'))
                continue
            if event.event_type in ('Produce','Transfer','Receive'):
                continue  # Biến đổi tồn; không cộng lần hai vào chi phí phục vụ.
            vouchers.add(('Stock Entry',event.stock_entry,event.purpose or 'Other'))
        if event.stock_reconciliation:
            vouchers.add(('Stock Reconciliation',event.stock_reconciliation,'Count Variance'))
        if event.event_type in ('Issue','Produce') and not event.stock_entry:
            exceptions.append(dict(event=event.name,problem='Thiếu chứng từ kho'))
    for doctype,name,purpose in vouchers:
        bucket=totals.setdefault(purpose,dict(cost=0,stock_qty_by_item={}))
        for row in frappe.get_all('Stock Ledger Entry',filters={'voucher_type':doctype,'voucher_no':name,'is_cancelled':0},
                                  fields=['item_code','actual_qty','stock_value_difference']):
            bucket['cost']-=flt(row.stock_value_difference)
            bucket['stock_qty_by_item'][row.item_code]=bucket['stock_qty_by_item'].get(row.item_code,0)-flt(row.actual_qty)
    revenue=0
    native_cost=0
    invoices=[]
    start=business_boundary(property,from_date)
    end=business_boundary(property,getdate(to_date)+timedelta(days=1))
    for dt in ['POS Invoice','Sales Invoice']:
        filters={'hospitality_property':property,'fnb_version':'FNB v1','docstatus':1,'posting_date':['between',[start.date(),end.date()]]}
        if outlet:
            filters['fnb_outlet']=outlet
        for inv in frappe.get_all(dt,filters=filters,fields=['name','base_net_total','is_return','currency','conversion_rate']):
            doc=frappe.get_doc(dt,inv.name)
            at=get_datetime(str(doc.posting_date)+' '+str(doc.posting_time or '00:00:00'))
            if not start<=at<end:
                continue
            from hospitality_core.api.composite_item_utils import is_consolidated_pos_sales_invoice
            if is_consolidated_pos_sales_invoice(doc):
                continue
            revenue+=flt(inv.base_net_total)
            invoices.append(dict(doctype=dt,**inv))
            for row in frappe.get_all('Stock Ledger Entry',filters={'voucher_type':dt,'voucher_no':inv.name,'is_cancelled':0},fields=['stock_value_difference']):
                native_cost-=flt(row.stock_value_difference)
    # Món bỏ sau chế biến chỉ đổi phân loại chi phí; không có SLE mới.
    for event in events:
        if event.event_type!='Waste' or not event.origin or not event.quantity:
            continue
        origin=frappe.get_doc('FNB Inventory Event',event.origin)
        if origin.event_type!='Prepare' or not origin.stock_entry or not origin.quantity:
            continue
        amount=-flt(frappe.db.sql('''SELECT COALESCE(SUM(stock_value_difference),0)
            FROM `tabStock Ledger Entry` WHERE voucher_type='Stock Entry' AND voucher_no=%s AND is_cancelled=0''',origin.stock_entry)[0][0])*event.quantity/origin.quantity
        totals.setdefault(origin.purpose or 'Other',dict(cost=0,stock_qty_by_item={}))['cost']-=amount
        totals.setdefault('Waste',dict(cost=0,stock_qty_by_item={}))['cost']+=amount
    totals['Native Stock Sales']=dict(cost=native_cost,stock_qty_by_item={})
    total_cost=sum(r['cost'] for r in totals.values())
    counts=frappe.get_all('FNB Stock Count',filters={'property':property,'status':'Closed','business_date':['between',[from_date,to_date]]},pluck='name')
    selling_cost=sum(totals.get(purpose,{}).get('cost',0) for purpose in ('Sale','Buffet','Banquet'))+native_cost
    return dict(currency=frappe.get_cached_value('Company',prop.operating_company,'default_currency'),
        from_date=from_date,to_date=to_date,property=property,outlet=outlet,revenue=revenue,
        cost=total_cost,selling_cost=selling_cost,cost_percent=selling_cost/revenue*100 if revenue>0 else None,
        categories=totals,exceptions=exceptions,invoices=invoices,counts=counts,
        provisional=True,notice='Số liệu từ chứng từ; cần kiểm kê đủ các kho và đối soát phân loại trước khi chốt.')


@frappe.whitelist()
def dashboard(property, outlet=None):
    require_property(property)
    queues=[]
    for dt,states in [('FNB Service Ticket',['Sent','Prepared','Served']),('FNB Production Batch',['Draft']),
        ('FNB Waste Record',['Draft']),('FNB Stock Count',['Draft','Counting']),('FNB Service Session',['Draft','Approved'])]:
        if not frappe.has_permission(dt,'read'):
            continue
        filters={'property':property,'status':['in',states]}
        if outlet:
            filters['outlet']=outlet
        rows=frappe.get_list(dt,filters=filters,fields=['name','status','outlet','posting_datetime'],limit_page_length=50,order_by='modified desc')
        queues.append(dict(doctype=dt,rows=rows))
    return dict(queues=queues,can_view_cost=bool(set(frappe.get_roles()).intersection({'FNB Cost Controller','FNB Finance Approver','System Manager'})) or frappe.session.user=='Administrator')


@frappe.whitelist()
def recipe_cost(recipe, standard):
    recipe=load('FNB Recipe Version',recipe,'read')
    standard=load('FNB Cost Standard',standard,'read')
    if recipe.status!='Approved' or standard.status!='Approved' or recipe.operating_company!=standard.operating_company:
        frappe.throw(_('Công thức và giá chuẩn phải đã duyệt, cùng Company.'))
    prices={r.item:r.rate for r in standard.prices}
    snapshot=json.loads(recipe.snapshot)
    rows=[]
    for row in snapshot['ingredients']:
        if row['item'] not in prices:
            frappe.throw(_('Thiếu giá chuẩn nguyên liệu {0}.').format(row['item']))
        rows.append(dict(**row,rate=prices[row['item']],amount=row['qty']*prices[row['item']]))
    total=sum(r['amount'] for r in rows)
    return dict(currency=standard.currency,batch_cost=total,unit_cost=total/snapshot['quantity'],ingredients=rows)


@frappe.whitelist()
def session_cost(name):
    role({'FNB Cost Controller','FNB Finance Approver','System Manager'})
    doc=load('FNB Service Session',name,'read')
    theoretical={}
    for row in doc.menu:
        if not row.snapshot:
            continue
        snapshot=json.loads(row.snapshot)
        for ingredient in snapshot['ingredients']:
            theoretical[ingredient['item']]=theoretical.get(ingredient['item'],0)+ingredient['qty']*row.stock_qty*doc.actual_covers/snapshot['quantity']
    events=frappe.get_all('FNB Inventory Event',filters={'source_doctype':doc.doctype,'source_name':doc.name,'event_type':'Issue'},fields=['name','stock_entry'])
    costs=0
    actual={}
    names=[r.name for r in events]
    if names:
        events+=frappe.get_all('FNB Inventory Event',filters={'origin':['in',names],'event_type':'Return'},fields=['name','stock_entry'])
    for event in events:
        for row in frappe.get_all('Stock Ledger Entry',filters={'voucher_type':'Stock Entry','voucher_no':event.stock_entry,'is_cancelled':0},fields=['item_code','actual_qty','stock_value_difference']):
            costs-=flt(row.stock_value_difference)
            actual[row.item_code]=actual.get(row.item_code,0)-flt(row.actual_qty)
    return dict(currency=doc.currency,budget=doc.budget,actual_cost=costs,actual_covers=doc.actual_covers,
        cost_per_cover=costs/doc.actual_covers if doc.actual_covers else None,budget_variance=costs-doc.budget,
        ingredients=[dict(item=item,theoretical=theoretical.get(item,0),actual=actual.get(item,0),
            variance=actual.get(item,0)-theoretical.get(item,0)) for item in sorted(set(actual)|set(theoretical))],
        provisional=doc.status!='Closed')


@frappe.whitelist(methods=['POST'])
@atomic
def approve_standard(name):
    doc=load('FNB Cost Standard',name)
    if doc.status=='Approved':
        return doc.name
    if doc.status!='Draft':
        frappe.throw(_('Chỉ duyệt bảng giá chuẩn nháp.'))
    approve_actor(doc)
    doc.status='Approved'
    doc.approved_by=frappe.session.user
    doc.approved_at=now_datetime()
    save(doc)
    return doc.name


@frappe.whitelist(methods=['POST'])
@atomic
def close_period(name):
    doc=load('FNB Period Close',name)
    if doc.status=='Closed':
        return doc.name
    if doc.status!='Draft':
        frappe.throw(_('Chỉ chốt kỳ nháp.'))
    role({'FNB Cost Controller','FNB Finance Approver','System Manager'})
    approve_actor(doc)
    if not frappe.conf.get('fnb_period_close_verified'):
        frappe.throw(_('Chưa nghiệm thu đủ đối soát F&B trên site để chốt kỳ.'))
    standard=load('FNB Cost Standard',doc.cost_standard,'read')
    if standard.status!='Approved' or standard.operating_company!=doc.operating_company or getdate(standard.from_date)>getdate(doc.from_date) or getdate(standard.to_date)<getdate(doc.to_date):
        frappe.throw(_('Giá chuẩn không bao phủ kỳ chốt.'))
    controls=frappe.get_all('FNB Warehouse Control',filters={'property':doc.property},pluck='name')
    locked=lock_warehouses(controls)
    if not locked:
        frappe.throw(_('Không có kho F&B để đối soát.'))
    end=business_boundary(doc.property,getdate(doc.to_date)+timedelta(days=1))-timedelta(microseconds=1)
    if end>now_datetime():
        frappe.throw(_('Không chốt kỳ chưa kết thúc.'))
    if frappe.db.exists('Repost Item Valuation',{'company':doc.operating_company,'status':['in',['Queued','In Progress','Failed']]}):
        frappe.throw(_('Còn tác vụ định giá ảnh hưởng Company chưa xử lý xong.'))
    if frappe.db.exists('FNB Service Ticket',{'property':doc.property,'status':['in',['Sent','Prepared','Served']],
        'business_date':['<=',doc.to_date]}):
        frappe.throw(_('Còn phiếu phục vụ chưa đối soát.'))
    if frappe.db.exists('FNB Service Session',{'property':doc.property,'status':['in',['Draft','Approved']],
        'business_date':['<=',doc.to_date]}):
        frappe.throw(_('Còn phiên buffet/tiệc/bữa sáng chưa kết thúc; hoàn tất khách thực dùng và hàng thừa trước khi chốt kỳ.'))
    for wh in controls:
        if not frappe.db.exists('FNB Stock Count',{'warehouse':wh,'status':'Closed','business_date':doc.to_date}):
            frappe.throw(_('Kho {0} chưa có kiểm kê chốt ngày cuối kỳ.').format(wh))
    summary=cost_summary(doc.property,doc.from_date,doc.to_date)
    if summary['exceptions']:
        frappe.throw(_('Còn lỗi nguồn kho; chưa được chốt.'))
    summary['provisional']=False
    doc.snapshot=frappe.as_json(summary)
    doc.status='Closed'
    doc.approved_by=frappe.session.user
    doc.approved_at=now_datetime()
    save(doc)
    for row in locked:
        control=load('FNB Warehouse Control',row.name,'read')
        if not control.closed_through or get_datetime(control.closed_through)<end:
            control.closed_through=end
            save(control)
    return doc.name
