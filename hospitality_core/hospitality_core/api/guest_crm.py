"""Hồ sơ chung; truy vấn lịch sử luôn qua quyền cơ sở."""
from collections import defaultdict
import json
from datetime import timedelta
import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime
from hospitality_core.hospitality_core.api.property_scope import manager


def canonical(guest):
    seen=set()
    while guest:
        if guest in seen:
            frappe.throw(_('Mapping hồ sơ khách có vòng lặp.'))
        seen.add(guest)
        target=frappe.db.get_value('Guest',guest,'merged_into')
        if not target:
            return guest
        guest=target


@frappe.whitelist()
def get_profile(guest):
    if not guest:
        return {}
    doc=frappe.get_doc('Guest',canonical(guest))
    doc.check_permission('read')
    guests=[doc.name]
    frontier=[doc.name]
    while frontier:
        frontier=frappe.get_all('Guest',filters={'merged_into':['in',frontier],'name':['not in',guests]},pluck='name')
        guests.extend(frontier)
    history=frappe.get_list('Hotel Reservation',filters={'guest':['in',guests]},
        fields=['name','status','arrival_date','departure_date','room','room_type','folio','property','currency'],
        order_by='departure_date desc',limit_page_length=0)
    folios=frappe.get_list('Guest Folio',filters={'guest':['in',guests]},
        fields=['name','status','property','currency','outstanding_balance','total_charges','total_discounts'],limit_page_length=0)
    indexed={f.name:f for f in folios}
    spend=defaultdict(float); balances=defaultdict(float)
    for f in folios:
        if f.status=='Closed':
            spend[f.currency or 'Chưa ánh xạ']+=flt(f.total_charges)-flt(f.total_discounts)
        balances[f.currency or 'Chưa ánh xạ']+=flt(f.outstanding_balance)
    rooms = {h.room for h in history if h.room}
    room_map = {}
    if rooms:
        room_data = frappe.get_all("Hotel Room", filters={"name": ["in", list(rooms)]}, fields=["name", "room_number"])
        room_map = {r.name: r.room_number for r in room_data}
    for h in history:
        f=indexed.get(h.folio)
        h.balance=flt(f.outstanding_balance) if f else None
        h.room_number = room_map.get(h.room) or h.room
    visits=[h for h in history if h.status=='Checked Out']
    preferences=frappe.get_list('Guest Preference',filters={'guest':['in',guests],'active':1},
        or_filters=[['valid_until','is','not set'],['valid_until','>=',frappe.utils.nowdate()]],
        fields=['name','preference_type','preference_value','sharing_scope','property','valid_until'],limit_page_length=0)
    memberships=frappe.get_list('Guest Membership',filters={'guest':['in',guests]},
        fields=['name','program','operating_company','currency','tier','qualifying_spend'],limit_page_length=0)
    # Không chuyển việc đọc hồ sơ thành mutation sổ điểm.
    from hospitality_core.hospitality_core.api.guest_loyalty import balances as point_balance
    for m in memberships:
        rows=frappe.get_all('Hospitality Loyalty Entry',filters={'membership':m.name},
            fields=['name','event_type','points','source_entry','expires_at','evidence'])
        m.update(point_balance(rows))
    interactions=frappe.get_list('Guest Interaction',filters={'guest':['in',guests],'status':['!=','Resolved']},
        fields=['name','subject','status','assigned_to','property'],limit_page_length=100)
    last=visits[0] if visits else None
    last_room_no = room_map.get(last.room) if (last and last.room) else None
    return dict(guest=doc.as_dict(),history=history[:200],history_count=len(history),preferences=preferences,
        memberships=memberships,interactions=interactions,spend_by_currency=dict(spend),balances_by_currency=dict(balances),
        stats=dict(total_stays=len(visits),total_spend=next(iter(spend.values())) if len(spend)==1 else None,
            avg_rate=None,last_room=last_room_no,last_visit=last.departure_date if last else None))


def _merge_memberships(source_guest,target_guest):
    """TRƯỚC ĐÂY: merge_guest() chỉ ghi quan hệ merged_into, KHÔNG hợp nhất
    Guest Membership — nếu cả 2 khách đã có membership RIÊNG trong CÙNG 1
    chương trình, sau khi gộp khách vẫn tồn tại 2 tài khoản điểm tách biệt (2
    số dư/2 hạng khác nhau), get_profile() liệt kê cả 2 thay vì 1 hồ sơ điểm
    duy nhất — tính năng "gộp" không thực sự gộp phần loyalty, khách có thể
    mất quyền lợi (điểm/hạng) đang nằm ở tài khoản không được xem tới.

    Sửa: với mỗi chương trình mà CẢ 2 khách đều có membership đang hoạt động,
    chuyển toàn bộ điểm KHẢ DỤNG (available, đã trừ phần đang giữ/hết hạn) từ
    membership nguồn sang membership đích qua 1 cặp sự kiện Earn/Redeem có
    nguồn rõ ràng (khớp mẫu "mọi thay đổi điểm là sự kiện có nguồn" của module
    này — không cộng thẳng vào field số dư), rồi lấy HẠNG CAO HƠN giữa 2 tài
    khoản (so theo min_spend của tier) làm hạng tạm thời cho membership đích
    ngay tại thời điểm gộp. Membership nguồn được VÔ HIỆU HÓA (enabled=0,
    KHÔNG xóa — property_scope.py's prevent_trash() chặn xóa mọi bản ghi có
    Guest Membership để giữ lịch sử kiểm toán) để không còn được dùng để
    tích/đổi điểm nữa, nhưng lịch sử Hospitality Loyalty Entry của nó vẫn còn
    nguyên để tra cứu.

    LƯU Ý: hạng "lấy cao hơn" ở đây là snapshot ngay lúc gộp — hạng THẬT SỰ
    vẫn do update_tier() tính lại theo tổng doanh số hưởng hạng trong 365
    ngày ở các lần chạy sau (guest_loyalty.py's scheduled()/reconcile_reservation()),
    nên nếu doanh số thật của tài khoản đích không đủ duy trì hạng đó, hạng
    có thể tự động hạ lại ở lần tính tiếp theo — đây là giới hạn đã biết, chấp
    nhận được vì hạng thành viên vốn được thiết kế phản ánh doanh số thật,
    không phải thứ merge có thể ghi đè vĩnh viễn.
    """
    from hospitality_core.hospitality_core.api.guest_loyalty import _member, _event, balances, _entries, key

    source_memberships = frappe.get_all('Guest Membership', filters={'guest': source_guest, 'enabled': 1},
        fields=['name', 'program'])
    if not source_memberships:
        return
    target_memberships = {m.program: m.name for m in frappe.get_all('Guest Membership',
        filters={'guest': target_guest, 'enabled': 1}, fields=['name', 'program'])}

    for sm in source_memberships:
        target_name = target_memberships.get(sm.program)
        if not target_name:
            # target_guest does not yet have a membership in this program: transfer ownership of source membership
            frappe.db.set_value('Guest Membership', sm.name, 'guest', target_guest)
            target_memberships[sm.program] = sm.name
            continue
        if target_name == sm.name:
            continue
        source_member = _member(sm.name, lock=True)
        target_member = _member(target_name, lock=True)
        program = frappe.get_doc('Hospitality Loyalty Program', target_member.program)

        state = balances(_entries(source_member.name))
        if state['available'] > 0:
            _event(target_member, 'Earn', key('merge-in', sm.name, target_name), state['available'],
                evidence=json.dumps({'reason': 'Chuyển điểm sau khi gộp hồ sơ khách', 'source_membership': sm.name}),
                expires_at=now_datetime() + timedelta(days=program.expiry_days))
            _event(source_member, 'Redeem', key('merge-out', sm.name, target_name), -state['available'],
                evidence=json.dumps({'reason': 'Đã chuyển sang membership đích sau khi gộp hồ sơ khách', 'target_membership': target_name}))

        tier_min_spend = {t.tier_name: t.min_spend for t in program.tiers}
        if tier_min_spend.get(source_member.tier, -1) > tier_min_spend.get(target_member.tier, -1):
            frappe.db.set_value('Guest Membership', target_member.name, 'tier', source_member.tier)

        source_member.flags.hospitality_service = True
        source_member.enabled = 0
        source_member.save(ignore_permissions=True)
        # KHÔNG gọi update_tier() ở đây: update_tier() tính lại tier THUẦN TÚY
        # từ qualifying_spend gắn với reservation trong 365 ngày qua — không
        # hề biết gì về hạng vừa gán ở trên, nên gọi ngay tại đây sẽ GHI ĐÈ
        # LẠI hạng vừa nâng NGAY TRONG CÙNG LỆNH GỌI (không phải "tự hạ lại ở
        # lần chạy sau" như kỳ vọng) — vô hiệu hóa hoàn toàn phần "lấy hạng
        # cao hơn". Để tier vừa gán đứng nguyên tới khi guest_loyalty.py's
        # scheduled()/reconcile_reservation() tự nhiên tính lại theo lịch của
        # riêng nó, đúng như đã ghi trong docstring của hàm này.


@frappe.whitelist(methods=['POST'])
def merge_guest(source_guest,target_guest,reason):
    if not manager() or len(str(reason or '').strip())<10:
        frappe.throw(_('Cần quyền quản trị và lý do gộp hồ sơ ít nhất 10 ký tự.'))
    target=canonical(target_guest)
    # source_guest CÓ THỂ đã từng là nguồn của 1 lần gộp trước đó (đã có
    # merged_into trỏ đi nơi khác, VD B) — nếu merge thẳng theo source_guest,
    # sẽ GHI ĐÈ merged_into của source_guest từ B sang target hiện tại, làm
    # đứt mạch: B (nơi đang thực sự giữ điểm/hạng đã được hợp nhất từ lần gộp
    # trước) không còn được bất kỳ ai trỏ tới nữa, get_profile()'s BFS không
    # bao giờ tìm lại được B — điểm/hạng của B coi như mất trắng vĩnh viễn.
    # Phải luôn thao tác trên hồ sơ CANONICAL của source_guest (nơi dữ liệu
    # thật sự đang nằm), không phải trên chính source_guest nếu nó đã bị gộp.
    effective_source=canonical(source_guest)
    if effective_source==target:
        frappe.throw(_('Hai hồ sơ đã cùng định danh.'))
    source=frappe.get_doc('Guest',effective_source,for_update=True)
    source.check_permission('write')
    # Giữ nguyên nguồn chứng từ và membership; chỉ thêm quan hệ định danh.
    source.merged_into=target
    source.flags.hospitality_service=True
    source.save(ignore_permissions=True)
    log=frappe.get_doc(dict(doctype='Guest Merge Log',source_guest=source_guest,target_guest=target,
        reason=reason,performed_by=frappe.session.user))
    log.flags.hospitality_service=True
    log.insert(ignore_permissions=True)
    _merge_memberships(source.name,target)
    return dict(guest=target,merge_log=log.name)
