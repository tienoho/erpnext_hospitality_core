import functools
import hashlib
import json
from contextlib import contextmanager
from datetime import timedelta, datetime, time
from math import isfinite
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime
from hospitality_core.hospitality_core.api.property_scope import require_property

POLICY = 'FNB v1'
APPROVERS = {'FNB Supervisor', 'FNB Cost Controller', 'FNB Finance Approver', 'System Manager'}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()


def positive(value, label='Số lượng', zero=False):
    number = flt(value)
    if not isfinite(number) or number < 0 or (not zero and number == 0):
        frappe.throw(_('{0} phải hữu hạn và {1}.').format(label, 'không âm' if zero else 'dương'))
    return number


def atomic(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        point = 'fnb_' + frappe.generate_hash(length=12)
        frappe.db.savepoint(point)
        try:
            return fn(*args, **kwargs)
        except Exception:
            frappe.db.rollback(save_point=point)
            raise
    return wrapped


def role(roles=APPROVERS):
    if frappe.session.user != 'Administrator' and not set(frappe.get_roles()).intersection(roles):
        frappe.throw(_('Không có vai trò thực hiện nghiệp vụ F&B này.'), frappe.PermissionError)


def approve_actor(doc):
    role()
    if doc.owner == frappe.session.user:
        frappe.throw(_('Người lập không được tự duyệt chứng từ F&B.'))


def load(dt, name, permission='write'):
    doc = frappe.get_doc(dt, name, for_update=True)
    doc.check_permission(permission)
    require_property(doc.property)
    return doc


def settings(property, active=True):
    require_property(property)
    doc = frappe.get_doc('FNB Settings', property)
    if active and not doc.enabled:
        frappe.throw(_('F&B chưa được kích hoạt tại cơ sở.'))
    return doc


def outlet(name, active=True):
    doc = load('FNB Outlet', name, 'read')
    if active and not doc.enabled:
        frappe.throw(_('Outlet chưa được kích hoạt.'))
    return doc, settings(doc.property, active)


def business_date(property, at):
    prop = require_property(property)
    # Datetime Frappe lưu theo timezone của site, không phải UTC.
    from frappe.utils import get_system_timezone
    instant = get_datetime(at).replace(tzinfo=ZoneInfo(get_system_timezone())).astimezone(ZoneInfo(prop.timezone))
    cutoff = str(prop.business_day_start or '00:00:00')
    h, m, s = [int(float(v)) for v in cutoff.split(':')]
    return (instant - timedelta(hours=h, minutes=m, seconds=s)).date()


def business_boundary(property, day):
    """Đầu ngày kinh doanh, đổi về Datetime theo timezone site."""
    from frappe.utils import get_system_timezone, getdate
    prop=require_property(property)
    h,m,s=[int(float(v)) for v in str(prop.business_day_start or '00:00:00').split(':')]
    local=datetime.combine(getdate(day),time(h,m,s),tzinfo=ZoneInfo(prop.timezone))
    return local.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


def save(doc):
    doc.flags.fnb_service = True
    if doc.is_new():
        return doc.insert(ignore_permissions=True)
    return doc.save(ignore_permissions=True)


def stock_quantity(item, qty, uom):
    value = positive(qty)
    item_doc = frappe.get_cached_doc('Item', item)
    if item_doc.disabled:
        frappe.throw(_('Item đã ngừng sử dụng.'))
    factor = 1 if uom == item_doc.stock_uom else frappe.db.get_value('UOM Conversion Detail',
        {'parent':item,'parenttype':'Item','uom':uom},'conversion_factor')
    factor = positive(factor, 'Hệ số quy đổi')
    return value * factor, factor, item_doc.stock_uom


def check_warehouse(name, property, company):
    wh = frappe.get_doc('Warehouse', name)
    wh.check_permission('read')
    if wh.is_group or wh.disabled or wh.company != company:
        frappe.throw(_('Kho phải hoạt động, là kho chi tiết và thuộc đúng Company.'))
    mapping = frappe.db.get_value('FNB Warehouse Control', name, 'property')
    if mapping and mapping != property:
        frappe.throw(_('Kho đã thuộc cơ sở F&B khác.'))
    return wh


def event_existing(doc, action, request_id, payload):
    if not isinstance(request_id,str) or not request_id.strip() or len(request_id)>140:
        frappe.throw(_('Cần khóa chống trùng tối đa 140 ký tự.'))
    source_key = digest([doc.doctype,doc.name,action,request_id])
    payload_hash = digest(payload)
    existing = frappe.db.get_value('FNB Inventory Event', {'source_key':source_key}, ['name','payload_hash'], as_dict=True)
    if existing:
        if existing.payload_hash != payload_hash:
            frappe.throw(_('Khóa chống trùng đã được dùng với nội dung khác.'))
        return frappe.get_doc('FNB Inventory Event',existing.name), source_key, payload_hash
    return None, source_key, payload_hash


def make_event(doc, action, source_key, payload_hash, **values):
    at = values.pop('posting_datetime',None) or doc.get('posting_datetime') or now_datetime()
    property = doc.get('property') or doc.get('hospitality_property')
    company = require_property(property).operating_company
    return save(frappe.get_doc(dict(doctype='FNB Inventory Event',property=property,
        operating_company=company,currency=frappe.get_cached_value('Company',company,'default_currency'),outlet=doc.get('outlet') or doc.get('fnb_outlet'),
        source_doctype=doc.doctype,source_name=doc.name,source_key=source_key,payload_hash=payload_hash,
        event_type=action,posting_datetime=at,business_date=business_date(property,at),
        policy_version=POLICY,**values)))
