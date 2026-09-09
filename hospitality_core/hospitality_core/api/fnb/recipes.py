import json
import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime
from .common import load, save, approve_actor, atomic, stock_quantity, positive, outlet, digest


def select_recipe(outlet_name,item,at):
    rows=frappe.get_all('FNB Recipe Version',filters={'outlet':outlet_name,'item':item,'status':'Approved',
        'is_group_template':0,'effective_from':['<=',at]},fields=['name','effective_to'])
    rows=[r for r in rows if not r.effective_to or get_datetime(at)<get_datetime(r.effective_to)]
    if len(rows)!=1:
        frappe.throw(_('Cần đúng một công thức đã duyệt đang hiệu lực cho {0}.').format(item))
    doc=load('FNB Recipe Version',rows[0].name,'read')
    return doc,json.loads(doc.snapshot)


def expand(doc, stack=None):
    stack=list(stack or [])
    if doc.name in stack:
        frappe.throw(_('Công thức tham chiếu vòng.'))
    stack.append(doc.name)
    result={}
    for row in doc.ingredients:
        qty,conversion_factor,uom=stock_quantity(row.item,row.qty,row.uom)
        stock=frappe.get_cached_value('Item',row.item,'is_stock_item')
        if stock:
            if row.child_recipe:
                frappe.throw(_('Bán thành phẩm có tồn không được xuất lại nguyên liệu con.'))
            value=result.setdefault(row.item,dict(item=row.item,qty=0,uom=uom))
            value['qty']+=qty
        else:
            if not row.child_recipe:
                frappe.throw(_('Nguyên liệu không có tồn cần phiên bản công thức con.'))
            child=load('FNB Recipe Version',row.child_recipe,'read')
            if child.item!=row.item or child.status!='Approved' or child.outlet!=doc.outlet:
                frappe.throw(_('Công thức con phải đã duyệt, đúng Item và outlet.'))
            if child.name in stack or not child.snapshot:
                frappe.throw(_('Công thức con thiếu snapshot hoặc tham chiếu vòng.'))
            child_snapshot=json.loads(child.snapshot)
            for ingredient in child_snapshot['ingredients']:
                value=result.setdefault(ingredient['item'],dict(item=ingredient['item'],qty=0,uom=ingredient['uom']))
                value['qty']+=ingredient['qty']*qty/child_snapshot['quantity']
    return dict(recipe=doc.name,item=doc.item,quantity=flt(doc.quantity),uom=doc.uom,
                ingredients=list(result.values()),version='FNB v1')


@frappe.whitelist(methods=['POST'])
@atomic
def approve_recipe(name):
    doc=load('FNB Recipe Version',name)
    if doc.status=='Approved':
        return doc.name
    if doc.status!='Draft':
        frappe.throw(_('Chỉ duyệt công thức nháp.'))
    approve_actor(doc)
    doc.validate()
    # Khóa outlet làm mutex cho cả hai bản mới chưa có dòng để khóa.
    previous=None
    if doc.outlet:
        out,config=outlet(doc.outlet,active=False)
        if doc.get('supersedes'):
            previous=load('FNB Recipe Version',doc.supersedes)
            if previous.status!='Approved' or previous.outlet!=doc.outlet or previous.item!=doc.item:
                frappe.throw(_('Phiên bản thay thế phải đúng Item/outlet và đã duyệt.'))
            at=get_datetime(doc.effective_from)
            if at<=now_datetime() or at<=get_datetime(previous.effective_from) or (previous.effective_to and at>=get_datetime(previous.effective_to)):
                frappe.throw(_('Phiên bản kế tiếp phải bắt đầu trong tương lai, bên trong hiệu lực bản được thay thế.'))
        for other in frappe.get_all('FNB Recipe Version',filters={'outlet':doc.outlet,'item':doc.item,'status':'Approved'},fields=['name','effective_from','effective_to']):
            if previous and other.name==previous.name:
                continue
            if (not doc.effective_to or get_datetime(other.effective_from)<get_datetime(doc.effective_to)) and (not other.effective_to or get_datetime(doc.effective_from)<get_datetime(other.effective_to)):
                frappe.throw(_('Công thức trùng khoảng hiệu lực.'))
    snapshot=expand(doc)
    if not doc.is_group_template:
        bom=frappe.get_doc(dict(doctype='BOM',item=doc.item,quantity=doc.quantity,uom=doc.uom,
            company=doc.operating_company,currency=doc.currency,is_active=1,is_default=0,
            hospitality_property=doc.property,fnb_outlet=doc.outlet,
            items=[dict(item_code=r['item'],qty=r['qty'],uom=r['uom'],conversion_factor=1) for r in snapshot['ingredients']]))
        bom.flags.fnb_service=True
        bom.insert(ignore_permissions=True)
        bom.submit()
        doc.bom=bom.name
    doc.snapshot=frappe.as_json(snapshot)
    doc.status='Approved'
    doc.approved_by=frappe.session.user
    doc.approved_at=now_datetime()
    if previous:
        previous.effective_to=doc.effective_from
        save(previous)
    save(doc)
    return doc.name


@frappe.whitelist(methods=['POST'])
@atomic
def create_successor(name,effective_from):
    source=load('FNB Recipe Version',name,'read')
    from .common import role
    role({'FNB Cost Controller','FNB Finance Approver','System Manager'})
    if source.status!='Approved' or source.is_group_template or get_datetime(effective_from)<=now_datetime():
        frappe.throw(_('Chọn công thức địa phương đã duyệt và ngày hiệu lực trong tương lai.'))
    # Bản nháp có thể chỉnh; duyệt mới kết thúc hiệu lực bản gốc trong cùng transaction.
    doc=frappe.get_doc(dict(doctype='FNB Recipe Version',property=source.property,outlet=source.outlet,
        item=source.item,quantity=source.quantity,uom=source.uom,effective_from=effective_from,supersedes=source.name,
        ingredients=[dict(item=r['item'],qty=r['qty'],uom=r['uom']) for r in json.loads(source.snapshot)['ingredients']]))
    doc.insert()
    return doc.name


def ingredients(snapshot, quantity):
    positive(quantity)
    return [dict(item=r['item'],qty=r['qty']*quantity/snapshot['quantity'],uom=r['uom']) for r in snapshot['ingredients']]


@frappe.whitelist(methods=['POST'])
@atomic
def import_recipe(source_doctype, source_name, outlet_name, effective_from):
    if source_doctype not in ('Item Recipe','FNB Recipe Version'):
        frappe.throw(_('Nguồn phải là công thức cũ hoặc mẫu đã duyệt.'))
    out,cfg=outlet(outlet_name,active=False)
    source=frappe.get_doc(source_doctype,source_name)
    source.check_permission('read')
    if source_doctype=='FNB Recipe Version':
        if source.status!='Approved' or not source.is_group_template:
            frappe.throw(_('Chỉ sao chép mẫu chung đã duyệt.'))
        snapshot=json.loads(source.snapshot)
        rows=[dict(item=r['item'],qty=r['qty'],uom=r['uom']) for r in snapshot['ingredients']]
    else:
        rows=[dict(item=r.ingredient_item,qty=r.qty,uom=r.uom) for r in source.ingredients]
    import_key=digest([source_doctype,source.name,out.name,str(get_datetime(effective_from))])
    content_hash=digest(dict(item=source.item,quantity=source.quantity,uom=source.uom,ingredients=rows))
    previous=frappe.db.get_value('FNB Recipe Version',{'import_key':import_key},['name','import_content_hash'],as_dict=True)
    if previous:
        if previous.import_content_hash!=content_hash:
            frappe.throw(_('Nguồn công thức đã thay đổi; cần nhập thành phiên bản có thời điểm hiệu lực mới.'))
        return previous.name
    doc=frappe.get_doc(dict(doctype='FNB Recipe Version',property=out.property,outlet=out.name,
        template=source.name if source_doctype=='FNB Recipe Version' else None,item=source.item,
        quantity=source.quantity,uom=source.uom,effective_from=effective_from,ingredients=rows,
        import_key=import_key,import_content_hash=content_hash))
    doc.flags.fnb_service=True
    from .common import role
    role({'FNB Cost Controller','FNB Finance Approver','System Manager'})
    doc.insert()
    return doc.name
