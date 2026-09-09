import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, flt, now_datetime
from .common import (positive, role, require_property, check_warehouse, stock_quantity,
                     business_date, save, load, approve_actor, atomic)

INTERNAL = {'FNB Inventory Event','FNB Warehouse Control'}
CONFIG = {'FNB Settings','FNB Outlet','FNB Cost Standard','FNB Recipe Version'}


class FNBBase(Document):
    def validate(self):
        prop = require_property(self.property)
        self.operating_company = prop.operating_company
        self.currency = frappe.get_cached_value('Company',prop.operating_company,'default_currency')
        old = self.get_doc_before_save()
        if old and self.doctype in ('FNB Settings', 'FNB Outlet'):
            fields = ['warehouse'] if self.doctype == 'FNB Outlet' else ['main_warehouse', 'transit_warehouse']
            if any(self.get(field) != old.get(field) for field in fields):
                frappe.throw(_('Không đổi kho đã ánh xạ; tạo cấu hình mới sau khi đối soát kho cũ.'))
        if self.doctype in INTERNAL and not self.flags.fnb_service:
            frappe.throw(_('Hồ sơ F&B nội bộ chỉ được ghi bởi dịch vụ nghiệp vụ.'))
        if old and old.property != self.property:
            frappe.throw(_('Không đổi cơ sở của hồ sơ F&B đã tạo.'))
        if not self.flags.fnb_service:
            if self.doctype in CONFIG:
                role({'FNB Cost Controller','FNB Finance Approver','System Manager'})
            if old and old.get('status') not in (None,'Draft'):
                frappe.throw(_('Chứng từ đã chuyển trạng thái; dùng thao tác nghiệp vụ hoặc tạo phiên bản mới.'))
            for name in ['status','approved_by','approved_at','snapshot','stock_entry','stock_reconciliation',
                         'counted_by','recounted_by','count_snapshot','setup_verified','import_key','import_content_hash','paused','pause_reason']:
                if self.meta.has_field(name) and self.get(name) != (old.get(name) if old else ('Draft' if name=='status' else None)):
                    # Check fields are normalized to zero by Frappe.
                    if name in ('setup_verified','paused') and not self.get(name) and not (old.get(name) if old else 0):
                        continue
                    frappe.throw(_('Trường {0} do hệ thống quản lý.').format(name))
            if self.doctype == 'FNB Settings' and bool(self.enabled) != bool(old.enabled if old else 0):
                frappe.throw(_('Dùng thao tác kích hoạt F&B sau nghiệm thu.'))
            if self.doctype == 'FNB Outlet' and old and bool(self.enabled) != bool(old.enabled):
                frappe.throw(_('Dùng thao tác kích hoạt hoặc vô hiệu hóa outlet.'))
            if self.doctype == 'FNB Settings' and old and old.enabled and not old.get('paused'):
                frappe.throw(_('Cấu hình đang hoạt động không được sửa trực tiếp.'))
            if self.doctype=='FNB Settings' and old and old.enabled and any(self.get(k)!=old.get(k) for k in ['main_warehouse','transit_warehouse','cutover_at']):
                frappe.throw(_('Không đổi kho hoặc mốc chuyển đổi của cơ sở đã hoạt động.'))
        if self.get('outlet'):
            outlet = frappe.get_doc('FNB Outlet',self.outlet)
            if outlet.property != self.property:
                frappe.throw(_('Outlet không thuộc cơ sở.'))
        if self.get('posting_datetime'):
            self.business_date = business_date(self.property,self.posting_datetime)
        for field in ['room','reservation']:
            if self.get(field):
                dt = 'Hotel Room' if field=='room' else 'Hotel Reservation'
                linked = frappe.get_doc(dt,self.get(field))
                linked.check_permission('read')
                if linked.property != self.property:
                    frappe.throw(_('Phòng/đặt phòng thuộc cơ sở khác.'))
        if self.doctype == 'FNB Settings':
            self.validate_settings()
        elif self.doctype == 'FNB Outlet':
            self.validate_outlet()
        elif self.doctype == 'FNB Recipe Version':
            self.validate_recipe()
        elif self.doctype == 'FNB Cost Standard':
            self.validate_standard()
        for field in ['items','ingredients','menu']:
            for row in (self.get(field) or []):
                if row.meta.has_field('qty'):
                    prior=next((r for r in (old.get(field) or []) if r.name==row.name),None) if old else None
                    if prior and old.get('status') not in (None,'Draft'):
                        if any(row.get(k)!=prior.get(k) for k in ['item','qty','uom']):
                            frappe.throw(_('Không thay Item/lượng/UOM của dòng đã chốt.'))
                        row.stock_qty,row.conversion_factor=prior.stock_qty,prior.conversion_factor
                    else:
                        row.stock_qty,row.conversion_factor,stock_uom = stock_quantity(row.item,row.qty,row.uom)
                if row.meta.has_field('snapshot') and not self.flags.fnb_service:
                    prior = next((r for r in old.get(field,[]) if r.name==row.name),None) if old else None
                    for key in ['snapshot','recipe','prepared_qty','served_qty','billed_qty','cancelled_qty']:
                        if row.get(key) not in (None,'',0) and row.get(key) != (prior.get(key) if prior else None):
                            frappe.throw(_('Không sửa số lượng xử lý hoặc snapshot qua bảng con.'))

    def validate_settings(self):
        for field in ['main_warehouse','transit_warehouse']:
            check_warehouse(self.get(field),self.property,self.operating_company)
        if self.main_warehouse == self.transit_warehouse:
            frappe.throw(_('Kho tổng và kho trung chuyển phải khác nhau.'))
        if frappe.db.get_value('Warehouse',self.transit_warehouse,'warehouse_type') != 'Transit':
            frappe.throw(_('Chọn kho có loại Transit.'))
        for field in ['cogs_account','staff_account','complimentary_account','waste_account','variance_account']:
            account = frappe.get_doc('Account',self.get(field))
            if account.company != self.operating_company or account.is_group or account.disabled or account.root_type != 'Expense':
                frappe.throw(_('Tài khoản chi phí F&B không hợp lệ: {0}.').format(field))
        if frappe.db.get_value('Cost Center',self.cost_center,'company') != self.operating_company:
            frappe.throw(_('Cost Center khác Company.'))
        for field in ['price_tolerance_percent','quantity_tolerance_percent']:
            positive(self.get(field),field,zero=True)

    def validate_outlet(self):
        check_warehouse(self.warehouse,self.property,self.operating_company)
        if not self.menu:
            frappe.throw(_('Cần danh mục món của outlet.'))
        if len({r.item for r in self.menu}) != len(self.menu):
            frappe.throw(_('Item trùng trong danh mục outlet.'))
        for row in self.menu:
            stock = frappe.get_cached_value('Item',row.item,'is_stock_item')
            if bool(stock) != (row.stock_mode=='Stock'):
                frappe.throw(_('Chế độ Stock phải khớp Is Stock Item; không tự đổi Item lịch sử.'))
            positive(row.par_qty,'Định mức tồn',zero=True)
        for row in self.pos_profiles:
            profile = frappe.get_doc('POS Profile',row.pos_profile)
            if profile.company != self.operating_company or profile.warehouse != self.warehouse or profile.get('hospitality_property') != self.property:
                frappe.throw(_('POS Profile phải khớp Company, Property và kho outlet.'))
            others = frappe.get_all('FNB POS Mapping',filters={'pos_profile':row.pos_profile,'parent':['!=',self.name]},pluck='parent')
            if others:
                frappe.throw(_('POS Profile đã gắn với outlet khác.'))
        old = self.get_doc_before_save()
        if old and old.enabled and not self.flags.fnb_service and (not old.get('paused') or old.warehouse!=self.warehouse or not self.enabled):
            frappe.throw(_('Outlet đang hoạt động phải ngừng nhận nghiệp vụ trước khi sửa cấu hình.'))

    def validate_recipe(self):
        positive(self.quantity,'Sản lượng')
        if self.uom != frappe.get_cached_value('Item',self.item,'stock_uom'):
            frappe.throw(_('UOM sản lượng phải là đơn vị tồn của Item đầu ra.'))
        if not self.ingredients or len({r.item for r in self.ingredients})!=len(self.ingredients):
            frappe.throw(_('Công thức cần nguyên liệu không trùng.'))
        if self.effective_to and get_datetime(self.effective_to)<=get_datetime(self.effective_from):
            frappe.throw(_('Khoảng hiệu lực không hợp lệ.'))
        if not self.is_group_template and not self.outlet:
            frappe.throw(_('Công thức địa phương cần outlet.'))
        if self.is_group_template and self.outlet:
            frappe.throw(_('Mẫu chung không gắn outlet.'))
        if any(r.item==self.item for r in self.ingredients):
            frappe.throw(_('Công thức không được tự tham chiếu.'))

    def validate_standard(self):
        if self.to_date < self.from_date or not self.prices:
            frappe.throw(_('Kỳ giá chuẩn hoặc danh sách giá không hợp lệ.'))
        if len({r.item for r in self.prices})!=len(self.prices):
            frappe.throw(_('Giá chuẩn trùng Item.'))
        for row in self.prices:
            positive(row.rate,'Giá chuẩn',zero=True)
            # TRƯỚC ĐÂY: gọi thẳng frappe.get_doc(row.source_doctype,row.source_name)
            # không kiểm tra rỗng — source_doctype/source_name khai báo reqd=1 trên
            # DocType nhưng frappe/model/document.py's insert() chạy custom validate()
            # (nơi validate_standard() này được gọi) TRƯỚC _validate_mandatory() (xác
            # nhận đọc thẳng document.py: run_before_save_methods() ở dòng trước
            # self._validate()) — nghĩa là bỏ trống 1 trong 2 trường "bắt buộc" này
            # LUÔN crash ở đây bằng lỗi kỹ thuật thô ("First non keyword argument must
            # be a string or dict") TRƯỚC KHI framework kịp báo đúng "Trường ... là bắt
            # buộc". Đã tái hiện thật khi viết test sống. Kiểm tra rõ ràng trước.
            if not row.source_doctype or not row.source_name:
                frappe.throw(_('Dòng giá chuẩn của {0} thiếu chứng từ nguồn (Source Doctype/Source Name).').format(row.item))
            frappe.get_doc(row.source_doctype,row.source_name).check_permission('read')

    def on_update(self):
        if self.doctype in {'FNB Settings','FNB Outlet'}:
            warehouses = [self.warehouse] if self.doctype=='FNB Outlet' else [self.main_warehouse,self.transit_warehouse]
            for warehouse in warehouses:
                if not frappe.db.exists('FNB Warehouse Control',warehouse):
                    save(frappe.get_doc(dict(doctype='FNB Warehouse Control',warehouse=warehouse,property=self.property)))

    def on_trash(self):
        if self.doctype in INTERNAL or self.get('status') not in (None,'Draft') or self.get('enabled'):
            frappe.throw(_('Không xóa hồ sơ F&B có lịch sử hoặc đang hoạt động.'))


@frappe.whitelist(methods=['POST'])
@atomic
def activate(property):
    role({'FNB Finance Approver','System Manager'})
    doc = load('FNB Settings',property)
    if not frappe.conf.get('fnb_release_verified'):
        frappe.throw(_('Chưa nghiệm thu F&B trên site; chưa được kích hoạt.'))
    if not doc.cutover_at or get_datetime(doc.cutover_at)>now_datetime():
        frappe.throw(_('Cần thời điểm chuyển đổi đã được xác nhận.'))
    doc.setup_verified = 1
    doc.enabled = 1
    save(doc)
    return doc.name


@frappe.whitelist(methods=['POST'])
@atomic
def set_paused(doctype,name,paused,reason):
    role({'FNB Cost Controller','FNB Finance Approver','System Manager'})
    if doctype not in ('FNB Settings','FNB Outlet') or not str(reason or '').strip():
        frappe.throw(_('Cần cấu hình F&B và lý do tạm dừng/mở lại.'))
    from frappe.utils import cint
    doc=load(doctype,name)
    if not doc.enabled:
        frappe.throw(_('Chỉ tạm dừng/mở lại cấu hình đã kích hoạt.'))
    if cint(paused):
        scope={'property':doc.property}
        if doctype=='FNB Outlet':
            scope['outlet']=doc.name
        for dt,states in [('FNB Service Ticket',['Sent','Prepared','Served']),('FNB Service Session',['Approved']),('FNB Stock Count',['Counting'])]:
            if frappe.db.exists(dt,dict(scope,status=['in',states])):
                frappe.throw(_('Cần hoàn tất nghiệp vụ đang mở trước khi sửa cấu hình F&B.'))
    else:
        from .recipes import select_recipe
        names=[doc.name] if doctype=='FNB Outlet' else frappe.get_all('FNB Outlet',filters={'property':doc.property,'enabled':1},pluck='name')
        for outlet_name in names:
            out=frappe.get_doc('FNB Outlet',outlet_name)
            out.validate_outlet()
            for row in out.menu:
                if row.stock_mode=='Recipe':
                    select_recipe(out.name,row.item,now_datetime())
    doc.paused=int(bool(cint(paused)))
    doc.pause_reason=reason
    save(doc)
    return doc.name


@frappe.whitelist(methods=['POST'])
@atomic
def deactivate(doctype,name,reason):
    # TRƯỚC ĐÂY: FNB Settings/FNB Outlet đã enabled=1 KHÔNG CÓ CÁCH NÀO tắt hẳn
    # (enabled=0) — validate() chặn cứng MỌI thay đổi enabled một khi đã bật
    # (dòng "Dùng thao tác kích hoạt F&B sau nghiệm thu."), và trước đây chỉ có
    # activate() (bật) chứ không có API đối xứng để tắt. set_paused() (mới
    # thêm gần đây, có thể do 1 tiến trình khác) chỉ tạm dừng nhận nghiệp vụ,
    # KHÔNG đổi enabled — không giải quyết được nhu cầu "ngừng vĩnh viễn 1
    # outlet/cơ sở F&B" (VD đóng cửa nhà hàng, sáp nhập 2 outlet). Đã xác nhận
    # thật: gọi save(doc) (helper luôn set flags.fnb_service=True) bỏ qua đúng
    # nhánh chặn này, nên chỉ cần 1 hàm nghiệp vụ RIÊNG, có kiểm tra an toàn
    # đầy đủ, giống hệt activate()/set_paused() đã làm.
    # Bắt buộc phải TẠM DỪNG (set_paused(paused=1)) trước — tái dùng ĐÚNG bộ
    # kiểm tra "không còn nghiệp vụ đang mở" mà set_paused() đã có, tránh
    # trùng lặp logic và tránh vô hiệu hóa đột ngột 1 outlet đang phục vụ.
    role({'FNB Finance Approver','System Manager'})
    if doctype not in ('FNB Settings','FNB Outlet') or not str(reason or '').strip():
        frappe.throw(_('Cần cấu hình F&B và lý do vô hiệu hóa.'))
    doc=load(doctype,name)
    if not doc.enabled:
        frappe.throw(_('Cấu hình chưa kích hoạt.'))
    if not doc.get('paused'):
        frappe.throw(_('Cần tạm dừng (set_paused) trước khi vô hiệu hóa vĩnh viễn.'))
    ensure_no_transit(doc)
    doc.enabled=0
    doc.paused=0
    doc.pause_reason=reason
    save(doc)
    return doc.name


def ensure_no_transit(doc):
    filters = {'docstatus': 1, 'add_to_transit': 1, 'hospitality_property': doc.property}
    if doc.doctype == 'FNB Outlet':
        filters['fnb_outlet'] = doc.name
    for name in frappe.get_all('Stock Entry', filters=filters, pluck='name'):
        entry = frappe.get_doc('Stock Entry', name, for_update=True)
        if any(float(row.transfer_qty or 0) > float(row.transferred_qty or 0) + 1e-9 for row in entry.items):
            frappe.throw(_('Còn hàng đang giao qua kho trung chuyển; nhận hết trước khi vô hiệu hóa.'))


@frappe.whitelist(methods=['POST'])
@atomic
def activate_outlet(name):
    role({'FNB Finance Approver', 'System Manager'})
    doc = load('FNB Outlet', name)
    from .common import settings
    from .recipes import select_recipe
    settings(doc.property)
    doc.validate_outlet()
    for row in doc.menu:
        if row.stock_mode == 'Recipe':
            select_recipe(doc.name, row.item, now_datetime())
    doc.enabled = 1
    doc.paused = 0
    save(doc)
    return doc.name
