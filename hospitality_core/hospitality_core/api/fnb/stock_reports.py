"""Bảo vệ báo cáo SLE chuẩn, kể cả export và kết quả Prepared Report cũ."""
import frappe
from frappe import _
from frappe.core.doctype.report.report import Report


def validate_scope(report_name,filters=None,user=None):
    from hospitality_core.hospitality_core.api.property_scope import manager,allowed_properties
    if manager(user) or not frappe.db.has_table('FNB Warehouse Control'):
        return
    report=frappe.get_doc('Report',report_name)
    if report.report_type=='Custom Report' and report.reference_report:
        return validate_scope(report.reference_report,filters,user)
    if report.ref_doctype!='Stock Ledger Entry' and report.module!='Stock':
        return
    filters=frappe.parse_json(filters) if isinstance(filters,str) else (filters or {})
    if not isinstance(filters,dict):
        frappe.throw(_('Bộ lọc báo cáo kho không hợp lệ.'))
    allowed=set(allowed_properties(user))
    company=filters.get('company')
    mappings=frappe.get_all('FNB Warehouse Control',fields=['warehouse','property','operating_company'])
    # Only audited reports have the established warehouse/company filter contract.
    # Other Stock reports may ignore these keys; never let a fabricated filter
    # grant access to an aggregate that includes unpermitted warehouses.
    trusted_filters = report.name in ('Stock Balance', 'Stock Ledger', 'Stock Projected Qty')
    if not trusted_filters:
        company = None
    selected=filters.get('warehouse') if trusted_filters else None
    selected=frappe.parse_json(selected) if isinstance(selected,str) and selected.startswith('[') else selected
    selected=[selected] if isinstance(selected,str) else (selected or [])
    covered=set()
    for name in selected:
        wh=frappe.get_doc('Warehouse',name)
        if not frappe.has_permission('Warehouse', 'read', doc=wh, user=user):
            frappe.throw(_('Không có quyền đọc kho báo cáo.'), frappe.PermissionError)
        if company and wh.company!=company:
            frappe.throw(_('Kho không thuộc Company báo cáo.'))
        covered.update(frappe.get_all('Warehouse',filters={'lft':['>=',wh.lft],'rgt':['<=',wh.rgt]},pluck='name'))
    for mapping in mappings:
        if company and mapping.operating_company!=company:
            continue
        if selected and mapping.warehouse not in covered:
            continue
        if mapping.property not in allowed:
            frappe.throw(_('Báo cáo chứa kho ngoài quyền cơ sở. Chọn kho được cấp quyền trước khi xem hoặc xuất.'),frappe.PermissionError)
    prepared=filters.get('prepared_report_name')
    if prepared:
        doc=frappe.get_doc('Prepared Report',prepared)
        doc.check_permission('read')
        source_filters=frappe.parse_json(doc.filters or '{}')
        source_filters.pop('prepared_report_name',None)
        validate_scope(doc.report_name,source_filters,user)


class ScopedStockReport(Report):
    def execute_script_report(self,filters):
        validate_scope(self.name,filters)
        return super().execute_script_report(filters)

    def execute_query_report(self,filters):
        validate_scope(self.name,filters)
        return super().execute_query_report(filters)


def before_request():
    form=frappe.local.form_dict or {}
    command=form.get('cmd') or (frappe.request.path.rsplit('/',1)[-1] if frappe.request else '')
    if command not in ('frappe.desk.query_report.run','frappe.desk.query_report.export_query'):
        return
    if form.get('report_name'):
        validate_scope(form.report_name,form.get('filters'))


def prepared_permission(doc,user=None,ptype=None,**kwargs):
    try:
        filters=frappe.parse_json(doc.filters or '{}')
        filters.pop('prepared_report_name',None)
        validate_scope(doc.report_name,filters,user)
        return True
    except frappe.PermissionError:
        return False


def file_permission(doc,user=None,ptype=None,**kwargs):
    from hospitality_core.hospitality_core.api.property_scope import has_permission
    from .guards import STOCK_READ
    if not has_permission(doc,user=user,ptype=ptype,**kwargs):
        return False
    if doc.attached_to_doctype=='Prepared Report' and doc.attached_to_name:
        return frappe.has_permission('Prepared Report','read',doc=doc.attached_to_name,user=user)
    if doc.attached_to_doctype in STOCK_READ and doc.attached_to_name:
        return frappe.has_permission(doc.attached_to_doctype, 'read', doc=doc.attached_to_name, user=user)
    return True
