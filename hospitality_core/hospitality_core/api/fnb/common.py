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


def parse_payload(value, expected=dict, empty=None, label='Dữ liệu'):
    """frappe.parse_json() ném lỗi decode thô (không phải frappe.throw()) nếu
    chuỗi JSON từ client (POS/kitchen-display) không hợp lệ — bọc lại thành
    thông báo rõ ràng, và ép đúng kiểu mong đợi (dict/list) thay vì để code
    gọi sau đó tự crash bằng TypeError/KeyError khi cố index/iterate sai kiểu."""
    if value is None or value == '':
        return empty() if callable(empty) else empty
    try:
        parsed = frappe.parse_json(value) if isinstance(value, str) else value
    except Exception:
        frappe.throw(_('{0} không đúng định dạng JSON.').format(label))
    if not isinstance(parsed, expected):
        frappe.throw(_('{0} không đúng định dạng mong đợi.').format(label))
    return parsed


def positive(value, label='Số lượng', zero=False):
    number = flt(value)
    if not isfinite(number) or number < 0 or (not zero and number == 0):
        frappe.throw(_('{0} phải hữu hạn và {1}.').format(label, 'không âm' if zero else 'dương'))
    return number


def atomic(fn):
    # TRƯỚC ĐÂY: chỉ savepoint 1 lần + rollback(save_point=...) khi lỗi —
    # xác nhận THẬT qua 2 lần test đua THẬT trên Docker (2 tiến trình cùng
    # approve_recipe()/start_count() cho cùng outlet/kho, outlet() dùng FOR
    # UPDATE làm mutex nhân tạo): nhánh THUA CUỘC đôi lúc nhận
    # `OperationalError: SAVEPOINT ... does not exist`, đôi lúc nhận thẳng
    # `frappe.QueryDeadlockError` ("Deadlock found when trying to get lock")
    # — XÁC NHẬN đây là CÙNG 1 hiện tượng: MySQL/InnoDB tự phát hiện deadlock
    # thật giữa 2 giao dịch (mutex outlet()'s FOR UPDATE làm giảm nhưng
    # KHÔNG loại trừ hoàn toàn khả năng deadlock chu trình, có thể do cùng
    # lúc tranh chấp thêm 1 tài nguyên khác — VD dòng Series đặt tên BOM/
    # FNB Warehouse Control) và tự ROLLBACK TOÀN BỘ giao dịch của "nạn nhân"
    # để giải phóng — hủy luôn savepoint đang giữ, khiến rollback(save_point=)
    # sau đó thất bại nếu code chưa kịp thấy lỗi deadlock ở đúng câu lệnh gây
    # ra nó. Hậu quả: người dùng/hỗ trợ thấy lỗi kỹ thuật khó hiểu thay vì
    # thông báo nghiệp vụ rõ ràng ("Công thức trùng khoảng hiệu lực."/"Kho
    # ... đang kiểm kê."), hoặc tệ hơn là mất hẳn thao tác đáng lẽ RETRY được
    # (deadlock là hiện tượng THOÁNG QUA dưới tải đồng thời — cách xử lý
    # ĐÚNG chuẩn, khớp đúng lý do frappe.QueryDeadlockError tồn tại như 1
    # loại exception RIÊNG trong core, là tự động thử lại toàn bộ thao tác
    # từ đầu, không phải coi là lỗi nghiệp vụ vĩnh viễn). Đã sửa: bắt riêng
    # frappe.QueryDeadlockError, tự rollback sạch rồi THỬ LẠI toàn bộ hàm
    # (tối đa 3 lần, savepoint mới mỗi lần) — sau khi rollback đầy đủ, lần
    # thử lại sẽ thấy đúng trạng thái mới nhất (kể cả bản ghi 'Approved' của
    # nhánh thắng vừa commit) nên tự nhiên rơi về đúng lỗi nghiệp vụ nếu vẫn
    # xung đột thật, không phải retry vô nghĩa. Với lỗi KHÁC (nghiệp vụ), vẫn
    # dự phòng rollback toàn phần nếu rollback(save_point=) tự nó lỗi, rồi
    # ném lại đúng lỗi gốc.
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        for attempt in range(3):
            point = 'fnb_' + frappe.generate_hash(length=12)
            frappe.db.savepoint(point)
            try:
                return fn(*args, **kwargs)
            except frappe.QueryDeadlockError:
                try:
                    frappe.db.rollback(save_point=point)
                except Exception:
                    frappe.db.rollback()
                if attempt == 2:
                    raise
            except Exception:
                try:
                    frappe.db.rollback(save_point=point)
                except Exception:
                    frappe.db.rollback()
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


def settings(property, active=True, allow_paused=False):
    require_property(property)
    doc = frappe.get_doc('FNB Settings', property)
    if active and not doc.enabled:
        frappe.throw(_('F&B chưa được kích hoạt tại cơ sở.'))
    if active and doc.get('paused') and not allow_paused:
        frappe.throw(_('F&B đang tạm dừng tại cơ sở; cần mở lại trước khi ghi nghiệp vụ.'))
    return doc


def outlet(name, active=True, allow_paused=False):
    # LƯU Ý HIỆU NĂNG (ĐÃ CÂN NHẮC, KHÔNG SỬA): load() luôn khóa FOR UPDATE
    # bất kể permission='read' — outlet() được gọi ở HẦU HẾT mọi thao tác bếp/
    # POS/kho của module F&B, khóa dòng FNB Outlet suốt cả transaction khiến
    # MỌI thao tác cùng 1 outlet bị tuần tự hóa, kể cả dòng/vé/kho khác nhau —
    # rủi ro thật "Lock wait timeout" dưới tải đồng thời ở outlet đông khách.
    # ĐÃ THỬ bỏ khóa riêng cho lệnh gọi này (rà toàn bộ module xác nhận `out`
    # không bị sửa/save lại ở các luồng bếp/POS thông thường) nhưng phát hiện
    # `recipes.py`'s `approve_recipe()` (dòng ~58, tự comment "Khóa outlet làm
    # mutex cho cả hai bản mới chưa có dòng để khóa") CHỦ ĐÍCH dựa vào ĐÚNG
    # khóa này để chặn 2 lần duyệt công thức trùng khoảng hiệu lực chạy đồng
    # thời — bỏ khóa ở outlet() sẽ âm thầm mở lại race đó. Không tự tách
    # riêng an toàn được nếu không có site thật để kiểm thử tải đồng thời;
    # để nguyên, chỉ ghi chú rõ đây là điểm cần benchmark/thiết kế lại (VD:
    # tách khóa mutex-cho-duyệt-công-thức thành cơ chế riêng, không mượn khóa
    # outlet()) trước khi đưa module vào vận hành thật với nhiều outlet đông
    # khách đồng thời.
    doc = load('FNB Outlet', name, 'read')
    if active and not doc.enabled:
        frappe.throw(_('Outlet chưa được kích hoạt.'))
    if active and doc.get('paused') and not allow_paused:
        frappe.throw(_('Outlet F&B đang tạm dừng.'))
    return doc, settings(doc.property, active, allow_paused=allow_paused)


def _zoneinfo(tz_name, property):
    """ZoneInfo() ném ZoneInfoNotFoundError (không phải frappe.throw) nếu chuỗi
    timezone rỗng/sai định dạng — dữ liệu cấu hình (Hospitality Property), không
    phải input người dùng, nhưng 1 property cấu hình sai sẽ làm MỌI giao dịch
    F&B của property đó crash bằng traceback thô thay vì thông báo rõ ràng."""
    try:
        return ZoneInfo(tz_name)
    except Exception:
        frappe.throw(_('Cơ sở {0} có Timezone cấu hình không hợp lệ ({1}); cần sửa trước khi ghi giao dịch F&B.').format(property, tz_name))


def business_date(property, at):
    prop = require_property(property)
    # Datetime Frappe lưu theo timezone của site, không phải UTC.
    from frappe.utils import get_system_timezone
    instant = get_datetime(at).replace(tzinfo=_zoneinfo(get_system_timezone(), property)).astimezone(_zoneinfo(prop.timezone, property))
    cutoff = str(prop.business_day_start or '00:00:00')
    h, m, s = [int(float(v)) for v in cutoff.split(':')]
    return (instant - timedelta(hours=h, minutes=m, seconds=s)).date()


def business_boundary(property, day):
    """Đầu ngày kinh doanh, đổi về Datetime theo timezone site."""
    from frappe.utils import get_system_timezone, getdate
    prop=require_property(property)
    h,m,s=[int(float(v)) for v in str(prop.business_day_start or '00:00:00').split(':')]
    local=datetime.combine(getdate(day),time(h,m,s),tzinfo=_zoneinfo(prop.timezone, property))
    return local.astimezone(_zoneinfo(get_system_timezone(), property)).replace(tzinfo=None)


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
