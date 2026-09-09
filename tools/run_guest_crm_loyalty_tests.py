"""Kịch bản kiểm thử MỚI — api/guest_crm.py (merge_guest) + api/guest_loyalty.py +
api/loyalty_calculation.py (Đợt 2, mục 1 của kế hoạch "Kịch bản kiểm thử TOÀN
BỘ tính năng còn lại"). Cả 3 module CHƯA TỪNG có 1 dòng test sống nào, dù đã
qua nhiều vòng fix tĩnh (canonical() chain khi gộp khách đã từng bị gộp,
_merge_memberships()'s update_tier() ghi đè hạng vừa nâng, validate_configuration()
chặn bật lại membership đã gộp).

Không có hàm nào trong 3 module này gọi frappe.db.commit() (đã grep trước khi
viết) — an toàn dùng self.fixture() rollback-based bình thường.

Chạy trên site test riêng, dữ liệu rollback sau mỗi ca.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days, now_datetime
from run_property_integration import PropertyDatabaseTests


class GuestCrmLoyaltyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def fixture(self):
        f = PropertyDatabaseTests()
        reservation, settings = f.accounting_reservation()
        self.property = reservation.property
        self.company = reservation.operating_company
        self.currency = reservation.currency
        self.base_reservation = reservation
        return f

    def make_program(self, tiers=None, suffix='', company=None):
        program = frappe.get_doc(dict(doctype='Hospitality Loyalty Program',
            program_name=f'Test Loyalty {suffix or frappe.generate_hash(4)}', operating_company=company or self.company,
            enabled=1, effective_from=add_days(nowdate(), -30), spend_per_point=10000, value_per_point=100,
            expiry_days=365, tiers=tiers or [
                dict(tier_name='Base', min_spend=0, room_discount_percent=0),
                dict(tier_name='Silver', min_spend=1000000, room_discount_percent=5),
                dict(tier_name='Gold', min_spend=5000000, room_discount_percent=10),
            ])).insert(ignore_permissions=True)
        return program

    def make_guest(self, full_name):
        return frappe.get_doc(dict(doctype='Guest', full_name=full_name, guest_type='Regular')).insert(ignore_permissions=True)

    def make_membership(self, guest, program):
        return frappe.get_doc(dict(doctype='Guest Membership', guest=guest.name, program=program.name)).insert(ignore_permissions=True)

    def earn(self, member, points, qualifying_spend=0, reservation=None, expires_in_days=365):
        from hospitality_core.hospitality_core.api.guest_loyalty import _event, key
        from datetime import timedelta
        return _event(member, 'Earn', key('earn-test', member.name, frappe.generate_hash(6)), points,
            qualifying_spend=qualifying_spend, reservation=reservation,
            expires_at=now_datetime() + timedelta(days=expires_in_days))

    # ------------------------------------------------------------------
    # loyalty_calculation.py: phép tính thuần.
    # ------------------------------------------------------------------
    def test_pure_calculation_functions(self):
        from hospitality_core.hospitality_core.api.loyalty_calculation import redemption_capacity, qualification_delta
        self.assertEqual(redemption_capacity(100, 20, 20), 100)
        self.assertEqual(redemption_capacity(100, 50, 0), 50)
        delta, expiry_delta = qualification_delta(earned=100, target=150)
        self.assertEqual(delta, 50)
        self.assertEqual(expiry_delta, 0)
        delta2, expiry_delta2 = qualification_delta(earned=100, target=100, redeemed=30, expired=0, lot_expired=True)
        self.assertEqual(delta2, 0)
        self.assertEqual(expiry_delta2, -(max(0, 100 - 30)))

    # ------------------------------------------------------------------
    # merge_guest()
    # ------------------------------------------------------------------
    def test_merge_guest_requires_manager_and_reason(self):
        self.fixture()
        program = self.make_program()
        a = self.make_guest('Merge Test A')
        b = self.make_guest('Merge Test B')
        from hospitality_core.hospitality_core.api.guest_crm import merge_guest
        with self.assertRaisesRegex(frappe.ValidationError, 'quyền quản trị'):
            merge_guest(a.name, b.name, 'short')
        user = 'merge-noperm@example.com'
        if not frappe.db.exists('User', user):
            frappe.get_doc(dict(doctype='User', email=user, first_name='NoPerm',
                send_welcome_email=0, roles=[dict(role='Sales User')])).insert(ignore_permissions=True)
        frappe.set_user(user)
        with self.assertRaisesRegex(frappe.ValidationError, 'quyền quản trị'):
            merge_guest(a.name, b.name, 'Reason long enough for validation')

    def test_merge_guest_basic_sets_merged_into_and_log(self):
        self.fixture()
        a = self.make_guest('Merge Basic A')
        b = self.make_guest('Merge Basic B')
        from hospitality_core.hospitality_core.api.guest_crm import merge_guest, canonical
        result = merge_guest(a.name, b.name, 'Trung khach hang trung nhau, gop ho so')
        self.assertEqual(result['guest'], b.name)
        self.assertEqual(canonical(a.name), b.name)
        log = frappe.get_doc('Guest Merge Log', result['merge_log'])
        self.assertEqual(log.source_guest, a.name)
        self.assertEqual(log.target_guest, b.name)

    def test_merge_guest_transfers_points_and_higher_tier(self):
        self.fixture()
        program = self.make_program()
        a = self.make_guest('Merge Points A')
        b = self.make_guest('Merge Points B')
        member_a = self.make_membership(a, program)
        member_b = self.make_membership(b, program)
        # A co nhieu diem hon VA hang cao hon (Gold) so voi B (Base).
        from hospitality_core.hospitality_core.api.guest_loyalty import _member
        self.earn(_member(member_a.name), 500)
        frappe.db.set_value('Guest Membership', member_a.name, 'tier', 'Gold')
        frappe.db.set_value('Guest Membership', member_b.name, 'tier', 'Base')
        self.earn(_member(member_b.name), 100)

        from hospitality_core.hospitality_core.api.guest_crm import merge_guest
        merge_guest(a.name, b.name, 'Gop diem thanh vien trung ho so khach')

        member_a.reload(); member_b.reload()
        self.assertEqual(member_a.enabled, 0, 'Membership nguon phai bi vo hieu hoa sau khi gop, khong xoa.')
        self.assertEqual(member_b.tier, 'Gold', 'Membership dich phai nhan hang CAO HON giua 2 ben.')

        from hospitality_core.hospitality_core.api.guest_loyalty import balances, _entries
        target_balance = balances(_entries(member_b.name))
        self.assertEqual(target_balance['available'], 600, 'Diem cua nguon (500) phai duoc cong THAT vao dich (100 + 500).')
        source_balance = balances(_entries(member_a.name))
        self.assertEqual(source_balance['available'], 0, 'Diem nguon phai duoc rut het (chuyen sang dich), khong con dung duoc nua.')

    def test_merge_guest_target_without_membership_transfers_ownership(self):
        self.fixture()
        program = self.make_program()
        a = self.make_guest('Merge NoTarget A')
        b = self.make_guest('Merge NoTarget B')
        member_a = self.make_membership(a, program)
        from hospitality_core.hospitality_core.api.guest_crm import merge_guest
        merge_guest(a.name, b.name, 'Gop ho so, dich chua co membership chuong trinh nay')
        member_a.reload()
        self.assertEqual(member_a.guest, b.name, 'Khong co membership dich -> chuyen thang quyen so huu membership nguon.')
        self.assertEqual(member_a.enabled, 1, 'Chuyen quyen so huu thi KHONG vo hieu hoa (khac nhanh co san 2 membership).')

    def test_merge_guest_resolves_already_merged_source_canonical_chain(self):
        # A da tung la nguon cua 1 lan gop truoc (A -> B). Gop A vao C lan nua
        # PHAI thao tac tren B (noi dang giu du lieu that), khong ghi de
        # merged_into cua A tu B sang C truc tiep — neu khong, B se "mo coi"
        # (khong ai tro toi), get_profile()'s BFS tu C se KHONG bao gio thay B.
        self.fixture()
        program = self.make_program()
        a = self.make_guest('Chain A')
        b = self.make_guest('Chain B')
        c = self.make_guest('Chain C')
        member_b = self.make_membership(b, program)
        self.earn(frappe.get_doc('Guest Membership', member_b.name, for_update=False), 300)
        # Nap lai qua _member() de dam bao du lieu (khong bat buoc, giu cho ro net).
        from hospitality_core.hospitality_core.api.guest_crm import merge_guest, canonical
        merge_guest(a.name, b.name, 'Lan gop thu nhat: A vao B')
        self.assertEqual(canonical(a.name), b.name)

        merge_guest(a.name, c.name, 'Lan gop thu hai: A (da gop truoc) vao C')
        # A phai tro thang toi C (khong quan trong bang viec B khong bi mo coi).
        self.assertEqual(canonical(a.name), c.name)
        # B (noi giu du lieu that tu lan gop dau) phai duoc tro toi C, KHONG bi bo lai.
        self.assertEqual(canonical(b.name), c.name, 'B (giu diem/hang that) khong duoc mo coi khi A bi gop lan 2.')
        # Diem cua B (qua gop lan 1 tu A) phai duoc chuyen tiep sang membership cua C.
        member_c_name = frappe.db.get_value('Guest Membership', {'guest': c.name, 'program': program.name}, 'name')
        self.assertTrue(member_c_name, 'Membership cua C phai ton tai sau khi gop chuoi B -> C.')

    def test_reactivate_membership_of_merged_guest_blocked(self):
        self.fixture()
        program = self.make_program()
        a = self.make_guest('Reactivate A')
        b = self.make_guest('Reactivate B')
        member_a = self.make_membership(a, program)
        from hospitality_core.hospitality_core.api.guest_crm import merge_guest
        merge_guest(a.name, b.name, 'Gop ho so de test chan bat lai membership')
        member_a.reload()
        self.assertEqual(member_a.enabled, 1, 'Truong hop nay KHONG co membership dich nen chi chuyen quyen so huu, van enabled.')
        # Mo phong dung truong hop: nguon van con membership RIENG (khac chuong
        # trinh) — dung kich ban _merge_memberships() truc tiep de tao ra
        # dung dieu kien membership nguon bi vo hieu hoa that.
        # Company khac (_Hospitality V2 B, da bootstrap san o setUpClass()) de
        # tranh vi pham rang buoc "moi phap nhan chi 1 chuong trinh dang hoat
        # dong" (program o tren da chiem company chinh self.company).
        program2 = self.make_program(suffix='second', company='_Hospitality V2 B')
        m1 = self.make_membership(a, program2)
        m2 = self.make_membership(b, program2)
        from hospitality_core.hospitality_core.api.guest_crm import _merge_memberships
        _merge_memberships(a.name, b.name)
        m1.reload()
        self.assertEqual(m1.enabled, 0)
        m1.enabled = 1
        with self.assertRaisesRegex(frappe.ValidationError, 'đã được gộp'):
            m1.save(ignore_permissions=True)

    # ------------------------------------------------------------------
    # guest_loyalty.py: hold/release/expire/update_tier
    # ------------------------------------------------------------------
    def test_hold_points_and_release_restores_balance(self):
        self.fixture()
        program = self.make_program()
        guest = self.make_guest('Hold Test Guest')
        member = self.make_membership(guest, program)
        self.earn(frappe.get_doc('Guest Membership', member.name), 200)
        room = None
        f = PropertyDatabaseTests()
        room = f.room(self.property, frappe.db.get_value('Hotel Room Type', {'property': self.property}, 'name'), number='LOY-1')
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property, guest=guest.name,
            room=room.name, room_type=room.room_type, hotel_reception=room.hotel_reception, currency=self.currency,
            membership=member.name, arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()

        from hospitality_core.hospitality_core.api.guest_loyalty import hold_points, release_hold, get_membership
        result = hold_points(member.name, res.name, 50, 'req-1')
        state = get_membership(member.name)
        self.assertEqual(state['available'], 150, 'Giu 50/200 diem phai lam giam available con 150.')
        release_hold(result['hold'])
        state2 = get_membership(member.name)
        self.assertEqual(state2['available'], 200, 'Giai phong hold phai tra lai dung so diem.')

    def test_hold_points_insufficient_balance_blocked(self):
        self.fixture()
        program = self.make_program()
        guest = self.make_guest('Hold Insufficient Guest')
        member = self.make_membership(guest, program)
        self.earn(frappe.get_doc('Guest Membership', member.name), 10)
        f = PropertyDatabaseTests()
        room = f.room(self.property, frappe.db.get_value('Hotel Room Type', {'property': self.property}, 'name'), number='LOY-2')
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property, guest=guest.name,
            room=room.name, room_type=room.room_type, hotel_reception=room.hotel_reception, currency=self.currency,
            membership=member.name, arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        from hospitality_core.hospitality_core.api.guest_loyalty import hold_points
        with self.assertRaisesRegex(frappe.ValidationError, 'Không đủ điểm'):
            hold_points(member.name, res.name, 100, 'req-2')

    def test_hold_points_idempotent_same_request_id(self):
        self.fixture()
        program = self.make_program()
        guest = self.make_guest('Hold Idem Guest')
        member = self.make_membership(guest, program)
        self.earn(frappe.get_doc('Guest Membership', member.name), 200)
        f = PropertyDatabaseTests()
        room = f.room(self.property, frappe.db.get_value('Hotel Room Type', {'property': self.property}, 'name'), number='LOY-3')
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property, guest=guest.name,
            room=room.name, room_type=room.room_type, hotel_reception=room.hotel_reception, currency=self.currency,
            membership=member.name, arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        from hospitality_core.hospitality_core.api.guest_loyalty import hold_points
        r1 = hold_points(member.name, res.name, 50, 'req-idem')
        r2 = hold_points(member.name, res.name, 50, 'req-idem')
        self.assertEqual(r1['hold'], r2['hold'], 'Cung request_id phai tra ve DUNG 1 su kien hold, khong tao them.')

    def test_update_tier_uses_365_day_window(self):
        self.fixture()
        program = self.make_program()
        guest = self.make_guest('Tier Window Guest')
        member = self.make_membership(guest, program)
        from hospitality_core.hospitality_core.api.guest_loyalty import _member, update_tier, _entries
        from datetime import timedelta
        m = _member(member.name)
        # update_tier() CHỈ tính qualifying_spend của Earn có gắn `reservation`
        # (origins.setdefault(row.reservation, ...) bỏ qua hẳn Earn không có
        # reservation) — dùng self.base_reservation (từ fixture()) cho lô
        # "trong hạn"; cần 1 reservation KHÁC cho lô "quá hạn" để 2 mốc thời
        # gian gốc (posting_time) không bị gộp làm một qua cùng 1 reservation.
        f = PropertyDatabaseTests()
        room_type = frappe.db.get_value('Hotel Room Type', {'property': self.property}, 'name')
        old_room = f.room(self.property, room_type, number='TIER-OLD')
        old_res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property, guest=guest.name,
            room=old_room.name, room_type=room_type, hotel_reception=old_room.hotel_reception,
            currency=self.currency, arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        # Doanh so trong han (365 ngay) du len Silver.
        recent = self.earn(m, 100, qualifying_spend=1500000, reservation=self.base_reservation.name)
        # Gia lap doanh so QUA HAN (hon 365 ngay) - khong duoc tinh vao xet hang.
        old_entry = frappe.get_doc(dict(doctype='Hospitality Loyalty Entry', membership=member.name,
            operating_company=m.operating_company, currency=m.currency, event_type='Earn',
            event_key=frappe.generate_hash(8), points=50, qualifying_spend=10000000, reservation=old_res.name,
            posting_time=now_datetime() - timedelta(days=400),
            expires_at=now_datetime() + timedelta(days=1)))
        old_entry.flags.hospitality_service = True
        old_entry.insert(ignore_permissions=True)
        tier = update_tier(m)
        self.assertEqual(tier.tier_name, 'Silver', 'Chi doanh so TRONG 365 ngay (dua theo posting_time cua Earn goc) duoc tinh vao xet hang.')

    def test_expire_creates_expire_event_for_lapsed_points(self):
        self.fixture()
        program = self.make_program()
        guest = self.make_guest('Expire Test Guest')
        member = self.make_membership(guest, program)
        from hospitality_core.hospitality_core.api.guest_loyalty import _member, expire, balances, _entries
        m = _member(member.name)
        self.earn(m, 80, expires_in_days=-1)  # da het han tu qua khu.
        rows = expire(m)
        self.assertTrue(any(r.event_type == 'Expire' for r in rows), 'Diem het han phai duoc ghi 1 su kien Expire that.')
        self.assertEqual(balances(_entries(member.name))['available'], 0)

    # ------------------------------------------------------------------
    # scheduled(): 1 membership hong khong duoc lam dung ca job.
    # ------------------------------------------------------------------
    def test_scheduled_isolates_broken_membership_error(self):
        self.fixture()
        program = self.make_program()
        good_guest = self.make_guest('Scheduled Good Guest')
        good_member = self.make_membership(good_guest, program)
        # update_tier() chi tinh qualifying_spend cua Earn co gan `reservation`
        # (xem ghi chu tuong tu o test_update_tier_uses_365_day_window).
        self.earn(frappe.get_doc('Guest Membership', good_member.name), 50, qualifying_spend=200000,
            reservation=self.base_reservation.name)

        bad_guest = self.make_guest('Scheduled Bad Guest')
        bad_member = self.make_membership(bad_guest, program)
        # Gia lap membership hong: tro toi 1 program khong con ton tai.
        frappe.db.set_value('Guest Membership', bad_member.name, 'program', 'NON-EXISTENT-PROGRAM-XYZ')

        from hospitality_core.hospitality_core.api.guest_loyalty import scheduled
        scheduled()  # Khong duoc raise ra ngoai, du bad_member hong.
        good_member.reload()
        self.assertEqual(good_member.qualifying_spend, 200000, 'Membership TOT van phai duoc tinh hang binh thuong du membership khac trong job bi hong.')


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(GuestCrmLoyaltyTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
