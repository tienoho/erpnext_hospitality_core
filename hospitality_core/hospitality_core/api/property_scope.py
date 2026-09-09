"""Ngữ cảnh cơ sở và ràng buộc server; không lấy Company từ user default."""
from hashlib import sha256
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

SCOPED = {
    'Hotel Room', 'Hotel Room Type', 'Hotel Reception', 'Room Rate Plan', 'Hotel Reservation',
    'Guest Folio', 'Hotel Group Booking', 'Guest Balance Ledger', 'Hotel Maintenance Request',
    'Lost and Found Item', 'Hospitality Expense', 'Sales Report', 'Night Audit Log',
    'Housekeeping Room Status Log', 'Folio Transaction Move Log', 'Folio Transaction',
    'Hospitality Property Settings', 'Hospitality Channel Connection', 'Guest Interaction',
    'Guest Benefit Entitlement', 'Hospitality Charge Posting', 'Hospitality Invoice Allocation',
    'Hospitality Audit Run',
}
COMPANY_SCOPED = {'Hospitality Company Accounting Settings', 'Hospitality Loyalty Program',
                  'Guest Membership', 'Hospitality Loyalty Entry'}
# DocType lõi của Frappe/ERPNext (không phải do app này định nghĩa) — được gắn
# field `hospitality_property` (KHÁC tên `property` mà SCOPED dùng) qua
# migrations/property_v2.py (create_custom_fields trực tiếp cho Sales
# Invoice/POS Invoice/Payment Entry/Journal Entry, và Accounting Dimension
# cho GL Entry). TRƯỚC ĐÂY các doctype này hoàn toàn không nằm trong bất kỳ
# tập scoping nào — 1 user chỉ được cấp quyền Property A vẫn xem được hóa
# đơn/giao dịch kế toán của Property B qua list view/report ORM chuẩn, vì
# permission_query_conditions/has_permission chưa từng biết về field này.
# KHÔNG gộp chung xử lý với SCOPED vì các doctype này KHÔNG phải lúc nào cũng
# thuộc nghiệp vụ hospitality (VD 1 Journal Entry điều chỉnh cuối tháng không
# liên quan khách sạn, hoặc Payment Entry trả tiền nhà cung cấp) — bản ghi có
# hospitality_property RỖNG phải được coi là NGOÀI PHẠM VI hospitality, không
# được lọc/chặn (khác hẳn quy ước "property rỗng = bản ghi cũ chưa ánh xạ,
# tạm ẩn với non-manager" áp dụng cho SCOPED, vì SCOPED là doctype CỦA RIÊNG
# app này nên chắc chắn 100% thuộc hospitality).
CORE_SCOPED = {'Sales Invoice', 'POS Invoice', 'Payment Entry', 'Journal Entry', 'GL Entry'}
CORE_SCOPED_FIELD = 'hospitality_property'
INTERNAL = {'Hospitality Charge Posting', 'Hospitality Invoice Allocation', 'Hospitality Loyalty Entry',
            'Guest Benefit Entitlement', 'Guest Merge Log', 'Hospitality Audit Run'}
LINKS = {'room': 'Hotel Room', 'room_type': 'Hotel Room Type', 'hotel_reception': 'Hotel Reception',
         'rate_plan': 'Room Rate Plan', 'reservation': 'Hotel Reservation', 'folio': 'Guest Folio',
         'group_booking': 'Hotel Group Booking', 'master_folio': 'Guest Folio',
         'channel_connection': 'Hospitality Channel Connection',
         # Lost and Found Item's Link tới Hotel Room không đặt tên "room" như
         # mọi doctype khác (đặt tên "found_location" — chỗ tìm thấy đồ) nên
         # trước đây KHÔNG khớp bất kỳ key nào ở trên: doc.property không bao
         # giờ được tự suy ra từ phòng, rơi thẳng xuống resolve() không tham
         # số — hàm này CHỈ chấp nhận đúng 1 cơ sở đang "allowed" cho user
         # hiện tại (với quản trị viên, allowed_properties() trả về TẤT CẢ
         # Hospitality Property bất kể enabled) — ngay khi site có từ 2 cơ sở
         # trở lên (đúng mô hình multi-property mà Property v2 hướng tới),
         # MỌI lần tạo Lost and Found Item sẽ crash "Vui lòng chọn cơ sở;
         # không thể suy ra duy nhất một cơ sở hợp lệ." — tính năng báo cáo
         # đồ thất lạc ngừng hoạt động hoàn toàn trên site đa cơ sở.
         'found_location': 'Hotel Room',
         # CÙNG LỚP LỖI, nghiêm trọng hơn: "Folio Transaction Move Log" (do
         # folio.py's move_transactions() tạo — nền tảng dùng chung cho CẢ
         # merge_folios() LẪN execute_split_tour_folio(), tức MỌI thao tác
         # chuyển giao dịch giữa 2 folio trong toàn app) có 2 Link tới Guest
         # Folio tên "source_folio"/"target_folio" (không phải "folio"/
         # "master_folio" như các doctype khác) — cũng KHÔNG khớp key nào
         # trong LINKS trước đây, khiến property không được suy ra, và HÀM
         # NÀY SẼ CRASH ngay khi site có từ 2 cơ sở trở lên — chặn đứng TOÀN
         # BỘ tính năng gộp/tách folio trên site đa cơ sở. Thêm cả 2 field
         # (không chỉ 1) để nhân tiện được kiểm tra chéo AN TOÀN: nếu
         # source_folio/target_folio lỡ thuộc 2 cơ sở khác nhau (không nên
         # xảy ra vì merge_folios()/move_transactions() không hỗ trợ chuyển
         # xuyên cơ sở), vòng lặp LINKS sẽ tự phát hiện và throw
         # "thuộc cơ sở khác" thay vì âm thầm gán sai.
         'source_folio': 'Guest Folio', 'target_folio': 'Guest Folio'}


def key(*parts):
    return sha256('\x1f'.join(str(p or '') for p in parts).encode()).hexdigest()


def installed():
    return frappe.db.has_table('Hospitality Property')


def manager(user=None):
    user = user or frappe.session.user
    return user == 'Administrator' or 'System Manager' in frappe.get_roles(user)


def allowed_properties(user=None):
    user = user or frappe.session.user
    if not installed() or user == 'Guest':
        return []
    if manager(user):
        return frappe.get_all('Hospitality Property', pluck='name')
    return frappe.get_all('Hospitality Property Access', filters={'user': user, 'enabled': 1}, pluck='property')


def require_property(property, user=None):
    if property not in allowed_properties(user):
        frappe.throw(_('Không có quyền truy cập cơ sở {0}.').format(property), frappe.PermissionError)
    return frappe.get_cached_doc('Hospitality Property', property)


def resolve(property=None, *, linked=None, currency=None, active=False):
    if linked:
        doc = frappe.get_doc(*linked)
        doc.check_permission('read')
        if property and doc.get('property') != property:
            frappe.throw(_('Chứng từ không thuộc cơ sở đã chọn.'))
        property = doc.get('property')
    if not property:
        candidates = allowed_properties()
        if len(candidates) != 1:
            frappe.throw(_('Vui lòng chọn cơ sở; không thể suy ra duy nhất một cơ sở hợp lệ.'))
        property = candidates[0]
    prop = require_property(property)
    if active and not prop.enabled:
        frappe.throw(_('Cơ sở chưa được kích hoạt.'))
    return frappe._dict(property=prop.name, operating_company=prop.operating_company,
        currency=currency or prop.currency, base_currency=frappe.get_cached_value('Company', prop.operating_company, 'default_currency'))


def company_settings(company):
    doc = frappe.get_cached_doc('Hospitality Company Accounting Settings', company)
    if not doc.enabled:
        frappe.throw(_('Cấu hình kế toán của pháp nhân chưa được kích hoạt.'))
    return doc


def settings(doctype, property=None):
    """Duy trì Single cho giao dịch cũ; caller v2 phải truyền Property."""
    if not property:
        return frappe.get_single(doctype)
    prop = require_property(property)
    if doctype == 'Hospitality Accounting Settings':
        return company_settings(prop.operating_company)
    return frappe.get_cached_doc('Hospitality Property Settings', property)


def conditions(user=None, doctype=None):
    if not installed() or manager(user) or not frappe.db.exists('Hospitality Property', {'enabled': 1}):
        return ''
    props = allowed_properties(user)
    values = ','.join(frappe.db.escape(p) for p in props) or "''"
    if doctype in SCOPED:
        return f'`tab{doctype}`.`property` IN ({values})'
    if doctype == 'Hospitality Property':
        return f'`tabHospitality Property`.`name` IN ({values})'
    if doctype == 'Hospitality Property Access':
        return '`tabHospitality Property Access`.`user`=' + frappe.db.escape(user or frappe.session.user)
    if doctype == 'Guest Preference':
        return f"(`tabGuest Preference`.sharing_scope='Group' OR `tabGuest Preference`.property IN ({values}))"
    if doctype in COMPANY_SCOPED:
        return (f'`tab{doctype}`.operating_company IN (SELECT operating_company '
                f'FROM `tabHospitality Property` WHERE name IN ({values}))')
    if doctype in CORE_SCOPED:
        # NULL/rỗng = bản ghi ngoài phạm vi hospitality (không phải chưa ánh
        # xạ) — luôn cho qua, chỉ lọc bản ghi ĐÃ gắn hospitality_property.
        return (f'(`tab{doctype}`.`{CORE_SCOPED_FIELD}` IS NULL OR '
                f'`tab{doctype}`.`{CORE_SCOPED_FIELD}`=\'\' OR '
                f'`tab{doctype}`.`{CORE_SCOPED_FIELD}` IN ({values}))')
    return ''


def has_permission(doc, user=None, ptype=None, **kwargs):
    # Hook chỉ được phủ quyết. True tiếp tục xét DocPerm/User Permission;
    # None cũng bị Frappe coi là từ chối, không phải là "dùng quyền mặc định".
    if not installed() or manager(user) or not frappe.db.exists('Hospitality Property', {'enabled': 1}):
        return True
    if doc.doctype == 'File' and doc.attached_to_doctype and doc.attached_to_name:
        if doc.attached_to_doctype in SCOPED | COMPANY_SCOPED | CORE_SCOPED | {'Guest Preference', 'Hospitality Property'}:
            return frappe.has_permission(doc.attached_to_doctype, 'read', doc=doc.attached_to_name, user=user)
    if doc.doctype == 'Guest Preference' and doc.sharing_scope == 'Group' and ptype == 'read':
        return True
    if doc.doctype in SCOPED | {'Guest Preference', 'Hospitality Property'}:
        prop = doc.name if doc.doctype == 'Hospitality Property' else doc.get('property')
        return prop in allowed_properties(user)
    if doc.doctype in COMPANY_SCOPED:
        companies = frappe.get_all('Hospitality Property', filters={'name': ['in', allowed_properties(user)]}, pluck='operating_company')
        return doc.operating_company in companies
    if doc.doctype in CORE_SCOPED:
        prop = doc.get(CORE_SCOPED_FIELD)
        if not prop:
            # Không gắn hospitality_property = ngoài phạm vi hospitality
            # (VD Journal Entry điều chỉnh kế toán chung, Payment Entry trả
            # nhà cung cấp) — không phải "bản ghi cũ chưa ánh xạ" như SCOPED,
            # nên KHÔNG được ẩn; nhường lại cho phân quyền chuẩn của ERPNext.
            return True
        return prop in allowed_properties(user)
    return True


def _same_company(doctype, name, company):
    if name and frappe.db.get_value(doctype, name, 'company') != company:
        frappe.throw(_('{0} {1} không thuộc pháp nhân {2}.').format(doctype, name, company))


def validate_document(doc, method=None):
    if frappe.flags.in_migrate or frappe.flags.in_install or not installed():
        return
    if doc.doctype in INTERNAL and not doc.flags.hospitality_service:
        frappe.throw(_('Chứng từ được quản lý bởi dịch vụ Hospitality; không sửa trực tiếp.'))
    if doc.doctype == 'Guest':
        old = doc.get_doc_before_save()
        if not doc.flags.hospitality_service and (doc.get('merged_into') or None) != (old.get('merged_into') if old else None):
            frappe.throw(_('Dùng thao tác gộp hồ sơ để lưu nguồn và lý do.'))
    if doc.doctype == 'File' and doc.get('attached_to_doctype') in SCOPED | COMPANY_SCOPED | {'Guest Preference', 'Hospitality Property'}:
        if doc.attached_to_name:
            frappe.get_doc(doc.attached_to_doctype,doc.attached_to_name).check_permission('write')
        doc.is_private = 1
    if doc.doctype == 'File' and doc.get('attached_to_doctype') in CORE_SCOPED and doc.get('attached_to_name'):
        # CORE_SCOPED (Sales Invoice/POS Invoice/Payment Entry/Journal
        # Entry/GL Entry) dùng chung cho MỌI nghiệp vụ kế toán, không riêng
        # hospitality — KHÔNG được ép is_private vô điều kiện như với SCOPED
        # (sẽ đổi hành vi đính kèm hóa đơn/chứng từ kế toán thông thường
        # không liên quan khách sạn, VD hóa đơn nhà cung cấp). Chỉ ép
        # private + check quyền ghi trên chứng từ cha khi CHÍNH bản ghi đó
        # đã gắn hospitality_property (thực sự thuộc phạm vi hospitality).
        if frappe.db.get_value(doc.attached_to_doctype, doc.attached_to_name, CORE_SCOPED_FIELD):
            frappe.get_doc(doc.attached_to_doctype,doc.attached_to_name).check_permission('write')
            doc.is_private = 1
    if doc.doctype == 'Hospitality Property Access':
        if not manager():
            frappe.throw(_('Chỉ quản trị được cấp quyền cơ sở.'), frappe.PermissionError)
        doc.access_key = key(doc.property, doc.user)
    if doc.doctype == 'Hospitality Property':
        try:
            ZoneInfo(doc.timezone)
        except (KeyError, ValueError):
            frappe.throw(_('Timezone không hợp lệ.'))
        old = doc.get_doc_before_save()
        if old and old.operating_company != doc.operating_company:
            frappe.throw(_('Không đổi pháp nhân trên cơ sở đã tạo; cần hồ sơ vận hành mới.'))
        if not doc.flags.hospitality_service:
            doc.migration_verified = old.migration_verified if old else 0
        if doc.enabled:
            if not frappe.conf.get('hospitality_v2_release_verified'):
                frappe.throw(_('Chưa có nghiệm thu tích hợp Property v2 trên site; chưa được kích hoạt cơ sở.'))
            company_settings(doc.operating_company)
            if not doc.migration_verified or not doc.cutover_date or not frappe.db.exists('Hospitality Property Settings', doc.name):
                frappe.throw(_('Cần mapping đã kiểm tra, cấu hình cơ sở và ngày chuyển đổi trước khi kích hoạt.'))
    if doc.doctype == 'Hospitality Company Accounting Settings':
        doc.currency = frappe.get_cached_value('Company', doc.operating_company, 'default_currency')
        for f in ['receivable_account','unbilled_account','income_account','exchange_difference_account',
                  'round_off_account','loyalty_expense_account']:
            _same_company('Account',doc.get(f),doc.operating_company)
        _same_company('Cost Center',doc.cost_center,doc.operating_company)
        _same_company('Sales Taxes and Charges Template',doc.tax_template,doc.operating_company)
        if doc.unbilled_account == doc.receivable_account:
            frappe.throw(_('Tài khoản doanh thu chưa xuất hóa đơn phải khác tài khoản công nợ hóa đơn.'))
        for f in ['unbilled_account','income_account','exchange_difference_account','round_off_account','loyalty_expense_account']:
            if doc.get(f) and frappe.get_cached_value('Account',doc.get(f),'account_currency') != doc.currency:
                frappe.throw(_('Tài khoản {0} phải dùng tiền bản vị của pháp nhân.').format(f))
    if doc.doctype in {'Hospitality Loyalty Program','Guest Membership'}:
        from hospitality_core.hospitality_core.api.guest_loyalty import validate_configuration
        validate_configuration(doc)
    if doc.doctype == 'Guest Preference':
        if doc.sharing_scope == 'Property':
            require_property(doc.property)
        elif not allowed_properties():
            frappe.throw(_('Không có quyền quản lý hồ sơ khách.'), frappe.PermissionError)
    if doc.doctype not in SCOPED:
        return
    if doc.doctype == 'Folio Transaction':
        parent = frappe.get_doc('Guest Folio', doc.parent)
        for f in ['property','operating_company','currency','accounting_version']:
            doc.set(f, parent.get(f))
        if parent.get('accounting_version') == 'Property v2' and not (
                doc.flags.hospitality_service or doc.flags.from_rate_plan or doc.flags.from_folio_mirror):
            frappe.throw(_('Giao dịch v2 phải được tạo từ nghiệp vụ có chứng từ nguồn.'))
    if doc.doctype == 'Guest Folio' and not doc.is_new() and frappe.db.get_value('Guest Folio',doc.name,'accounting_version') == 'Property v2':
        stored={r.name:r for r in frappe.get_all('Folio Transaction',filters={'parent':doc.name},
            fields=['name','amount','item','is_void','reference_doctype','reference_name'])} if not doc.is_new() else {}
        if set(stored)!={r.name for r in doc.get('transactions', [])}:
            frappe.throw(_('Không thêm/xóa giao dịch v2 qua bảng con; dùng nghiệp vụ có nguồn.'))
        for row in doc.get('transactions', []):
            if any(row.get(f)!=stored[row.name].get(f) for f in ['amount','item','is_void','reference_doctype','reference_name']):
                frappe.throw(_('Không sửa giao dịch v2 trực tiếp trên Folio.'))
    for f, dt in LINKS.items():
        if doc.get(f):
            linked_property = frappe.db.get_value(dt, doc.get(f), 'property')
            if linked_property:
                if doc.get('property') and doc.property != linked_property:
                    frappe.throw(_('{0} thuộc cơ sở khác.').format(f))
                doc.property = linked_property
    if not doc.get('property'):
        # Giao dịch lịch sử chưa ánh xạ giữ nguyên đường cũ.
        if not doc.is_new() or not frappe.db.exists('Hospitality Property', {'enabled': 1}):
            return
        doc.property = resolve().property
    prop = require_property(doc.property)
    if doc.get('operating_company') and doc.operating_company != prop.operating_company:
        frappe.throw(_('Pháp nhân không khớp cơ sở.'))
    if doc.meta.has_field('operating_company'):
        doc.operating_company = prop.operating_company
    if doc.meta.has_field('currency'):
        if doc.doctype in ('Hotel Room Type', 'Room Rate Plan'):
            # 2 doctype nay la catalog/cau hinh CUA property (khong phai
            # giao dich khach co the chon tien te khac property, kieu USD
            # tren property VND) — khong co ly do nghiep vu hop le nao de
            # currency lech khoi prop.currency (rate_plan.py's snapshot_for()
            # con throw thang neu lech). Ep buoc VO DIEU KIEN giong het
            # operating_company o tren, KHONG dung "or" fallback: field
            # 'currency' la ten chuan cua Frappe, bi Document.insert()'s
            # _set_defaults() (chay TRUOC before_validate) tu dong dien tu
            # Global Defaults cua SITE khi con trong — nen field KHONG BAO
            # GIO thuc su rong luc toi day, fallback "doc.get(...) or ..."
            # (con giu ben duoi cho cac doctype giao dich) khong bao gio
            # kich hoat va co the am tham giu sai tien te (site mac dinh
            # thay vi tien te that cua property).
            doc.currency = prop.currency
        else:
            doc.currency = doc.get('currency') or prop.currency
    old = doc.get_doc_before_save()
    if old:
        for f in ['property','operating_company','currency']:
            if old.get(f) and old.get(f) != doc.get(f):
                frappe.throw(_('Không đổi {0} trên bản ghi đã gán phạm vi; hãy tạo bản ghi mới.').format(f))
    if doc.meta.has_field('accounting_version'):
        if old:
            doc.accounting_version = old.get('accounting_version') or 'Legacy'
        elif doc.doctype != 'Folio Transaction':
            doc.accounting_version = 'Property v2' if prop.enabled and prop.cutover_date and getdate(nowdate()) >= getdate(prop.cutover_date) else 'Legacy'
            if doc.get('reservation'):
                doc.accounting_version = frappe.db.get_value('Hotel Reservation',doc.reservation,'accounting_version') or 'Legacy'
        if doc.doctype == 'Hotel Reservation' and doc.is_new() and not prop.accept_new_bookings:
            frappe.throw(_('Cơ sở chưa mở nhận booking mới.'))
    if doc.meta.has_field('billing_customer') and doc.meta.get_field('company') and doc.meta.get_field('company').options == 'Customer':
        if doc.billing_customer and doc.company and doc.billing_customer != doc.company:
            frappe.throw(_('Bên thanh toán mới và trường Company cũ không khớp.'))
        doc.billing_customer = doc.billing_customer or doc.company or frappe.db.get_value('Guest',doc.get('guest'),'customer')
        if doc.doctype == 'Guest Folio' or doc.get('is_company_guest'):
            doc.company = doc.billing_customer
    if doc.doctype in {'Hotel Room','Hotel Room Type'}:
        label = 'room_number' if doc.doctype == 'Hotel Room' else 'room_type_name'
        duplicate = frappe.db.exists(doc.doctype, {'property':doc.property,label:doc.get(label),'name':['!=',doc.name or '']})
        if duplicate:
            frappe.throw(_('Số phòng/tên loại phòng đã tồn tại trong cơ sở.'))
    if doc.doctype == 'Room Rate Plan' and doc.room_type:
        room_currency = frappe.db.get_value('Hotel Room Type',doc.room_type,'currency')
        if not doc.currency:
            doc.currency = room_currency
    if doc.doctype == 'Hotel Room Type':
        seen=set()
        for rate in doc.get('currency_rates',[]):
            if rate.currency in seen or rate.default_rate < 0:
                frappe.throw(_('Giá mặc định trùng currency hoặc âm.'))
            seen.add(rate.currency)
    if doc.doctype == 'Hospitality Channel Connection':
        doc.connection_key = key(doc.provider,doc.external_property_id)
    if doc.doctype in {'Hospitality Property Settings','Hotel Room'}:
        for f,dt in [('warehouse','Warehouse'),('pos_profile','POS Profile'),('bank_account','Bank Account'),('tax_template','Sales Taxes and Charges Template')]:
            _same_company(dt,doc.get(f),prop.operating_company)


def prevent_trash(doc, method=None):
    if doc.doctype in INTERNAL or (doc.doctype == 'Guest' and frappe.db.exists('Guest Membership',{'guest':doc.name})):
        frappe.throw(_('Không xóa lịch sử Hospitality; dùng thao tác điều chỉnh có lưu vết.'))


@frappe.whitelist()
def get_properties():
    return frappe.get_all('Hospitality Property',filters={'name':['in',allowed_properties()]},
        fields=['name','property_name','operating_company','currency','enabled'])
