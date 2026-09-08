"""Wizard mapping có dry run; không suy đoán pháp nhân từ mặc định người chạy."""
import frappe
from frappe import _
from hospitality_core.hospitality_core.api.property_scope import manager, SCOPED, LINKS


def _admin():
    if not manager():
        frappe.throw(_('Chỉ quản trị được chuyển dữ liệu cơ sở.'),frappe.PermissionError)


@frappe.whitelist()
def inspect_mapping(property, mapping):
    _admin()
    prop=frappe.get_doc('Hospitality Property',property)
    mapping=frappe.parse_json(mapping)
    if not isinstance(mapping,dict):
        frappe.throw(_('Mapping phải là bảng DocType và danh sách mã bản ghi.'))
    errors=[]; rows=[]
    for dt,names in mapping.items():
        if dt not in SCOPED or not isinstance(names,list):
            frappe.throw(_('DocType hoặc danh sách mapping không hợp lệ.'))
        for name in names:
            d=frappe.get_doc(dt,name)
            if d.get('property') and d.property!=property:
                errors.append(f'{dt} {name}: đã thuộc cơ sở khác')
            if d.get('operating_company') and d.operating_company!=prop.operating_company:
                errors.append(f'{dt} {name}: pháp nhân khác')
            if d.get('currency') and d.currency!=prop.currency:
                errors.append(f'{dt} {name}: tiền tệ khác')
            if dt=='Hotel Room' and d.warehouse and frappe.db.get_value('Warehouse',d.warehouse,'company')!=prop.operating_company:
                errors.append(f'{dt} {name}: kho thuộc pháp nhân khác')
            # TRƯỚC ĐÂY: chỉ check bản ghi TỰ NÓ đã có property/company/currency
            # khác chưa — không check các bản ghi NÓ LIÊN KẾT TỚI (VD map 1
            # Hotel Reservation vào Property X trong khi chính Hotel Room mà nó
            # tham chiếu đã được map vào Property Y trước đó, do người khác
            # hoặc 1 phiên mapping khác chạy song song). verify_property() có
            # check đúng việc này nhưng chạy TÁCH RỜI, SAU khi apply_mapping()
            # đã ghi xong — admin dễ quên chạy, để lại dữ liệu liên kết lệch
            # property mà không ai phát hiện ngay. Kiểm tra sớm ngay tại đây
            # (dùng lại đúng LINKS mà verify_property() dùng) để chặn NGAY LÚC
            # MAPPING, không đợi tới bước xác minh riêng sau đó.
            for f, target_dt in LINKS.items():
                linked_name = d.get(f)
                if not linked_name:
                    continue
                linked_property = frappe.db.get_value(target_dt, linked_name, 'property')
                if linked_property and linked_property != property:
                    errors.append(f'{dt} {name}: liên kết {f}={linked_name} đã thuộc cơ sở khác ({linked_property})')
            rows.append(dict(doctype=dt,name=name,balance=d.get('outstanding_balance')))
    return dict(property=property,company=prop.operating_company,currency=prop.currency,rows=rows,errors=errors)


@frappe.whitelist(methods=['POST'])
def apply_mapping(property, mapping, confirmed_currency):
    _admin()
    # Khóa mutex đặt tên (MySQL GET_LOCK) theo property — TRƯỚC ĐÂY 2 admin
    # (hoặc 2 tab của cùng 1 admin) chạy apply_mapping() gần như đồng thời
    # đều đọc inspect_mapping() ở trạng thái CŨ trước khi bên kia kịp ghi,
    # nên cả 2 có thể cùng vượt qua kiểm tra rồi ghi chồng lên nhau. Khóa
    # toàn bộ thao tác ghi theo TỪNG PROPERTY để tuần tự hóa (không khóa được
    # theo từng bản ghi vì 1 lần mapping có thể gồm nhiều DocType/bản ghi
    # khác nhau) — kết hợp với việc apply_mapping() luôn tự gọi lại
    # inspect_mapping() (đọc dữ liệu MỚI NHẤT) ngay trước khi ghi, 1 phiên
    # mapping của property KHÁC vô tình chạm cùng bản ghi cũng sẽ bị chặn
    # ngay ở bước kiểm tra liên kết, không chỉ ở lần verify_property() sau.
    lock_key = f"property_mapping:{property}"
    got_lock = frappe.db.sql("SELECT GET_LOCK(%s, 10)", lock_key)[0][0]
    if not got_lock:
        frappe.throw(_('Đang có một phiên mapping khác chạy cho cơ sở này; vui lòng thử lại sau.'))
    try:
        report=inspect_mapping(property,mapping)
        if report['errors']:
            frappe.throw('\n'.join(report['errors']))
        if confirmed_currency!=report['currency']:
            frappe.throw(_('Cần xác nhận tiền tệ của số liệu lịch sử; không thực hiện quy đổi trong mapping.'))
        for row in report['rows']:
            frappe.db.set_value(row['doctype'],row['name'],{
                'property':property,'operating_company':report['company'],'currency':confirmed_currency},update_modified=False)
            if row['doctype']=='Guest Folio':
                frappe.db.sql('''UPDATE `tabFolio Transaction` SET property=%s,operating_company=%s,currency=%s
                    WHERE parent=%s''',(property,report['company'],confirmed_currency,row['name']))
            if row['doctype']=='Hotel Room Type':
                room=frappe.get_doc('Hotel Room Type',row['name'])
                if not any(r.currency==confirmed_currency for r in room.currency_rates):
                    room.append('currency_rates',dict(currency=confirmed_currency,default_rate=room.default_rate))
                    room.save(ignore_permissions=True)
        return report
    finally:
        frappe.db.sql("SELECT RELEASE_LOCK(%s)", lock_key)


@frappe.whitelist(methods=['POST'])
def copy_legacy_settings(property):
    _admin()
    prop=frappe.get_doc('Hospitality Property',property)
    if frappe.db.exists('Hospitality Property Settings',property):
        return property
    dest=frappe.new_doc('Hospitality Property Settings')
    dest.property=property
    for source in ['Hospitality Accounting Settings','Hospitality Surcharge Settings','Hospitality Police Settings']:
        old=frappe.get_single(source)
        for f in dest.meta.fields:
            if old.meta.has_field(f.fieldname) and f.fieldname not in ['property','operating_company','currency']:
                if f.fieldtype=='Password':
                    value=old.get_password(f.fieldname,raise_exception=False)
                else:
                    value=old.get(f.fieldname)
                dest.set(f.fieldname,value)
    dest.insert(ignore_permissions=True)
    return dest.name


@frappe.whitelist(methods=['POST'])
def verify_property(property):
    _admin()
    from hospitality_core.hospitality_core.api.property_scope import LINKS, company_settings
    prop=frappe.get_doc('Hospitality Property',property)
    company_settings(prop.operating_company)
    errors=[]
    for dt in ['Hotel Room','Hotel Room Type','Room Rate Plan','Hotel Reservation','Guest Folio']:
        for name in frappe.get_all(dt,filters={'property':property},pluck='name'):
            doc=frappe.get_doc(dt,name)
            for f,target in LINKS.items():
                if doc.get(f) and frappe.db.get_value(target,doc.get(f),'property')!=property:
                    errors.append(f'{dt} {name}: {f} chưa ánh xạ cùng cơ sở')
    if errors:
        frappe.throw('\n'.join(errors))
    prop.flags.hospitality_service=True
    prop.migration_verified=1
    prop.save(ignore_permissions=True)
    return dict(property=property,verified=True)
