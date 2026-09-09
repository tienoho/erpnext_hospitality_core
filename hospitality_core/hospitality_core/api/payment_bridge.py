import frappe
from frappe import _

def _get_hotel_company(folio=None):
    if folio:
        if getattr(folio, "operating_company", None):
            return folio.operating_company
        if getattr(folio, "hotel_company", None):
            return folio.hotel_company
    default_co = frappe.db.get_single_value("Global Defaults", "default_company")
    if default_co:
        return default_co
    user_co = frappe.defaults.get_user_default("Company")
    if user_co:
        return user_co
    first_co = frappe.db.get_value("Company", {}, "name")
    return first_co or "CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO"

@frappe.whitelist()
def create_folio_payment(folio_name, amount, mode_of_payment, hotel_reception):
    """
    Simplified payment recording from the Guest Folio.
    Receives only: folio, amount, mode of payment, and hotel reception.
    Automatically resolves: customer, account, poster name, room number, and submits.
    """
    if not frappe.has_permission("Guest Folio", "write", doc=folio_name):
        frappe.throw(_("Not permitted to record a payment on Folio {0}.").format(folio_name), frappe.PermissionError)

    amount = float(amount or 0)
    if amount <= 0:
        frappe.throw(_("Amount must be greater than zero."))

    # 1. Load the Folio
    folio = frappe.get_doc("Guest Folio", folio_name)
    if folio.status not in ("Open", "Closed"):
        frappe.throw(_("Cannot record payment for a folio with status: {0}").format(folio.status))

    COMPANY = _get_hotel_company(folio)

    # 2. Resolve Customer (from Guest or Company)
    customer = None
    guest_name_display = folio.guest or ""

    if folio.guest:
        customer = frappe.db.get_value("Guest", folio.guest, "customer")
        full_name = frappe.db.get_value("Guest", folio.guest, "full_name")
        if full_name:
            guest_name_display = full_name

    # If no customer linked yet, auto-create one
    if not customer and folio.guest:
        cust = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": guest_name_display,
            "customer_type": "Individual"
        })
        cust.insert(ignore_permissions=True)
        frappe.db.set_value("Guest", folio.guest, "customer", cust.name)
        customer = cust.name

    if not customer:
        frappe.throw(_("No customer could be resolved for Folio {0}.").format(folio_name))

    # 3. Resolve the paid_to Account from Mode of Payment (always using Edo Heritage Hotel)
    mop_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": COMPANY},
        "default_account"
    )
    if not mop_account:
        # Try without company filter as fallback
        mop_account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mode_of_payment},
            "default_account"
        )
    if not mop_account:
        frappe.throw(_(
            "No account configured for Mode of Payment '{0}' under {1}. "
            "Please add a default account for it."
        ).format(mode_of_payment, COMPANY))

    # 4. Resolve the Accounts Receivable account from operating company
    receivable_account = frappe.db.get_value(
        "Company", COMPANY, "default_receivable_account"
    )
    if not receivable_account:
        frappe.throw(_("No Default Receivable Account found for '{0}'. Please configure it in Company settings.").format(COMPANY))

    # 5. Resolve poster's full name from session
    poster_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

    # 6. Build and insert the Payment Entry
    pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "company": COMPANY,
        "payment_type": "Receive",
        "posting_date": frappe.utils.nowdate(),
        "party_type": "Customer",
        "party": customer,
        "party_name": guest_name_display,
        "paid_from": receivable_account,
        "paid_to": mop_account,
        "paid_amount": amount,
        "received_amount": amount,
        "source_exchange_rate": 1,
        "target_exchange_rate": 1,
        "mode_of_payment": mode_of_payment,
        "hotel_reception": hotel_reception,
        "reference_no": folio_name,
        "reference_date": frappe.utils.nowdate(),
        "room_number": folio.room,
        "cashier": frappe.session.user,
        # TRƯỚC ĐÂY: không set hospitality_property — Payment Entry (nằm
        # trong CORE_SCOPED) mãi mãi NULL nếu KHÔNG đi qua property_accounting.py's
        # payment_updated() (chỉ chạy khi hospitality_accounting_version=='Property
        # v2') — luồng payment_bridge.py này chạy cho MỌI folio Legacy, kể cả
        # folio ĐÃ có property riêng (property và accounting_version tách biệt),
        # nên field này sẽ NULL vĩnh viễn nếu không set ở đây.
        "hospitality_property": folio.get('property'),
        "remarks": (
            f"Payment by {poster_name} — Guest: {guest_name_display} "
            f"| Room: {folio.room} | Reception: {hotel_reception} | Folio: {folio_name}"
        )
    })
    pe.insert(ignore_permissions=True)
    pe.submit()

    return pe.name

@frappe.whitelist()
def issue_folio_refund(folio_name, amount, hotel_reception):
    """
    Issues a refund to a guest with excess balance.
    Creates a Payment Entry of type 'Pay'.
    """
    from hospitality_core.hospitality_core.api.folio_operations import _check_supervisor
    _check_supervisor()

    amount = float(amount or 0)
    if amount <= 0:
        frappe.throw(_("Refund amount must be greater than zero."))

    # 1. Load the Folio
    folio = frappe.get_doc("Guest Folio", folio_name)
    if folio.status not in ("Open", "Closed"):
        frappe.throw(_("Cannot record refund for a folio with status: {0}").format(folio.status))

    COMPANY = _get_hotel_company(folio)

    # Check excess balance
    if folio.outstanding_balance >= -0.01:
        frappe.throw(_("Cannot issue refund. The folio does not have an excess balance."))

    excess_balance = abs(folio.outstanding_balance)
    if amount > (excess_balance + 0.01): # allow small floating diff
        frappe.throw(_("Refund amount cannot exceed the available credit of {0}.").format(
            frappe.format(excess_balance, "Currency")
        ))

    # 2. Resolve Customer (from Guest or Company)
    customer = None
    guest_name_display = folio.guest or ""

    if folio.guest:
        customer = frappe.db.get_value("Guest", folio.guest, "customer")
        full_name = frappe.db.get_value("Guest", folio.guest, "full_name")
        if full_name:
            guest_name_display = full_name

    # If no customer linked yet, auto-create one
    if not customer and folio.guest:
        cust = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": guest_name_display,
            "customer_type": "Individual"
        })
        cust.insert(ignore_permissions=True)
        frappe.db.set_value("Guest", folio.guest, "customer", cust.name)
        customer = cust.name

    if not customer:
        frappe.throw(_("No customer could be resolved for Folio {0}.").format(folio_name))

    mode_of_payment = "Refund - Reception"
    if not frappe.db.exists("Mode of Payment", mode_of_payment):
        mop = frappe.new_doc("Mode of Payment")
        mop.mode_of_payment = mode_of_payment
        mop.type = "Cash"
        # We need an account, default cash account
        cash_account = frappe.db.get_value("Company", COMPANY, "default_cash_account")
        if not cash_account:
            cash_account = frappe.db.get_value("Account", {"account_type": "Cash", "company": COMPANY}, "name")
        mop.append("accounts", {"company": COMPANY, "default_account": cash_account})
        mop.insert(ignore_permissions=True)

    # 3. Resolve the paid_from Account from Mode of Payment
    mop_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": COMPANY},
        "default_account"
    )
    if not mop_account:
        mop_account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mode_of_payment},
            "default_account"
        )
    if not mop_account:
        frappe.throw(_(
            "No account configured for Mode of Payment '{0}' under Edo Heritage Hotel. "
            "Please add a default account for it."
        ).format(mode_of_payment))

    # 4. Resolve the Accounts Receivable account from Edo Heritage Hotel
    receivable_account = frappe.db.get_value(
        "Company", COMPANY, "default_receivable_account"
    )
    if not receivable_account:
        frappe.throw(_("No Default Receivable Account found for 'Edo Heritage Hotel'. Please configure it in Company settings."))

    # 5. Resolve poster's full name from session
    poster_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

    # 6. Build and insert the Payment Entry
    pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "company": COMPANY,
        "payment_type": "Pay",
        "posting_date": frappe.utils.nowdate(),
        "party_type": "Customer",
        "party": customer,
        "party_name": guest_name_display,
        "paid_from": mop_account,
        "paid_to": receivable_account,
        "paid_amount": amount,
        "received_amount": amount,
        "source_exchange_rate": 1,
        "target_exchange_rate": 1,
        "mode_of_payment": mode_of_payment,
        "hotel_reception": hotel_reception,
        "reference_no": folio_name,
        "reference_date": frappe.utils.nowdate(),
        "room_number": folio.room,
        "cashier": frappe.session.user,
        # Xem chú thích tương tự ở create_folio_payment() — folio Legacy vẫn có
        # thể có property riêng, không set ở đây thì hospitality_property NULL
        # vĩnh viễn với Payment Entry loại hoàn tiền này.
        "hospitality_property": folio.get('property'),
        "remarks": (
            f"Refund by {poster_name} — Guest: {guest_name_display} "
            f"| Room: {folio.room} | Reception: {hotel_reception} | Folio: {folio_name}"
        )
    })
    pe.insert(ignore_permissions=True)
    pe.submit()

    return pe.name

@frappe.whitelist()
def issue_ledger_refund(ledger_name, amount, hotel_reception):
    """
    Issues a refund from the Guest Balance Ledger.
    Delegates to the originating folio's refund method and updates the ledger record.
    """
    ledger = frappe.get_doc("Guest Balance Ledger", ledger_name)
    if ledger.status != "Available":
        frappe.throw(_("Can only refund from an Available ledger entry."))
    
    amount = float(amount or 0)
    if amount <= 0:
        frappe.throw(_("Refund amount must be greater than zero."))
    
    if amount > (float(ledger.amount) + 0.01):
        frappe.throw(_("Refund amount cannot exceed the ledger balance of {0}.").format(
            frappe.format(ledger.amount, "Currency")
        ))

    # Process the refund against the originating folio
    # This creates the Payment Entry and posts a Folio Transaction
    payment_name = issue_folio_refund(ledger.folio, amount, hotel_reception)
    
    # Update the Ledger
    new_amount = float(ledger.amount) - amount
    if new_amount <= 0.01:
        frappe.db.set_value("Guest Balance Ledger", ledger_name, {
            "amount": 0,
            "status": "Refunded"
        })
    else:
        frappe.db.set_value("Guest Balance Ledger", ledger_name, "amount", new_amount)
        
    return payment_name

def process_payment_entry(doc, method=None):
    """
    Hook: Payment Entry (on_submit, on_cancel)
    Logic: If Reference No matches a Guest Folio ID, post or void a credit transaction to that Folio.
    """
    if doc.get('hospitality_accounting_version') == 'Property v2':
        return
    # Check if linked to Folio via Reference No
    # We expect reference_no to hold the Folio ID (e.g., FOLIO-...)
    if not doc.reference_no or not frappe.db.exists("Guest Folio", doc.reference_no):
        return
        
    folio_name = doc.reference_no
    
    # Determine Amount (Paid Amount is usually positive in Payment Entry)
    amount = doc.paid_amount

    if doc.docstatus == 1: # On Submit
        if doc.payment_type == "Pay":
            credit_amount = abs(amount)
            item_code = "REFUND"
            item_name = "Refund Debit"
        else:
            credit_amount = -1 * abs(amount)
            item_code = "PAYMENT"
            item_name = "Payment Credit"
        
        # Ensure Payment Item Exists with proper UOM
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists(item_code, item_name)
        
        # Determine bill_to based on whether this is a Company or Group Master Folio
        # TRƯỚC ĐÂY: chỉ kiểm tra is_company_master — group_booking.py's
        # record_group_deposit()/create_company_folio_payment() giờ CŨNG tạo
        # Payment Entry thẳng trên Master Folio của ĐOÀN (không bao giờ có
        # is_company_master=1, xem ghi chú tương tự ở city_ledger.py), khiến
        # giao dịch cọc đoàn bị gắn nhầm bill_to="Guest" thay vì "Group" —
        # không khớp quy ước Company/Group/Guest dùng nhất quán ở mọi nơi
        # khác (pos_bridge.py, folio.py, rate_plan.py).
        is_company_folio = frappe.db.get_value("Guest Folio", folio_name, "is_company_master")
        is_group_folio = frappe.db.exists("Hotel Group Booking", {"master_folio": folio_name})
        bill_to = "Company" if is_company_folio else ("Group" if is_group_folio else "Guest")

        # Insert Transaction
        # TRƯỚC ĐÂY: thiếu flags.hospitality_service — property_scope.py's
        # validate_document() bắt buộc 1 trong 3 flag cho MỌI Folio Transaction
        # ghi vào folio Property v2. Đây là hàm hook on_submit của MỌI Payment
        # Entry liên kết folio (thanh toán/hoàn tiền khách) — thiếu flag này sẽ
        # chặn đứng TOÀN BỘ việc ghi nhận thanh toán khách ngay khi property
        # đầu tiên cutover Property v2, nghiêm trọng hơn cả lỗi tương tự đã
        # tìm thấy ở pos_bridge.py's process_room_charge() vì đây là luồng
        # thanh toán chạy hàng ngày, không riêng ký nợ phòng qua POS.
        payment_txn = frappe.get_doc({
            "doctype": "Folio Transaction",
            "parent": folio_name,
            "parenttype": "Guest Folio",
            "parentfield": "transactions",
            "posting_date": doc.posting_date,
            "item": item_code,
            "description": f"Payment Entry: {doc.name} ({doc.mode_of_payment})",
            "qty": 1,
            "amount": credit_amount,
            "bill_to": bill_to,
            "reference_doctype": "Payment Entry",
            "reference_name": doc.name,
            "is_invoiced": 0  # Payments are not invoices
        })
        payment_txn.flags.hospitality_service = True
        payment_txn.insert(ignore_permissions=True)
        
        # Handle Accounting: Suspense -> Income transfer
        from hospitality_core.hospitality_core.api.accounting import handle_payment_income_realization
        handle_payment_income_realization(doc, folio_name, amount, cancel=1 if doc.payment_type == "Pay" else 0)
        
        msg = "Refund" if doc.payment_type == "Pay" else "Payment"
        frappe.msgprint(_("{0} of {1} successfully recorded on Folio {2}").format(msg, amount, folio_name))

    elif doc.docstatus == 2: # On Cancel
        # 1. Find and Delete the Folio Transaction
        frappe.db.delete("Folio Transaction", {
            "reference_doctype": "Payment Entry",
            "reference_name": doc.name
        })
        
        # 2. Reverse Accounting Realization
        from hospitality_core.hospitality_core.api.accounting import handle_payment_income_realization
        handle_payment_income_realization(doc, folio_name, amount, cancel=0 if doc.payment_type == "Pay" else 1)
    
    # Sync Balance
    from hospitality_core.hospitality_core.api.folio import sync_folio_balance
    sync_folio_balance(frappe.get_doc("Guest Folio", folio_name))

@frappe.whitelist()
def create_company_folio_payment(folio_name, amount, mode_of_payment, hotel_reception, reference_no='', remarks=''):
    """
    Records a payment received from a company against its City Ledger (Company Master Folio).
    Creates a proper Payment Entry (same as guest payments) so that accounting entries are
    generated correctly. The process_payment_entry hook then posts the credit Folio Transaction.
    """
    from hospitality_core.hospitality_core.api.folio_operations import _check_supervisor
    _check_supervisor()

    amount = float(amount or 0)
    if amount <= 0:
        frappe.throw(_("Amount must be greater than zero."))

    folio = frappe.get_doc("Guest Folio", folio_name)

    # Master Folio của ĐOÀN (Hotel Group Booking) không bao giờ được gán
    # is_company_master=1 (chỉ Master Folio của Company mới có, xem
    # ensure_company_folio() trong hotel_reservation.py) — dùng cùng cách
    # nhận diện đã thiết lập cho city_ledger.py/ar_aging_summary.py để hàm
    # này CŨNG dùng ghi nhận đặt cọc/thanh toán đoàn được (xem
    # group_booking.py's record_group_deposit()), thay vì phải viết lại
    # toàn bộ logic tạo Payment Entry lần thứ 2.
    is_group_master = frappe.db.exists("Hotel Group Booking", {"master_folio": folio.name})
    if not folio.is_company_master and not is_group_master:
        frappe.throw(_("Record Payment to Company can only be used on a Company or Group Master Folio."))

    if folio.status != "Open":
        frappe.throw(_("Cannot record a payment on a folio with status: {0}").format(folio.status))

    # Hàm này (và create_folio_payment() — bản dành cho khách lẻ) chỉ triển
    # khai đúng cơ chế kế toán LEGACY: tạo Payment Entry KHÔNG set
    # hospitality_accounting_version, dựa vào process_payment_entry()'s hook
    # (on_submit của Payment Entry) để vừa ghi Folio Transaction giảm số dư
    # VỪA chạy handle_payment_income_realization() (chuyển Suspense->Income
    # theo đúng mô hình kế toán Legacy). Property v2 dùng mô hình HOÀN TOÀN
    # khác (income đã ghi nhận thẳng lúc phát sinh charge qua post_charge(),
    # không qua Suspense) và có luồng thanh toán RIÊNG
    # (property_accounting.py's receive_payment()) — nhưng luồng đó hiện chỉ
    # xử lý thanh toán KHÁCH LẺ (party=folio.billing_customer, bill_to='Guest'
    # cứng), CHƯA có phiên bản dành cho Company/Group giống hàm này. Nếu cứ
    # để hàm Legacy này chạy tiếp trên 1 folio đã là 'Property v2' (như Master
    # Folio đoàn của 1 property đã cutover), sẽ xảy ra 1 trong 2 hậu quả xấu:
    # (a) crash "Account is required" nếu global Hospitality Accounting
    # Settings (Legacy) chưa cấu hình song song (thường ĐÚNG NHƯ VẬY trên 1
    # site đã chuyển hẳn sang Property v2), hoặc (b), nguy hiểm hơn, ghi
    # nhận doanh thu TRÙNG LẦN THỨ HAI qua handle_payment_income_realization()
    # nếu lỡ có cấu hình Legacy song song — vì doanh thu đã được ghi nhận
    # đúng 1 lần lúc phát sinh charge (post_charge()) rồi. Chặn tường minh,
    # rõ ràng ở đây thay vì để crash khó hiểu hoặc âm thầm ghi sai GL — cho
    # tới khi có 1 hàm thanh toán Company/Group riêng cho Property v2.
    if folio.get("accounting_version") == "Property v2":
        frappe.throw(_(
            "Folio {0} đã dùng kế toán Property v2 — chức năng ghi nhận thanh toán Công ty/Đoàn này chỉ hỗ trợ "
            "Folio kế toán Legacy. Property v2 hiện chưa có hàm thanh toán Công ty/Đoàn riêng (chỉ có "
            "receive_payment() cho khách lẻ)."
        ).format(folio.name))

    if not folio.company:
        frappe.throw(_("This Company Folio has no company linked. Please set the Company field first."))

    # folio.company is a Link to Customer — use it directly as the party
    customer = folio.company
    company_name = frappe.db.get_value("Customer", customer, "customer_name") or customer

    # Company (hotel)
    COMPANY = _get_hotel_company(folio)

    # Resolve paid_to account from Mode of Payment
    mop_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": COMPANY},
        "default_account"
    )
    if not mop_account:
        mop_account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mode_of_payment},
            "default_account"
        )
    if not mop_account:
        frappe.throw(_(
            "No account configured for Mode of Payment '{0}' under {1}. "
            "Please add a default account for it."
        ).format(mode_of_payment, COMPANY))

    # Resolve Accounts Receivable account
    receivable_account = frappe.db.get_value("Company", COMPANY, "default_receivable_account")
    if not receivable_account:
        frappe.throw(_("No Default Receivable Account found for '{0}'. Please configure it in Company settings.").format(COMPANY))

    poster_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    narration = remarks or (
        f"City Ledger Payment — Company: {company_name} | Mode: {mode_of_payment}"
        + (f" | Ref: {reference_no}" if reference_no else "")
        + f" | Folio: {folio_name} | By: {poster_name}"
    )

    # Build and submit the Payment Entry — identical pattern to guest payments
    pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "company": COMPANY,
        "payment_type": "Receive",
        "posting_date": frappe.utils.nowdate(),
        "party_type": "Customer",
        "party": customer,
        "party_name": company_name,
        "paid_from": receivable_account,
        "paid_to": mop_account,
        "paid_amount": amount,
        "received_amount": amount,
        "source_exchange_rate": 1,
        "target_exchange_rate": 1,
        "mode_of_payment": mode_of_payment,
        "hotel_reception": hotel_reception,
        "reference_no": folio_name,          # triggers process_payment_entry hook
        "reference_date": frappe.utils.nowdate(),
        "cashier": frappe.session.user,
        # Xem chú thích tương tự ở create_folio_payment() — Master Folio công ty
        # Legacy vẫn có thể có property riêng.
        "hospitality_property": folio.get('property'),
        "remarks": narration
    })
    pe.insert(ignore_permissions=True)
    pe.submit()

    # Note: process_payment_entry hook (on_submit) will automatically:
    #   1. Post the credit Folio Transaction (bill_to='Company')
    #   2. Sync the folio balance

    return pe.name


@frappe.whitelist()
def create_company_folio_transaction(folio_name, item, description, qty, amount, posting_date, remarks=''):
    """
    Manually posts a debit (charge) transaction to a Company Master Folio (City Ledger).
    Used for recording miscellaneous charges directly against a company account.
    """
    from hospitality_core.hospitality_core.api.folio_operations import _check_supervisor
    _check_supervisor()

    amount = float(amount or 0)
    qty = float(qty or 1)

    if amount <= 0:
        frappe.throw(_("Amount must be a positive value for a debit entry."))

    folio = frappe.get_doc("Guest Folio", folio_name)

    if not folio.is_company_master:
        frappe.throw(_("Record Transaction can only be used on a Company Master Folio."))

    if folio.status != "Open":
        frappe.throw(_("Cannot post a transaction to a folio with status: {0}").format(folio.status))

    if not folio.company:
        frappe.throw(_("This Company Folio has no company linked. Please set the Company field first."))

    # Validate Item
    if not frappe.db.exists("Item", item):
        frappe.throw(_("Item '{0}' does not exist.").format(item))

    poster_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    full_description = description
    if remarks:
        full_description = f"{description} | {remarks}"
    full_description += f" [Posted by: {poster_name}]"

    txn = frappe.get_doc({
        "doctype": "Folio Transaction",
        "parent": folio_name,
        "parenttype": "Guest Folio",
        "parentfield": "transactions",
        "posting_date": posting_date or frappe.utils.nowdate(),
        "item": item,
        "description": full_description,
        "qty": qty,
        "amount": abs(amount),   # Positive = debit charge
        "bill_to": "Company",
        "is_void": 0,
        "is_invoiced": 0
    })
    txn.flags.hospitality_service = True  # xem chú thích ở process_payment_entry()
    txn.insert(ignore_permissions=True)

    # Sync Company Folio Balance
    from hospitality_core.hospitality_core.api.folio import sync_folio_balance
    sync_folio_balance(frappe.get_doc("Guest Folio", folio_name))

    frappe.msgprint(
        _("Debit transaction of {0} posted to Company Folio {1}.").format(
            frappe.format(abs(amount), "Currency"), folio_name
        )
    )

    return txn.name


def adjust_payment_date(doc, method=None):
    """
    Hook: Payment Entry (before_insert)
    Logic: If a payment is created before 8 AM, it belongs to the previous Hospitality Day.
    Therefore, the posting_date should be set to yesterday.
    """
    from frappe.utils import now_datetime, add_days, getdate
    
    if now_datetime().hour < 8:
        # If it's before 8 AM, adjust posting date to yesterday
        doc.posting_date = add_days(getdate(), -1)
