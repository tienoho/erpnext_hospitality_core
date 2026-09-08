import frappe
from frappe import _
from frappe.utils import flt

def sync_folio_balance(doc, method=None):
    """
    Recalculates Total Charges, Total Payments, and Outstanding Balance.
    Triggered on: Guest Folio (on_update), Folio Transaction (on_update/on_trash).
    """
    # If called from Child Table event, doc is the child
    if doc.doctype == "Folio Transaction":
        folio_name = doc.parent
        # Trigger Mirroring only on new/updated transactions
        # We skip mirroring for transfer items to avoid zeroing out the Master Folio at checkout
        if (not doc.is_void and not doc.get("mirror_source")
                and doc.reference_doctype != "Folio Transaction"
                and doc.item not in ["TRANSFER", "TRANSFER-GROUP"]):
            if doc.bill_to == "Company":
                mirror_to_company_folio(doc)
            elif doc.bill_to == "Group":
                mirror_to_group_folio(doc)
    else:
        folio_name = doc.name

    # Khóa dòng Guest Folio (SELECT ... FOR UPDATE) để tuần tự hóa các lệnh
    # ghi lên chính field của Guest Folio giữa các lần gọi đồng thời.
    frappe.db.sql("SELECT name FROM `tabGuest Folio` WHERE name=%s FOR UPDATE", folio_name)

    # Aggregation Query
    # We filter out void transactions
    # Separate Actual Payments from Discounts/Complimentary items
    #
    # QUAN TRỌNG: bản thân câu SELECT tổng hợp này CŨNG PHẢI là locking read
    # (FOR UPDATE), không chỉ khóa dòng Guest Folio ở trên. Dưới REPEATABLE
    # READ (mặc định MariaDB), snapshot dùng cho các plain SELECT của cả
    # transaction được cố định từ lần đọc đầu tiên (thường xảy ra rất sớm, lúc
    # xác thực phiên/quyền — TRƯỚC KHI đến đoạn code này) — khóa FOR UPDATE ở
    # dòng Guest Folio phía trên chỉ đảm bảo đọc được bản mới nhất của CHÍNH
    # dòng đó, KHÔNG khiến câu SELECT tổng hợp bên dưới (một plain SELECT
    # khác, trên bảng Folio Transaction) tự động thấy được giao dịch vừa
    # commit của một transaction khác — nếu không thêm FOR UPDATE ở đây, 2
    # giao dịch đồng thời vẫn có thể lần lượt "xếp hàng" chờ khóa nhưng mỗi
    # bên vẫn tính tổng trên snapshot cũ, tái diễn đúng lỗi mà khóa này được
    # thêm vào để ngăn chặn — chỉ khác là lỗi xảy ra tuần tự thay vì đồng thời.
    totals = frappe.db.sql("""
        SELECT
            SUM(CASE WHEN amount > 0 AND item NOT IN ('DISCOUNT', 'COMPLIMENTARY') THEN amount ELSE 0 END) as charges,
            SUM(CASE
                WHEN amount < 0 AND item NOT IN ('DISCOUNT', 'COMPLIMENTARY') THEN ABS(amount)
                ELSE 0 END) as payments,
            SUM(CASE
                WHEN item IN ('DISCOUNT', 'COMPLIMENTARY') THEN -amount
                ELSE 0 END) as discounts
        FROM `tabFolio Transaction`
        WHERE parent = %s AND is_void = 0
        FOR UPDATE
    """, (folio_name,), as_dict=True)[0]

    total_charges = totals.charges or 0.0
    total_payments = totals.payments or 0.0
    total_discounts = totals.discounts or 0.0
    outstanding = total_charges - total_payments - total_discounts
    excess_payment = abs(outstanding) if outstanding < -0.01 else 0.0

    # Direct DB update
    frappe.db.set_value("Guest Folio", folio_name, {
        "total_charges": total_charges,
        "total_payments": total_payments,
        "total_discounts": total_discounts,
        "outstanding_balance": outstanding,
        "excess_payment": excess_payment
    })
    
    # Check Credit Limit if linked to Company
    folio_company = frappe.db.get_value("Guest Folio", folio_name, "company")
    if folio_company and outstanding > 0:
        check_credit_limit(folio_company, outstanding)

def check_credit_limit(customer_id, current_exposure):
    """
    Checks if the Customer has exceeded their Credit Limit including current exposure.
    """
    try:
        hotel_company = frappe.defaults.get_user_default("Company")
        if not hotel_company:
            hotel_company = frappe.db.get_single_value("Global Defaults", "default_company")
        
        if not hotel_company:
            return

        credit_limit = 0.0
        
        # 1. Try Child Table (v15+)
        if frappe.db.get_value("DocType", "Customer Credit Limit", "name"):
            credit_limit = frappe.db.get_value("Customer Credit Limit", 
                {"parent": customer_id, "company": hotel_company}, 
                "credit_limit"
            )
        
        # 2. Fallback to main field
        if not credit_limit:
             credit_limit = frappe.db.get_value("Customer", customer_id, "credit_limit")

        if not credit_limit or flt(credit_limit) <= 0:
            return

        # Get current ERP Balance for Customer
        erp_balance = 0.0
        try:
            from erpnext.accounts.utils import get_balance_on
            erp_balance = get_balance_on(party_type="Customer", party=customer_id)
        except ImportError:
            erp_balance = frappe.db.get_value("Customer", customer_id, "total_unpaid") or 0.0
        except Exception:
            pass

        total_liability = flt(erp_balance) + flt(current_exposure)
        
        if total_liability > flt(credit_limit):
            frappe.msgprint(_("Warning: Credit Limit Exceeded for {0}. Limit: {1}, Liability: {2}").format(
                customer_id, 
                frappe.format(credit_limit, "Currency"), 
                frappe.format(total_liability, "Currency")
            ), alert=True)

    except Exception as e:
        frappe.log_error(f"Credit Limit Check Failed for {customer_id}: {str(e)}", "Hospitality Core")

def mirror_to_company_folio(transaction_doc):
    """
    If a transaction is Bill To Company, we post a copy to the Company's Master Folio.
    Updates: Ensures description contains Guest/Reservation info.
    """
    # 1. Identify the Company
    guest_folio = frappe.get_doc("Guest Folio", transaction_doc.parent)
    company = guest_folio.company
    
    if not company:
        return

    # 2. Find Master Folio for Company
    master_filters = {
        "company": company, 
        "status": "Open",
        "is_company_master": 1,
        "name": ["!=", guest_folio.name]
    }
    if guest_folio.get('property'):
        master_filters.update(property=guest_folio.property, operating_company=guest_folio.operating_company, currency=guest_folio.currency)
    else:
        # Folio CHƯA được ánh xạ property (property=NULL, chờ wizard di trú) —
        # TRƯỚC ĐÂY không lọc gì thêm ở nhánh này, nên nếu 1 Customer dùng
        # chung cho nhiều property (VD 1 đại lý lữ hành đặt phòng ở cả 2 cơ
        # sở), câu tìm Master Folio có thể vô tình khớp trúng Master Folio
        # CỦA PROPERTY KHÁC (đã ánh xạ, property != NULL) — mirror nhầm chi
        # phí của cơ sở A vào sổ sách cơ sở B. Ép chỉ khớp Master Folio CŨNG
        # chưa ánh xạ (cùng "thế hệ" dữ liệu legacy) để không bao giờ vượt
        # ranh giới property.
        master_filters["property"] = ["is", "not set"]
    master_folio = frappe.db.get_value("Guest Folio", master_filters, "name")

    # If no master exists, we skip. It usually should be created at Reservation Check-in.
    if not master_folio:
        if not guest_folio.get('property'):
            # Folio nguồn chưa ánh xạ (property NULL) nhưng KHÔNG tìm thấy Master
            # Folio "cùng thế hệ" (cũng NULL) nào — có thể Master Folio của cùng
            # Company NÀY đã được migration wizard gán property TRƯỚC (property
            # chỉ bị khóa SAU lần lưu đầu có property, không có gì cấm 1 bản ghi
            # cũ đang NULL được gán property lần đầu bất cứ lúc nào), trong khi
            # giao dịch/folio con này thì chưa. Kết quả: giao dịch này sẽ KHÔNG
            # BAO GIỜ được mirror sang sổ Company nữa — không lỗi, không dấu vết,
            # chỉ phát hiện được qua đối soát thủ công. Ghi log rõ ràng ở đây để
            # vận hành còn biết mà xử lý, thay vì mất dấu hoàn toàn trong im lặng.
            orphan_risk = frappe.db.exists("Guest Folio", {
                "company": company, "status": "Open", "is_company_master": 1,
                "name": ["!=", guest_folio.name], "property": ["is", "set"],
            })
            if orphan_risk:
                frappe.log_error(
                    title="Folio Transaction chưa mirror do lệch nhịp cutover property",
                    message=(
                        f"Transaction {transaction_doc.name} trên Guest Folio {guest_folio.name} "
                        f"(company={company}, property chưa ánh xạ) không tìm được Master Folio "
                        f"cùng chưa ánh xạ, nhưng Master Folio {orphan_risk} của company này đã có "
                        f"property. Giao dịch này sẽ không được mirror sang Master Folio cho tới khi "
                        f"đối soát/mapping thủ công."
                    ),
                )
        return

    # 3. Check if already mirrored
    exists = frappe.db.exists("Folio Transaction", {
        "parent": master_folio,
        "reference_name": transaction_doc.name,
        "reference_doctype": "Folio Transaction"
    })
    
    if exists:
        return

    # 4. Create Mirror Transaction
    # Enhanced Description for clarity on Master Bill: "Original Desc [Res: ID (Guest Name)]"
    ref_info = ""
    if guest_folio.reservation:
        ref_info = f"Res: {guest_folio.reservation}"
        # Fetch guest name if not evident
        guest_name = frappe.db.get_value("Hotel Reservation", guest_folio.reservation, "guest")
        if guest_name:
            guest_full_name = frappe.db.get_value("Guest", guest_name, "full_name")
            ref_info += f" ({guest_full_name})"
    else:
        ref_info = f"Room: {guest_folio.room}"
    
    new_txn = frappe.get_doc({
        "doctype": "Folio Transaction",
        "parent": master_folio,
        "parenttype": "Guest Folio",
        "parentfield": "transactions",
        "posting_date": transaction_doc.posting_date,
        "item": transaction_doc.item,
        "description": f"{transaction_doc.description} [{ref_info}]",
        "qty": transaction_doc.qty,
        "amount": transaction_doc.amount,
        "bill_to": "Company",
        "reference_doctype": "Folio Transaction",
        "reference_name": transaction_doc.name,
        "mirror_source": transaction_doc.name,
        "pricing_details": transaction_doc.get('pricing_details'),
        "pricing_reservation": transaction_doc.get('pricing_reservation'),
        "pricing_origin": transaction_doc.get('pricing_origin'),
        "is_void": 0
    })
    new_txn.flags.from_folio_mirror = True
    new_txn.insert(ignore_permissions=True)
    
    # Sync Company Folio Balance
    sync_folio_balance(frappe.get_doc("Guest Folio", master_folio))

def mirror_to_group_folio(transaction_doc):
    """
    If a transaction is Bill To Group, we post a copy to the Group's Master Folio.
    """
    # 1. Identify the Group
    guest_folio = frappe.get_doc("Guest Folio", transaction_doc.parent)
    reservation = guest_folio.reservation
    
    if not reservation:
        return

    group_booking = frappe.db.get_value("Hotel Reservation", reservation, "group_booking")
    if not group_booking:
        return

    # 2. Find Master Folio for Group
    master_folio = frappe.db.get_value("Hotel Group Booking", group_booking, "master_folio")

    # If no master exists, we skip.
    if not master_folio or master_folio == guest_folio.name:
        return

    # 3. Check if already mirrored
    exists = frappe.db.exists("Folio Transaction", {
        "parent": master_folio,
        "reference_name": transaction_doc.name,
        "reference_doctype": "Folio Transaction"
    })
    
    if exists:
        return

    # 4. Create Mirror Transaction
    guest_name = frappe.db.get_value("Hotel Reservation", reservation, "guest")
    guest_full_name = frappe.db.get_value("Guest", guest_name, "full_name") if guest_name else "Unknown"
    
    ref_info = f"Res: {reservation} ({guest_full_name}) | Room: {guest_folio.room}"
    
    new_txn = frappe.get_doc({
        "doctype": "Folio Transaction",
        "parent": master_folio,
        "parenttype": "Guest Folio",
        "parentfield": "transactions",
        "posting_date": transaction_doc.posting_date,
        "item": transaction_doc.item,
        "description": f"{transaction_doc.description} [{ref_info}]",
        "qty": transaction_doc.qty,
        "amount": transaction_doc.amount,
        "bill_to": "Group",
        "reference_doctype": "Folio Transaction",
        "reference_name": transaction_doc.name,
        "mirror_source": transaction_doc.name,
        "pricing_details": transaction_doc.get('pricing_details'),
        "pricing_reservation": transaction_doc.get('pricing_reservation'),
        "pricing_origin": transaction_doc.get('pricing_origin'),
        "is_void": 0
    })
    new_txn.flags.from_folio_mirror = True
    new_txn.insert(ignore_permissions=True)
    
    # Sync Group Folio Balance
    sync_folio_balance(frappe.get_doc("Guest Folio", master_folio))

@frappe.whitelist()
def move_transactions(transaction_names, target_folio):
    """
    Moves selected transactions from Source Folio to Target Folio.
    """
    # Deferred import to avoid a circular import (folio_operations.py imports from
    # this module); reuse the same role list its callers (merge_folios,
    # execute_split_tour_folio) are already gated by.
    from hospitality_core.hospitality_core.api.folio_operations import _check_supervisor
    _check_supervisor()

    if isinstance(transaction_names, str):
        import json
        transaction_names = json.loads(transaction_names)

    if not transaction_names:
        frappe.throw(_("No transactions selected"))

    # Chặn di chuyển MỘT PHẦN của 1 "nhóm" giao dịch do engine tính giá phòng
    # quản lý — charge ROOM-RENT gốc và các dòng giảm giá/điều chỉnh LOS con
    # của nó (liên kết qua pricing_origin) PHẢI ở CÙNG 1 folio; nếu lễ tân
    # dùng dialog "Move Transactions" (chọn TỪNG giao dịch riêng lẻ) chỉ chọn
    # 1 trong 2, sau khi di chuyển 2 dòng sẽ nằm ở 2 folio KHÁC NHAU dù cùng
    # thuộc 1 khoản charge — folio nguồn còn dòng giảm giá không có charge
    # gốc để trừ vào, folio đích có charge gốc nhưng thiếu giảm giá tương ứng,
    # cả 2 số dư đều sai. merge_folios()/execute_split_tour_folio() luôn chọn
    # TOÀN BỘ giao dịch của 1 folio nên không bao giờ vi phạm điều kiện này.
    selected = set(transaction_names)
    txn_rows = frappe.get_all("Folio Transaction",
        filters={"name": ["in", list(selected)]},
        fields=["name", "parent", "pricing_origin"])
    for row in txn_rows:
        family = set()
        if row.pricing_origin and frappe.db.exists("Folio Transaction",
                {"name": row.pricing_origin, "parent": row.parent, "is_void": 0}):
            family.add(row.pricing_origin)
        family.update(frappe.get_all("Folio Transaction", filters={
            "pricing_origin": row.name, "parent": row.parent, "is_void": 0
        }, pluck="name"))
        missing = family - selected
        if missing:
            frappe.throw(_(
                "Giao dịch {0} có liên kết với (các) giao dịch {1} trên cùng folio (charge tiền phòng gốc/dòng "
                "giảm giá-điều chỉnh cùng nhóm) — vui lòng chọn đầy đủ cả nhóm cùng lúc để tránh lệch số dư."
            ).format(row.name, ", ".join(missing)))

    target_doc = frappe.get_doc("Guest Folio", target_folio)
    if target_doc.status != "Open":
        frappe.throw(_("Target Folio must be Open"))

    # TRƯỚC ĐÂY: biến source_folio_name bị GHI ĐÈ mỗi vòng lặp, nên nếu các
    # giao dịch được chọn đến từ NHIỀU folio nguồn khác nhau, chỉ folio nguồn
    # CUỐI CÙNG được đồng bộ lại số dư ở cuối hàm — các folio nguồn khác vẫn
    # còn giữ outstanding_balance CŨ (thiếu mất các giao dịch vừa bị chuyển
    # đi) cho đến khi có sự kiện nào khác vô tình trigger đồng bộ lại. Dùng
    # một set để theo dõi TẤT CẢ folio nguồn duy nhất, rồi đồng bộ lại toàn bộ.
    source_folio_names = set()

    for txn_name in transaction_names:
        txn = frappe.get_doc("Folio Transaction", txn_name)

        if txn.is_invoiced:
            frappe.throw(_("Cannot move invoiced transaction: {0}").format(txn.description))

        source_folio_names.add(txn.parent)

        # Log the move before updating parent
        log = frappe.get_doc({
            "doctype": "Folio Transaction Move Log",
            "transaction_name": txn.name,
            "source_folio": txn.parent,
            "target_folio": target_folio,
            "item": txn.item,
            "amount": txn.amount,
            "user": frappe.session.user,
            "move_datetime": frappe.utils.now_datetime()
        })
        log.insert(ignore_permissions=True)

        # Move: Update Parent
        frappe.db.set_value("Folio Transaction", txn.name, "parent", target_folio)

        # Audit Trail
        txn.add_comment("Info", _("Moved from Folio {0} to {1}").format(txn.parent, target_folio))

    # Sync Balances for every folio touched (mọi folio nguồn + folio đích) —
    # LUÔN đồng bộ Master Folio (nếu có trong tập cần đồng bộ) TRƯỚC, folio
    # thường sau, khớp đúng thứ tự khóa mà mirror_to_company_folio()/
    # mirror_to_group_folio() ở trên (cùng file) đã dùng (khóa Master Folio
    # TRƯỚC rồi mới khóa lại folio gốc khi mirror một charge). Nếu một
    # supervisor dùng "Move Transactions" chuyển giao dịch TỪ folio khách SANG
    # chính Master Folio của công ty/đoàn đó, đúng lúc một charge khác đang
    # được mirror vào CÙNG folio khách đó, mà 2 nơi dùng 2 thứ tự khóa khác
    # nhau (VD một bên "nguồn trước đích sau", một bên luôn "Master trước") —
    # đó là kinh điển deadlock AB-BA. Ép cùng một quy tắc "Master trước" ở cả
    # 2 nơi loại bỏ khả năng này; nếu không bên nào là Master thì thứ tự không
    # quan trọng vì không đụng luồng mirror.
    folios_to_sync = source_folio_names | {target_folio}
    master_folios, regular_folios = [], []
    for folio_name in folios_to_sync:
        is_master = (
            frappe.db.get_value("Guest Folio", folio_name, "is_company_master")
            or frappe.db.exists("Hotel Group Booking", {"master_folio": folio_name})
        )
        (master_folios if is_master else regular_folios).append(folio_name)

    for folio_name in master_folios + regular_folios:
        sync_folio_balance(frappe.get_doc("Guest Folio", folio_name))
    
    return True
@frappe.whitelist()
def debug_folio_totals(folio_name):
    """
    Diagnostic tool to see raw SQL vs field values.
    """
    # TRƯỚC ĐÂY: hàm whitelisted này KHÔNG hề kiểm tra quyền — bất kỳ user đã
    # đăng nhập nào (kể cả vai trò thấp nhất) cũng có thể xem toàn bộ chi tiết
    # tài chính (số dư, từng giao dịch, bill_to) của BẤT KỲ Guest Folio nào
    # chỉ cần biết/đoán được tên folio — lộ thông tin tài chính của khách
    # khác. Bản `api/folio_debug.py`'s debug_folio_totals() (tạo sau) đã có
    # đúng check này, nhưng bản ở đây bị bỏ sót không đồng bộ theo.
    if not frappe.has_permission("Guest Folio", "read", doc=folio_name):
        frappe.throw(_("Not permitted to view Folio {0}.").format(folio_name), frappe.PermissionError)

    totals = frappe.db.sql("""
        SELECT 
            SUM(CASE WHEN amount > 0 AND item NOT IN ('DISCOUNT', 'COMPLIMENTARY') THEN amount ELSE 0 END) as charges,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as payments
        FROM `tabFolio Transaction`
        WHERE parent = %s AND is_void = 0
    """, (folio_name,), as_dict=True)[0]
    
    doc = frappe.get_doc("Guest Folio", folio_name)
    
    txns = frappe.db.get_all("Folio Transaction", 
        filters={"parent": folio_name, "is_void": 0},
        fields=["name", "item", "description", "amount"]
    )
    
    return {
        "sql_totals": totals,
        "doc_fields": {
            "total_charges": doc.total_charges,
            "total_payments": doc.total_payments,
            "total_discounts": doc.total_discounts,
            "outstanding_balance": doc.outstanding_balance
        },
        "transactions": txns
    }

def record_guest_balance(folio_doc):
    """
    If a folio is closed with a credit balance (outstanding_balance < 0),
    record it in the Guest Balance Ledger.
    """
    if flt(folio_doc.outstanding_balance) < -0.01:
        credit_amount = abs(flt(folio_doc.outstanding_balance))
        
        # Check if already recorded to avoid duplicates
        if not frappe.db.exists("Guest Balance Ledger", {"folio": folio_doc.name}):
            ledger_entry = frappe.new_doc("Guest Balance Ledger")
            ledger_entry.guest = folio_doc.guest
            ledger_entry.folio = folio_doc.name
            ledger_entry.amount = credit_amount
            ledger_entry.status = "Available"
            for field in ('property', 'operating_company', 'currency'):
                if folio_doc.get(field):
                    ledger_entry.set(field, folio_doc.get(field))
            ledger_entry.insert(ignore_permissions=True)
            
            frappe.msgprint(_("Recorded credit balance of {0} for Guest {1} in Balance Ledger.").format(
                frappe.format(credit_amount, "Currency"), folio_doc.guest
            ))

def transfer_existing_balances(folio_doc):
    """
    Checks for available credit balances for the guest and transfers them to the new folio.
    """
    if not folio_doc.guest:
        return

    balance_filters = {"guest": folio_doc.guest, "status": "Available"}
    if folio_doc.get('property'):
        balance_filters.update(operating_company=folio_doc.operating_company, currency=folio_doc.currency,
                               property=folio_doc.property)
    available_balances = frappe.get_all("Guest Balance Ledger", 
        filters=balance_filters,
        fields=["name", "amount", "folio"]
    )

    if not available_balances:
        return

    total_transferred = 0.0
    for balance in available_balances:
        # Create a payment transaction in the new folio
        txn = frappe.get_doc({
            "doctype": "Folio Transaction",
            "parent": folio_doc.name,
            "parenttype": "Guest Folio",
            "parentfield": "transactions",
            "posting_date": frappe.utils.nowdate(),
            "item": "BALANCE-TRANSFER",
            "description": f"Balance Transfer from Folio {balance.folio}",
            "qty": 1,
            "amount": -1 * flt(balance.amount), # Payment (Credit)
            "is_void": 0
        })
        
        # Ensure BALANCE-TRANSFER item exists with proper UOM
        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
        ensure_item_exists("BALANCE-TRANSFER", "Guest Balance Transfer")

        # Xem chú thích tại payment_bridge.py's process_payment_entry() —
        # thiếu flags.hospitality_service sẽ chặn đứng việc tự động chuyển
        # số dư tín dụng cũ của khách sang folio mới ngay khi property
        # cutover Property v2.
        txn.flags.hospitality_service = True
        txn.insert(ignore_permissions=True)
        
        # Update Ledger Status
        frappe.db.set_value("Guest Balance Ledger", balance.name, {
            "status": "Transferred",
            "transferred_to_folio": folio_doc.name
        })
        
        total_transferred += flt(balance.amount)

    if total_transferred > 0:
        sync_folio_balance(folio_doc)
        frappe.msgprint(_("Transferred {0} from previous credit balances to this folio.").format(
            frappe.format(total_transferred, "Currency")
        ))

def process_ledger_adjustment(doc, method=None):
    """
    Hook: Folio Ledger Adjustment (on_submit)
    """
    folio = frappe.get_doc("Guest Folio", doc.folio)
    
    amount = flt(doc.amount)
    if doc.adjustment_type == "Clear Debt":
        amount = -1 * abs(amount) # Credit
    else:
        amount = abs(amount) # Debit
        
    txn = frappe.get_doc({
        "doctype": "Folio Transaction",
        "parent": folio.name,
        "parenttype": "Guest Folio",
        "parentfield": "transactions",
        "posting_date": frappe.utils.nowdate(),
        "item": "MANUAL_ADJUSTMENT",
        "description": doc.description,
        "qty": 1,
        "amount": amount,
        "bill_to": "Company" if folio.is_company_master else "Guest",
        "reference_doctype": "Folio Ledger Adjustment",
        "reference_name": doc.name,
        "is_void": 0
    })

    # Xem chú thích tại payment_bridge.py's process_payment_entry() — thiếu
    # flags.hospitality_service sẽ chặn đứng việc điều chỉnh sổ cái thủ công
    # ngay khi property cutover Property v2.
    txn.flags.hospitality_service = True
    txn.insert(ignore_permissions=True)
    
def cancel_ledger_adjustment(doc, method=None):
    """
    Hook: Folio Ledger Adjustment (on_cancel)
    """
    txns = frappe.get_all("Folio Transaction", filters={
        "reference_doctype": "Folio Ledger Adjustment",
        "reference_name": doc.name
    })
    
    for txn in txns:
        frappe.delete_doc("Folio Transaction", txn.name, ignore_permissions=True)
