"""Kịch bản kiểm thử MỚI — api/folio_operations.py phần còn lại (Đợt 2, mục 3
của kế hoạch "Kịch bản kiểm thử TOÀN BỘ tính năng còn lại"): merge_folios(),
omni_search(), get_split_tour_preview()/execute_split_tour_folio(). split_transaction()
đã được kiểm thử sống ở Bước 4 (run_docker_verification.py) trước đó, không
lặp lại ở đây.

Không có hàm nào trong folio_operations.py/folio.py gọi frappe.db.commit()
(đã grep trước khi viết) — an toàn dùng self.fixture() rollback-based.

Chạy trên site test riêng, dữ liệu rollback sau mỗi ca.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days
from run_property_integration import PropertyDatabaseTests


class FolioOperationsTests(unittest.TestCase):
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
        self.room_type = reservation.room_type
        self.reservation = reservation
        return f

    def make_reservation(self, f, full_name, number):
        room = f.room(self.property, self.room_type, number=number)
        guest = frappe.get_doc(dict(doctype='Guest', full_name=full_name, guest_type='Regular')).insert(ignore_permissions=True)
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property, guest=guest.name,
            room=room.name, room_type=self.room_type, hotel_reception=room.hotel_reception,
            currency=self.currency, arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        frappe.db.set_value('Guest Folio', res.folio, 'status', 'Open')
        return room, guest, res

    def make_charge(self, folio_name, item='MISC', amount=100000, bill_to='Guest'):
        if not frappe.db.exists('Item', item):
            frappe.get_doc(dict(doctype='Item', item_code=item, item_name=item, item_group='Services',
                stock_uom='Nos', is_stock_item=0, is_sales_item=1)).insert(ignore_permissions=True)
        txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=folio_name, parenttype='Guest Folio',
            parentfield='transactions', posting_date=nowdate(), item=item, description='Test charge',
            qty=1, amount=amount, bill_to=bill_to, is_void=0))
        txn.flags.hospitality_service = True
        txn.insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.api.folio import sync_folio_balance
        sync_folio_balance(frappe.get_doc('Guest Folio', folio_name))
        return txn

    def make_user(self, email, roles):
        if not frappe.db.exists('User', email):
            frappe.get_doc(dict(doctype='User', email=email, first_name=email.split('@')[0],
                send_welcome_email=0, roles=[dict(role=r) for r in roles])).insert(ignore_permissions=True)
        return email

    # ------------------------------------------------------------------
    # merge_folios()
    # ------------------------------------------------------------------
    def test_merge_folios_moves_transactions_and_closes_source(self):
        f = self.fixture()
        room_a, guest_a, res_a = self.make_reservation(f, 'Merge Folio Guest A', 'FO-1')
        room_b, guest_b, res_b = self.make_reservation(f, 'Merge Folio Guest B', 'FO-2')
        self.make_charge(res_a.folio, amount=150000)
        from hospitality_core.hospitality_core.api.folio_operations import merge_folios
        result = merge_folios(res_a.folio, res_b.folio)
        self.assertEqual(result, res_b.folio)
        self.assertEqual(frappe.db.get_value('Guest Folio', res_a.folio, 'status'), 'Closed')
        self.assertEqual(frappe.db.get_value('Guest Folio', res_b.folio, 'outstanding_balance'), 150000,
            'So du phai duoc chuyen THAT sang folio dich, khong chi doi trang thai.')

    def test_merge_folios_requires_both_open(self):
        f = self.fixture()
        room_a, guest_a, res_a = self.make_reservation(f, 'Merge Closed Guest A', 'FO-3')
        room_b, guest_b, res_b = self.make_reservation(f, 'Merge Closed Guest B', 'FO-4')
        frappe.db.set_value('Guest Folio', res_b.folio, 'status', 'Closed')
        from hospitality_core.hospitality_core.api.folio_operations import merge_folios
        with self.assertRaisesRegex(frappe.ValidationError, 'must be Open'):
            merge_folios(res_a.folio, res_b.folio)

    def test_merge_folios_rejects_same_folio(self):
        f = self.fixture()
        room_a, guest_a, res_a = self.make_reservation(f, 'Merge Same Guest', 'FO-5')
        from hospitality_core.hospitality_core.api.folio_operations import merge_folios
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be the same'):
            merge_folios(res_a.folio, res_a.folio)

    def test_merge_folios_requires_supervisor_role(self):
        f = self.fixture()
        room_a, guest_a, res_a = self.make_reservation(f, 'Merge Perm Guest A', 'FO-6')
        room_b, guest_b, res_b = self.make_reservation(f, 'Merge Perm Guest B', 'FO-7')
        user = self.make_user('folio-noperm@example.com', ['Sales User'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.folio_operations import merge_folios
        with self.assertRaisesRegex(frappe.ValidationError, 'Access Denied'):
            merge_folios(res_a.folio, res_b.folio)

    # ------------------------------------------------------------------
    # omni_search()
    # ------------------------------------------------------------------
    def test_omni_search_finds_by_name_phone_room(self):
        f = self.fixture()
        room, guest, res = self.make_reservation(f, 'Omni Search Target', 'FO-OMNI-1')
        frappe.db.set_value('Guest', guest.name, 'mobile_no', '0909123456')
        from hospitality_core.hospitality_core.api.folio_operations import omni_search
        by_name = omni_search('Omni Search Target')
        self.assertTrue(any(r.reservation == res.name for r in by_name))
        by_phone = omni_search('0909123456')
        self.assertTrue(any(r.reservation == res.name for r in by_phone))
        by_room = omni_search('FO-OMNI-1')
        self.assertTrue(any(r.reservation == res.name for r in by_room))

    def test_omni_search_requires_permission(self):
        self.fixture()
        user = self.make_user('omni-noperm@example.com', ['Sales User'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.folio_operations import omni_search
        with self.assertRaises(frappe.PermissionError):
            omni_search('anything')

    def test_omni_search_ignores_too_short_query(self):
        self.fixture()
        from hospitality_core.hospitality_core.api.folio_operations import omni_search
        self.assertEqual(omni_search('a'), [])
        self.assertEqual(omni_search(''), [])

    def test_omni_search_excludes_checked_out_and_cancelled(self):
        f = self.fixture()
        room, guest, res = self.make_reservation(f, 'Omni Gone Guest', 'FO-OMNI-2')
        frappe.db.set_value('Hotel Reservation', res.name, 'status', 'Checked Out')
        from hospitality_core.hospitality_core.api.folio_operations import omni_search
        results = omni_search('Omni Gone Guest')
        self.assertFalse(any(r.reservation == res.name for r in results),
            'Chi tim khach dang Reserved/Checked In, khong tim khach da Checked Out.')

    # ------------------------------------------------------------------
    # get_split_tour_preview() / execute_split_tour_folio()
    # ------------------------------------------------------------------
    def test_split_tour_preview_separates_room_and_incidental_charges(self):
        f = self.fixture()
        room, guest, res = self.make_reservation(f, 'Split Tour Guest', 'FO-SPLIT-1')
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists('ROOM-RENT', 'Room Rent')
        self.make_charge(res.folio, item='ROOM-RENT', amount=1500000)
        self.make_charge(res.folio, item='MINIBAR-TEST', amount=80000)
        from hospitality_core.hospitality_core.api.folio_operations import get_split_tour_preview
        preview = get_split_tour_preview(res.folio)
        self.assertEqual(preview['room_total'], 1500000)
        self.assertEqual(preview['incidental_total'], 80000)
        self.assertEqual(len(preview['room_charges']), 1)
        self.assertEqual(len(preview['incidental_charges']), 1)
        self.assertEqual(preview['grand_total'], 1580000)

    def test_split_tour_preview_requires_permission(self):
        f = self.fixture()
        room, guest, res = self.make_reservation(f, 'Split Tour NoPerm Guest', 'FO-SPLIT-2')
        user = self.make_user('splittour-noperm@example.com', ['Sales User'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.folio_operations import get_split_tour_preview
        with self.assertRaises(frappe.PermissionError):
            get_split_tour_preview(res.folio)

    def test_execute_split_tour_moves_selected_transactions(self):
        f = self.fixture()
        room, guest, res = self.make_reservation(f, 'Split Tour Exec Guest', 'FO-SPLIT-3')
        room_b, guest_b, res_b = self.make_reservation(f, 'Split Tour Exec Sub Guest', 'FO-SPLIT-4')
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists('ROOM-RENT', 'Room Rent')
        self.make_charge(res.folio, item='ROOM-RENT', amount=1500000)
        minibar_txn = self.make_charge(res.folio, item='MINIBAR-TEST-2', amount=60000)
        from hospitality_core.hospitality_core.api.folio_operations import execute_split_tour_folio
        result = execute_split_tour_folio(res.folio, res_b.folio, [minibar_txn.name])
        self.assertTrue(result['success'])
        self.assertEqual(result['moved_count'], 1)
        self.assertEqual(frappe.db.get_value('Guest Folio', res.folio, 'outstanding_balance'), 1500000,
            'Folio nguon chi con lai tien phong sau khi chuyen di dich vu ca nhan.')
        self.assertEqual(frappe.db.get_value('Guest Folio', res_b.folio, 'outstanding_balance'), 60000,
            'Folio dich phai nhan dung khoan dich vu ca nhan da chon.')

    def test_execute_split_tour_requires_supervisor_role(self):
        f = self.fixture()
        room, guest, res = self.make_reservation(f, 'Split Tour Perm Guest', 'FO-SPLIT-5')
        room_b, guest_b, res_b = self.make_reservation(f, 'Split Tour Perm Sub Guest', 'FO-SPLIT-6')
        txn = self.make_charge(res.folio, amount=50000)
        user = self.make_user('splitexec-noperm@example.com', ['Sales User'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.folio_operations import execute_split_tour_folio
        with self.assertRaisesRegex(frappe.ValidationError, 'Access Denied'):
            execute_split_tour_folio(res.folio, res_b.folio, [txn.name])

    def test_execute_split_tour_rejects_empty_selection(self):
        f = self.fixture()
        room, guest, res = self.make_reservation(f, 'Split Tour Empty Guest', 'FO-SPLIT-7')
        room_b, guest_b, res_b = self.make_reservation(f, 'Split Tour Empty Sub Guest', 'FO-SPLIT-8')
        from hospitality_core.hospitality_core.api.folio_operations import execute_split_tour_folio
        with self.assertRaisesRegex(frappe.ValidationError, 'ít nhất một giao dịch'):
            execute_split_tour_folio(res.folio, res_b.folio, [])


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(FolioOperationsTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
