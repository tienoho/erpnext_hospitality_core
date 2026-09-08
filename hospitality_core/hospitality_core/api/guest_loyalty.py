"""Sổ điểm Guest theo pháp nhân; mỗi thay đổi là sự kiện có nguồn."""
import json
import math
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, now_datetime, nowdate
from hospitality_core.hospitality_core.api.property_scope import key, require_property, manager


def validate_configuration(doc):
    if doc.doctype=='Guest Membership':
        program=frappe.get_doc('Hospitality Loyalty Program',doc.program)
        doc.operating_company=program.operating_company
        doc.currency=program.currency
        doc.membership_key=key(doc.guest,doc.program)
        if not manager():
            program.check_permission('read')
        old=doc.get_doc_before_save()
        if old and (doc.guest!=old.guest or doc.program!=old.program):
            frappe.throw(_('Không đổi chủ sở hữu của membership đã tạo.'))
        if not doc.flags.hospitality_service:
            doc.tier=old.tier if old else None
            doc.qualifying_spend=old.qualifying_spend if old else 0
            # Guest merge (guest_crm.py's merge_guest) vô hiệu hóa membership
            # nguồn thay vì xóa để giữ lịch sử — nếu cho phép người dùng
            # thường bật lại (enabled 0->1), hồ sơ khách đã bị gộp sang nơi
            # khác sẽ có 2 membership CÙNG chương trình cùng hoạt động song
            # song (1 cái đã "biến mất" khỏi luồng nghiệp vụ nhưng vẫn có thể
            # tích/đổi điểm độc lập) — chỉ chặn khi hồ sơ khách SỞ HỮU
            # membership này đã có merged_into (đã bị gộp), không chặn việc
            # tạm khóa/mở khóa membership bình thường (VD nghi ngờ gian lận).
            if old and not old.enabled and doc.enabled and frappe.db.get_value('Guest', doc.guest, 'merged_into'):
                frappe.throw(_('Không thể kích hoạt lại membership của hồ sơ khách đã được gộp sang hồ sơ khác.'))
        return
    doc.currency=frappe.get_cached_value('Company',doc.operating_company,'default_currency')
    old=doc.get_doc_before_save()
    if old and old.operating_company!=doc.operating_company:
        frappe.throw(_('Không đổi pháp nhân của chương trình điểm đã tạo.'))
    thresholds=set(); names=set()
    for tier in doc.tiers:
        if tier.min_spend<0 or tier.min_spend in thresholds or tier.tier_name in names:
            frappe.throw(_('Ngưỡng tier không âm và không trùng; tên tier phải duy nhất.'))
        if not 0<=flt(tier.room_discount_percent)<=100 or tier.breakfast_per_night<0:
            frappe.throw(_('Quyền lợi tier không hợp lệ.'))
        thresholds.add(tier.min_spend); names.add(tier.tier_name)
    if doc.enabled:
        if doc.spend_per_point<=0 or doc.value_per_point<=0 or doc.expiry_days<1 or 0 not in thresholds:
            frappe.throw(_('Cần tỷ lệ tích/đổi dương, thời hạn điểm và tier khởi đầu bằng 0.'))
        duplicates=frappe.db.exists('Hospitality Loyalty Program',{'operating_company':doc.operating_company,
            'enabled':1,'name':['!=',doc.name or '']})
        if duplicates:
            frappe.throw(_('Mỗi pháp nhân chỉ có một chương trình Hospitality hoạt động.'))
    doc.policy_version=(old.policy_version or 1)+1 if old else 1


def _member(name, lock=False):
    doc=frappe.get_doc('Guest Membership',name,for_update=lock)
    doc.check_permission('read')
    return doc


def _entries(member):
    return frappe.db.sql('''SELECT name,event_type,points,qualifying_spend,posting_time,expires_at,
        source_entry,reservation,invoice,evidence,value FROM `tabHospitality Loyalty Entry`
        WHERE membership=%s ORDER BY creation,name FOR UPDATE''',member,as_dict=True)


def balances(rows, at=None):
    at=at or now_datetime()
    balance=sum(r.points for r in rows if r.event_type not in ('Hold','Release'))
    balance-=sum(_lot_remaining(rows,r) for r in rows if r.event_type=='Earn'
        and getattr(r,'expires_at',None) and get_datetime(r.expires_at)<=at)
    released={r.source_entry for r in rows if r.event_type=='Release'}
    held=sum(r.points for r in rows if r.event_type=='Hold' and r.name not in released and get_datetime(r.expires_at)>at)
    return dict(balance=balance,held=held,available=balance-held)


def _event(member,event_type,event_key,points,**values):
    found=frappe.db.get_value('Hospitality Loyalty Entry',{'event_key':event_key},'name')
    if found:
        return frappe.get_doc('Hospitality Loyalty Entry',found)
    d=frappe.get_doc(dict(doctype='Hospitality Loyalty Entry',membership=member.name,
        operating_company=member.operating_company,currency=member.currency,event_type=event_type,
        event_key=event_key,points=points,posting_time=now_datetime(),**values))
    d.flags.hospitality_service=True
    return d.insert(ignore_permissions=True)


def _lot_remaining(rows,earn):
    remaining=earn.points
    for row in rows:
        if row.source_entry==earn.name and row.event_type in ('Reverse','Expire'):
            remaining+=row.points
        if row.event_type=='Redeem':
            remaining-=sum(x['points'] for x in json.loads(row.evidence or '{}').get('lots',[]) if x['entry']==earn.name)
    return max(0,remaining)


def expire(member,rows=None):
    rows=rows if rows is not None else _entries(member.name)
    at=now_datetime()
    for row in list(rows):
        if row.event_type=='Earn' and row.expires_at and get_datetime(row.expires_at)<=at:
            points=_lot_remaining(rows,row)
            if points:
                rows.append(_event(member,'Expire',key('expire',row.name),-points,source_entry=row.name))
        if row.event_type=='Hold' and get_datetime(row.expires_at)<=at:
            if not any(r.event_type=='Release' and r.source_entry==row.name for r in rows):
                rows.append(_event(member,'Release',key('release',row.name),-row.points,source_entry=row.name))
    return rows


def update_tier(member,rows=None):
    rows=rows if rows is not None else _entries(member.name)
    since=now_datetime()-timedelta(days=365)
    # Điều chỉnh giữ kỳ xét hạng của lần cấp gốc, không tạo doanh số mới ngày hoàn.
    origins={}
    for row in rows:
        if row.event_type=='Earn' and row.reservation:
            origins.setdefault(row.reservation,get_datetime(row.posting_time))
    spend=sum(flt(r.qualifying_spend) for r in rows if origins.get(r.reservation, since-timedelta(days=1))>=since)
    program=frappe.get_doc('Hospitality Loyalty Program',member.program)
    tier=max((t for t in program.tiers if t.min_spend<=max(0,spend)),key=lambda t:t.min_spend,default=None)
    frappe.db.set_value('Guest Membership',member.name,{'tier':tier.tier_name if tier else None,'qualifying_spend':max(0,spend)})
    return tier


def snapshot(res):
    if not res.get('membership'):
        return dict(vip_percent=0)
    member=_member(res.membership,lock=True)
    from hospitality_core.hospitality_core.api.guest_crm import canonical
    if canonical(member.guest)!=canonical(res.guest) or member.operating_company!=res.operating_company or not member.enabled:
        frappe.throw(_('Membership không thuộc khách/pháp nhân của đặt phòng hoặc đã ngừng hoạt động.'))
    program=frappe.get_doc('Hospitality Loyalty Program',member.program)
    if not program.enabled or getdate(program.effective_from)>getdate(nowdate()):
        return dict(vip_percent=0)
    tier=update_tier(member)
    return dict(membership=member.name,program=program.name,policy_version=program.policy_version,
        vip_percent=flt(tier.room_discount_percent) if tier else 0,tier=tier.tier_name if tier else None,
        breakfast_per_night=tier.breakfast_per_night if tier else 0,
        late_checkout=bool(tier and tier.late_checkout),upgrade=bool(tier and tier.upgrade))


@frappe.whitelist(methods=['POST'])
def get_membership(membership):
    member=_member(membership,lock=True)
    rows=expire(member)
    tier=update_tier(member,rows)
    return dict(membership=member.name,currency=member.currency,company=member.operating_company,
        tier=tier.tier_name if tier else None,**balances(rows))


def _target(membership,reservation):
    member=_member(membership,lock=True)
    res=frappe.get_doc('Hotel Reservation',reservation)
    res.check_permission('write')
    require_property(res.property)
    from hospitality_core.hospitality_core.api.guest_crm import canonical
    if canonical(member.guest)!=canonical(res.guest) or member.operating_company!=res.operating_company or res.membership!=member.name:
        frappe.throw(_('Không thể dùng điểm khác khách, membership hoặc pháp nhân.'))
    program=frappe.get_doc('Hospitality Loyalty Program',member.program)
    if not member.enabled or not program.enabled:
        frappe.throw(_('Chương trình hoặc membership đã ngừng hoạt động.'))
    return member,res,program


@frappe.whitelist(methods=['POST'])
def hold_points(membership,reservation,points,request_id):
    member,res,program=_target(membership,reservation)
    if not request_id or len(request_id)>100:
        frappe.throw(_('Cần mã yêu cầu đổi điểm hợp lệ.'))
    numeric=Decimal(str(points))
    if not numeric.is_finite() or numeric<=0 or numeric!=numeric.to_integral_value():
        frappe.throw(_('Số điểm phải là số nguyên dương.'))
    points=int(numeric)
    event_key=key('hold',member.name,request_id)
    old=frappe.db.get_value('Hospitality Loyalty Entry',{'event_key':event_key},['name','reservation','points'],as_dict=True)
    if old:
        if old.reservation!=reservation or old.points!=points:
            frappe.throw(_('Mã yêu cầu đã được dùng với dữ liệu khác.'))
        return dict(hold=old.name)
    rows=expire(member)
    if balances(rows)['available']<points:
        frappe.throw(_('Không đủ điểm khả dụng.'))
    event=_event(member,'Hold',event_key,points,reservation=res.name,
        expires_at=now_datetime()+timedelta(minutes=15),value=points*program.value_per_point,
        evidence=json.dumps({'value_per_point':program.value_per_point,'policy_version':program.policy_version}))
    return dict(hold=event.name,expires_at=event.expires_at,value=event.value,currency=member.currency)


@frappe.whitelist(methods=['POST'])
def release_hold(hold):
    entry=frappe.get_doc('Hospitality Loyalty Entry',hold)
    member,res,program=_target(entry.membership,entry.reservation)
    if entry.event_type!='Hold':
        frappe.throw(_('Không phải sự kiện giữ điểm.'))
    _event(member,'Release',key('release',entry.name),-entry.points,source_entry=entry.name)
    return dict(released=True)


@frappe.whitelist(methods=['POST'])
def redeem_points(hold,invoice):
    entry=frappe.get_doc('Hospitality Loyalty Entry',hold)
    member,res,program=_target(entry.membership,entry.reservation)
    event_key=key('redeem',entry.name)
    old=frappe.db.get_value('Hospitality Loyalty Entry',{'event_key':event_key},['name','invoice'],as_dict=True)
    if old:
        if old.invoice!=invoice:
            frappe.throw(_('Yêu cầu đã đổi điểm trên hóa đơn khác.'))
        return old
    rows=expire(member)
    if entry.event_type!='Hold' or get_datetime(entry.expires_at)<=now_datetime() or any(r.event_type=='Release' and r.source_entry==hold for r in rows):
        frappe.throw(_('Lượt giữ điểm đã hết hạn hoặc được giải phóng.'))
    from hospitality_core.hospitality_core.api.loyalty_calculation import redemption_capacity
    state=balances(rows)
    if redemption_capacity(state['balance'],state['held'],entry.points)<entry.points:
        frappe.throw(_('Số dư điểm không còn đủ.'))
    inv=frappe.get_doc('Sales Invoice',invoice,for_update=True)
    inv.check_permission('write')
    if inv.docstatus!=1 or inv.company!=member.operating_company or inv.is_return:
        frappe.throw(_('Hóa đơn phải hợp lệ và cùng pháp nhân.'))
    eligible=frappe.db.sql('''SELECT COALESCE(SUM(a.base_amount),0) FROM `tabHospitality Invoice Allocation` a
        JOIN `tabHospitality Charge Posting` p ON p.name=a.posting
        WHERE a.invoice=%s AND a.status='Posted' AND p.reservation=%s''',(invoice,res.name))[0][0]
    prior=sum(flt(r.value) for r in rows if r.event_type=='Redeem' and r.invoice==invoice and r.reservation==res.name)
    if entry.value>flt(eligible)-prior or entry.value>flt(inv.outstanding_amount)*flt(inv.conversion_rate)+0.000001:
        frappe.throw(_('Giá trị đổi vượt tiền phòng đủ điều kiện hoặc công nợ còn lại.'))
    lots=[]; left=entry.points
    for earn in sorted((r for r in rows if r.event_type=='Earn'),key=lambda r:get_datetime(r.expires_at)):
        available=_lot_remaining(rows,earn)
        take=min(left,available)
        if take:
            lots.append(dict(entry=earn.name,points=take)); left-=take
        if not left:
            break
    if left:
        frappe.throw(_('Không thể phân bổ đủ điểm còn hiệu lực.'))
    from hospitality_core.hospitality_core.api.property_accounting import redeem_journal
    journal=redeem_journal(inv,entry.value)
    result=_event(member,'Redeem',event_key,-entry.points,source_entry=entry.name,reservation=res.name,
        invoice=invoice,value=entry.value,journal_entry=journal.name,evidence=json.dumps({'lots':lots}))
    _event(member,'Release',key('release',entry.name),-entry.points,source_entry=entry.name)
    reconcile_reservation(res.name)
    return dict(name=result.name,journal_entry=journal.name)


def reconcile_reservation(reservation):
    res=frappe.get_doc('Hotel Reservation',reservation)
    if not res.get('membership') or res.get('accounting_version')!='Property v2':
        return
    member=_member(res.membership,lock=True)
    program=frappe.get_doc('Hospitality Loyalty Program',member.program)
    if not program.enabled or not member.enabled or getdate(res.arrival_date)<getdate(program.effective_from):
        return
    rows=expire(member)
    allocations=frappe.db.sql('''SELECT a.base_amount,a.invoice,i.docstatus,i.outstanding_amount,i.is_return,
        p.transaction_id FROM `tabHospitality Invoice Allocation` a
        JOIN `tabHospitality Charge Posting` p ON p.name=a.posting
        JOIN `tabSales Invoice` i ON i.name=a.invoice
        WHERE p.reservation=%s AND a.status='Posted' FOR UPDATE''',res.name,as_dict=True)
    unbilled=frappe.db.sql('''SELECT p.name FROM `tabHospitality Charge Posting` p WHERE p.reservation=%s
        AND NOT EXISTS(SELECT 1 FROM `tabHospitality Invoice Allocation` a WHERE a.posting=p.name AND a.status='Posted')''',res.name)
    eligible=0
    if res.status=='Checked Out' and allocations and not unbilled and all(a.docstatus==1 and abs(flt(a.outstanding_amount))<0.000001 for a in allocations):
        eligible=max(0,sum(flt(a.base_amount) for a in allocations)-sum(flt(r.value) for r in rows if r.event_type=='Redeem' and r.reservation==res.name))
    previous=sum(flt(r.qualifying_spend) for r in rows if r.reservation==res.name)
    earned=sum(r.points for r in rows if r.reservation==res.name and r.event_type in ('Earn','Reverse'))
    # Sau lần cấp đầu, giữ tỷ lệ ban đầu khi xử lý hoàn tiền.
    origin=next((r for r in rows if r.reservation==res.name and r.event_type=='Earn'),None)
    unit=json.loads(origin.evidence).get('spend_per_point') if origin else program.spend_per_point
    target=int((Decimal(str(eligible))/Decimal(str(unit))).to_integral_value(rounding=ROUND_DOWN))
    from hospitality_core.hospitality_core.api.loyalty_calculation import qualification_delta
    expired=-sum(r.points for r in rows if r.event_type=='Expire' and origin and r.source_entry==origin.name)
    redeemed=sum(x['points'] for r in rows if r.event_type=='Redeem'
        for x in json.loads(r.evidence or '{}').get('lots',[]) if origin and x['entry']==origin.name)
    delta,expiry_delta=qualification_delta(earned,target,redeemed,expired,
        bool(origin and get_datetime(origin.expires_at)<=now_datetime()))
    if delta or abs(eligible-previous)>0.000001:
        event_type='Reverse' if origin else 'Earn'
        values=dict(reservation=res.name,qualifying_spend=eligible-previous,
            evidence=json.dumps({'spend_per_point':unit,'eligible':eligible,'policy_version':program.policy_version}))
        if event_type=='Earn':
            values['expires_at']=now_datetime()+timedelta(days=program.expiry_days)
        elif origin:
            values['source_entry']=origin.name
        _event(member,event_type,key('qualification',res.name,len(rows),eligible,target),delta,**values)
        if expiry_delta and origin:
            _event(member,'Expire',key('expiry-adjustment',res.name,len(rows),target),expiry_delta,
                source_entry=origin.name,evidence=json.dumps({'reason':'Điều chỉnh phần đã hết hạn theo quyền hưởng gốc'}))
    update_tier(member)


def scheduled():
    # TRƯỚC ĐÂY: không có try/except/savepoint quanh từng bản ghi — khác với
    # mẫu an toàn đã dùng ở group_booking.py's mass_check_in() (savepoint +
    # rollback + log_error mỗi dòng). 1 Guest Membership hỏng (VD program bị
    # xóa/đổi tên, update_tier() -> frappe.get_doc('Hospitality Loyalty
    # Program', ...) ném DoesNotExistError) sẽ làm ngoại lệ lan ra khỏi toàn
    # bộ scheduled(), dừng NGAY việc tính hạng/tích điểm cho MỌI membership và
    # MỌI reservation còn lại trong job — lỗi này lặp lại MỖI GIỜ, vô thời
    # hạn, cho tới khi ai đó tìm ra bản ghi hỏng và sửa thủ công.
    for name in frappe.get_all('Guest Membership',filters={'enabled':1},pluck='name'):
        frappe.db.savepoint('loyalty_scheduled')
        try:
            member=_member(name,lock=True)
            update_tier(member,expire(member))
        except Exception as e:
            frappe.db.rollback(save_point='loyalty_scheduled')
            frappe.log_error(f"Loyalty scheduled tier/expiry failed for {name}: {e}", "Loyalty Scheduled Error")
    for name in frappe.get_all('Hotel Reservation',filters={'accounting_version':'Property v2','membership':['is','set']},pluck='name'):
        frappe.db.savepoint('loyalty_scheduled')
        try:
            reconcile_reservation(name)
        except Exception as e:
            frappe.db.rollback(save_point='loyalty_scheduled')
            frappe.log_error(f"Loyalty scheduled reconciliation failed for {name}: {e}", "Loyalty Scheduled Error")


def issue_benefits(res):
    if res.status not in ('Reserved','Checked In') or not res.get('loyalty_snapshot'):
        return
    policy=json.loads(res.loyalty_snapshot)
    days=(getdate(res.departure_date)-getdate(res.arrival_date)).days
    wanted=[]
    if policy.get('breakfast_per_night'):
        wanted += [('Breakfast',getdate(res.arrival_date)+timedelta(days=i),policy['breakfast_per_night']) for i in range(days)]
    wanted += [(kind,getdate(res.departure_date),1) for flag,kind in [('late_checkout','Late Checkout'),('upgrade','Upgrade')] if policy.get(flag)]
    for kind,day,qty in wanted:
        event_key=key('benefit',res.name,kind,day)
        if frappe.db.exists('Guest Benefit Entitlement',{'event_key':event_key}):
            continue
        doc=frappe.get_doc(dict(doctype='Guest Benefit Entitlement',property=res.property,
            operating_company=res.operating_company,currency=res.currency,guest=res.guest,reservation=res.name,
            benefit_type=kind,benefit_date=day,quantity=qty,status='Confirmed' if kind=='Breakfast' else 'Requested',
            event_key=event_key,policy_snapshot=res.loyalty_snapshot))
        doc.flags.hospitality_service=True
        doc.insert(ignore_permissions=True)


@frappe.whitelist(methods=['POST'])
def set_benefit_status(benefit,status,reason):
    doc=frappe.get_doc('Guest Benefit Entitlement',benefit,for_update=True)
    require_property(doc.property)
    allowed={'Requested':{'Confirmed','Cancelled'},'Confirmed':{'Used','Cancelled'}}
    if status not in allowed.get(doc.status,set()) or not str(reason or '').strip():
        frappe.throw(_('Chuyển trạng thái không hợp lệ hoặc thiếu lý do xác nhận.'))
    doc.flags.hospitality_service=True
    doc.status=status; doc.decision_reason=reason
    doc.save(ignore_permissions=True)
    return doc.name
