"""Sinh schema chuẩn của Hospitality v2; chạy lại không xóa field hiện hữu."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'hospitality_core/hospitality_core/doctype'


def field(name, kind='Data', options=None, **kwargs):
    result = dict(fieldname=name, label=name.replace('_', ' ').title(), fieldtype=kind, **kwargs)
    if options is not None:
        result['options'] = options
    return result


def link(name, target, **kwargs):
    return field(name, 'Link', target, **kwargs)


def create(name, fields, child=False, writable=False, autoname='hash'):
    slug = name.lower().replace(' ', '_')
    folder = ROOT / slug
    folder.mkdir(exist_ok=True)
    data = dict(doctype='DocType', name=name, module='Hospitality Core', engine='InnoDB',
                autoname=autoname, istable=int(child), track_changes=int(not child),
                field_order=[f['fieldname'] for f in fields], fields=fields,
                permissions=[] if child else [dict(role='System Manager', read=1, write=1, create=1,
                    delete=0, report=1, export=1), dict(role='Hospitality User', read=1,
                    write=int(writable), create=int(writable), report=1)])
    (folder / (slug + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')
    (folder / '__init__.py').touch()
    controller = folder / (slug + '.py')
    if not controller.exists():
        controller.write_text('from frappe.model.document import Document\n\n\nclass '+name.replace(' ', '')+'(Document):\n    pass\n', encoding='utf-8')


def extend(name, fields):
    path = ROOT / name / (name + '.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    existing = {f['fieldname'] for f in data['fields']}
    for f in fields:
        if f['fieldname'] not in existing:
            data['fields'].append(f)
            data['field_order'].append(f['fieldname'])
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')


SCOPE = [link('property', 'Hospitality Property', in_list_view=1),
         link('operating_company', 'Company', read_only=1), link('currency', 'Currency')]


def build():
    create('Hospitality Property', [field('property_code', reqd=1, unique=1), field('property_name', reqd=1),
        link('operating_company', 'Company', reqd=1), link('currency', 'Currency', reqd=1),
        field('timezone', default='Asia/Ho_Chi_Minh', reqd=1), field('business_day_start', 'Time', default='08:00:00'),
        field('audit_time', 'Time', default='14:00:00'), field('enabled', 'Check', default='0'),
        field('accept_new_bookings', 'Check', default='0'), field('cutover_date', 'Date'),
        field('migration_verified', 'Check', read_only=1), field('setup_preview', 'HTML')], autoname='field:property_code')
    create('Hospitality Property Access', [link('property', 'Hospitality Property', reqd=1),
        link('user', 'User', reqd=1), field('enabled', 'Check', default='1'),
        field('access_key', unique=1, read_only=1)])
    create('Hospitality Company Accounting Settings', [link('operating_company', 'Company', reqd=1, unique=1),
        link('currency', 'Currency', read_only=1), link('receivable_account', 'Account', reqd=1),
        link('unbilled_account', 'Account', reqd=1), link('income_account', 'Account', reqd=1),
        link('exchange_difference_account', 'Account', reqd=1), link('round_off_account', 'Account', reqd=1),
        link('loyalty_expense_account', 'Account'), link('cost_center', 'Cost Center', reqd=1),
        link('tax_template', 'Sales Taxes and Charges Template', reqd=1),
        field('enabled', 'Check', default='0')], autoname='field:operating_company')
    property_fields = [link('property', 'Hospitality Property', reqd=1, unique=1),
        link('operating_company', 'Company', read_only=1), link('currency', 'Currency', read_only=1),
        link('warehouse', 'Warehouse'), link('pos_profile', 'POS Profile'), link('default_reception', 'Hotel Reception'),
        link('bank_account', 'Bank Account'), link('tax_template', 'Sales Taxes and Charges Template')]
    names = {f['fieldname'] for f in property_fields}
    for source in ['hospitality_surcharge_settings', 'hospitality_police_settings', 'hospitality_accounting_settings']:
        data = json.loads((ROOT/source/(source+'.json')).read_text(encoding='utf-8'))
        for original in data['fields']:
            if original['fieldname'] not in names and original['fieldname'] not in {
                    'receivable_account','income_suspense_account','income_account','cost_center',
                    'consumption_tax_account','vat_account','service_charge_account'}:
                f = dict(original)
                f.pop('reqd', None)
                property_fields.append(f)
                names.add(f['fieldname'])
    create('Hospitality Property Settings', property_fields, autoname='field:property')
    channel = json.loads((ROOT/'hospitality_channel_manager_settings/hospitality_channel_manager_settings.json').read_text(encoding='utf-8'))
    create('Hospitality Channel Connection', [*SCOPE, field('provider', reqd=1),
        field('external_property_id', reqd=1), field('connection_key', unique=1, read_only=1),
        field('webhook_secret', 'Password', reqd=1), *[dict(f, reqd=0) for f in channel['fields']
        if f['fieldname'] not in {'property','operating_company','currency'}]])
    create('Room Type Currency Rate', [link('currency', 'Currency', reqd=1),
        field('default_rate', 'Currency', 'currency', reqd=1)], child=True)
    create('Hospitality Loyalty Tier', [field('tier_name', reqd=1), field('min_spend', 'Currency', 'currency', reqd=1),
        field('room_discount_percent', 'Percent'), field('breakfast_per_night', 'Int'),
        field('late_checkout', 'Check'), field('upgrade', 'Check')], child=True)
    create('Hospitality Loyalty Program', [field('program_name', reqd=1),
        link('operating_company', 'Company', reqd=1), link('currency', 'Currency', read_only=1),
        field('enabled', 'Check', default='0'), field('effective_from', 'Date', reqd=1),
        field('spend_per_point', 'Currency', 'currency'), field('value_per_point', 'Currency', 'currency'),
        field('expiry_days', 'Int'), field('policy_version', 'Int', read_only=1),
        field('tiers', 'Table', 'Hospitality Loyalty Tier', reqd=1)])
    create('Guest Membership', [link('guest', 'Guest', reqd=1), link('program', 'Hospitality Loyalty Program', reqd=1),
        link('operating_company', 'Company', read_only=1), link('currency', 'Currency', read_only=1),
        field('membership_key', unique=1, read_only=1), field('enabled', 'Check', default='1'),
        field('tier', read_only=1), field('qualifying_spend', 'Currency', 'currency', read_only=1)], writable=True)
    create('Hospitality Loyalty Entry', [link('membership', 'Guest Membership', reqd=1),
        link('operating_company', 'Company', reqd=1), link('currency', 'Currency', reqd=1),
        field('event_type', 'Select', 'Earn\nHold\nRedeem\nRelease\nExpire\nReverse', reqd=1),
        field('event_key', unique=1, reqd=1), field('points', 'Int', reqd=1),
        field('qualifying_spend', 'Currency', 'currency'), field('value', 'Currency', 'currency'),
        field('posting_time', 'Datetime', reqd=1), field('expires_at', 'Datetime'),
        link('source_entry', 'Hospitality Loyalty Entry'), link('reservation', 'Hotel Reservation'),
        link('invoice', 'Sales Invoice'), link('journal_entry', 'Journal Entry'), field('evidence', 'Long Text')])
    create('Guest Preference', [link('guest','Guest',reqd=1), field('preference_type',reqd=1),
        field('preference_value','Small Text',reqd=1), field('sharing_scope','Select','Property\nGroup',default='Property',reqd=1),
        link('property','Hospitality Property'), field('source','Small Text'), field('valid_until','Date'),
        field('active','Check',default='1')], writable=True)
    create('Guest Interaction', [link('guest','Guest',reqd=1), link('property','Hospitality Property',reqd=1),
        link('reservation','Hotel Reservation'), field('subject',reqd=1), field('details','Text'),
        link('assigned_to','User'), field('status','Select','Open\nIn Progress\nResolved',default='Open')], writable=True)
    create('Guest Merge Log', [link('source_guest','Guest',reqd=1),link('target_guest','Guest',reqd=1),
        field('reason','Small Text',reqd=1),link('performed_by','User',reqd=1)], writable=False)
    create('Guest Benefit Entitlement', [*SCOPE,link('guest','Guest',reqd=1),link('reservation','Hotel Reservation',reqd=1),
        field('benefit_type','Select','Breakfast\nLate Checkout\nUpgrade',reqd=1),field('benefit_date','Date'),
        field('quantity','Int',default='1'),field('status','Select','Requested\nConfirmed\nUsed\nCancelled',default='Requested'),
        field('event_key',unique=1,reqd=1),field('policy_snapshot','Long Text'),field('decision_reason','Small Text')], writable=False)
    create('Hospitality Charge Posting', [*SCOPE,link('folio','Guest Folio',reqd=1),link('reservation','Hotel Reservation'),
        field('transaction_id',reqd=1),field('source_key',unique=1,reqd=1),field('business_date','Date',reqd=1),
        field('gross_amount','Currency','currency'),field('net_amount','Currency','currency'),
        field('exchange_rate','Float'),field('base_net_amount','Currency'),link('journal_entry','Journal Entry'),
        field('evidence','Long Text')])
    create('Hospitality Invoice Allocation', [*SCOPE,link('posting','Hospitality Charge Posting',reqd=1),
        link('invoice','Sales Invoice',reqd=1),field('invoice_item'),field('allocation_key',unique=1,reqd=1),
        field('amount','Currency','currency'),field('base_amount','Currency'),
        field('status','Select','Reserved\nPosted\nReleased',default='Reserved'),link('transfer_journal','Journal Entry')])
    create('Hospitality Audit Run', [link('property','Hospitality Property',reqd=1),field('business_date','Date',reqd=1),
        field('run_key',unique=1,reqd=1),field('status','Select','Running\nCompleted\nFailed',reqd=1),field('details','Long Text')])
    scoped = ['hotel_room','hotel_room_type','hotel_reception','room_rate_plan','hotel_reservation','guest_folio',
        'hotel_group_booking','guest_balance_ledger','hotel_maintenance_request','lost_and_found_item',
        'hospitality_expense','sales_report','night_audit_log','housekeeping_room_status_log','folio_transaction_move_log']
    for name in scoped:
        extend(name, SCOPE)
        path=ROOT/name/(name+'.json')
        data=json.loads(path.read_text(encoding='utf-8'))
        for f in data['fields']:
            if f['fieldtype']=='Currency' and not f['fieldname'].startswith('base_'):
                f['options']='currency'
        path.write_text(json.dumps(data,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    for name in ['hotel_reservation','guest_folio','hotel_group_booking','guest_balance_ledger']:
        extend(name,[field('accounting_version','Select','Legacy\nProperty v2',read_only=1,no_copy=1),
                     link('billing_customer','Customer')])
    extend('hotel_room_type',[field('currency_rates','Table','Room Type Currency Rate'),field('is_virtual','Check')])
    extend('hotel_reservation',[link('membership','Guest Membership'),field('loyalty_snapshot','Long Text',read_only=1),
        link('channel_connection','Hospitality Channel Connection'),field('channel_booking_key',unique=1,read_only=1)])
    extend('folio_transaction', SCOPE+[field('accounting_version','Select','Legacy\nProperty v2',read_only=1),
        field('base_amount','Currency',read_only=1),field('exchange_rate','Float',read_only=1),
        field('source_key',unique=1,read_only=1),link('beneficiary_guest','Guest',read_only=1)])
    extend('guest',[link('merged_into','Guest',read_only=1)])
    for name, fname in [('hotel_room','room_number'),('hotel_room_type','room_type_name'),('guest','full_name')]:
        path=ROOT/name/(name+'.json'); data=json.loads(path.read_text(encoding='utf-8'))
        data['autoname']='hash' if name != 'guest' else 'GUEST-.########'
        data['title_field']=fname
        for f in data['fields']:
            if f['fieldname']==fname:
                f.pop('unique',None)
        path.write_text(json.dumps(data,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')


if __name__ == '__main__':
    build()
