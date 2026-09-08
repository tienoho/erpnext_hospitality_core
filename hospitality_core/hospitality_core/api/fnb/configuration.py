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
                         'counted_by','recounted_by','count_snapshot','setup_verified','import_key','import_content_hash']:
                if self.meta.has_field(name) and self.get(name) != (old.get(name) if old else ('Draft' if name=='status' else None)):
                    # Check fields are normalized to zero by Frappe.
                    if name == 'setup_verified' and not self.get(name):
                        continue
                    frappe.throw(_('Trường {0} do hệ thống quản lý.').format(name))
            if self.doctype == 'FNB Settings' and bool(self.enabled) != bool(old.enabled if old else 0):
                frappe.throw(_('Dùng thao tác kích hoạt F&B sau nghiệm thu.'))
            if self.doctype == 'FNB Settings' and old and old.enabled:
                frappe.throw(_('Cấu hình đang hoạt động không được sửa trực tiếp.'))
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
        if old and old.enabled and (old.warehouse!=self.warehouse or old.as_json()!=self.as_json()) and not self.flags.fnb_service:
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
