"""Kịch bản kiểm thử MỚI — Đợt 3 (mục 14): api/property_setup.py — wizard ánh xạ
property (inspect_mapping/apply_mapping/copy_legacy_settings/verify_property).
Module CHƯA TỪNG có test sống nào trước đây, dù đã qua nhiều vòng fix tĩnh:
- inspect_mapping() thêm check liên kết chéo qua LINKS (chặn NGAY LÚC MAPPING
  thay vì chỉ phát hiện sau ở verify_property()).
- apply_mapping() thêm khóa mutex GET_LOCK theo property.

Không có hàm nào trong property_setup.py gọi frappe.db.commit() (đã grep
trước khi viết) — an toàn dùng self.fixture()/PropertyDatabaseTests
rollback-based, không cần kiến trúc fixture cô lập như city_ledger tests.
"""
import unittest
import frappe
from run_property_integration import PropertyDatabaseTests


class PropertySetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def fixture(self):
        f = PropertyDatabaseTests()
        reservation, settings = f.accounting_reservation()
        self.reservation = reservation
        # accounting_reservation() da tao san 1 Hotel Room Type 'Integration
        # Deluxe' + 1 Hotel Room '101' cho HV-A — tai su dung (khong tao moi)
        # de tranh vi pham rang buoc "khong trung so phong/ten loai phong
        # trong cung 1 co so" (property_scope.py's validate_document()).
        self.room_type_a = reservation.room_type
        self.company_a = frappe.db.get_value('Hospitality Property', 'HV-A', 'operating_company')
        return f

    def make_user(self, email, roles):
        if not frappe.db.exists('User', email):
            frappe.get_doc(dict(doctype='User', email=email, first_name=email.split('@')[0],
                send_welcome_email=0, roles=[dict(role=r) for r in roles])).insert(ignore_permissions=True)
        return email

    def make_charge(self, folio_name, amount=100000):
        if not frappe.db.exists('Item', 'SETUP-MISC'):
            frappe.get_doc(dict(doctype='Item', item_code='SETUP-MISC', item_name='SETUP-MISC',
                item_group='Services', stock_uom='Nos', is_stock_item=0, is_sales_item=1)).insert(ignore_permissions=True)
        from frappe.utils import nowdate
        txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=folio_name, parenttype='Guest Folio',
            parentfield='transactions', posting_date=nowdate(), item='SETUP-MISC', description='Setup test charge',
            qty=1, amount=amount, bill_to='Guest', is_void=0))
        txn.flags.hospitality_service = True
        txn.insert(ignore_permissions=True)
        return txn

    def _unmap(self, doctype, name, clear_company_currency=True):
        """Giả lập bản ghi legacy CHƯA được ánh xạ property (bypass hook)."""
        frappe.db.set_value(doctype, name, 'property', None, update_modified=False)
        if clear_company_currency:
            if frappe.get_meta(doctype).has_field('operating_company'):
                frappe.db.set_value(doctype, name, 'operating_company', None, update_modified=False)
            if frappe.get_meta(doctype).has_field('currency'):
                frappe.db.set_value(doctype, name, 'currency', None, update_modified=False)

    # ------------------------------------------------------------------
    # Phân quyền
    # ------------------------------------------------------------------
    def test_inspect_mapping_requires_admin(self):
        f = self.fixture()
        user = self.make_user('setup-noperm@example.com', ['Sales User'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.property_setup import inspect_mapping
        with self.assertRaises(frappe.PermissionError):
            inspect_mapping('HV-A', frappe.as_json({'Hotel Room Type': [self.room_type_a]}))

    def test_apply_mapping_requires_admin(self):
        f = self.fixture()
        user = self.make_user('setup-noperm2@example.com', ['Sales User'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.property_setup import apply_mapping
        with self.assertRaises(frappe.PermissionError):
            apply_mapping('HV-A', frappe.as_json({'Hotel Room Type': [self.room_type_a]}), 'VND')

    # ------------------------------------------------------------------
    # inspect_mapping() — validate input
    # ------------------------------------------------------------------
    def test_inspect_mapping_rejects_doctype_not_in_scoped(self):
        self.fixture()
        from hospitality_core.hospitality_core.api.property_setup import inspect_mapping
        with self.assertRaises(frappe.ValidationError):
            inspect_mapping('HV-A', frappe.as_json({'User': ['Administrator']}))

    def test_inspect_mapping_rejects_non_dict_mapping(self):
        self.fixture()
        from hospitality_core.hospitality_core.api.property_setup import inspect_mapping
        with self.assertRaises(frappe.ValidationError):
            inspect_mapping('HV-A', frappe.as_json(['Hotel Room Type']))

    # ------------------------------------------------------------------
    # inspect_mapping() — phát hiện xung đột
    # ------------------------------------------------------------------
    def test_inspect_mapping_detects_property_conflict(self):
        f = self.fixture()
        rt_b = f.room_type('HV-B')
        from hospitality_core.hospitality_core.api.property_setup import inspect_mapping
        report = inspect_mapping('HV-A', frappe.as_json({'Hotel Room Type': [rt_b.name]}))
        self.assertTrue(any('đã thuộc cơ sở khác' in e for e in report['errors']))

    def test_inspect_mapping_detects_company_conflict(self):
        f = self.fixture()
        rt_b = f.room_type('HV-B')
        # De trong property (chua anh xa) nhung operating_company van con la
        # cua HV-B — mo phong du lieu legacy dinh sai phap nhan.
        self._unmap('Hotel Room Type', rt_b.name, clear_company_currency=False)
        frappe.db.set_value('Hotel Room Type', rt_b.name, 'currency', None, update_modified=False)
        from hospitality_core.hospitality_core.api.property_setup import inspect_mapping
        report = inspect_mapping('HV-A', frappe.as_json({'Hotel Room Type': [rt_b.name]}))
        self.assertTrue(any('pháp nhân khác' in e for e in report['errors']))

    def test_inspect_mapping_detects_currency_conflict(self):
        f = self.fixture()
        self._unmap('Hotel Room Type', self.room_type_a, clear_company_currency=False)
        frappe.db.set_value('Hotel Room Type', self.room_type_a, 'operating_company', None, update_modified=False)
        frappe.db.set_value('Hotel Room Type', self.room_type_a, 'currency', 'USD', update_modified=False)
        from hospitality_core.hospitality_core.api.property_setup import inspect_mapping
        report = inspect_mapping('HV-A', frappe.as_json({'Hotel Room Type': [self.room_type_a]}))
        self.assertTrue(any('tiền tệ khác' in e for e in report['errors']))

    def test_inspect_mapping_detects_linked_record_cross_property_drift(self):
        # Xac nhan fix duoc them o vong review tinh: check LINKS ngay tai
        # inspect_mapping(), khong doi den verify_property() rieng sau do.
        f = self.fixture()
        room = f.room('HV-A', room_type=self.room_type_a, number='SETUP-DRIFT-1')
        guest = frappe.get_doc(dict(doctype='Guest', full_name='Setup Drift Guest', guest_type='Regular')).insert(ignore_permissions=True)
        from frappe.utils import nowdate, add_days
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property='HV-A', guest=guest.name,
            room=room.name, room_type=room.room_type, hotel_reception=room.hotel_reception,
            currency='VND', arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        # Mo phong phong bi re-map sang HV-B SAU KHI dat phong da tao (drift).
        frappe.db.set_value('Hotel Room', room.name, 'property', 'HV-B', update_modified=False)
        from hospitality_core.hospitality_core.api.property_setup import inspect_mapping
        report = inspect_mapping('HV-A', frappe.as_json({'Hotel Reservation': [res.name]}))
        self.assertTrue(any('liên kết' in e and 'room' in e for e in report['errors']),
            f"Phai phat hien lien ket room da thuoc co so khac: {report['errors']}")

    def test_inspect_mapping_happy_path_no_errors(self):
        f = self.fixture()
        self._unmap('Hotel Room Type', self.room_type_a)
        from hospitality_core.hospitality_core.api.property_setup import inspect_mapping
        report = inspect_mapping('HV-A', frappe.as_json({'Hotel Room Type': [self.room_type_a]}))
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['company'], self.company_a)
        self.assertEqual(report['currency'], 'VND')

    # ------------------------------------------------------------------
    # apply_mapping()
    # ------------------------------------------------------------------
    def test_apply_mapping_happy_path_maps_unmapped_record(self):
        f = self.fixture()
        self._unmap('Hotel Room Type', self.room_type_a)
        from hospitality_core.hospitality_core.api.property_setup import apply_mapping
        apply_mapping('HV-A', frappe.as_json({'Hotel Room Type': [self.room_type_a]}), 'VND')
        doc = frappe.db.get_value('Hotel Room Type', self.room_type_a, ['property', 'operating_company', 'currency'], as_dict=True)
        self.assertEqual(doc.property, 'HV-A')
        self.assertEqual(doc.operating_company, self.company_a)
        self.assertEqual(doc.currency, 'VND')

    def test_apply_mapping_blocks_and_writes_nothing_when_errors_present(self):
        f = self.fixture()
        rt_b = f.room_type('HV-B')
        from hospitality_core.hospitality_core.api.property_setup import apply_mapping
        with self.assertRaises(frappe.ValidationError):
            apply_mapping('HV-A', frappe.as_json({'Hotel Room Type': [rt_b.name]}), 'VND')
        self.assertEqual(frappe.db.get_value('Hotel Room Type', rt_b.name, 'property'), 'HV-B',
            'Khong duoc ghi gi khi inspect_mapping bao loi.')

    def test_apply_mapping_requires_confirmed_currency_to_match_property_currency(self):
        f = self.fixture()
        self._unmap('Hotel Room Type', self.room_type_a)
        from hospitality_core.hospitality_core.api.property_setup import apply_mapping
        with self.assertRaisesRegex(frappe.ValidationError, 'xác nhận tiền tệ'):
            apply_mapping('HV-A', frappe.as_json({'Hotel Room Type': [self.room_type_a]}), 'USD')

    def test_apply_mapping_cascades_property_to_folio_transactions(self):
        f = self.fixture()
        self.make_charge(self.reservation.folio, amount=250000)
        self._unmap('Guest Folio', self.reservation.folio)
        frappe.db.sql("UPDATE `tabFolio Transaction` SET property=NULL, operating_company=NULL, currency=NULL WHERE parent=%s",
            (self.reservation.folio,))
        from hospitality_core.hospitality_core.api.property_setup import apply_mapping
        apply_mapping('HV-A', frappe.as_json({'Guest Folio': [self.reservation.folio]}), 'VND')
        folio = frappe.db.get_value('Guest Folio', self.reservation.folio, ['property', 'operating_company', 'currency'], as_dict=True)
        self.assertEqual(folio.property, 'HV-A')
        self.assertEqual(folio.operating_company, self.company_a)
        txn_props = frappe.db.get_all('Folio Transaction', filters={'parent': self.reservation.folio},
            fields=['property', 'operating_company', 'currency'])
        self.assertTrue(txn_props, 'Phai co it nhat 1 giao dich duoc tao boi accounting_reservation().')
        for row in txn_props:
            self.assertEqual(row.property, 'HV-A')
            self.assertEqual(row.operating_company, self.company_a)
            self.assertEqual(row.currency, 'VND')

    def test_hotel_room_type_currency_forced_to_property_currency_even_when_unset(self):
        # Xac nhan fix property_scope.py: truoc day, de trong 'currency' luc
        # tao Hotel Room Type se bi Frappe's Document._set_defaults() (chay
        # TRUOC before_validate) tu dien bang Global Defaults CUA SITE (vi du
        # 'INR' — mac dinh ERPNext, khong lien quan gi HV-A's 'VND') TRUOC KHI
        # property_scope.py's fallback cu ("doc.get('currency') or
        # prop.currency") kip chay — fallback do khong bao gio kich hoat vi
        # field da "trong nhu co gia tri". Nay Hotel Room Type/Room Rate Plan
        # duoc EP BUOC VO DIEU KIEN ve prop.currency (giong het operating_company),
        # nen ket qua PHAI la 'VND' (tien te that cua HV-A) du khong ai
        # truyen currency= khi tao.
        f = self.fixture()
        rt = frappe.get_doc(dict(doctype='Hotel Room Type', room_type_name='Setup Unset Currency RT',
            property='HV-A', max_adults=2, max_children=1, default_rate=1800000)).insert()
        self.assertEqual(rt.currency, 'VND',
            'currency phai bi ep ve dung prop.currency (VND), khong duoc la Global Default cua site.')

    def test_apply_mapping_appends_missing_currency_rate_for_room_type(self):
        f = self.fixture()
        # currency='VND' truyen tuong minh o day chi de dam bao ca nay chi
        # kiem tra DUNG 1 hanh vi (tu them dong currency_rate con thieu) —
        # hanh vi "de trong currency van ra dung prop.currency" da kiem tra
        # rieng o test_hotel_room_type_currency_forced_to_property_currency_even_when_unset o tren.
        rt = frappe.get_doc(dict(doctype='Hotel Room Type', room_type_name='Setup Missing Rate RT',
            property='HV-A', currency='VND', max_adults=2, max_children=1, default_rate=2000000,
            currency_rates=[dict(currency='USD', default_rate=130)])).insert()
        self.assertFalse(any(r.currency == 'VND' for r in rt.currency_rates))
        from hospitality_core.hospitality_core.api.property_setup import apply_mapping
        apply_mapping('HV-A', frappe.as_json({'Hotel Room Type': [rt.name]}), 'VND')
        rt.reload()
        self.assertTrue(any(r.currency == 'VND' and r.default_rate == rt.default_rate for r in rt.currency_rates),
            'apply_mapping phai tu them dong currency_rate con thieu cho tien te da xac nhan.')

    # ------------------------------------------------------------------
    # copy_legacy_settings()
    # ------------------------------------------------------------------
    def test_copy_legacy_settings_copies_fields_and_is_idempotent(self):
        self.fixture()
        frappe.db.set_single_value('Hospitality Accounting Settings', 'enable_vietqr', 1)
        frappe.db.set_single_value('Hospitality Accounting Settings', 'vietqr_bank_id', '970436')
        frappe.db.set_single_value('Hospitality Police Settings', 'police_station_name', 'CA Phuong Setup Test')
        frappe.db.set_single_value('Hospitality Surcharge Settings', 'early_tier1_pct', 30)
        from hospitality_core.hospitality_core.api.property_setup import copy_legacy_settings
        name = copy_legacy_settings('HV-B')
        self.assertEqual(name, 'HV-B')
        dest = frappe.get_doc('Hospitality Property Settings', 'HV-B')
        self.assertEqual(dest.enable_vietqr, 1)
        self.assertEqual(dest.vietqr_bank_id, '970436')
        self.assertEqual(dest.police_station_name, 'CA Phuong Setup Test')
        self.assertEqual(dest.early_tier1_pct, 30)
        self.assertEqual(dest.property, 'HV-B', 'property khong duoc bi ghi de tu Single nguon (da loai tru).')
        # Goi lai lan 2 — phai idempotent (bo qua, khong tao ban ghi trung/loi).
        name2 = copy_legacy_settings('HV-B')
        self.assertEqual(name2, 'HV-B')

    # ------------------------------------------------------------------
    # verify_property()
    # ------------------------------------------------------------------
    def test_verify_property_happy_path_sets_migration_verified(self):
        self.fixture()
        frappe.db.set_value('Hospitality Property', 'HV-A', 'migration_verified', 0, update_modified=False)
        from hospitality_core.hospitality_core.api.property_setup import verify_property
        result = verify_property('HV-A')
        self.assertTrue(result['verified'])
        self.assertEqual(frappe.db.get_value('Hospitality Property', 'HV-A', 'migration_verified'), 1)

    def test_verify_property_detects_linked_drift_and_blocks(self):
        f = self.fixture()
        room = f.room('HV-A', room_type=self.room_type_a, number='SETUP-DRIFT-2')
        guest = frappe.get_doc(dict(doctype='Guest', full_name='Verify Drift Guest', guest_type='Regular')).insert(ignore_permissions=True)
        from frappe.utils import nowdate, add_days
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property='HV-A', guest=guest.name,
            room=room.name, room_type=room.room_type, hotel_reception=room.hotel_reception,
            currency='VND', arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        frappe.db.set_value('Hotel Room', room.name, 'property', 'HV-B', update_modified=False)
        from hospitality_core.hospitality_core.api.property_setup import verify_property
        with self.assertRaisesRegex(frappe.ValidationError, 'chưa ánh xạ cùng cơ sở'):
            verify_property('HV-A')


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(PropertySetupTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
