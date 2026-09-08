"""Căn cứ giá cố định và bút toán điều chỉnh LOS; không ghi đè lịch sử."""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate, now_datetime, add_days

from hospitality_core.hospitality_core.api.rate_calculation import (
    discount_breakdown, money, quote_day, quote_stay,
)


def is_virtual(res):
    return res.room_type == 'Virtual'


def snapshot_for(rate_plan, room_type, currency=None, property=None):
    room = frappe.get_doc('Hotel Room Type', room_type)
    precision = room.precision('default_rate')
    snapshot = dict(version=1, rate_plan=rate_plan or None, room_type=room_type,
                    default_rate=flt(room.default_rate), precision=2 if precision is None else precision,
                    seasons=[], los_discounts=[])
    if room.get('property'):
        from hospitality_core.hospitality_core.api.property_scope import resolve
        from babel.numbers import get_currency_precision
        context = resolve(property, linked=('Hotel Room Type', room_type), currency=currency)
        snapshot.update(context, version=2, precision=get_currency_precision(context.currency))
        rates = [r for r in room.get('currency_rates', []) if r.currency == context.currency]
        if not rates and not room.get('is_virtual'):
            frappe.throw(_('Chưa có giá mặc định {0} cho loại phòng {1}.').format(context.currency, room_type))
        snapshot['default_rate'] = flt(rates[0].default_rate) if rates else 0
    if room_type == 'Virtual':
        snapshot.update(rate_plan=None, default_rate=0)
        return snapshot
    if rate_plan:
        plan = frappe.get_doc('Room Rate Plan', rate_plan)
        if snapshot.get('property') and (plan.property != snapshot['property'] or plan.currency != snapshot['currency']):
            frappe.throw(_('Bảng giá không khớp cơ sở hoặc tiền tệ.'))
        if not plan.active:
            frappe.throw(_('Bảng giá {0} đã ngừng áp dụng.').format(rate_plan))
        if plan.room_type != room_type:
            frappe.throw(_('Bảng giá {0} không thuộc loại phòng {1}.').format(rate_plan, room_type))
        snapshot['seasons'] = [dict(season_name=s.season_name, valid_from=str(s.valid_from),
            valid_to=str(s.valid_to), weekday_rate=flt(s.weekday_rate), weekend_rate=flt(s.weekend_rate))
            for s in plan.seasons]
        snapshot['los_discounts'] = [dict(min_nights=cint(t.min_nights), discount_percent=flt(t.discount_percent))
                                     for t in plan.los_discounts]
    return snapshot


def prepare_reservation(res):
    """Không tin snapshot do client gửi; chỉ server được tạo/cập nhật."""
    old = res.get_doc_before_save() if not res.is_new() else None
    changed = old and (old.rate_plan != res.rate_plan or old.room_type != res.room_type
        or old.get('membership') != res.get('membership') or old.get('currency') != res.get('currency'))
    if old and old.status != 'Reserved' and changed:
        frappe.throw(_('Không được đổi bảng giá hoặc loại phòng trực tiếp sau khi nhận phòng. Hãy dùng Chuyển phòng.'))
    if is_virtual(res):
        res.rate_plan = None
    if old and old.get('rate_snapshot') and not changed:
        res.rate_snapshot = old.rate_snapshot
        res.loyalty_snapshot = old.get('loyalty_snapshot')
    else:
        snapshot = snapshot_for(res.rate_plan, res.room_type, res.get('currency'), res.get('property'))
        if res.get('accounting_version') == 'Property v2':
            from hospitality_core.hospitality_core.api.guest_loyalty import snapshot as loyalty_snapshot
            policy = loyalty_snapshot(res)
            res.loyalty_snapshot = json.dumps(policy, ensure_ascii=False)
            snapshot.update(vip_percent=policy.get('vip_percent', 0), loyalty=policy)
        res.rate_snapshot = json.dumps(snapshot, ensure_ascii=False)
    # Validate manual discounts even when there are no room charges yet.
    quote_reservation(res, res.arrival_date)


def reservation_snapshot(res):
    raw = res.get('rate_snapshot')
    snapshot = json.loads(raw) if raw else snapshot_for(res.rate_plan, res.room_type, res.get('currency'), res.get('property'))
    if snapshot['room_type'] != res.room_type or (snapshot.get('rate_plan') or None) != (res.rate_plan or None):
        frappe.throw(_('Căn cứ giá không khớp đặt phòng. Vui lòng lưu lại đặt phòng.'))
    return snapshot


def quote_reservation(res, target_date, apply_los=True, apply_manual=True):
    try:
        return quote_day(reservation_snapshot(res), target_date,
            res.arrival_date if apply_los else None, res.departure_date if apply_los else None,
            res.discount_type if apply_manual else None, res.discount_value if apply_manual else 0,
            bool(res.get('is_complimentary')) if apply_manual else False)
    except ValueError as error:
        frappe.throw(str(error))


def charge_date_for_checkin(at=None):
    at = at or now_datetime()
    return add_days(at.date(), -1) if at.hour < 8 else str(at.date())


def post_daily_charge(res, target_date):
    if is_virtual(res) or not res.folio:
        return False
    # Cùng khóa với check-in và thay đổi ngày lưu trú, tránh ghi trùng giữa các worker.
    frappe.db.sql('SELECT name FROM `tabHotel Reservation` WHERE name=%s FOR UPDATE', res.name)
    from hospitality_core.hospitality_core.api.night_audit import already_charged_today, ensure_item_exists
    if already_charged_today(res.folio, target_date, room=res.room):
        return False
    quote = quote_reservation(res, target_date)
    snapshot = reservation_snapshot(res)
    if res.get('accounting_version') == 'Property v2':
        from hospitality_core.hospitality_core.api.property_accounting import tax_quote
        folio = frappe.get_doc('Guest Folio', res.folio)
        gross = tax_quote(folio, 'ROOM-RENT', quote['base_rate'], target_date).grand_total
        final_gross = tax_quote(folio, 'ROOM-RENT', quote['final_rate'], target_date).grand_total
    else:
        gross, final_gross = quote['base_rate'], quote['final_rate']
    bill_to = 'Company' if res.is_company_guest else 'Group' if res.get('is_group_guest') else 'Guest'
    if bill_to == 'Guest':
        rent_group = frappe.db.get_value('Item', 'ROOM-RENT', 'item_group')
        routing = frappe.get_all('Reservation Routing', filters={'parent': res.name}, fields=['item_group', 'bill_to'])
        bill_to = next((r.bill_to for r in routing if r.item_group == rent_group), bill_to)
    ensure_item_exists('ROOM-RENT', 'Room Rent')
    details = dict(quote, snapshot=snapshot, discount_type=res.discount_type,
                   discount_value=flt(res.discount_value), complimentary=bool(res.get('is_complimentary')),
                   room=res.room)
    common = dict(doctype='Folio Transaction', parent=res.folio, parenttype='Guest Folio',
                  parentfield='transactions', posting_date=str(target_date), qty=1, bill_to=bill_to,
                  pricing_reservation=res.name)
    rent = frappe.get_doc(dict(common, item='ROOM-RENT', amount=gross,
        description=f'Room Charge - {res.room}', pricing_details=json.dumps(details, ensure_ascii=False)))
    rent.flags.from_rate_plan = True
    rent.insert(ignore_permissions=True)
    if gross != final_gross:
        item = 'COMPLIMENTARY' if details['complimentary'] else 'DISCOUNT'
        ensure_item_exists(item, item)
        discount = frappe.get_doc(dict(common, item=item, amount=final_gross-gross, pricing_origin=rent.name,
            description=f"Room Discount - {res.room}: LOS {quote['los_percent']}% ({quote['los_discount']}), "
                        f"khác {quote['manual_discount']}"))
        discount.flags.from_rate_plan = True
        discount.insert(ignore_permissions=True)
    if res.get('accounting_version') == 'Property v2':
        from hospitality_core.hospitality_core.api.property_accounting import post_charge
        post_charge(res, rent, quote['final_rate'], target_date)
    return True


def reconcile_los(res):
    """Thêm chênh lệch vào ngày hiện tại; giữ nguyên tiền, ngày và hóa đơn gốc."""
    if is_virtual(res) or not res.folio:
        return
    frappe.db.sql('SELECT name FROM `tabHotel Reservation` WHERE name=%s FOR UPDATE', res.name)
    roots = frappe.get_all('Folio Transaction', filters={'pricing_reservation': res.name,
        'item': 'ROOM-RENT', 'is_void': 0, 'mirror_source': ['is', 'not set']},
        fields=['name', 'parent', 'bill_to', 'amount', 'pricing_details'])
    for root in roots:
        if not root.pricing_details:
            continue
        details = json.loads(root.pricing_details)
        nights = (getdate(res.departure_date) - getdate(res.arrival_date)).days
        desired = discount_breakdown(details['base_rate'], details['snapshot']['los_discounts'], nights,
            details['source'] == 'season', details['discount_type'], details['discount_value'],
            details['complimentary'], details['snapshot'].get('precision', 2), details['snapshot'].get('vip_percent', 0))
        # Locking read: tính cả những điều chỉnh vừa commit từ request khác.
        rows = frappe.db.sql('''SELECT name, amount FROM `tabFolio Transaction`
            WHERE pricing_origin=%s AND is_void=0 AND COALESCE(mirror_source, '')='' FOR UPDATE''',
            root.name, as_dict=True)
        tax_evidence = None
        rate_delta = None
        if res.get('accounting_version') == 'Property v2':
            from hospitality_core.hospitality_core.api.property_accounting import tax_quote, post_charge
            posting = frappe.get_doc('Hospitality Charge Posting', {'transaction_id': root.name})
            tax_evidence = json.loads(posting.evidence)
            sources = frappe.get_all('Hospitality Charge Posting',
                filters={'transaction_id': ['in', [root.name] + [r.name for r in rows]]}, fields=['evidence'])
            current_rate = sum(flt(json.loads(p.evidence)['rate']) for p in sources)
            rate_delta = money(desired['final_rate'] - current_rate, details['snapshot'].get('precision', 2))
            if not rate_delta:
                continue
            folio = frappe.get_doc('Guest Folio', root.parent)
            adjustment_quote = tax_quote(folio, 'ROOM-RENT', rate_delta, nowdate(), tax_evidence=tax_evidence)
            delta = adjustment_quote.grand_total
            target = tax_quote(folio, 'ROOM-RENT', desired['final_rate'], nowdate(), tax_evidence=tax_evidence)
            difference = target.grand_total - (flt(root.amount) + sum(flt(r.amount) for r in rows) + delta)
            if money(difference, target.precision('grand_total')):
                frappe.throw(_('Điều chỉnh có chênh lệch làm tròn thuế; cần chứng từ đối soát trước khi đổi số đêm.'))
        else:
            delta = money(desired['final_rate'] - (flt(root.amount) + sum(flt(r.amount) for r in rows)),
                          details['snapshot'].get('precision', 2))
        if not delta:
            continue
        if frappe.db.get_value('Guest Folio', root.parent, 'status') != 'Open':
            frappe.throw(_('Folio {0} đã đóng; cần xử lý điều chỉnh trước khi đổi số đêm.').format(root.parent))
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists('DISCOUNT', 'Room Discount')
        adjustment = frappe.get_doc(dict(doctype='Folio Transaction', parent=root.parent, parenttype='Guest Folio',
            parentfield='transactions', posting_date=nowdate(), item='DISCOUNT', qty=1, amount=delta,
            pricing_origin=root.name, pricing_reservation=res.name, bill_to=root.bill_to,
            pricing_details=json.dumps(dict(target=desired, nights=nights), ensure_ascii=False),
            description=f"LOS Adjustment - {details['room']}: {nights} đêm, {desired['los_percent']}%"
        ))
        adjustment.flags.from_rate_plan = True
        adjustment.insert(ignore_permissions=True)
        if rate_delta is not None:
            post_charge(res, adjustment, rate_delta, nowdate(), tax_evidence=tax_evidence)


def guard_legacy_repricing(res):
    """Không suy ngược giá gốc của giao dịch trước khi có căn cứ giá."""
    if not res.folio:
        return
    legacy = frappe.db.exists('Folio Transaction', {'parent': res.folio, 'item': 'ROOM-RENT',
        'is_void': 0, 'pricing_details': ['is', 'not set'], 'reference_doctype': ['!=', 'Folio Transaction']})
    if legacy and reservation_snapshot(res).get('los_discounts'):
        frappe.throw(_('Đặt phòng có tiền phòng lịch sử chưa lưu căn cứ giá. Cần đối soát khoản cũ trước khi đổi số đêm và áp dụng LOS.'))


@frappe.whitelist()
def preview_plan_configuration(room_type, seasons, los_discounts, arrival_date, departure_date):
    if not frappe.has_permission('Room Rate Plan', 'read'):
        frappe.throw(_('Không có quyền xem bảng giá.'), frappe.PermissionError)
    snapshot = snapshot_for(None, room_type)
    snapshot.update(seasons=frappe.parse_json(seasons), los_discounts=frappe.parse_json(los_discounts))
    try:
        return quote_stay(snapshot, arrival_date, departure_date)
    except (ValueError, KeyError, TypeError) as error:
        frappe.throw(_('Cấu hình giá chưa hợp lệ: {0}').format(error))


def void_pricing_charge(transaction, reason):
    """Hủy cả tiền phòng và giảm giá liên quan, giữ nguyên số tiền gốc để kiểm toán."""
    if transaction.get('pricing_origin') or transaction.get('mirror_source'):
        frappe.throw(_('Hãy hủy dòng tiền phòng gốc để xử lý cả các khoản giảm giá liên quan.'))
    frappe.db.sql('SELECT name FROM `tabHotel Reservation` WHERE name=%s FOR UPDATE', transaction.pricing_reservation)
    rows = [transaction]
    rows += [frappe.get_doc('Folio Transaction', r.name) for r in frappe.get_all('Folio Transaction',
        filters={'pricing_origin': transaction.name, 'is_void': 0, 'mirror_source': ['is', 'not set']}, fields=['name'])]
    originals = [r.name for r in rows]
    rows += [frappe.get_doc('Folio Transaction', r.name) for r in frappe.get_all('Folio Transaction',
        filters={'mirror_source': ['in', originals], 'is_void': 0}, fields=['name'])]
    if any(r.is_invoiced for r in rows):
        frappe.throw(_('Khoản tiền phòng hoặc giảm giá đã lên hóa đơn; cần xử lý hóa đơn điều chỉnh trước.'))
    for row in rows:
        row.flags.from_rate_plan = True
        row.is_void = 1
        row.void_reason = reason
        row.save(ignore_permissions=True)
