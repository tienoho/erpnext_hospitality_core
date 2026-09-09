"""Kịch bản kiểm thử MỚI — Đợt 3 (mục 12-13): vietqr_bridge.py + id_scanner.py.
Cả 2 module CHƯA TỪNG có test sống nào trước đây, dù đã qua fix tĩnh
(vietqr_bridge.py: thiếu tag 52/59/60; id_scanner.py: mặc định giới tính SAI
"Nam" thay vì để trống, MRZ index thẳng crash IndexError).

Không có hàm nào trong 2 module này gọi frappe.db.commit() (đã grep trước khi
viết) — an toàn dùng self.fixture()/PropertyDatabaseTests rollback-based.
"""
import unittest
import frappe
from run_property_integration import PropertyDatabaseTests


class VietQRTests(unittest.TestCase):
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
        return f

    def make_user(self, email, roles):
        if not frappe.db.exists('User', email):
            frappe.get_doc(dict(doctype='User', email=email, first_name=email.split('@')[0],
                send_welcome_email=0, roles=[dict(role=r) for r in roles])).insert(ignore_permissions=True)
        return email

    # ------------------------------------------------------------------
    # remove_vietnamese_accents() / crc16_ccitt() — hàm thuần túy
    # ------------------------------------------------------------------
    def test_remove_vietnamese_accents(self):
        from hospitality_core.hospitality_core.api.vietqr_bridge import remove_vietnamese_accents
        self.assertEqual(remove_vietnamese_accents('Nguyễn Văn Đức'), 'Nguyen Van Duc')
        self.assertEqual(remove_vietnamese_accents('Đà Nẵng'), 'Da Nang')
        self.assertEqual(remove_vietnamese_accents(''), '')
        self.assertEqual(remove_vietnamese_accents(None), '')

    def test_crc16_ccitt_known_test_vector(self):
        # CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF, không đảo bit) có test
        # vector CHUẨN quốc tế, độc lập với cách triển khai trong file này:
        # check value của ASCII "123456789" là 0x29B1.
        from hospitality_core.hospitality_core.api.vietqr_bridge import crc16_ccitt
        self.assertEqual(crc16_ccitt(b'123456789'), '29B1')

    # ------------------------------------------------------------------
    # build_emvco_vietqr() — xác nhận fix thiếu tag 52/59/60
    # ------------------------------------------------------------------
    def test_build_emvco_contains_mandatory_tags_52_59_60(self):
        from hospitality_core.hospitality_core.api.vietqr_bridge import build_emvco_vietqr
        payload = build_emvco_vietqr('970436', '0123456789', amount=100000,
            description='FOL001', account_name='NGUYEN VAN A', merchant_city='Ha Long')
        self.assertIn('5204', payload, 'Tag 52 (Merchant Category Code) phai co mat.')
        self.assertIn('0000', payload)
        self.assertIn('59', payload)
        self.assertIn('NGUYEN VAN A', payload, 'Ten nguoi thu huong (tag 59) phai xuat hien trong chuoi.')
        self.assertIn('HA LONG', payload.upper(), 'Thanh pho thu huong (tag 60) phai xuat hien trong chuoi.')

    def test_build_emvco_missing_name_city_falls_back_to_defaults(self):
        from hospitality_core.hospitality_core.api.vietqr_bridge import build_emvco_vietqr
        payload = build_emvco_vietqr('970436', '0123456789', amount=50000)
        self.assertIn('UNKNOWN', payload)
        self.assertIn('VIETNAM', payload)

    def test_build_emvco_point_of_initiation_static_vs_dynamic(self):
        from hospitality_core.hospitality_core.api.vietqr_bridge import build_emvco_vietqr
        static_payload = build_emvco_vietqr('970436', '0123456789', amount=0)
        dynamic_payload = build_emvco_vietqr('970436', '0123456789', amount=100000)
        self.assertIn('010211', static_payload, 'amount=0 phai la QR tinh (Point of Initiation=11).')
        self.assertIn('010212', dynamic_payload, 'amount>0 phai la QR dong (Point of Initiation=12).')

    def test_build_emvco_crc_is_correct_and_appended_last(self):
        from hospitality_core.hospitality_core.api.vietqr_bridge import build_emvco_vietqr, crc16_ccitt
        payload = build_emvco_vietqr('970436', '0123456789', amount=100000, account_name='TEST', merchant_city='HANOI')
        self.assertTrue(payload.endswith(payload[-4:]))
        body, crc_in_payload = payload[:-4], payload[-4:]
        self.assertEqual(crc16_ccitt(body.encode('utf-8')), crc_in_payload,
            'CRC16 cuoi chuoi phai khop voi CRC tinh tren toan bo phan truoc no.')

    def test_build_emvco_accented_name_cleaned_and_truncated(self):
        from hospitality_core.hospitality_core.api.vietqr_bridge import build_emvco_vietqr
        payload = build_emvco_vietqr('970436', '0123456789', amount=1000,
            account_name='Nguyễn Thị Rất Là Dài Tên Để Kiểm Tra Cắt Bớt Ký Tự Vượt Giới Hạn', merchant_city='Hà Nội')
        self.assertNotIn('Ễ', payload)
        self.assertIn('HA NOI', payload.upper())

    def test_build_emvco_description_tag_62_only_when_present(self):
        from hospitality_core.hospitality_core.api.vietqr_bridge import build_emvco_vietqr
        with_desc = build_emvco_vietqr('970436', '0123456789', amount=1000, description='THANH TOAN PHONG')
        without_desc = build_emvco_vietqr('970436', '0123456789', amount=1000)
        self.assertIn('62', with_desc)
        self.assertIn('THANH TOAN PHONG', with_desc)
        self.assertNotIn('THANH TOAN PHONG', without_desc)

    # ------------------------------------------------------------------
    # generate_vietqr_payload() — API whitelisted, cần DB thật
    # ------------------------------------------------------------------
    def _configure_vietqr(self, enabled=1, bank_id='970436', account_number='0011002233',
                           account_name='CTY TNHH TUAN CHAU', template='compact2', prefix='TCG'):
        frappe.db.set_single_value('Hospitality Accounting Settings', 'enable_vietqr', enabled)
        frappe.db.set_single_value('Hospitality Accounting Settings', 'vietqr_bank_id', bank_id)
        frappe.db.set_single_value('Hospitality Accounting Settings', 'vietqr_account_number', account_number)
        frappe.db.set_single_value('Hospitality Accounting Settings', 'vietqr_account_name', account_name)
        frappe.db.set_single_value('Hospitality Accounting Settings', 'vietqr_template', template)
        frappe.db.set_single_value('Hospitality Accounting Settings', 'vietqr_content_prefix', prefix)

    def test_generate_payload_blocked_when_feature_disabled(self):
        self.fixture()
        self._configure_vietqr(enabled=0)
        from hospitality_core.hospitality_core.api.vietqr_bridge import generate_vietqr_payload
        with self.assertRaisesRegex(frappe.ValidationError, 'chưa được kích hoạt'):
            generate_vietqr_payload()

    def test_generate_payload_blocked_when_missing_bank_config(self):
        self.fixture()
        self._configure_vietqr(bank_id='')
        from hospitality_core.hospitality_core.api.vietqr_bridge import generate_vietqr_payload
        with self.assertRaisesRegex(frappe.ValidationError, 'Mã BIN'):
            generate_vietqr_payload()

    def test_generate_payload_from_folio_uses_outstanding_balance_and_room(self):
        f = self.fixture()
        self._configure_vietqr()
        frappe.db.set_value('Guest Folio', self.reservation.folio, 'outstanding_balance', 1500000)
        from hospitality_core.hospitality_core.api.vietqr_bridge import generate_vietqr_payload
        result = generate_vietqr_payload(folio_name=self.reservation.folio)
        self.assertTrue(result['success'])
        self.assertEqual(result['amount'], 1500000)
        self.assertIn(self.reservation.folio, result['description'])
        self.assertTrue(result['emvco_string'])
        self.assertIn('970436', result['emvco_string'])

    def test_generate_payload_explicit_amount_overrides_folio_balance(self):
        f = self.fixture()
        self._configure_vietqr()
        frappe.db.set_value('Guest Folio', self.reservation.folio, 'outstanding_balance', 1500000)
        from hospitality_core.hospitality_core.api.vietqr_bridge import generate_vietqr_payload
        result = generate_vietqr_payload(folio_name=self.reservation.folio, amount=200000)
        self.assertEqual(result['amount'], 200000, 'So tien tuong minh (dat coc/thanh toan tung phan) phai duoc uu tien.')

    def test_generate_payload_requires_folio_read_permission(self):
        f = self.fixture()
        self._configure_vietqr()
        user = self.make_user('vietqr-noperm@example.com', ['Sales User'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.vietqr_bridge import generate_vietqr_payload
        with self.assertRaises(frappe.PermissionError):
            generate_vietqr_payload(folio_name=self.reservation.folio)

    def test_generate_payload_zero_amount_without_folio_blocked(self):
        self.fixture()
        self._configure_vietqr()
        from hospitality_core.hospitality_core.api.vietqr_bridge import generate_vietqr_payload
        with self.assertRaisesRegex(frappe.ValidationError, 'lớn hơn 0'):
            generate_vietqr_payload(amount=0)


class IDScannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PropertyDatabaseTests.setUpClass()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()

    def make_user(self, email, roles):
        if not frappe.db.exists('User', email):
            frappe.get_doc(dict(doctype='User', email=email, first_name=email.split('@')[0],
                send_welcome_email=0, roles=[dict(role=r) for r in roles])).insert(ignore_permissions=True)
        return email

    # ------------------------------------------------------------------
    # MRZ hộ chiếu
    # ------------------------------------------------------------------
    def _mrz(self, line2):
        line1 = 'P<VNMNGUYEN<<VAN<A' + '<' * (44 - len('P<VNMNGUYEN<<VAN<A'))
        return line1 + '\n' + line2

    def test_parse_passport_mrz_happy_path_vietnamese(self):
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        line2 = 'C1234567<8VNM9001015M3001017<<<<<<<<<<<<<<02'
        line2 = (line2 + '<' * 44)[:44]
        result = parse_id_document(raw_text=self._mrz(line2))
        self.assertTrue(result['success'])
        self.assertEqual(result['document_type'], 'Passport')
        self.assertEqual(result['nationality'], 'Việt Nam')
        self.assertEqual(result['is_alien'], 0)
        self.assertEqual(result['gender'], 'Nam')
        self.assertEqual(result['date_of_birth'], '1990-01-01')

    def test_parse_passport_mrz_foreign_national_is_alien(self):
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        line2 = 'L898902C<3USA6503145F0912311<<<<<<<<<<<<<<08'
        line2 = (line2 + '<' * 44)[:44]
        result = parse_id_document(raw_text=self._mrz(line2))
        self.assertTrue(result['success'])
        self.assertEqual(result['nationality'], 'USA')
        self.assertEqual(result['is_alien'], 1)
        self.assertEqual(result['gender'], 'Nữ')

    def test_parse_passport_mrz_unknown_gender_char_left_blank(self):
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        line2 = 'L898902C<3USA6503145<0912311<<<<<<<<<<<<<<08'
        line2 = (line2 + '<' * 44)[:44]
        result = parse_id_document(raw_text=self._mrz(line2))
        self.assertTrue(result['success'])
        self.assertEqual(result['gender'], '', 'Ky tu MRZ khong xac dinh (<) phai de trong, khong suy doan.')

    def test_parse_passport_mrz_truncated_line2_no_crash(self):
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        # Dòng 2 bị cắt ngắn (dán tay thiếu ký tự) — trước đây line2[20] index
        # thẳng se crash IndexError; nay phải trả ve gender rong, khong crash.
        short_line2 = 'L898902C<3USA650314'
        result = parse_id_document(raw_text=self._mrz(short_line2))
        self.assertTrue(result['success'])
        self.assertEqual(result['gender'], '')

    # ------------------------------------------------------------------
    # CCCD qua QR code (phan cach boi |)
    # ------------------------------------------------------------------
    def test_parse_cccd_qr_code(self):
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        qr = '001234567890|123456789|NGUYEN VAN B|01011990|Nam|123 Duong ABC, Ha Long, Quang Ninh'
        result = parse_id_document(raw_text=qr)
        self.assertTrue(result['success'])
        self.assertEqual(result['document_type'], 'CCCD')
        self.assertEqual(result['id_number'], '001234567890')
        self.assertEqual(result['full_name'], 'NGUYEN VAN B')
        self.assertEqual(result['date_of_birth'], '1990-01-01')
        self.assertEqual(result['gender'], 'Nam')
        self.assertIn('Ha Long', result['address'])
        self.assertEqual(result['nationality'], 'Việt Nam')
        self.assertEqual(result['is_alien'], 0)

    # ------------------------------------------------------------------
    # CCCD qua văn bản OCR co nhan ro rang
    # ------------------------------------------------------------------
    def test_parse_cccd_ocr_with_labeled_fields(self):
        # Regex bóc tách nhãn dùng ĐÚNG tiếng Việt có dấu ("Họ và tên", "Ngày
        # sinh", "Giới tính", "Nơi thường trú") — khớp đúng văn bản OCR thật
        # từ CCCD (luôn in có dấu), không phải văn bản không dấu.
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        text = (
            'CĂN CƯỚC CÔNG DÂN\n'
            'Số: 001234567890\n'
            'Họ và tên: NGUYEN VAN C\n'
            'Ngày sinh: 15/05/1985\n'
            'Giới tính: Nam\n'
            'Nơi thường trú: 456 Duong XYZ, Ha Long\n'
        )
        result = parse_id_document(raw_text=text)
        self.assertTrue(result['success'])
        self.assertEqual(result['full_name'], 'NGUYEN VAN C')
        self.assertEqual(result['date_of_birth'], '1985-05-15')
        self.assertEqual(result['gender'], 'Nam')
        self.assertIn('456', result['address'])

    def test_parse_cccd_ocr_without_gender_label_stays_blank(self):
        # Xac nhan fix quan trong nhat: van ban CCCD LUON chua chu "Nam" trong
        # "Viet Nam" (quoc tich) — truoc day do van "Nam"/"Nu" tran trui se
        # khop NHAM chu do, gan gioi tinh SAI CHAC CHAN. Nay phai de trong khi
        # khong co nhan "Gioi tinh/Gender/Sex" ro rang.
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        text = (
            'CONG HOA XA HOI CHU NGHIA VIET NAM\n'
            'CAN CUOC CONG DAN\n'
            'So: 001234567891\n'
            'Ho va ten: TRAN THI D\n'
            'Ngay sinh: 20/03/1992\n'
        )
        result = parse_id_document(raw_text=text)
        self.assertTrue(result['success'])
        self.assertEqual(result['gender'], '', 'Khong co nhan Gioi tinh ro rang thi phai de trong, khong duoc suy doan tu chu Nam trong Viet Nam.')

    def test_parse_no_valid_document_returns_failure(self):
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        result = parse_id_document(raw_text='Van ban khong lien quan, khong co so CCCD hay MRZ nao.')
        self.assertFalse(result['success'])

    def test_parse_no_input_at_all_returns_failure(self):
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        result = parse_id_document()
        self.assertFalse(result['success'])

    def test_scanner_permission_blocks_role_without_access(self):
        user = self.make_user('scanner-noperm@example.com', ['Sales User'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.id_scanner import parse_id_document
        with self.assertRaises(frappe.PermissionError):
            parse_id_document(raw_text='001234567890')


if __name__ == "__main__":
    import sys, json
    try:
        suite = unittest.TestSuite()
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(VietQRTests))
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(IDScannerTests))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
