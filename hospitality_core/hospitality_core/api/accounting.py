import frappe
from frappe import _
from frappe.utils import flt

def get_tax_breakdown(total_amount):
    """
    Returns a breakdown of an inclusive amount:
    Total = Net + 5% CT + 7.5% VAT + 10% SC = 1.225 * Net
    """
    total_amount = flt(total_amount)
    net_amount = flt(total_amount / 1.225, 2)
    ct_amount = flt(net_amount * 0.05, 2)
    vat_amount = flt(net_amount * 0.075, 2)
    sc_amount = flt(net_amount * 0.10, 2)
    
    # Adjust net for rounding differences to ensure total matches
    total_deduction = ct_amount + vat_amount + sc_amount
    net_amount = flt(total_amount - total_deduction, 2)
    
    return {
        "net_amount": net_amount,
        "ct_amount": ct_amount,
        "vat_amount": vat_amount,
        "sc_amount": sc_amount,
        "total_deduction": total_deduction,
        "total_amount": total_amount
    }

def make_gl_entries_for_folio_transaction(txn_doc, method=None):
    """Ghi chênh lệch GL của giao dịch gốc; gọi lại không ghi trùng."""
    if txn_doc.get('accounting_version') == 'Property v2':
        return
    if (txn_doc.get('mirror_source') or txn_doc.reference_doctype in ('POS Invoice', 'Payment Entry', 'Folio Transaction')
            or txn_doc.item in ('PAYMENT', 'TRANSFER', 'TRANSFER-GROUP')
            or str(txn_doc.item or '').startswith('PAYMENT-')):
        return
    amount = 0 if txn_doc.is_void or txn_doc.docstatus == 2 or method == 'on_cancel' else flt(txn_doc.amount)
    if amount == 0 and not txn_doc.is_void:
        return
    frappe.db.sql('SELECT name FROM `tabGuest Folio` WHERE name=%s FOR UPDATE', txn_doc.parent)
    settings = frappe.get_single('Hospitality Accounting Settings')
    folio = frappe.get_doc('Guest Folio', txn_doc.parent)
    customer = folio.company or frappe.db.get_value('Guest', folio.guest, 'customer')
    if not customer:
        frappe.throw(_('Khách chưa liên kết Customer; không thể ghi công nợ folio.'))
    company = frappe.db.get_value('Account', settings.receivable_account, 'company')
    if not company:
        frappe.throw(_('Cần cấu hình tài khoản phải thu của khách sạn.'))
    # Giao dịch 'Legacy' (chưa cutover sang Property v2) của 1 property có
    # operating_company KHÁC với công ty sở hữu tài khoản phải thu toàn cục
    # (Hospitality Accounting Settings — Single, 1 bộ tài khoản duy nhất cho
    # CẢ site) TRƯỚC ĐÂY sẽ vẫn bị ghi sổ GL vào công ty của Settings toàn
    # cục — SAI PHÁP NHÂN — vì hàm này không hề đối chiếu operating_company
    # của giao dịch với company suy ra từ Settings. Logic thuế/tài khoản kiểu
    # Legacy (income_suspense/consumption_tax/vat/service_charge) chỉ được
    # thiết kế cho 1 công ty duy nhất — không thể tự suy ra cấu hình đúng cho
    # công ty khác, nên phải CHẶN RÕ RÀNG thay vì âm thầm ghi nhầm sổ, buộc
    # property đó phải hoàn tất cutover sang Property v2 (có
    # Hospitality Company Accounting Settings riêng) trước khi tiếp tục ghi
    # nhận doanh thu kiểu Legacy.
    folio_company = folio.get('operating_company')
    folio_property = folio.get('property')
    if folio_property and not folio_company:
        # property đã gán (Property v2) nhưng operating_company còn trống —
        # thường do property_setup.py's apply_mapping() ghi thẳng bằng
        # frappe.db.set_value (bỏ qua validate_document(), vốn tự động điền
        # operating_company từ Hospitality Property khi có property). Trạng
        # thái này nghĩa là mapping CHƯA hoàn tất — không có căn cứ để biết
        # công ty toàn cục có đúng là pháp nhân của property này hay không,
        # nên phải chặn thay vì âm thầm coi như khớp.
        frappe.throw(_(
            'Folio thuộc cơ sở {0} nhưng chưa xác định pháp nhân (operating_company) — '
            'mapping property chưa hoàn tất, cần chạy lại wizard mapping trước khi ghi nhận giao dịch.'
        ).format(folio_property))
    if folio_company and folio_company != company:
        frappe.throw(_(
            'Giao dịch thuộc pháp nhân {0} nhưng cấu hình kế toán Legacy toàn cục đang trỏ tới pháp nhân {1}. '
            'Cần hoàn tất chuyển đổi (cutover) property này sang Property v2 trước khi ghi nhận thêm giao dịch.'
        ).format(folio_company, company))
    parts = get_tax_breakdown(abs(amount))
    sign = 1 if amount >= 0 else -1
    expected = {}
    for account, debit_minus_credit in [
        (settings.receivable_account, amount),
        (settings.income_suspense_account, -sign * parts['net_amount']),
        (settings.consumption_tax_account, -sign * parts['ct_amount']),
        (settings.vat_account, -sign * parts['vat_amount']),
        (settings.service_charge_account, -sign * parts['sc_amount'])
    ]:
        expected[account] = flt(expected.get(account, 0) + debit_minus_credit, 2)
    existing = frappe.db.sql("""SELECT account, debit, credit FROM `tabGL Entry`
        WHERE voucher_type='Guest Folio' AND voucher_no=%s
        AND (voucher_detail_no=%s OR remarks LIKE %s) FOR UPDATE""",
        (txn_doc.parent, txn_doc.name, f'%(Ref: {txn_doc.name})%'), as_dict=True)
    for row in existing:
        expected[row.account] = flt(expected.get(row.account, 0) - flt(row.debit) + flt(row.credit), 2)
    if abs(sum(expected.values())) > 0.01:
        frappe.throw(_('GL lịch sử của giao dịch không cân bằng; cần đối soát trước khi điều chỉnh.'))
    for account, delta in expected.items():
        if not delta:
            continue
        # debit_in_account_currency/credit_in_account_currency: site này chỉ
        # dùng 1 tiền tệ (VND) nên luôn khớp debit/credit — TRƯỚC ĐÂY thiếu
        # cả 2 field này (xem ghi chú chi tiết ở reverse_charge_time_gl_on_invoice_submit()
        # bên dưới, cùng lỗi lặp lại ở MỌI hàm ghi GL trong file này).
        debit_amt, credit_amt = max(delta, 0), max(-delta, 0)
        # hospitality_property: GL Entry nam trong CORE_SCOPED (property_scope.py)
        # nhung KHONG co co che tu dong dien nhu SCOPED — TRUOC DAY khong ham
        # ghi GL nao trong ca file nay gan field nay (grep xac nhan 0 ket qua
        # xuyen suot file), khien moi dong GL Legacy bi AN cho user bi gioi
        # han property (bao cao vd taxes_and_charges_report.py loc dung
        # hospitality_property se khong bao gio thay cac dong nay). Da them
        # dong nhat cho ca 6 ham ghi GL trong file nay.
        entry = dict(doctype='GL Entry', posting_date=txn_doc.posting_date, account=account,
            company=company, cost_center=settings.cost_center, voucher_type='Guest Folio',
            voucher_no=txn_doc.parent, voucher_detail_no=txn_doc.name,
            debit=debit_amt, credit=credit_amt,
            debit_in_account_currency=debit_amt, credit_in_account_currency=credit_amt,
            hospitality_property=folio_property,
            remarks=f'{txn_doc.description} (Ref: {txn_doc.name})')
        if account == settings.receivable_account:
            entry.update(party_type='Customer', party=customer)
        frappe.get_doc(entry).insert(ignore_permissions=True)


def reverse_charge_time_gl_on_invoice_submit(doc, method=None):
    """
    Hook: Sales Invoice (on_submit/on_cancel)

    Xác nhận CHẮC CHẮN (einvoice.py's issue_einvoice_from_folio() gọi thẳng
    invoicing.py's create_invoice_from_folio() RỒI TỰ ĐỘNG submit()) rằng
    Sales Invoice tạo từ Folio Legacy THẬT SỰ được submit trong luồng phát
    hành hóa đơn điện tử tiêu chuẩn — không phải rủi ro giả định. Vì MỌI
    Folio Transaction trên folio Legacy đã được make_gl_entries_for_folio_transaction()
    ghi GL (Receivable/Income Suspense/3 TK thuế) NGAY LÚC PHÁT SINH CHARGE,
    GL chuẩn của ERPNext khi submit hóa đơn (Debtors/Income) sẽ ghi TRÙNG
    doanh thu nếu không xử lý.

    Sửa TẬN GỐC: với mỗi Folio Transaction đã được invoicing.py gắn
    reference_doctype='Sales Invoice'/reference_name=doc.name (chỉ áp dụng
    cho hóa đơn Legacy — hóa đơn Property v2 dùng cơ chế Hospitality
    Invoice Allocation riêng, không đi qua đây), tìm CHÍNH XÁC các GL Entry
    đã ghi lúc charge (voucher_type='Guest Folio' + voucher_no + đúng
    voucher_detail_no — CÙNG bộ khóa mà make_gl_entries_for_folio_transaction()
    dùng, không suy đoán lại số tiền qua công thức riêng) rồi ĐẢO NGƯỢC
    chính xác đúng số tiền đó (debit<->credit) tại thời điểm hóa đơn
    submit — dùng chung idiom make_gl_entries(cancel=...) đã có sẵn trong
    file này (redirect_pos_income_to_suspense/reclassify_pos_taxes) để tự
    động đối xứng khi hóa đơn bị Cancel sau đó (phục hồi lại GL charge-time
    ban đầu).

    HẠN CHẾ ĐÃ BIẾT: nếu hóa đơn này sau đó được Amend (Cancel rồi Amend
    theo quy trình ERPNext chuẩn), Sales Invoice MỚI có tên khác — Folio
    Transaction vẫn còn reference_name trỏ hóa đơn CŨ (không có cơ chế
    re-link như property_accounting.py's _relink_amended_allocations() cho
    đường Property v2) — hóa đơn amend sẽ không tìm thấy GL để đảo, có thể
    ghi trùng doanh thu lần nữa. Đây là hạn chế đã biết của toàn bộ đường
    Legacy (vốn không hỗ trợ amend tốt), không phải lỗi mới.

    CHÚ Ý KỸ THUẬT (phát hiện qua đọc trực tiếp erpnext/accounts/general_ledger.py):
    KHÔNG dùng `make_gl_entries(cancel=...)` như bản đầu — hàm đó, khi các
    dict truyền vào không có key "name", sẽ rơi vào nhánh "blanket cancel"
    (UPDATE is_cancelled=1 cho MỌI GL Entry cùng voucher_type+voucher_no,
    không khớp riêng từng dòng). Bút toán đảo ở đây dùng
    voucher_type='Sales Invoice'+voucher_no=doc.name — TRÙNG với chính GL
    Entry GỐC mà ERPNext tự ghi cho hóa đơn này (Debtors/Income) — blanket
    cancel có thể đánh dấu NHẦM cả 2 loại nếu thứ tự hook thay đổi trong
    tương lai. Thay vào đó: tự insert() trực tiếp (khớp mẫu
    make_gl_entries_for_folio_transaction() đã dùng trong CHÍNH file này),
    gán voucher_detail_no=t.name (tên Folio Transaction — không gian ID
    khác hẳn voucher_detail_no của GL Entry gốc ERPNext ghi, vốn là tên
    dòng Sales Invoice Item) để nhận diện CHÍNH XÁC chỉ các dòng do hàm này
    tạo ra, không bao giờ lẫn với GL Entry gốc của ERPNext dù cùng
    voucher_type/voucher_no.
    """
    txns = frappe.get_all("Folio Transaction",
        filters={"reference_doctype": "Sales Invoice", "reference_name": doc.name},
        fields=["name", "parent"])
    if not txns:
        return

    settings = frappe.get_single('Hospitality Accounting Settings')

    if method == "on_cancel" or doc.docstatus == 2:
        # Hủy CHÍNH XÁC các dòng đảo do hàm này tạo (nhận diện qua
        # voucher_detail_no=t.name), phục hồi lại hiệu lực GL charge-time
        # gốc — không đụng tới bất kỳ GL Entry nào khác của hóa đơn.
        for t in txns:
            frappe.db.sql("""
                UPDATE `tabGL Entry` SET is_cancelled=1
                WHERE voucher_type='Sales Invoice' AND voucher_no=%s AND voucher_detail_no=%s
                  AND ifnull(is_cancelled, 0) = 0
            """, (doc.name, t.name))
        return

    gl_entries = []
    for t in txns:
        existing = frappe.db.sql("""
            SELECT account, debit, credit, party_type, party FROM `tabGL Entry`
            WHERE voucher_type='Guest Folio' AND voucher_no=%s AND voucher_detail_no=%s
              AND ifnull(is_cancelled, 0) = 0
        """, (t.parent, t.name), as_dict=True)
        for row in existing:
            if not (flt(row.debit) or flt(row.credit)):
                continue
            # debit_in_account_currency/credit_in_account_currency: đọc trực
            # tiếp erpnext/accounts/doctype/gl_entry/gl_entry.py xác nhận
            # ERPNext LUÔN set cả 2 cặp field này cùng lúc — get_balance_on()
            # (mặc định in_account_currency=True) và update_outstanding_amt()
            # tính số dư dựa trên CẶP field "_in_account_currency", KHÔNG
            # PHẢI debit/credit thô. Site này chỉ 1 tiền tệ (VND, không quy
            # đổi đa tiền tệ) nên 2 cặp luôn bằng nhau — thiếu cặp thứ 2 sẽ
            # khiến số dư tính theo tiền tệ tài khoản LUÔN RA 0 bất kể ghi gì.
            #
            # TRƯỚC ĐÂY: không copy party_type/party từ dòng GL gốc — xác
            # nhận thật (crash khi test trên Docker): dòng gốc ghi nợ tài
            # khoản Phải Thu LUÔN kèm party_type='Customer'/party=<khách>
            # (ERPNext's GL Entry.validate()'s check_mandatory() bắt buộc
            # với mọi account_type Receivable/Payable) — dòng đảo ở đây ghi
            # CÙNG tài khoản đó (chiều ngược lại) mà thiếu party sẽ bị chính
            # ERPNext từ chối ngay "Customer is required against Receivable
            # account", khiến TOÀN BỘ luồng phát hành HĐĐT Legacy
            # (issue_einvoice_from_folio() -> submit) crash ngay lần đầu
            # dùng thật — không phải rủi ro giả định, đã tái hiện được.
            gl_entries.append(dict(doctype='GL Entry', posting_date=doc.posting_date, account=row.account,
                company=doc.company, cost_center=settings.cost_center, voucher_type='Sales Invoice',
                voucher_no=doc.name, voucher_detail_no=t.name,
                party_type=row.party_type, party=row.party,
                debit=flt(row.credit), credit=flt(row.debit),
                debit_in_account_currency=flt(row.credit), credit_in_account_currency=flt(row.debit),
                hospitality_property=doc.get('hospitality_property'),
                remarks=f'Đảo bút toán charge-time (Guest Folio {t.parent}, giao dịch {t.name}) khi lập hóa đơn chính thức {doc.name}'))

    for entry in gl_entries:
        frappe.get_doc(entry).insert(ignore_permissions=True)


def handle_payment_income_realization(payment_doc, folio_id, amount, cancel=0):
    """
    Transfers amount from Suspense to Income upon Payment.
    dr Suspense / cr Income
    Only the Net portion is transferred, as Taxes were already split into 
    total liability accounts during the Folio Transaction (Charge).
    """
    if payment_doc.get('hospitality_accounting_version') == 'Property v2':
        return
    settings = frappe.get_single("Hospitality Accounting Settings")
    
    # Calculate Net portion: Total = 1.225 * Net
    net_amount = flt(abs(flt(amount)) / 1.225, 2)
    
    gl_entries = []

    # debit_in_account_currency/credit_in_account_currency phải luôn khớp
    # debit/credit (site 1 tiền tệ) — thiếu cặp này khiến get_balance_on()/
    # update_outstanding_amt() của ERPNext tính số dư = 0 (xem ghi chú đầy
    # đủ ở reverse_charge_time_gl_on_invoice_submit()).
    # Debit Suspense
    gl_entries.append(frappe.get_doc({
        "doctype": "GL Entry",
        "posting_date": payment_doc.posting_date,
        "account": settings.income_suspense_account,
        "debit": net_amount if not cancel else 0,
        "credit": 0 if not cancel else net_amount,
        "debit_in_account_currency": net_amount if not cancel else 0,
        "credit_in_account_currency": 0 if not cancel else net_amount,
        "voucher_type": "Payment Entry",
        "voucher_no": payment_doc.name,
        "remarks": f"Income Realization (Net) for Folio {folio_id}",
        "hospitality_property": payment_doc.get('hospitality_property'),
        "cost_center": settings.cost_center,
        "company": payment_doc.company or frappe.db.get_default("company")
    }))

    # Credit Income
    gl_entries.append(frappe.get_doc({
        "doctype": "GL Entry",
        "posting_date": payment_doc.posting_date,
        "account": settings.income_account,
        "debit": 0 if not cancel else net_amount,
        "credit": net_amount if not cancel else 0,
        "debit_in_account_currency": 0 if not cancel else net_amount,
        "credit_in_account_currency": net_amount if not cancel else 0,
        "voucher_type": "Payment Entry",
        "voucher_no": payment_doc.name,
        "remarks": f"Income Realization (Net) for Folio {folio_id}",
        "hospitality_property": payment_doc.get('hospitality_property'),
        "cost_center": settings.cost_center,
        "company": payment_doc.company or frappe.db.get_default("company")
    }))

    for entry in gl_entries:
        entry.insert(ignore_permissions=True)

def redirect_pos_income_to_suspense(pos_invoice, method=None):
    """
    Hook: POS Invoice (on_submit/on_cancel)
    Redirects the portion charged to room from Income to Suspense.
    dr Income / cr Suspense
    """
    if pos_invoice.get('fnb_version') == 'FNB v1':
        return  # Thuế/doanh thu thuộc Sales Invoice hợp nhất của ERPNext.
    is_cancelled = False
    if method == "on_cancel" or pos_invoice.docstatus == 2:
        is_cancelled = True

    room_charge_amount = 0
    for pay in pos_invoice.payments:
        if pay.mode_of_payment == "Guest Account":
            room_charge_amount += flt(pay.amount)

    if room_charge_amount <= 0:
        return

    settings = frappe.get_single("Hospitality Accounting Settings")
    
    from erpnext.accounts.general_ledger import make_gl_entries
    
    gl_entries = []

    # debit_in_account_currency/credit_in_account_currency phải luôn khớp
    # debit/credit (site 1 tiền tệ) — xem ghi chú đầy đủ ở
    # reverse_charge_time_gl_on_invoice_submit().
    # 1. Debit Income (Reduce Realized Income)
    gl_entries.append(frappe._dict({
        "account": settings.income_account,
        "debit": abs(flt(room_charge_amount)),
        "credit": 0,
        "debit_in_account_currency": abs(flt(room_charge_amount)),
        "credit_in_account_currency": 0,
        "posting_date": pos_invoice.posting_date,
        "voucher_type": "POS Invoice",
        "voucher_no": pos_invoice.name,
        "remarks": f"Deferring Income for Room Charge (Invoice {pos_invoice.name})",
        "hospitality_property": pos_invoice.get('hospitality_property'),
        "cost_center": settings.cost_center,
        "company": pos_invoice.company or frappe.db.get_default("company")
    }))

    # 2. Credit Suspense (Increase Unearned)
    gl_entries.append(frappe._dict({
        "account": settings.income_suspense_account,
        "debit": 0,
        "credit": abs(flt(room_charge_amount)),
        "debit_in_account_currency": 0,
        "credit_in_account_currency": abs(flt(room_charge_amount)),
        "posting_date": pos_invoice.posting_date,
        "voucher_type": "POS Invoice",
        "voucher_no": pos_invoice.name,
        "remarks": f"Deferring Income for Room Charge (Invoice {pos_invoice.name})",
        "hospitality_property": pos_invoice.get('hospitality_property'),
        "cost_center": settings.cost_center,
        "company": pos_invoice.company or frappe.db.get_default("company")
    }))

    if gl_entries:
        make_gl_entries(gl_entries, cancel=is_cancelled, adv_adj=True)

def reclassify_pos_taxes(pos_invoice, method=None):
    """
    Hook: POS Invoice (on_submit/on_cancel)
    Deducts taxes from the full income realized by ERPNext POS and reclassifies them.
    Total = 1.225 * Net
    dr Income (or Suspense if Room Charge) / cr CT, VAT, SC
    """
    if pos_invoice.get('fnb_version') == 'FNB v1':
        return
    is_cancelled = False
    if method == "on_cancel" or pos_invoice.docstatus == 2:
        is_cancelled = True

    if pos_invoice.grand_total <= 0:
        return

    settings = frappe.get_single("Hospitality Accounting Settings")
    from erpnext.accounts.general_ledger import make_gl_entries

    total_amount = flt(pos_invoice.grand_total, 2)
    net_amount = flt(total_amount / 1.225, 2)
    
    # Calculate Tax Components (Rounded)
    ct_amount = flt(net_amount * 0.05, 2)
    vat_amount = flt(net_amount * 0.075, 2)
    sc_amount = flt(net_amount * 0.10, 2)
    
    total_tax = ct_amount + vat_amount + sc_amount
    
    # Determine Source of Funds (Income vs Suspense)
    room_charge_paid = 0
    for pay in pos_invoice.payments:
        if pay.mode_of_payment == "Guest Account":
            room_charge_paid += flt(pay.amount, 2)
            
    if room_charge_paid > total_amount:
        room_charge_paid = total_amount

    suspense_ratio = room_charge_paid / total_amount if total_amount > 0 else 0
    
    tax_from_suspense = flt(total_tax * suspense_ratio, 2)
    tax_from_income = flt(total_tax - tax_from_suspense, 2)

    gl_entries = []

    # debit_in_account_currency/credit_in_account_currency phải luôn khớp
    # debit/credit (site 1 tiền tệ) — xem ghi chú đầy đủ ở
    # reverse_charge_time_gl_on_invoice_submit().
    # 1. Debit Income (Tax portion of Cash/Card sales)
    if tax_from_income > 0:
        gl_entries.append(frappe._dict({
            "account": settings.income_account,
            "debit": tax_from_income,
            "credit": 0,
            "debit_in_account_currency": tax_from_income,
            "credit_in_account_currency": 0,
            "posting_date": pos_invoice.posting_date,
            "voucher_type": "POS Invoice",
            "voucher_no": pos_invoice.name,
            "remarks": f"Tax Reclassification (Income) for POS {pos_invoice.name}",
            "hospitality_property": pos_invoice.get('hospitality_property'),
            "cost_center": settings.cost_center,
            "company": pos_invoice.company or frappe.db.get_default("company")
        }))

    # 2. Debit Suspense (Tax portion of Room Charges)
    if tax_from_suspense > 0:
        gl_entries.append(frappe._dict({
            "account": settings.income_suspense_account,
            "debit": tax_from_suspense,
            "credit": 0,
            "debit_in_account_currency": tax_from_suspense,
            "credit_in_account_currency": 0,
            "posting_date": pos_invoice.posting_date,
            "voucher_type": "POS Invoice",
            "voucher_no": pos_invoice.name,
            "remarks": f"Tax Reclassification (Suspense) for POS {pos_invoice.name}",
            "hospitality_property": pos_invoice.get('hospitality_property'),
            "cost_center": settings.cost_center,
            "company": pos_invoice.company or frappe.db.get_default("company")
        }))

    # 3. Credit Consumption Tax
    if ct_amount > 0:
        gl_entries.append(frappe._dict({
            "account": settings.consumption_tax_account,
            "debit": 0,
            "credit": ct_amount,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": ct_amount,
            "posting_date": pos_invoice.posting_date,
            "voucher_type": "POS Invoice",
            "voucher_no": pos_invoice.name,
            "remarks": f"Consumption Tax (5%) for POS {pos_invoice.name}",
            "hospitality_property": pos_invoice.get('hospitality_property'),
            "cost_center": settings.cost_center,
            "company": pos_invoice.company or frappe.db.get_default("company")
        }))

    # 4. Credit VAT
    if vat_amount > 0:
        gl_entries.append(frappe._dict({
            "account": settings.vat_account,
            "debit": 0,
            "credit": vat_amount,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": vat_amount,
            "posting_date": pos_invoice.posting_date,
            "voucher_type": "POS Invoice",
            "voucher_no": pos_invoice.name,
            "remarks": f"VAT (7.5%) for POS {pos_invoice.name}",
            "hospitality_property": pos_invoice.get('hospitality_property'),
            "cost_center": settings.cost_center,
            "company": pos_invoice.company or frappe.db.get_default("company")
        }))

    # 5. Credit Service Charge
    if sc_amount > 0:
        gl_entries.append(frappe._dict({
            "account": settings.service_charge_account,
            "debit": 0,
            "credit": sc_amount,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": sc_amount,
            "posting_date": pos_invoice.posting_date,
            "voucher_type": "POS Invoice",
            "voucher_no": pos_invoice.name,
            "remarks": f"Service Charge (10%) for POS {pos_invoice.name}",
            "hospitality_property": pos_invoice.get('hospitality_property'),
            "cost_center": settings.cost_center,
            "company": pos_invoice.company or frappe.db.get_default("company")
        }))

    if gl_entries:
        make_gl_entries(gl_entries, cancel=is_cancelled, adv_adj=True)

def create_expense_gl_entries(expense_doc, method=None):
    """
    Hook: Hospitality Expense (on_submit/on_cancel)
    """
    is_cancelled = False
    if method == "on_cancel" or expense_doc.docstatus == 2:
        is_cancelled = True

    if not expense_doc.expense_account or not expense_doc.payment_account:
        expense_doc.set_account_details()
        if not expense_doc.expense_account or not expense_doc.payment_account:
            frappe.throw(_("Expense Account and Payment Account are required for GL entries."))

    gl_entries = []
    company = expense_doc.company or frappe.db.get_default("company")

    # debit_in_account_currency/credit_in_account_currency phải luôn khớp
    # debit/credit (site 1 tiền tệ) — xem ghi chú đầy đủ ở
    # reverse_charge_time_gl_on_invoice_submit().
    # 1. Debit Expense Account (Net Amount)
    expense_debit = abs(flt(expense_doc.amount)) if not is_cancelled else 0
    expense_credit = 0 if not is_cancelled else abs(flt(expense_doc.amount))
    gl_entries.append(frappe.get_doc({
        "doctype": "GL Entry",
        "posting_date": expense_doc.expense_date,
        "account": expense_doc.expense_account,
        "debit": expense_debit,
        "credit": expense_credit,
        "debit_in_account_currency": expense_debit,
        "credit_in_account_currency": expense_credit,
        "voucher_type": "Hospitality Expense",
        "voucher_no": expense_doc.name,
        "remarks": f"Expense: {expense_doc.expense_category} - {expense_doc.description or ''}",
        "is_cancelled": 1 if is_cancelled else 0,
        # Hospitality Expense nam trong SCOPED (field 'property'), GL Entry
        # nam trong CORE_SCOPED (field 'hospitality_property') — 2 ten khac
        # nhau cho cung 1 khai niem, phai tu dich khi chuyen tu nguon sang dich.
        "hospitality_property": expense_doc.get('property'),
        "cost_center": expense_doc.cost_center,
        "company": company
    }))

    # 2. Debit Tax Accounts (if any)
    for tax in expense_doc.get("taxes"):
        if flt(tax.tax_amount) > 0:
            tax_debit = abs(flt(tax.tax_amount)) if not is_cancelled else 0
            tax_credit = 0 if not is_cancelled else abs(flt(tax.tax_amount))
            gl_entries.append(frappe.get_doc({
                "doctype": "GL Entry",
                "posting_date": expense_doc.expense_date,
                "account": tax.account_head,
                "debit": tax_debit,
                "credit": tax_credit,
                "debit_in_account_currency": tax_debit,
                "credit_in_account_currency": tax_credit,
                "voucher_type": "Hospitality Expense",
                "voucher_no": expense_doc.name,
                "remarks": f"Tax: {tax.description or tax.account_head} for {expense_doc.name}",
                "is_cancelled": 1 if is_cancelled else 0,
                "hospitality_property": expense_doc.get('property'),
                "cost_center": expense_doc.cost_center,
                "company": company
            }))

    # 3. Credit Payment Account (Grand Total)
    payment_debit = 0 if not is_cancelled else abs(flt(expense_doc.grand_total))
    payment_credit = abs(flt(expense_doc.grand_total)) if not is_cancelled else 0
    gl_entries.append(frappe.get_doc({
        "doctype": "GL Entry",
        "posting_date": expense_doc.expense_date,
        "account": expense_doc.payment_account,
        "debit": payment_debit,
        "credit": payment_credit,
        "debit_in_account_currency": payment_debit,
        "credit_in_account_currency": payment_credit,
        "voucher_type": "Hospitality Expense",
        "voucher_no": expense_doc.name,
        "remarks": f"Payment via {expense_doc.paid_via} for {expense_doc.name}",
        "is_cancelled": 1 if is_cancelled else 0,
        "hospitality_property": expense_doc.get('property'),
        "cost_center": expense_doc.cost_center,
        "company": company
    }))

    for entry in gl_entries:
        entry.insert(ignore_permissions=True)

@frappe.whitelist()
def run_pos_cancellation_test():
    import time
    from frappe.utils import nowdate
    print("Starting POS Cancellation Fix Verification Test...")
    
    # 1. Setup Data
    company = frappe.db.get_default("company") or frappe.defaults.get_user_default("Company") or "CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO"
    ts = str(int(time.time()))
    room_number = "101TEST"
    item_code = "TEST_BEER"
    
    if not frappe.db.exists("Hotel Room", room_number):
        frappe.get_doc({
            "doctype": "Hotel Room", 
            "room_number": room_number, 
            "status": "Available", 
            "is_group_room": 0,
            "room_type": "Classic Deluxe",
            "hotel_reception": "Old Building"
        }).insert()

    guest_name = "ZOFMON INVESTMENT"
    customer = frappe.db.get_value("Guest", guest_name, "customer")

    if not customer:
        # Fallback if specific guest doesn't have customer
        guest_name = frappe.db.get_value("Guest", {}, "name")
        customer = frappe.db.get_value("Guest", guest_name, "customer")

    if not frappe.db.exists("Item", item_code):
        frappe.get_doc({
            "doctype": "Item",
            "item_code": item_code,
            "item_name": "Test Beer",
            "item_group": "Drinks",
            "is_stock_item": 0,
            "opening_stock": 0,
            "valuation_rate": 0,
            "standard_rate": 2000
        }).insert()

    # Create Reservation & Check-in
    res = frappe.get_doc({
        "doctype": "Hotel Reservation",
        "company": company,
        "hotel_reception": "Old Building",
        "guest": guest_name,
        "room_type": "Classic Deluxe",
        "room": room_number,
        "arrival_date": nowdate(),
        "departure_date": nowdate(),
        "status": "Reserved",
        "allow_pos_posting": 1
    }).insert(ignore_permissions=True)
    res.process_check_in()
    
    folio_name = frappe.db.get_value("Guest Folio", {"reservation": res.name}, "name")
    print(f"Checkout Reservation: {res.name}, Folio: {folio_name}")

    # 2. Create POS Invoice
    pos_profile = frappe.db.get_value("POS Profile", {"company": company}, "name")
    
    pos_inv = frappe.get_doc({
        "doctype": "POS Invoice",
        "company": company,
        "customer": customer,
        "pos_profile": pos_profile,
        "posting_date": nowdate(),
        "hotel_room": room_number,
        "update_stock": 0,
        "items": [
            {
                "item_code": item_code,
                "qty": 1,
                "rate": 2450,
                "amount": 2450
            }
        ],
        "payments": [
            {
                "mode_of_payment": "Guest Account",
                "amount": 2450,
                "account": frappe.db.get_value("Mode of Payment Account", {"parent": "Guest Account", "company": company}, "default_account")
            }
        ]
    })
    
    pos_inv.insert(ignore_permissions=True)
    pos_inv.submit()
    print(f"Submitted POS Invoice: {pos_inv.name}")

    # 3. Verify GL Entries
    gl_entries = frappe.get_all("GL Entry", filters={"voucher_no": pos_inv.name, "is_cancelled": 0})
    print(f"Found {len(gl_entries)} GL entries for {pos_inv.name}")
    
    # 4. Cancel POS Invoice
    pos_inv.cancel()
    print(f"Successfully cancelled POS Invoice: {pos_inv.name}")

    # 5. Verify Reversal
    reversals = frappe.get_all("GL Entry", filters={"voucher_no": pos_inv.name, "is_cancelled": 1})
    print(f"Found {len(reversals)} reversal GL entries for {pos_inv.name}")

    if len(reversals) > 0:
        print("PASS: Reversal GL entries created.")
    else:
        print("FAIL: No reversal GL entries found.")

    # 6. Check Folio Transactions
    txn_count = frappe.db.count("Folio Transaction", {"reference_name": pos_inv.name})
    if txn_count == 0:
        print("PASS: Folio Transactions deleted upon cancellation.")
    else:
        print(f"FAIL: {txn_count} Folio Transactions still exist.")

@frappe.whitelist()
def execute_cleanup():
    # Full destructive data wipe — restrict to System Manager only.
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Access Denied. Only System Managers can execute this cleanup."), frappe.PermissionError)

    import hospitality_core.hospitality_core.hospitality_core.clear_hotel_data as clear_data
    clear_data.execute()
    return "Data wipe executed successfully via API."
