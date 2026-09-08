"""Tạo schema FNB có thể review; không kết nối hoặc sửa dữ liệu site."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'hospitality_core' / 'hospitality_core' / 'doctype'


def f(name, kind='Data', options=None, required=False, readonly=False, **kw):
    row = dict(fieldname=name, label=name.replace('_', ' ').title(), fieldtype=kind)
    if options:
        row['options'] = options
    if required:
        row['reqd'] = 1
    if readonly:
        row['read_only'] = 1
    return dict(row, **kw)


def link(name, dt, **kw):
    return f(name, 'Link', dt, **kw)


def table(name, dt):
    return f(name, 'Table', dt)


SCOPE = [link('property', 'Hospitality Property', required=True),
         link('operating_company', 'Company', readonly=True), link('currency', 'Currency', readonly=True)]
APPROVAL = [f('status', 'Select', 'Draft\nApproved\nSent\nPrepared\nServed\nReconciled\nCounting\nClosed\nCancelled', readonly=True, default='Draft'),
            link('approved_by', 'User', readonly=True), f('approved_at', 'Datetime', readonly=True), f('reason', 'Small Text')]
OP = SCOPE + [link('outlet', 'FNB Outlet', required=True), f('posting_datetime', 'Datetime', required=True),
              f('business_date', 'Date', readonly=True)] + APPROVAL
ITEM = [link('item', 'Item', required=True), f('qty', 'Float', required=True), link('uom', 'UOM', required=True),
        f('stock_qty', 'Float', readonly=True), f('conversion_factor', 'Float', readonly=True),
        link('batch_no', 'Batch'), f('notes', 'Small Text')]

SCHEMA = {
 'FNB Outlet Item': [link('item', 'Item', required=True), f('stock_mode', 'Select', 'Recipe\nStock\nSession\nNonStock', required=True),
                    f('cost_group', 'Select', 'Food\nBeverage\nOther', required=True), f('par_qty', 'Float')],
 'FNB POS Mapping': [link('pos_profile', 'POS Profile', required=True)],
 'FNB Recipe Ingredient': ITEM + [link('child_recipe', 'FNB Recipe Version'), f('net_qty', 'Float'), f('yield_percent', 'Percent')],
 'FNB Stock Line': ITEM + [f('counted_qty', 'Float'), f('recounted_qty', 'Float'),
     f('count_entered','Check',readonly=True),f('recount_entered','Check',readonly=True), f('expiry_date', 'Date')],
 'FNB Service Line': ITEM + [link('recipe', 'FNB Recipe Version', readonly=True), f('snapshot', 'Long Text', readonly=True),
                           f('prepared_qty', 'Float', readonly=True), f('served_qty', 'Float', readonly=True),
                           f('billed_qty', 'Float', readonly=True), f('cancelled_qty', 'Float', readonly=True)],
 'FNB Standard Price': [link('item', 'Item', required=True), f('rate', 'Currency', 'parent.currency', required=True),
                        f('price_date', 'Date', required=True), link('source_doctype', 'DocType', required=True),
                        f('source_name', 'Dynamic Link', 'source_doctype', required=True)],
 'FNB Invoice Allocation': [link('ticket', 'FNB Service Ticket', required=True), f('ticket_line', required=True),
                           f('invoice_line', required=True), f('stock_qty', 'Float', required=True)],
 'FNB Settings': SCOPE + [f('enabled', 'Check', readonly=True), f('cutover_at', 'Datetime'),
    link('main_warehouse', 'Warehouse', required=True), link('transit_warehouse', 'Warehouse', required=True),
    link('cost_center', 'Cost Center', required=True)] + [link(n, 'Account', required=True) for n in
    ['cogs_account','staff_account','complimentary_account','waste_account','variance_account']] + [
    f('allow_direct_receipt', 'Check'), f('price_tolerance_percent', 'Percent', required=True),
    f('quantity_tolerance_percent', 'Percent', required=True), f('setup_verified', 'Check', readonly=True)],
 'FNB Outlet': SCOPE + [f('outlet_name', required=True), link('warehouse', 'Warehouse', required=True),
    link('responsible_user', 'User', required=True), f('enabled', 'Check'), table('pos_profiles','FNB POS Mapping'),
    table('menu', 'FNB Outlet Item')],
 'FNB Recipe Version': SCOPE + [f('is_group_template','Check'), link('outlet','FNB Outlet'), link('item','Item',required=True),
    link('template','FNB Recipe Version'),f('import_key',readonly=True,unique=1),f('import_content_hash',readonly=True),
    f('quantity','Float',required=True),link('uom','UOM',required=True),
    f('effective_from','Datetime',required=True),f('effective_to','Datetime'),table('ingredients','FNB Recipe Ingredient'),
    f('snapshot','Long Text',readonly=True),link('bom','BOM',readonly=True)] + APPROVAL,
 'FNB Cost Standard': SCOPE + [f('from_date','Date',required=True), f('to_date','Date',required=True),table('prices','FNB Standard Price')] + APPROVAL,
 'FNB Service Ticket': OP + [f('table_number'),link('room','Hotel Room'),link('reservation','Hotel Reservation'),
    f('purpose','Select','Sale\nStaff\nComplimentary',required=True),f('beneficiary'),table('items','FNB Service Line')],
 'FNB Production Batch': OP + [link('recipe','FNB Recipe Version',required=True), f('output_qty','Float',required=True),
    link('output_batch','Batch'), f('expiry_date','Date'), table('items','FNB Stock Line'),f('snapshot','Long Text',readonly=True),
    link('stock_entry','Stock Entry',readonly=True)],
 'FNB Service Session': OP + [f('service_type','Select','Buffet\nBanquet\nBreakfast\nStaff\nComplimentary',required=True),
    f('expected_covers','Int',required=True),f('actual_covers','Int'),f('budget','Currency','currency',required=True),
    f('beneficiary'),table('menu','FNB Service Line'),table('items','FNB Stock Line')],
 'FNB Waste Record': OP + [f('disposition','Select','Inventory Loss\nPrepared Waste\nPhysical Return',required=True),
    link('source_event','FNB Inventory Event'),table('items','FNB Stock Line'),link('stock_entry','Stock Entry',readonly=True)],
 'FNB Stock Count': OP + [link('warehouse','Warehouse',required=True),table('items','FNB Stock Line'),
    link('counted_by','User',readonly=True),link('recounted_by','User',readonly=True),
    f('count_snapshot','Long Text',readonly=True,permlevel=1),link('stock_reconciliation','Stock Reconciliation',readonly=True)],
 'FNB Period Close': SCOPE + [f('from_date','Date',required=True),f('to_date','Date',required=True),
    link('cost_standard','FNB Cost Standard',required=True),f('snapshot','Long Text',readonly=True),
    link('supersedes','FNB Period Close')] + APPROVAL,
 'FNB Warehouse Control': SCOPE + [link('warehouse','Warehouse',required=True,unique=1),
    link('active_count','FNB Stock Count',readonly=True),f('closed_through','Datetime',readonly=True)],
 'FNB Inventory Event': SCOPE + [link('outlet','FNB Outlet'),f('source_key',required=True,unique=1),f('payload_hash',readonly=True),
    link('source_doctype','DocType',required=True),f('source_name','Dynamic Link','source_doctype',required=True),f('source_line'),
    f('event_type','Select','Prepare\nServe\nCancel\nProduce\nIssue\nWaste\nReturn\nAllocate\nRelease\nCount\nBenefit\nTransfer\nReceive\nRequest',required=True),
    f('posting_datetime','Datetime',required=True),f('business_date','Date',required=True),f('quantity','Float'),
    f('purpose'),link('origin','FNB Inventory Event'),f('snapshot','Long Text',readonly=True),
    link('stock_entry','Stock Entry',readonly=True),link('stock_reconciliation','Stock Reconciliation',readonly=True),
    f('policy_version',readonly=True,default='FNB v1')],
}
CHILDREN = {'FNB Outlet Item','FNB POS Mapping','FNB Recipe Ingredient','FNB Stock Line','FNB Service Line','FNB Standard Price','FNB Invoice Allocation'}
INTERNAL = {'FNB Inventory Event','FNB Warehouse Control'}


def generate():
    for name, fields in SCHEMA.items():
        child = name in CHILDREN
        folder = ROOT / name.lower().replace(' ', '_')
        folder.mkdir(exist_ok=True)
        (folder/'__init__.py').touch()
        permissions = [] if child else [dict(role='System Manager',read=1,write=1,create=1,report=1,export=1,print=1)]
        if not child:
            for role in ['FNB Operator','FNB Storekeeper','FNB Supervisor','FNB Cost Controller','FNB Finance Approver']:
                permissions.append(dict(role=role,read=1,write=int(name not in INTERNAL),create=int(name not in INTERNAL),report=1,print=1))
            permissions.append(dict(role='FNB Cost Controller',permlevel=1,read=1,write=1))
            permissions.append(dict(role='System Manager',permlevel=1,read=1,write=1))
        schema = dict(doctype='DocType',name=name,module='Hospitality Core',engine='InnoDB',istable=int(child),
            track_changes=int(not child),autoname='hash',fields=fields,field_order=[r['fieldname'] for r in fields],
            permissions=permissions,sort_field='modified',sort_order='DESC')
        if name == 'FNB Settings':
            schema['autoname']='field:property'
        if name == 'FNB Warehouse Control':
            schema['autoname']='field:warehouse'
        (folder/(folder.name+'.json')).write_text(json.dumps(schema,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
        base = 'Document' if child else 'FNBBase'
        imp = 'from frappe.model.document import Document' if child else 'from hospitality_core.hospitality_core.api.fnb.configuration import FNBBase'
        (folder/(folder.name+'.py')).write_text(f'{imp}\n\n\nclass {name.replace(" ", "")}({base}):\n    pass\n',encoding='utf-8')
    workspace=ROOT.parent/'workspace'/'fnb_cost_control'
    workspace.mkdir(parents=True,exist_ok=True)
    names=['FNB Settings','FNB Outlet','FNB Recipe Version','FNB Cost Standard','FNB Service Ticket','FNB Production Batch',
           'FNB Service Session','FNB Waste Record','FNB Stock Count','FNB Period Close','Material Request','Stock Entry']
    shortcuts=[dict(label='F&B Operations',type='Page',link_to='fnb-control',color='Blue')]
    shortcuts += [dict(label=n,type='DocType',link_to=n,doc_view='List',color='Blue') for n in names]
    content=[dict(id='fnb-title',type='header',data=dict(text='<span class="h4">F&amp;B Cost Control</span>',col=12))]
    content += [dict(id=f'fnb-{i}',type='shortcut',data=dict(shortcut_name=s['label'],col=4)) for i,s in enumerate(shortcuts)]
    data=dict(doctype='Workspace',name='F&B Cost Control',label='F&B Cost Control',title='F&B Cost Control',module='Hospitality Core',
        public=1,is_hidden=0,icon='stock',content=json.dumps(content),shortcuts=shortcuts,links=[],charts=[],
        roles=[dict(role=r) for r in ['FNB Operator','FNB Storekeeper','FNB Supervisor','FNB Cost Controller','FNB Finance Approver','System Manager']])
    (workspace/'fnb_cost_control.json').write_text(json.dumps(data,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')


if __name__ == '__main__':
    generate()
