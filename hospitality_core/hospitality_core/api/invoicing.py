import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def create_invoice_from_folio(folio_name):
    """
    Generates a Sales Invoice for all unbilled transactions in the Folio.
    """
    if frappe.db.get_value('Guest Folio', folio_name, 'accounting_version') == 'Property v2':
        from hospitality_core.hospitality_core.api.property_accounting import create_invoice
        return create_invoice(folio_name)
    if not frappe.has_permission("Guest Folio", "write", doc=folio_name):
        frappe.throw(_("Not permitted to invoice Folio {0}.").format(folio_name), frappe.PermissionError)

    # Khóa dòng Guest Folio (SELECT ... FOR UPDATE) TRƯỚC KHI đọc danh sách giao
    # dịch chưa xuất hóa đơn — nếu không, double-click nút "Tạo hóa đơn", hoặc
    # 2 nhân viên (lễ tân + kế toán) cùng thao tác trên cùng 1 folio gần như
    # đồng thời, đều có thể đọc thấy CÙNG một tập giao dịch "chưa xuất hóa đơn"
    # (vì is_invoiced chỉ được đánh dấu SAU KHI tạo hóa đơn xong ở cuối hàm),
    # dẫn đến 2 Sales Invoice riêng biệt cùng billing cho đúng các khoản đó —
    # khách/công ty bị lập hóa đơn trùng 2 lần cho cùng một khoản chi phí.
    frappe.db.sql("SELECT name FROM `tabGuest Folio` WHERE name=%s FOR UPDATE", folio_name)

    # QUAN TRỌNG: khóa TRỰC TIẾP các dòng Folio Transaction chưa xuất hóa đơn
    # bằng chính locking read này, thay vì chỉ tin vào folio.transactions nạp
    # qua frappe.get_doc() bên dưới (một plain SELECT riêng). Dưới REPEATABLE
    # READ (mặc định MariaDB), khóa FOR UPDATE ở dòng Guest Folio phía trên
    # chỉ đảm bảo đọc bản mới nhất của CHÍNH dòng đó — không khiến plain SELECT
    # tải bảng con bên dưới tự động thấy được is_invoiced=1 mà một request
    # khác vừa commit. Dùng danh sách `unbilled_names` (đọc bằng locking read
    # thật) làm nguồn chân lý duy nhất để quyết định giao dịch nào được billing,
    # thay vì tin vào cờ is_invoiced đọc được qua get_doc().
    unbilled_names = set(frappe.db.sql_list(
        "SELECT name FROM `tabFolio Transaction` WHERE parent=%s AND is_invoiced=0 AND is_void=0 FOR UPDATE",
        folio_name
    ))

    folio = frappe.get_doc("Guest Folio", folio_name)

    # Determine Customer
    # If Folio has a specific Company linked, use that. Otherwise, check Guest -> Customer link.
    customer = folio.company
    if not customer:
        guest_doc = frappe.get_doc("Guest", folio.guest)
        if guest_doc.customer:
            customer = guest_doc.customer
        else:
            frappe.throw(_("Please link a Customer (Company) to this Folio or the Guest Profile to generate an Invoice."))

    # Identify Unbilled Transactions
    items_to_bill = []
    transaction_ids = []
    
    # Use the Company defined on the Customer or default to user's company (but ideally Folio should drive this if multi-company)
    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")

    # Fetch default Cost Center for this Company
    default_cost_center = frappe.get_cached_value('Company', company, 'cost_center')

    # TRƯỚC ĐÂY: mỗi dòng item dùng income_account THẬT với rate GROSS (gồm
    # cả thuế, không áp tax template) — nhưng MỌI Folio Transaction trên
    # folio Legacy đã được accounting.py's make_gl_entries_for_folio_transaction()
    # ghi nhận doanh thu NGAY LÚC PHÁT SINH CHARGE (Receivable nợ / Income
    # Suspense có phần NET / 3 TK thuế có phần thuế), chạy tự động qua hook
    # on_update. Xác nhận CHẮC CHẮN (không phải giả định): `einvoice.py`'s
    # `issue_einvoice_from_folio()` gọi thẳng hàm này RỒI TỰ SUBMIT hóa đơn
    # (`si_doc.submit()`) — đây là luồng phát hành hóa đơn điện tử TIÊU
    # CHUẨN, chạy thật, không phải rủi ro giả định "nếu ai đó submit". GL
    # chuẩn của ERPNext khi submit sẽ ghi Debtors nợ / Income credit — DOANH
    # THU BỊ GHI NHẬN HAI LẦN cho cùng 1 khoản charge, mỗi lần công ty phát
    # hành hóa đơn điện tử.
    #
    # Sửa TẬN GỐC (không chỉ giảm nhẹ): tách rate thành NET (dùng
    # get_tax_breakdown() y hệt công thức accounting.py) + thêm 3 dòng thuế
    # thật trên hóa đơn — để hóa đơn điện tử hiển thị ĐÚNG chuẩn (income
    # account thật + breakdown thuế rõ ràng, không lộ tài khoản nội bộ
    # "Income Suspense" ra chứng từ pháp lý). Đồng thời wire hook MỚI
    # `accounting.py`'s `reverse_charge_time_gl_on_invoice_submit()` (đăng
    # ký ở on_submit/on_cancel của Sales Invoice) — hook đó tìm CHÍNH XÁC
    # các GL Entry đã ghi lúc charge (qua voucher_type='Guest Folio' +
    # voucher_no + voucher_detail_no, không suy đoán lại) rồi ĐẢO NGƯỢC
    # đúng số tiền đó tại thời điểm hóa đơn submit — triệt tiêu hoàn toàn
    # phần ghi trùng, không chỉ nhân đôi cùng tỷ lệ như hướng giảm nhẹ ban
    # đầu. Nhờ có cơ chế đảo chính xác này, income_account ở đây có thể
    # dùng THẬT (không cần né qua Income Suspense nữa).
    from hospitality_core.hospitality_core.api.accounting import get_tax_breakdown

    settings = frappe.get_single('Hospitality Accounting Settings')
    vat_account = getattr(settings, 'vat_account', None)
    service_charge_account = getattr(settings, 'service_charge_account', None)
    consumption_tax_account = getattr(settings, 'consumption_tax_account', None)
    can_split_tax = bool(vat_account and service_charge_account and consumption_tax_account)

    tax_totals = {}

    for trans in folio.transactions:
        if trans.name in unbilled_names:
            amount = flt(trans.amount)
            sign = -1 if amount < 0 else 1
            income_account = get_income_account(trans.item, company)
            if not income_account:
                frappe.throw(_("Could not determine Income Account for Item {0} in Company {1}. Please check Item or Item Group accounting defaults.").format(trans.item, company))

            if can_split_tax:
                parts = get_tax_breakdown(abs(amount))
                rate = sign * parts['net_amount'] / trans.qty if trans.qty else 0
                for acct, amt in ((vat_account, parts['vat_amount']),
                                  (service_charge_account, parts['sc_amount']),
                                  (consumption_tax_account, parts['ct_amount'])):
                    tax_totals[acct] = tax_totals.get(acct, 0) + sign * amt
            else:
                rate = amount / trans.qty if trans.qty else 0

            items_to_bill.append({
                "item_code": trans.item,
                "description": trans.description,
                "qty": trans.qty,
                "rate": rate,
                "income_account": income_account,
                "cost_center": default_cost_center
            })
            transaction_ids.append(trans.name)

    if not items_to_bill:
        frappe.throw(_("No unbilled transactions found to invoice."))

    # Create Sales Invoice
    si = frappe.new_doc("Sales Invoice")
    si.customer = customer
    si.company = company
    si.posting_date = frappe.utils.nowdate()
    si.due_date = frappe.utils.nowdate()
    si.set("items", items_to_bill)

    # Cộng dồn 3 khoản thuế (VAT/Service Charge/Consumption Tax) thành các
    # dòng "Actual" trên chính hóa đơn — khớp đúng số tiền đã ghi ở
    # charge-time (accounting.py's get_tax_breakdown()), không để income
    # account của item ở trên gánh luôn cả phần thuế.
    for acct, amt in tax_totals.items():
        if abs(amt) > 0.005:
            si.append("taxes", {
                "charge_type": "Actual",
                "account_head": acct,
                "description": acct,
                "tax_amount": amt,
                "cost_center": default_cost_center,
            })
    # TRƯỚC ĐÂY: không set hospitality_property — Sales Invoice tạo qua đường
    # Legacy này (folio.accounting_version != 'Property v2', NHƯNG folio vẫn
    # có thể đã có property riêng vì gán property và cutover kế toán là 2
    # khái niệm TÁCH BIỆT) sẽ mãi mãi có hospitality_property=NULL — theo
    # đúng quy ước NULL-safe của CORE_SCOPED (property_scope.py), nghĩa là
    # user chỉ được cấp quyền property khác vẫn xem được hóa đơn này qua
    # list view/report chuẩn. Vì folio Legacy có thể tồn tại vô thời hạn
    # (không tự chuyển sang Property v2), đây không phải khoảng trống tạm
    # thời mà là lỗ hổng VĨNH VIỄN cho toàn bộ hóa đơn xuất qua đường Legacy.
    if folio.get('property'):
        si.hospitality_property = folio.property
    # TRƯỚC ĐÂY: không set hospitality_folio — einvoice.py's
    # issue_einvoice_from_folio() dựa vào field này để kiểm tra "folio này
    # đã có hóa đơn chưa" trước khi tạo hóa đơn mới; thiếu field này khiến
    # kiểm tra đó luôn thất bại, có thể tạo hóa đơn Sales Invoice TRÙNG lặp
    # cho cùng 1 folio ở lần phát hành hóa đơn điện tử tiếp theo.
    si.hospitality_folio = folio_name

    # Set Taxes (Optional: Fetch from Template)
    # si.set_taxes() 

    si.save()
    
    # Link Invoice to Transactions (to prevent double billing)
    for row_name in transaction_ids:
        frappe.db.set_value("Folio Transaction", row_name, {
            "is_invoiced": 1,
            "reference_doctype": "Sales Invoice",
            "reference_name": si.name
        })
    
    return si.name

def get_income_account(item_code, company):
    """
    Resolves the Income Account for an Item in the given Company.
    Order: Item Default > Item Group Default > Company Default
    """
    account = None

    # 1. Check 'Item Default' child table
    account = frappe.db.get_value("Item Default", {"parent": item_code, "company": company}, "income_account")

    # 2. Check Item Group's own defaults
    # TRƯỚC ĐÂY: query doctype "Item Group Default" — doctype này KHÔNG TỒN
    # TẠI trong ERPNext thật (đã xác minh trực tiếp mã nguồn vendored, bản
    # v16.34.1): Item Group's bảng con defaults dùng CHUNG doctype "Item
    # Default" với Item (cùng bảng `tabItem Default`), chỉ phân biệt qua
    # parenttype='Item Group' — filter cũ sẽ ném lỗi DB "Unknown table
    # 'tabItem Group Default'" (crash thật, không phải chỉ trả None) mỗi
    # khi bước 1 không tìm thấy và item có item_group.
    if not account:
        item_group = frappe.db.get_value("Item", item_code, "item_group")
        if item_group:
            account = frappe.db.get_value("Item Default",
                {"parent": item_group, "parenttype": "Item Group", "company": company}, "income_account")

    # 3. Fallback to Company Default
    if not account:
        account = frappe.get_cached_value('Company', company, 'default_income_account')
        
    return account
