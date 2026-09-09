"""Kịch bản kiểm thử MỚI — api/city_ledger.py + api/financial_control.py (Đợt 1,
mục 4 của kế hoạch "Kịch bản kiểm thử TOÀN BỘ tính năng còn lại"). Cả 2 module
CHƯA TỪNG có 1 dòng test sống nào (xác nhận grep 5 file test cũ — 0 kết quả),
dù `financial_control.py`'s `void_transaction()` là thao tác tài chính hủy
giao dịch trực tiếp trên folio và `city_ledger.py` kiểm soát hạn mức tín dụng
đại lý (từng có lỗi thật `get_dashboard_info()` trả list bị treo dead-code).

Chạy trên site test riêng, dữ liệu rollback sau mỗi ca.
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days, flt, getdate
from run_property_integration import PropertyDatabaseTests


class CityLedgerFinancialControlTests(unittest.TestCase):
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
        self.reservation = reservation
        return f

    def void_fixture(self):
        """
        Fixture RIÊNG cho các test void_transaction() — KHÔNG được dùng
        self.fixture()/accounting_reservation() (property 'HV-A' dùng CHUNG
        cho MỌI file test khác) hay tái sử dụng 'HV-A' dưới bất kỳ hình thức
        nào.

        Lý do (phát hiện thật, xem NHẬT KÝ trong plan): financial_control.py's
        void_transaction() gọi frappe.db.commit() THẬT ở nhiều nhánh — kể cả
        nhánh "regular" đơn giản nhất (dòng ~113). Đây là hành vi SẢN PHẨM
        THẬT (không phải lỗi test) — trong 1 request thật, transaction vẫn tự
        commit khi request kết thúc, nên không có gì sai — nhưng nó phá vỡ
        hoàn toàn mô hình "rollback sau mỗi test" mà TOÀN BỘ hệ sinh thái file
        test khác (property_integration/group_booking/night_audit/...) dựa
        vào để tái sử dụng AN TOÀN 'HV-A' + Price List "Integration Selling"
        dùng chung. Từng thử tái sử dụng 'HV-A' idempotent (nếu đã enabled thì
        bỏ qua bootstrap) — VẪN SAI, vì bản thân việc gọi
        accounting_reservation() dù chỉ 1 lần cũng vĩnh viễn "khóa cứng"
        'HV-A'+Price List vào trạng thái enabled/tồn tại cho phần đời còn lại
        của SITE (không chỉ của tiến trình test này) — khiến MỌI file test
        KHÁC chạy SAU (kể cả ở lần gọi `docker compose exec` hoàn toàn riêng
        biệt) gặp "Duplicate entry 'Integration Selling'" ngay từ lần gọi
        accounting_reservation() đầu tiên, đã xác nhận thật, phải bench
        reinstall để khôi phục site 2 lần liền trong đúng phiên làm việc này.

        Giải pháp ĐÚNG (2 lớp, cả 2 đều cần thiết — đã xác nhận thật qua chạy
        liên tiếp không reinstall): (1) 1 Hospitality Property RIÊNG
        ('FC-TEST'), và (2) 1 ERPNext Company RIÊNG ('FC Test Co', KHÔNG dùng
        lại '_Hospitality V2 A'/B) — vì kế toán Legacy (accounting.py) ghi GL
        Entry theo COMPANY, không theo property: dù property tách biệt, nếu
        vẫn dùng chung company '_Hospitality V2 A', GL Entry thật (đã commit
        vĩnh viễn) của void_transaction() sẽ cộng dồn vào ĐÚNG receivable_account
        mà `run_property_integration.py`'s test khác kỳ vọng sạch từ đầu —
        đã xác nhận thật (test_daily_revenue_invoice_preserves_single_income
        lệch số dư đúng bằng số tiền các charge test void_transaction() để
        lại). Cả 'FC-TEST' lẫn 'FC Test Co' không bao giờ được bất kỳ file
        test nào khác tham chiếu, nên bị "khóa cứng" vĩnh viễn do commit thật
        của void_transaction()/Company creation là VÔ HẠI tuyệt đối.
        """
        # KHÔNG dùng company '_Hospitality V2 A'/'_Hospitality V2 B' dùng
        # chung — phát hiện thật: dù property 'FC-TEST' tách biệt hoàn toàn,
        # kế toán Legacy (accounting.py) ghi GL Entry theo COMPANY, không
        # theo property — Folio Transaction thật của các test void_transaction()
        # (đã commit thật, vĩnh viễn) sẽ CỘNG DỒN vào đúng receivable_account
        # mà run_property_integration.py's test_daily_revenue_invoice_preserves_single_income
        # kỳ vọng sạch từ đầu (assertEqual balance==1650000, thực tế lệch do
        # số dư dư ra từ test void_transaction() trước đó) — đã xác nhận thật
        # bằng cách chạy 2 file test liên tiếp không reinstall. Dùng 1 Company
        # RIÊNG, không company nào khác trong toàn bộ hệ sinh thái test tham
        # chiếu tới, để mọi GL Entry thật của void_transaction() không bao giờ
        # đụng tới số dư mà các file test khác kỳ vọng.
        company = 'FC Test Co'
        if not frappe.db.exists('Company', company):
            # ERPNext's Company doctype tự gọi frappe.db.commit() nội bộ khi
            # tạo mới (bootstrap chart of accounts) — không cần commit thêm
            # ở đây, chỉ cần đảm bảo KHÔNG công ty nào khác trong hệ sinh
            # thái test này tham chiếu tới tên company này.
            frappe.get_doc(dict(doctype='Company', company_name=company, abbr='FCTC', country='Vietnam',
                default_currency='VND', create_chart_of_accounts_based_on='Standard Template',
                chart_of_accounts='Standard')).insert(ignore_permissions=True)
        self.company = company
        self.currency = frappe.db.get_value('Company', company, 'default_currency') or 'VND'
        year = str(getdate(nowdate()).year)
        if not frappe.db.exists('Fiscal Year', year):
            frappe.get_doc(dict(doctype='Fiscal Year', year=year, year_start_date=year + '-01-01',
                year_end_date=year + '-12-31')).insert(ignore_permissions=True)
        else:
            # Site 'localhost' (sau khi gop bo test ve day) co san Fiscal Year
            # nam nay nhung GIOI HAN theo danh sach company THAT cua Tap doan
            # Tuan Chau (bang con 'companies') — 'FC Test Co' khong nam trong
            # do nen GL Entry bi tu choi "not in any active Fiscal Year".
            # Khop fix da ap dung o run_property_integration.py's
            # accounting_reservation(). Chi them neu bang con dang o che do
            # gioi han (khong rong) — rong nghia la ap dung cho MOI company,
            # khong dong vao de tranh vo tinh bat dau gioi han.
            fy = frappe.get_doc('Fiscal Year', year)
            existing_companies = {d.company for d in (fy.get('companies') or [])}
            if existing_companies and company not in existing_companies:
                fy.append('companies', dict(company=company))
                fy.save(ignore_permissions=True)
        # Folio 'Legacy' (FC-TEST không cutover Property v2) vẫn cần cấu hình
        # Single toàn cục "Hospitality Accounting Settings" (receivable_account
        # v.v.) để accounting.py's make_gl_entries_for_folio_transaction()
        # ghi GL được ngay khi tạo BẤT KỲ Folio Transaction nào — cấu hình 1
        # lần ở đây, dùng chung cho mọi test void_transaction().
        self.ensure_legacy_payment_prereqs()
        if not frappe.db.exists('Hospitality Property', 'FC-TEST'):
            frappe.get_doc(dict(doctype='Hospitality Property', property_code='FC-TEST', property_name='FC-TEST',
                operating_company=company, currency=self.currency, timezone='Asia/Ho_Chi_Minh',
                accept_new_bookings=1)).insert(ignore_permissions=True)
        self.property = 'FC-TEST'

        room_type = frappe.db.get_value('Hotel Room Type', {'property': self.property}, 'name')
        if not room_type:
            room_type = frappe.get_doc(dict(doctype='Hotel Room Type', property=self.property,
                room_type_name='FC Standard', max_adults=2, max_children=1, default_rate=1000000,
                currency_rates=[dict(currency=self.currency, default_rate=1000000)])).insert(ignore_permissions=True).name
        reception = frappe.db.get_value('Hotel Reception', {'property': self.property}, 'name')
        if not reception:
            reception = frappe.get_doc(dict(doctype='Hotel Reception', reception_name='FC-TEST-Reception',
                property=self.property)).insert(ignore_permissions=True).name

        suffix = frappe.generate_hash(6)
        room = frappe.get_doc(dict(doctype='Hotel Room', property=self.property, room_number=f'FCV-{suffix}',
            room_type=room_type, hotel_reception=reception, status='Available', is_enabled=1)).insert(ignore_permissions=True)
        guest = frappe.get_doc(dict(doctype='Guest', full_name=f'Void Test Guest {suffix}',
            guest_type='Regular')).insert(ignore_permissions=True)
        res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property, guest=guest.name,
            room=room.name, room_type=room_type, hotel_reception=reception, currency=self.currency,
            arrival_date=nowdate(), departure_date=add_days(nowdate(), 2))).insert(ignore_permissions=True)
        frappe.db.set_value('Guest Folio', res.folio, 'status', 'Open')
        self.reservation = res
        return res

    def make_agency(self, name, credit_limit=None):
        if not frappe.db.exists('Customer', name):
            cust = frappe.get_doc(dict(doctype='Customer', customer_name=name, customer_type='Company',
                customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                territory=frappe.db.get_value('Territory', {'is_group': 0})))
            if credit_limit is not None:
                cust.append('credit_limits', dict(company=self.company, credit_limit=credit_limit))
            cust.insert(ignore_permissions=True)
        return name

    def make_sales_invoice(self, customer, outstanding_amount):
        item = 'CITY-LEDGER-TEST-ITEM'
        if not frappe.db.exists('Item', item):
            frappe.get_doc(dict(doctype='Item', item_code=item, item_name=item, item_group='Services',
                stock_uom='Nos', is_stock_item=0, is_sales_item=1)).insert(ignore_permissions=True)
        income_account = frappe.db.get_value('Account', {'company': self.company, 'root_type': 'Income',
            'is_group': 0}, 'name')
        si = frappe.get_doc(dict(doctype='Sales Invoice', customer=customer, company=self.company,
            currency=self.currency, conversion_rate=1, due_date=nowdate(),
            items=[dict(item_code=item, qty=1, rate=outstanding_amount, income_account=income_account)]))
        si.insert(ignore_permissions=True)
        si.submit()
        return si

    def make_user(self, email, roles):
        if not frappe.db.exists('User', email):
            frappe.get_doc(dict(doctype='User', email=email, first_name=email.split('@')[0],
                send_welcome_email=0, roles=[dict(role=r) for r in roles])).insert(ignore_permissions=True)
        return email

    # ------------------------------------------------------------------
    # city_ledger.py: get_agent_credit_status()
    # ------------------------------------------------------------------
    def test_credit_status_green_yellow_red_thresholds(self):
        self.fixture()
        from hospitality_core.hospitality_core.api.city_ledger import get_agent_credit_status
        agency = self.make_agency('CL Test Agency Green', credit_limit=10_000_000)
        status = get_agent_credit_status(agency, company=self.company)
        self.assertEqual(status['status_level'], 'GREEN')

        agency2 = self.make_agency('CL Test Agency Yellow', credit_limit=10_000_000)
        self.make_sales_invoice(agency2, 8_500_000)  # 85% usage
        status2 = get_agent_credit_status(agency2, company=self.company)
        self.assertEqual(status2['status_level'], 'YELLOW')

        # ERPNext's OWN check_credit_limit() (chạy lúc submit Sales Invoice)
        # sẽ chặn ngay việc TẠO hóa đơn vượt hạn mức — không tạo được dữ
        # liệu để test "đã vượt trần" theo cách thông thường. Tạo agency
        # KHÔNG hạn mức, submit hóa đơn 12tr trước, RỒI mới gắn hạn mức 10tr
        # sau đó (mô phỏng đúng tình huống thật: hạn mức bị điều chỉnh giảm
        # SAU KHI đã phát sinh nợ, hoàn toàn hợp lệ về nghiệp vụ).
        agency3 = self.make_agency('CL Test Agency Red')
        self.make_sales_invoice(agency3, 12_000_000)
        # ERPNext's OWN Customer.validate_credit_limit_on_change() CŨNG chặn
        # hạ credit_limit xuống thấp hơn dư nợ hiện tại qua cust.save() bình
        # thường — dùng insert() trực tiếp trên dòng con (bỏ qua validate()
        # của Customer cha) để tạo đúng tình huống "hạn mức đã bị vượt".
        frappe.get_doc(dict(doctype='Customer Credit Limit', parent=agency3, parenttype='Customer',
            parentfield='credit_limits', company=self.company, credit_limit=10_000_000)).insert(ignore_permissions=True)
        status3 = get_agent_credit_status(agency3, company=self.company)
        self.assertEqual(status3['status_level'], 'RED')

    def test_credit_status_no_limit_configured(self):
        self.fixture()
        from hospitality_core.hospitality_core.api.city_ledger import get_agent_credit_status
        agency = self.make_agency('CL Test Agency NoLimit')
        status = get_agent_credit_status(agency, company=self.company)
        self.assertFalse(status['has_credit_limit'])
        self.assertEqual(status['status_level'], 'GREEN')

    def test_credit_status_filters_by_company(self):
        # Dư nợ ở CÔNG TY KHÁC không được cộng vào dư nợ của company đang kiểm tra.
        #
        # QUAN TRỌNG: KHÔNG tạo Company mới ở đây — phát hiện thật: ERPNext's
        # riêng Company doctype tự gọi frappe.db.commit() nội bộ khi tạo mới
        # (bootstrap chart of accounts mặc định, xem company.py dòng ~927/937),
        # HOÀN TOÀN ĐỘC LẬP với financial_control.py's void_transaction().
        # Một Company mới tạo giữa 1 test method (không phải setUpClass()) sẽ
        # khiến TOÀN BỘ fixture accounting_reservation() gọi TRƯỚC ĐÓ trong
        # CÙNG test (Price List "Integration Selling" v.v.) bị chốt vĩnh viễn
        # — test KHÁC gọi accounting_reservation() sau đó sẽ crash "Duplicate
        # entry" (đã xác nhận thật, phải bench reinstall để khôi phục site).
        # PropertyDatabaseTests.setUpClass() đã tự bootstrap sẵn ĐÚNG 1 lần
        # (kèm frappe.db.commit() TƯỜNG MINH, có chủ đích, ngoài phạm vi
        # rollback từng test) 2 company '_Hospitality V2 A'/'_Hospitality V2 B'
        # — dùng lại company B có sẵn thay vì tạo company thứ 3.
        self.fixture()
        other_company = '_Hospitality V2 B'
        agency = self.make_agency('CL Test Agency MultiCo', credit_limit=10_000_000)
        # Hóa đơn ở company khác — không dùng make_sales_invoice() (khác company/account).
        item = 'CITY-LEDGER-TEST-ITEM'
        if not frappe.db.exists('Item', item):
            frappe.get_doc(dict(doctype='Item', item_code=item, item_name=item, item_group='Services',
                stock_uom='Nos', is_stock_item=0, is_sales_item=1)).insert(ignore_permissions=True)
        other_income = frappe.db.get_value('Account', {'company': other_company, 'root_type': 'Income',
            'is_group': 0}, 'name')
        other_currency = frappe.db.get_value('Company', other_company, 'default_currency')
        si = frappe.get_doc(dict(doctype='Sales Invoice', customer=agency, company=other_company,
            currency=other_currency, conversion_rate=1, due_date=nowdate(),
            items=[dict(item_code=item, qty=1, rate=99_000_000, income_account=other_income)]))
        si.insert(ignore_permissions=True)
        si.submit()
        from hospitality_core.hospitality_core.api.city_ledger import get_agent_credit_status
        status = get_agent_credit_status(agency, company=self.company)
        self.assertEqual(status['status_level'], 'GREEN',
            'Dư nợ ở company KHÁC không được tính vào hạn mức tín dụng của company đang kiểm tra.')

    def test_credit_status_permission_denied_without_read_access(self):
        self.fixture()
        agency = self.make_agency('CL Test Agency Perm', credit_limit=1_000_000)
        user = self.make_user('cl-noperm@example.com', ['Sales User'])
        # Chặn quyền đọc Customer cho user thử nghiệm này bằng User Permission
        # giới hạn vào 1 Customer KHÁC — đơn giản hơn dựng cả 1 bộ role/DocPerm mới.
        other = self.make_agency('CL Test Agency Other')
        frappe.get_doc(dict(doctype='User Permission', user=user, allow='Customer', for_value=other)).insert(ignore_permissions=True)
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.city_ledger import get_agent_credit_status
        with self.assertRaises(frappe.PermissionError):
            get_agent_credit_status(agency, company=self.company)

    # ------------------------------------------------------------------
    # city_ledger.py: calculate_group_foc_rooms() / apply_foc_to_reservation()
    # ------------------------------------------------------------------
    def test_foc_calculation_and_apply_quota_enforced(self):
        f = self.fixture()
        settings = frappe.get_single('Hospitality Surcharge Settings')
        settings.enable_foc_policy = 1
        settings.rooms_per_foc = 2
        settings.save()

        agency = self.make_agency('CL FOC Agency')
        group = frappe.get_doc(dict(doctype='Hotel Group Booking', group_name=f'FOC Group {frappe.generate_hash(6)}',
            master_payer=agency, property=self.property, operating_company=self.company, currency=self.currency,
            arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()

        rooms = []
        for i in range(4):
            room = f.room(self.property, self.reservation.room_type, number=f'FOC-{i}')
            res = frappe.get_doc(dict(doctype='Hotel Reservation', property=self.property,
                guest=self.reservation.guest, room=room.name, room_type=self.reservation.room_type,
                hotel_reception=room.hotel_reception, currency=self.currency, group_booking=group.name,
                is_group_guest=1, arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
            rooms.append(res)

        from hospitality_core.hospitality_core.api.city_ledger import calculate_group_foc_rooms, apply_foc_to_reservation
        calc = calculate_group_foc_rooms(group.name)
        self.assertEqual(calc['total_rooms'], 4)
        self.assertEqual(calc['foc_eligible'], 2, '4 phòng / 2 phòng-mỗi-FOC = 2 phòng FOC đủ điều kiện.')
        self.assertEqual(calc['remaining_foc_quota'], 2)

        apply_foc_to_reservation(group.name, rooms[0].name)
        apply_foc_to_reservation(group.name, rooms[1].name)
        rooms[0].reload()
        self.assertEqual(rooms[0].is_complimentary, 1)
        self.assertEqual(rooms[0].discount_value, 100.0)

        calc2 = calculate_group_foc_rooms(group.name)
        self.assertEqual(calc2['remaining_foc_quota'], 0, 'Đã dùng hết 2/2 hạn mức FOC.')

        with self.assertRaisesRegex(frappe.ValidationError, 'hạn mức'):
            apply_foc_to_reservation(group.name, rooms[2].name)

    def test_foc_apply_rejects_reservation_outside_group(self):
        f = self.fixture()
        agency = self.make_agency('CL FOC Outside Agency')
        group = frappe.get_doc(dict(doctype='Hotel Group Booking', group_name=f'FOC Outside {frappe.generate_hash(6)}',
            master_payer=agency, property=self.property, operating_company=self.company, currency=self.currency,
            arrival_date=nowdate(), departure_date=add_days(nowdate(), 1))).insert()
        # self.reservation KHÔNG thuộc group này.
        from hospitality_core.hospitality_core.api.city_ledger import apply_foc_to_reservation
        with self.assertRaisesRegex(frappe.ValidationError, 'không thuộc đoàn'):
            apply_foc_to_reservation(group.name, self.reservation.name)

    def test_foc_disabled_policy_returns_not_enabled(self):
        self.fixture()
        settings = frappe.get_single('Hospitality Surcharge Settings')
        settings.enable_foc_policy = 0
        settings.save()
        from hospitality_core.hospitality_core.api.city_ledger import calculate_group_foc_rooms
        calc = calculate_group_foc_rooms('non-existent-group')
        self.assertFalse(calc['policy_enabled'])

    # ------------------------------------------------------------------
    # financial_control.py: void_transaction()
    # ------------------------------------------------------------------
    def make_charge(self, folio_name, amount=100000, is_invoiced=0):
        if not frappe.db.exists('Item', 'MISC'):
            frappe.get_doc(dict(doctype='Item', item_code='MISC', item_name='MISC', item_group='Services',
                stock_uom='Nos', is_stock_item=0, is_sales_item=1)).insert(ignore_permissions=True)
        txn = frappe.get_doc(dict(doctype='Folio Transaction', parent=folio_name, parenttype='Guest Folio',
            parentfield='transactions', posting_date=nowdate(), item='MISC', description='Test charge',
            qty=1, amount=amount, bill_to='Guest', is_invoiced=is_invoiced))
        # property_scope.py's validate_document() bắt buộc 1 trong 3 flag cho
        # Folio Transaction ghi vào folio Property v2 — đây là charge test
        # dựng tay (mô phỏng 1 nghiệp vụ hợp lệ), không phải nguồn nghi vấn.
        txn.flags.hospitality_service = True
        txn.insert(ignore_permissions=True)
        from hospitality_core.hospitality_core.api.folio import sync_folio_balance
        sync_folio_balance(frappe.get_doc('Guest Folio', folio_name))
        return txn

    def test_void_transaction_requires_supervisor_role(self):
        self.void_fixture()
        txn = self.make_charge(self.reservation.folio)
        if not frappe.db.exists('Allowance Reason Code', 'TEST-NO-APPROVAL'):
            frappe.get_doc(dict(doctype='Allowance Reason Code', reason_code='TEST-NO-APPROVAL',
                description='No approval needed', requires_manager_approval=0)).insert(ignore_permissions=True)
        user = self.make_user('fc-noperm@example.com', ['Sales User'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.financial_control import void_transaction
        with self.assertRaisesRegex(frappe.ValidationError, 'Access Denied'):
            void_transaction(txn.name, 'TEST-NO-APPROVAL')

    def test_void_transaction_regular_charge_zeroes_amount_and_syncs_balance(self):
        self.void_fixture()
        txn = self.make_charge(self.reservation.folio, amount=150000)
        if not frappe.db.exists('Allowance Reason Code', 'TEST-NO-APPROVAL'):
            frappe.get_doc(dict(doctype='Allowance Reason Code', reason_code='TEST-NO-APPROVAL',
                description='No approval needed', requires_manager_approval=0)).insert(ignore_permissions=True)
        user = self.make_user('fc-supervisor@example.com', ['Frontdesk Supervisor'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.financial_control import void_transaction
        void_transaction(txn.name, 'TEST-NO-APPROVAL')
        txn.reload()
        self.assertEqual(txn.is_void, 1)
        self.assertEqual(flt(txn.amount), 0)
        balance = frappe.db.get_value('Guest Folio', self.reservation.folio, 'outstanding_balance')
        self.assertEqual(flt(balance), 0, 'Hủy giao dịch phải trừ đúng khỏi số dư folio (đã zero-out amount + sync).')

    def test_void_transaction_already_invoiced_blocked(self):
        self.void_fixture()
        txn = self.make_charge(self.reservation.folio, is_invoiced=1)
        if not frappe.db.exists('Allowance Reason Code', 'TEST-NO-APPROVAL'):
            frappe.get_doc(dict(doctype='Allowance Reason Code', reason_code='TEST-NO-APPROVAL',
                description='No approval needed', requires_manager_approval=0)).insert(ignore_permissions=True)
        user = self.make_user('fc-supervisor2@example.com', ['Frontdesk Supervisor'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.financial_control import void_transaction
        with self.assertRaisesRegex(frappe.ValidationError, 'already been invoiced'):
            void_transaction(txn.name, 'TEST-NO-APPROVAL')

    def test_void_transaction_reason_requiring_manager_approval_blocks_supervisor(self):
        self.void_fixture()
        txn = self.make_charge(self.reservation.folio)
        if not frappe.db.exists('Allowance Reason Code', 'TEST-NEEDS-APPROVAL'):
            frappe.get_doc(dict(doctype='Allowance Reason Code', reason_code='TEST-NEEDS-APPROVAL',
                description='Needs manager approval', requires_manager_approval=1)).insert(ignore_permissions=True)
        user = self.make_user('fc-supervisor3@example.com', ['Frontdesk Supervisor'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.financial_control import void_transaction
        with self.assertRaisesRegex(frappe.ValidationError, 'Manager Approval'):
            void_transaction(txn.name, 'TEST-NEEDS-APPROVAL')

    def test_void_transaction_reason_requiring_manager_approval_allows_manager(self):
        self.void_fixture()
        txn = self.make_charge(self.reservation.folio)
        if not frappe.db.exists('Allowance Reason Code', 'TEST-NEEDS-APPROVAL'):
            frappe.get_doc(dict(doctype='Allowance Reason Code', reason_code='TEST-NEEDS-APPROVAL',
                description='Needs manager approval', requires_manager_approval=1)).insert(ignore_permissions=True)
        user = self.make_user('fc-manager@example.com', ['Frontdesk Supervisor', 'Hospitality Manager'])
        frappe.set_user(user)
        from hospitality_core.hospitality_core.api.financial_control import void_transaction
        void_transaction(txn.name, 'TEST-NEEDS-APPROVAL')
        txn.reload()
        self.assertEqual(txn.is_void, 1)

    def test_void_transaction_already_void_blocked(self):
        self.void_fixture()
        txn = self.make_charge(self.reservation.folio)
        if not frappe.db.exists('Allowance Reason Code', 'TEST-NO-APPROVAL'):
            frappe.get_doc(dict(doctype='Allowance Reason Code', reason_code='TEST-NO-APPROVAL',
                description='No approval needed', requires_manager_approval=0)).insert(ignore_permissions=True)
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.financial_control import void_transaction
        void_transaction(txn.name, 'TEST-NO-APPROVAL')
        with self.assertRaisesRegex(frappe.ValidationError, 'already void'):
            void_transaction(txn.name, 'TEST-NO-APPROVAL')

    def ensure_legacy_payment_prereqs(self):
        # create_folio_payment()/create_company_folio_payment() (Legacy) đi
        # qua handle_payment_income_realization(), dùng Single toàn cục
        # "Hospitality Accounting Settings" — chưa từng được fixture nào
        # trong bộ test này cấu hình (mọi test khác chạy dưới Property v2).
        # Cần cấu hình tối thiểu để test được đúng luồng hủy Payment Entry
        # hiện có (không liên quan tới cách folio đang ở accounting_version
        # nào — create_folio_payment() không tự phân biệt Legacy/Property v2).
        cash = frappe.db.get_value('Account', {'company': self.company, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', 'Cash'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Cash', type='Cash',
                accounts=[dict(company=self.company, default_account=cash)])).insert(ignore_permissions=True)
        elif not frappe.db.exists('Mode of Payment Account', {'parent': 'Cash', 'company': self.company}):
            mop = frappe.get_doc('Mode of Payment', 'Cash')
            mop.append('accounts', dict(company=self.company, default_account=cash))
            mop.save(ignore_permissions=True)

        def account(label, root_type):
            existing = frappe.db.get_value('Account', {'company': self.company, 'account_name': label}, 'name')
            if existing:
                return existing
            parent = frappe.db.get_value('Account', {'company': self.company, 'root_type': root_type,
                'is_group': 1}, 'name', order_by='lft')
            return frappe.get_doc(dict(doctype='Account', account_name=label, parent_account=parent,
                company=self.company, account_currency=self.currency)).insert().name
        # QUAN TRỌNG: gán THẲNG (không dùng "x = x or y") — "Hospitality
        # Accounting Settings" là Single TOÀN SITE, dùng chung bởi CẢ file
        # test này lẫn run_group_booking_tests.py's ensure_legacy_accounting_settings()
        # tương tự. Phát hiện thật: nếu 1 trong 2 test file "commit thật"
        # trước (qua void_transaction()/record_group_deposit()), kiểu gán
        # idempotent "chỉ điền nếu còn trống" sẽ khiến file test CHẠY SAU
        # kế thừa nhầm tài khoản/cost_center của COMPANY THUỘC FILE TRƯỚC
        # (VD "Cost Center Main - FCTC does not belong to Company
        # _Hospitality V2 A") — đã xác nhận thật khi chạy 2 file liên tiếp
        # không reinstall. Luôn gán lại đúng theo company của LẦN GỌI HIỆN
        # TẠI ngay trước khi dùng, không quan tâm giá trị cũ.
        settings = frappe.get_single('Hospitality Accounting Settings')
        settings.receivable_account = frappe.db.get_value('Company', self.company, 'default_receivable_account')
        settings.income_suspense_account = account('Legacy Income Suspense', 'Liability')
        settings.income_account = account('Legacy Room Revenue', 'Income')
        settings.consumption_tax_account = account('Legacy Consumption Tax', 'Liability')
        settings.vat_account = account('Legacy VAT', 'Liability')
        settings.service_charge_account = account('Legacy Service Charge', 'Liability')
        settings.cost_center = frappe.db.get_value('Company', self.company, 'cost_center')
        settings.enable_vietqr = 0
        settings.save()

    def test_void_transaction_payment_entry_cancels_and_removes_credit(self):
        self.void_fixture()
        self.ensure_legacy_payment_prereqs()
        from hospitality_core.hospitality_core.api.payment_bridge import create_folio_payment
        pe_name = create_folio_payment(self.reservation.folio, 50000, 'Cash',
            frappe.db.get_value('Hotel Reception', {'property': self.property}, 'name'))
        txn = frappe.get_doc('Folio Transaction', frappe.db.get_value('Folio Transaction',
            {'reference_doctype': 'Payment Entry', 'reference_name': pe_name}, 'name'))
        if not frappe.db.exists('Allowance Reason Code', 'TEST-NO-APPROVAL'):
            frappe.get_doc(dict(doctype='Allowance Reason Code', reason_code='TEST-NO-APPROVAL',
                description='No approval needed', requires_manager_approval=0)).insert(ignore_permissions=True)
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.financial_control import void_transaction
        void_transaction(txn.name, 'TEST-NO-APPROVAL')
        self.assertEqual(frappe.db.get_value('Payment Entry', pe_name, 'docstatus'), 2,
            'void_transaction() trên giao dịch gắn Payment Entry phải hủy chính Payment Entry đó.')


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(CityLedgerFinancialControlTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
