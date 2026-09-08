"""Schema bổ sung, không tự ánh xạ kho hoặc bật vận hành F&B."""
import frappe

NATIVE = ['Material Request','Purchase Order','Purchase Receipt','Purchase Invoice','Stock Entry',
          'Stock Reconciliation','Delivery Note','BOM','Warehouse']


def execute():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    for role in ['FNB Operator','FNB Storekeeper','FNB Supervisor','FNB Cost Controller','FNB Finance Approver']:
        if not frappe.db.exists('Role',role):
            frappe.get_doc(dict(doctype='Role',role_name=role,desk_access=1)).insert(ignore_permissions=True)
    profiles={
        'FNB Kitchen':['FNB Operator','Stock User'],
        'FNB Stores':['FNB Storekeeper','Stock User'],
        'FNB Supervision':['FNB Supervisor','Stock User','Sales User'],
        'FNB Cashier':['FNB Operator','Stock User','Accounts User'],
        'FNB Cost Control':['FNB Cost Controller','Stock Manager','Accounts User'],
        'FNB Finance':['FNB Finance Approver','Stock Manager','Accounts Manager'],
    }
    for name,roles in profiles.items():
        if not frappe.db.exists('Role Profile',name):
            frappe.get_doc(dict(doctype='Role Profile',role_profile=name,roles=[dict(role=r) for r in roles])).insert(ignore_permissions=True)
    fields = {}
    for dt in NATIVE + ['POS Invoice','Sales Invoice']:
        fields[dt] = [dict(fieldname='fnb_outlet',label='F&B Outlet',fieldtype='Link',options='FNB Outlet'),
            dict(fieldname='fnb_version',label='F&B Policy Version',fieldtype='Data',read_only=1,no_copy=1),
            dict(fieldname='fnb_source_event',label='F&B Source Event',fieldtype='Link',options='FNB Inventory Event',read_only=1,no_copy=1),
            dict(fieldname='fnb_approved_by',label='F&B Approved By',fieldtype='Link',options='User',read_only=1,no_copy=1),
            dict(fieldname='fnb_approval_hash',label='F&B Approval Hash',fieldtype='Data',read_only=1,no_copy=1)]
        if not frappe.get_meta(dt).has_field('hospitality_property'):
            fields[dt].append(dict(fieldname='hospitality_property',label='Hospitality Property',fieldtype='Link',options='Hospitality Property'))
    for dt in ['POS Invoice','Sales Invoice']:
        fields[dt] += [dict(fieldname='fnb_allocations',label='F&B Service Allocations',fieldtype='Table',options='FNB Invoice Allocation'),
            dict(fieldname='fnb_session',label='F&B Service Session',fieldtype='Link',options='FNB Service Session'),
            dict(fieldname='fnb_return_disposition',label='F&B Return Disposition',fieldtype='Select',options='\nFinancial Only\nPhysical Return')]
    for dt in ['POS Invoice Item','Sales Invoice Item']:
        fields[dt]=[dict(fieldname='fnb_snapshot',label='F&B Snapshot',fieldtype='Long Text',read_only=1,no_copy=1)]
    fields['Folio Transaction']=[dict(fieldname='fnb_pos_key',label='F&B POS Source',fieldtype='Data',unique=1,read_only=1,no_copy=1)]
    create_custom_fields(fields,update=True)
    for purpose in ['Material Issue','Material Receipt','Material Transfer','Manufacture']:
        if not frappe.db.exists('Stock Entry Type',purpose):
            frappe.get_doc(dict(doctype='Stock Entry Type',name=purpose,purpose=purpose,is_standard=1)).insert(ignore_permissions=True)
