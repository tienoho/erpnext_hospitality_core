"""Chứng từ ERPNext cho phí v2; không chèn GL trực tiếp."""
import json
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate
from babel.numbers import get_currency_precision
from hospitality_core.hospitality_core.api.property_scope import require_property,company_settings,key
from hospitality_core.hospitality_core.api.rate_calculation import money


def exchange(currency,base,date):
    from erpnext.setup.utils import get_exchange_rate
    rate=flt(get_exchange_rate(currency,base,date))
    if rate<=0:
        frappe.throw(_('Thiếu tỷ giá {0}/{1} ngày {2}.').format(currency,base,date))
    return rate


def _tax_rows(evidence):
    metadata = {'name','parent','parenttype','parentfield','creation','modified','owner','modified_by','idx','docstatus','doctype'}
    return [{k:v for k,v in row.items() if k not in metadata} for row in evidence['taxes']]


def tax_quote(folio,item,rate,date,tax_evidence=None):
    settings=company_settings(folio.operating_company)
    base=frappe.get_cached_value('Company',folio.operating_company,'default_currency')
    inv=frappe.new_doc('Sales Invoice')
    inv.company=folio.operating_company
    inv.customer=folio.billing_customer
    inv.currency=folio.currency
    inv.conversion_rate=exchange(folio.currency,base,date)
    inv.posting_date=date; inv.due_date=date
    inv.taxes_and_charges=settings.tax_template
    inv.append('items',dict(item_code=item,qty=-1 if rate < 0 else 1,rate=abs(rate),income_account=settings.income_account,cost_center=settings.cost_center))
    inv.set_missing_values()
    if tax_evidence is not None:
        inv.taxes_and_charges = tax_evidence['tax_template']
        inv.set('taxes', _tax_rows(tax_evidence))
    inv.calculate_taxes_and_totals()
    return inv


def _journal(company,property,date,accounts,remark):
    settings=company_settings(company)
    doc=frappe.get_doc(dict(doctype='Journal Entry',voucher_type='Journal Entry',company=company,
        posting_date=date,user_remark=remark,multi_currency=1,hospitality_property=property,
        hospitality_accounting_version='Property v2'))
    for row in accounts:
        row.setdefault('cost_center',settings.cost_center)
        row.setdefault('hospitality_property',property)
        doc.append('accounts',row)
    doc.flags.hospitality_service=True
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc


def _row(account,amount,**kwargs):
    return dict(account=account,debit_in_account_currency=max(amount,0),
        credit_in_account_currency=max(-amount,0),exchange_rate=1,**kwargs)


def post_charge(res,transaction,rate,date,revision='original',tax_evidence=None):
    """Ghi doanh thu chưa xuất hóa đơn theo mức giá đã chốt, có khóa nguồn."""
    if res.accounting_version!='Property v2':
        return
    folio=frappe.get_doc('Guest Folio',transaction.parent)
    require_property(folio.property)
    frappe.db.sql('SELECT name FROM `tabGuest Folio` WHERE name=%s FOR UPDATE',folio.name)
    source_key=key('charge',transaction.name,revision)
    found=frappe.db.get_value('Hospitality Charge Posting',{'source_key':source_key},'name')
    if found:
        return frappe.get_doc('Hospitality Charge Posting',found)
    inv=tax_quote(folio,'ROOM-RENT',rate,date,tax_evidence=tax_evidence)
    settings=company_settings(folio.operating_company)
    net=inv.items[0].net_amount
    base_net=inv.items[0].base_net_amount
    journal=None
    if base_net:
        journal=_journal(folio.operating_company,folio.property,date,
            [_row(settings.unbilled_account,base_net),_row(settings.income_account,-base_net)],
            f'Hospitality {source_key}: {transaction.name}')
    posting=frappe.get_doc(dict(doctype='Hospitality Charge Posting',property=folio.property,
        operating_company=folio.operating_company,currency=folio.currency,folio=folio.name,reservation=res.name,
        transaction_id=transaction.name,source_key=source_key,business_date=date,gross_amount=inv.grand_total,
        net_amount=net,exchange_rate=inv.conversion_rate,base_net_amount=base_net,
        journal_entry=journal.name if journal else None,evidence=json.dumps(dict(rate=rate,item='ROOM-RENT',
            pricing_origin=transaction.get('pricing_origin'),
            tax_template=inv.taxes_and_charges,taxes=[t.as_dict() for t in inv.taxes]),default=str)))
    posting.flags.hospitality_service=True
    posting.insert(ignore_permissions=True)
    return posting


@frappe.whitelist(methods=['POST'])
def create_invoice(folio_name,posting_names=None):
    folio=frappe.get_doc('Guest Folio',folio_name,for_update=True)
    folio.check_permission('write')
    require_property(folio.property)
    if folio.accounting_version!='Property v2':
        frappe.throw(_('Folio chưa sử dụng kế toán Property v2.'))
    wanted=frappe.parse_json(posting_names) if posting_names else None
    postings=frappe.db.sql('''SELECT p.* FROM `tabHospitality Charge Posting` p WHERE p.folio=%s
        AND NOT EXISTS(SELECT 1 FROM `tabHospitality Invoice Allocation` a
            WHERE a.posting=p.name AND a.status IN ('Reserved','Posted')) FOR UPDATE''',folio.name,as_dict=True)
    if wanted is not None:
        if not isinstance(wanted,list) or set(wanted)-{p.name for p in postings}:
            frappe.throw(_('Danh sách khoản phí không còn khả dụng hoặc thuộc folio khác.'))
        postings=[p for p in postings if p.name in wanted]
    if not postings:
        frappe.throw(_('Không còn khoản phí chưa phân bổ hóa đơn.'))
    settings=company_settings(folio.operating_company)
    inv=tax_quote(folio,'ROOM-RENT',0,nowdate())
    inv.set('items',[])
    inv.hospitality_property=folio.property; inv.hospitality_folio=folio.name
    inv.hospitality_accounting_version='Property v2'
    # Cùng template trong một invoice; không tính lại lịch sử bằng template khác.
    templates={json.loads(p.evidence)['tax_template'] for p in postings}
    if len(templates)!=1:
        frappe.throw(_('Các khoản phí có chính sách thuế khác nhau; hãy xuất hóa đơn riêng từng nhóm.'))
    evidence=json.loads(postings[0].evidence)
    inv.set('taxes',_tax_rows(evidence))
    for p in postings:
        rate = json.loads(p.evidence)['rate']
        inv.append('items',dict(item_code='ROOM-RENT',qty=-1 if rate < 0 else 1,rate=abs(rate),
            hospitality_posting=p.name,income_account=settings.income_account,cost_center=settings.cost_center,
            hospitality_property=folio.property,description=f'Room Charge {p.business_date} ({p.transaction_id})'))
    inv.flags.hospitality_service=True
    inv.insert(ignore_permissions=True)
    for item in inv.items:
        p=next(p for p in postings if p.name==item.hospitality_posting)
        allocation=frappe.get_doc(dict(doctype='Hospitality Invoice Allocation',property=folio.property,
            operating_company=folio.operating_company,currency=folio.currency,posting=p.name,invoice=inv.name,
            invoice_item=item.name,allocation_key=key(inv.name,p.name),amount=item.net_amount,
            base_amount=item.base_net_amount,status='Reserved'))
        allocation.flags.hospitality_service=True
        allocation.insert(ignore_permissions=True)
    return inv.name


def _relink_amended_allocations(doc):
    """TRƯỚC ĐÂY: sửa hóa đơn Property v2 (bắt buộc Cancel rồi Amend theo quy
    trình ERPNext chuẩn) tạo ra 1 Sales Invoice MỚI với TÊN KHÁC — trong khi
    Hospitality Invoice Allocation vẫn trỏ tới tên hóa đơn CŨ (đã chuyển
    status='Released' lúc cancel qua invoice_cancelled()). invoice_submitted()
    tra cứu allocation theo doc.name (tên hóa đơn MỚI sau amend) nên KHÔNG
    TÌM THẤY GÌ — toàn bộ bước đối soát (tạo JE điều chỉnh doanh thu,
    đánh dấu Folio Transaction.is_invoiced=1) bị bỏ qua ÂM THẦM, không có lỗi
    nào được ném ra. Hậu quả kép: (1) doanh thu được ghi nhận 2 lần — 1 lần
    lúc phát sinh charge (post_charge's JE unbilled->income), 1 lần nữa từ GL
    gốc do chính ERPNext tự ghi khi submit hóa đơn amend — không có gì triệt
    tiêu lần thứ 2; (2) Folio Transaction gốc vẫn is_invoiced=0 nên
    create_invoice()'s câu chọn charge chưa xuất hóa đơn vẫn coi charge đó là
    CHƯA XUẤT, có thể bị chọn xuất hóa đơn THÊM MỘT LẦN NỮA cho đúng 1 khoản
    charge — double-bill khách thật.

    Sửa: gọi ở ĐẦU invoice_submitted() (on_submit — lúc này doc.name của hóa
    đơn amend chắc chắn đã tồn tại, tránh phụ thuộc thời điểm chính xác
    doc.name được gán trong lúc validate()). Gán lại (re-link) các
    Hospitality Invoice Allocation đang 'Released' của hóa đơn cũ sang TÊN
    HÓA ĐƠN MỚI, đưa về 'Reserved' — để phần còn lại của invoice_submitted()
    xử lý đúng như một hóa đơn mới bình thường. Chỉ lọc theo status='Released'
    nên tự idempotent — gọi lại nhiều lần không re-link lần 2.
    """
    if not doc.get('amended_from'):
        return
    old_allocations = frappe.get_all('Hospitality Invoice Allocation',
        filters={'invoice': doc.amended_from, 'status': 'Released'}, fields=['name', 'posting'])
    if not old_allocations:
        return
    items_by_posting = {i.get('hospitality_posting'): i for i in doc.items if i.get('hospitality_posting')}
    for row in old_allocations:
        item = items_by_posting.get(row.posting)
        if not item:
            # Dòng charge gốc không còn nằm trong hóa đơn amend (đã bị bỏ ra
            # khi soạn nháp) — giữ nguyên 'Released', không re-link nhầm.
            continue
        a = frappe.get_doc('Hospitality Invoice Allocation', row.name, for_update=True)
        a.flags.hospitality_service = True
        a.invoice = doc.name
        a.invoice_item = item.name
        a.status = 'Reserved'
        a.save(ignore_permissions=True)


def validate_invoice(doc,method=None):
    if not doc.get('hospitality_folio'):
        return
    folio=frappe.get_doc('Guest Folio',doc.hospitality_folio)
    if folio.get('accounting_version')!='Property v2':
        return
    require_property(folio.property)
    if doc.company!=folio.operating_company or doc.currency!=folio.currency or doc.customer!=folio.billing_customer:
        frappe.throw(_('Hóa đơn không khớp pháp nhân, tiền tệ hoặc bên thanh toán của Folio.'))
    doc.hospitality_property=folio.property
    doc.hospitality_accounting_version='Property v2'
    # Chỉ các hóa đơn Hospitality dùng sổ Guest; không ảnh hưởng native loyalty khác.
    doc.loyalty_program=None; doc.redeem_loyalty_points=0; doc.loyalty_points=0; doc.loyalty_amount=0
    if not doc.is_new() and not doc.is_return:
        sources=frappe.get_all('Hospitality Invoice Allocation',filters={'invoice':doc.name,'status':['!=','Released']},fields=['posting','amount'])
        if sources and {r.posting for r in sources}!={i.get('hospitality_posting') for i in doc.items}:
            frappe.throw(_('Không thêm/xóa dòng nguồn trên hóa đơn Hospitality; hãy giải phóng và tạo lại bản nháp.'))
        for item in doc.items:
            if item.get('hospitality_posting'):
                posting=frappe.get_doc('Hospitality Charge Posting',item.hospitality_posting)
                rate = flt(json.loads(posting.evidence)['rate'])
                if posting.folio!=folio.name or item.qty!=(-1 if rate < 0 else 1) or flt(item.rate)!=abs(rate):
                    frappe.throw(_('Không thay đổi giá hoặc nguồn phí đã chốt.'))


def invoice_submitted(doc,method=None):
    if doc.get('hospitality_accounting_version')!='Property v2':
        return
    _relink_amended_allocations(doc)
    settings=company_settings(doc.company)
    allocations=frappe.get_all('Hospitality Invoice Allocation',filters={'invoice':doc.name,'status':'Reserved'},pluck='name')
    for name in allocations:
        a=frappe.get_doc('Hospitality Invoice Allocation',name,for_update=True)
        p=frappe.get_doc('Hospitality Charge Posting',a.posting)
        item=next(i for i in doc.items if i.hospitality_posting==p.name)
        base_invoice=flt(item.base_net_amount); original=flt(p.base_net_amount)
        difference=base_invoice-original
        rows=[_row(settings.income_account,base_invoice),_row(settings.unbilled_account,-original)]
        if difference:
            rows.append(_row(settings.exchange_difference_account,-difference))
        rows=[r for r in rows if r['debit_in_account_currency'] or r['credit_in_account_currency']]
        je=_journal(doc.company,doc.hospitality_property,doc.posting_date,rows,f'Hospitality invoice allocation {a.name}') if rows else None
        a.flags.hospitality_service=True; a.status='Posted'; a.amount=item.net_amount; a.base_amount=item.base_net_amount
        a.transfer_journal=je.name if je else None
        a.save(ignore_permissions=True)
        frappe.db.set_value('Folio Transaction',p.transaction_id,'is_invoiced',1)
    _reconcile_invoice_guests(doc.name)


def invoice_cancelled(doc,method=None):
    if doc.get('hospitality_accounting_version')!='Property v2':
        return
    for name in frappe.get_all('Hospitality Invoice Allocation',filters={'invoice':doc.name,'status':['!=','Released']},pluck='name'):
        a=frappe.get_doc('Hospitality Invoice Allocation',name,for_update=True)
        if a.transfer_journal:
            je=frappe.get_doc('Journal Entry',a.transfer_journal)
            if je.docstatus==1:
                je.cancel()
        a.flags.hospitality_service=True; a.status='Released'; a.save(ignore_permissions=True)
        p=frappe.get_doc('Hospitality Charge Posting',a.posting)
        frappe.db.set_value('Folio Transaction',p.transaction_id,'is_invoiced',0)
    _reconcile_invoice_guests(doc.name)


def _reconcile_invoice_guests(invoice):
    from hospitality_core.hospitality_core.api.guest_loyalty import reconcile_reservation
    for res in frappe.db.sql_list('''SELECT DISTINCT p.reservation FROM `tabHospitality Invoice Allocation` a
        JOIN `tabHospitality Charge Posting` p ON p.name=a.posting WHERE a.invoice=%s''',invoice):
        if res:
            reconcile_reservation(res)


def redeem_journal(invoice,value):
    settings=company_settings(invoice.company)
    if not settings.loyalty_expense_account:
        frappe.throw(_('Chưa cấu hình tài khoản chi phí đổi điểm.'))
    account_currency=frappe.get_cached_value('Account',invoice.debit_to,'account_currency')
    base=frappe.get_cached_value('Company',invoice.company,'default_currency')
    rate=exchange(account_currency,base,invoice.posting_date)
    credit=value/rate
    return _journal(invoice.company,invoice.hospitality_property,nowdate(),[
        _row(settings.loyalty_expense_account,value),
        dict(account=invoice.debit_to,credit_in_account_currency=credit,exchange_rate=rate,
            party_type='Customer',party=invoice.customer,reference_type='Sales Invoice',reference_name=invoice.name)
    ],f'Hospitality loyalty redemption {invoice.name}')


@frappe.whitelist(methods=['POST'])
def receive_payment(folio_name,account,amount,request_id,posting_date=None,invoice=None):
    folio=frappe.get_doc('Guest Folio',folio_name,for_update=True)
    folio.check_permission('write'); require_property(folio.property)
    if folio.accounting_version!='Property v2' or not request_id:
        frappe.throw(_('Folio hoặc mã yêu cầu thanh toán không hợp lệ.'))
    payment_key=key('payment',folio.name,request_id)
    old=frappe.db.get_value('Payment Entry',{'hospitality_event_key':payment_key},['name','received_amount','paid_to'],as_dict=True)
    if old:
        if flt(old.received_amount)!=flt(amount) or old.paid_to!=account:
            frappe.throw(_('Mã thanh toán đã dùng với dữ liệu khác.'))
        return old.name
    bank=frappe.get_doc('Account',account)
    if bank.company!=folio.operating_company or bank.is_group or bank.account_type not in ('Bank','Cash'):
        frappe.throw(_('Tài khoản nhận tiền không hợp lệ hoặc thuộc pháp nhân khác.'))
    if not Decimal(str(amount)).is_finite() or flt(amount)<=0:
        frappe.throw(_('Số tiền phải dương và hữu hạn.'))
    settings=company_settings(folio.operating_company)
    date=posting_date or nowdate()
    base=frappe.get_cached_value('Company',folio.operating_company,'default_currency')
    ar_currency=frappe.get_cached_value('Account',settings.receivable_account,'account_currency')
    received_rate=exchange(bank.account_currency,base,date)
    paid_rate=exchange(ar_currency,base,date)
    paid=money(flt(amount)*received_rate/paid_rate,get_currency_precision(ar_currency))
    pe=frappe.get_doc(dict(doctype='Payment Entry',payment_type='Receive',company=folio.operating_company,
        posting_date=date,party_type='Customer',party=folio.billing_customer,paid_from=settings.receivable_account,
        paid_to=account,paid_from_account_currency=ar_currency,paid_to_account_currency=bank.account_currency,
        paid_amount=paid,received_amount=amount,source_exchange_rate=paid_rate,target_exchange_rate=received_rate,
        reference_no=request_id,reference_date=date,hospitality_property=folio.property,hospitality_folio=folio.name,
        hospitality_accounting_version='Property v2',hospitality_event_key=payment_key))
    if invoice:
        inv=frappe.get_doc('Sales Invoice',invoice,for_update=True)
        inv.check_permission('write')
        if inv.company!=folio.operating_company or inv.customer!=folio.billing_customer or inv.hospitality_folio!=folio.name or inv.docstatus!=1:
            frappe.throw(_('Hóa đơn không thuộc Folio hoặc chưa được submit.'))
        allocation=min(paid,flt(inv.outstanding_amount))
        pe.append('references',dict(reference_doctype='Sales Invoice',reference_name=inv.name,allocated_amount=allocation))
    pe.flags.hospitality_service=True
    pe.insert(ignore_permissions=True); pe.submit()
    return pe.name


def payment_updated(doc,method=None):
    if doc.get('hospitality_accounting_version')!='Property v2':
        return
    folio=frappe.get_doc('Guest Folio',doc.hospitality_folio)
    existing=frappe.db.get_value('Folio Transaction',{'source_key':key('payment-row',doc.name)},'name')
    if doc.docstatus==1 and not existing:
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists('PAYMENT','Payment')
        base=frappe.get_cached_value('Company',folio.operating_company,'default_currency')
        folio_rate=exchange(folio.currency,base,doc.posting_date)
        amount=money(flt(doc.received_amount)*flt(doc.target_exchange_rate)/folio_rate,get_currency_precision(folio.currency))
        row=frappe.get_doc(dict(doctype='Folio Transaction',parent=folio.name,parenttype='Guest Folio',parentfield='transactions',
            posting_date=doc.posting_date,item='PAYMENT',qty=1,amount=-amount,bill_to='Guest',
            source_key=key('payment-row',doc.name),reference_doctype='Payment Entry',reference_name=doc.name,
            description=f'Payment Entry {doc.name}',exchange_rate=folio_rate,base_amount=-amount*folio_rate))
        row.flags.hospitality_service=True
        row.insert(ignore_permissions=True)
    elif doc.docstatus==2 and existing:
        row=frappe.get_doc('Folio Transaction',existing)
        row.flags.hospitality_service=True
        row.is_void=1; row.void_reason=f'Cancelled Payment Entry {doc.name}'
        row.save(ignore_permissions=True)
    for ref in doc.references:
        if ref.reference_doctype=='Sales Invoice':
            _reconcile_invoice_guests(ref.reference_name)
