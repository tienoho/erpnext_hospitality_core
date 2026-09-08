import frappe
from frappe import _
from frappe.utils import get_datetime, flt
from .common import positive, check_warehouse, save
from .guards import lock_warehouses


def post_stock(event, outlet, config, rows, purpose='Material Issue', output=None, count=None):
    """Một sự kiện -> một chứng từ ERPNext; không commit ngoài transaction gọi."""
    warehouse=outlet.warehouse
    at=get_datetime(event.posting_datetime)
    check_warehouse(warehouse,event.property,event.operating_company)
    lock_warehouses([warehouse],at,count=count)
    account={'Staff':config.staff_account,'Complimentary':config.complimentary_account,
             'Waste':config.waste_account}.get(event.purpose,config.cogs_account)
    entry=frappe.get_doc(dict(doctype='Stock Entry',company=event.operating_company,
        stock_entry_type=purpose,purpose=purpose,set_posting_time=1,posting_date=at.date(),posting_time=at.time(),
        hospitality_property=event.property,fnb_outlet=outlet.name,fnb_version='FNB v1',fnb_source_event=event.name))
    expanded=[]
    for source in rows:
        if purpose!='Material Receipt' and not source.get('batch_no') and frappe.get_cached_value('Item',source['item'],'has_batch_no'):
            from erpnext.stock.doctype.batch.batch import get_batch_qty
            batches=get_batch_qty(item_code=source['item'],warehouse=warehouse,posting_datetime=at)
            batches=sorted(batches,key=lambda r:(str(frappe.get_cached_value('Batch',r.batch_no,'expiry_date') or '9999-12-31'),r.batch_no))
            remaining=positive(source['qty'])
            for batch in batches:
                take=min(max(0,flt(batch.qty)),remaining)
                if take:
                    expanded.append(dict(source,qty=take,batch_no=batch.batch_no))
                    remaining-=take
                if remaining<=1e-9:
                    break
            if remaining>1e-9:
                frappe.throw(_('Không đủ lô còn hạn cho {0}.').format(source['item']))
        else:
            expanded.append(source)
    rows=expanded
    for source in rows:
        item=frappe.get_cached_doc('Item',source['item'])
        if not item.is_stock_item:
            frappe.throw(_('Phiếu kho chỉ nhận Item có tồn.'))
        if item.has_serial_no:
            frappe.throw(_('F&B chưa hỗ trợ Item có serial; dùng nghiệp vụ ERPNext chuyên dụng.'))
        qty=positive(source['qty'])
        if source.get('uom') and source['uom']!=item.stock_uom:
            frappe.throw(_('Dịch vụ kho F&B chỉ nhận số lượng đã quy đổi sang stock UOM.'))
        row=dict(item_code=item.name,qty=qty,uom=item.stock_uom,stock_uom=item.stock_uom,
            conversion_factor=1,expense_account=account,cost_center=config.cost_center,
            hospitality_property=event.property)
        if purpose=='Material Receipt':
            row.update(t_warehouse=warehouse,basic_rate=positive(source.get('rate'),'Giá hoàn',zero=True),
                       set_basic_rate_manually=1,allow_zero_valuation_rate=int(not source.get('rate')))
        else:
            row['s_warehouse']=warehouse
        if item.has_batch_no:
            batch=source.get('batch_no')
            if not batch:
                frappe.throw(_('Cần chọn lô nguyên liệu {0}.').format(item.name))
            batch_doc=frappe.get_doc('Batch',batch)
            if batch_doc.item!=item.name or batch_doc.disabled or (batch_doc.expiry_date and str(batch_doc.expiry_date)<str(at.date())):
                frappe.throw(_('Lô không đúng Item, bị khóa hoặc đã hết hạn.'))
            row.update(batch_no=batch,use_serial_batch_fields=1)
        entry.append('items',row)
    if output:
        item=frappe.get_cached_doc('Item',output['item'])
        if not item.is_stock_item:
            frappe.throw(_('Thành phẩm mẻ phải có tồn kho.'))
        row=dict(item_code=item.name,qty=positive(output['qty']),uom=item.stock_uom,conversion_factor=1,
                 t_warehouse=warehouse,is_finished_item=1,cost_center=config.cost_center,hospitality_property=event.property)
        if item.has_batch_no:
            if not output.get('batch_no'):
                frappe.throw(_('Cần lô thành phẩm.'))
            batch=frappe.get_doc('Batch',output['batch_no'])
            if batch.item!=item.name or batch.disabled:
                frappe.throw(_('Lô thành phẩm không hợp lệ.'))
            row.update(batch_no=batch.name,use_serial_batch_fields=1)
        entry.append('items',row)
    entry.flags.fnb_service=True
    entry.flags.fnb_count=count
    entry.insert(ignore_permissions=True)
    entry.submit()
    event.stock_entry=entry.name
    save(event)
    return entry


def rows_from_doc(doc):
    return [dict(item=r.item,qty=r.stock_qty,uom=frappe.get_cached_value('Item',r.item,'stock_uom'),batch_no=r.batch_no)
            for r in doc.items]
