import frappe
from frappe import _
from frappe.utils import flt
from hospitality_core.hospitality_core.api.folio import mirror_to_company_folio
from hospitality_core.hospitality_core.doctype.hotel_room.hotel_room import resolve_hotel_room, get_room_number

def assign_hospitality_property(doc, method=None):
    """
    Hook: POS Invoice (validate)
    TRƯỚC ĐÂY: POS Invoice nằm trong CORE_SCOPED (property_scope.py) nhưng
    KHÔNG CÓ BẤT KỲ nơi nào từng set field hospitality_property của nó —
    khiến toàn bộ bảo vệ phân quyền theo property cho POS Invoice là VÔ
    NGHĨA (mọi bản ghi mãi mãi NULL = "ngoài phạm vi", không bị lọc). Nay
    lấy từ field hospitality_property mới trên chính POS Profile của hóa
    đơn (1 property có thể có nhiều POS Profile/outlet — nhà hàng, bar,
    spa... — nên mapping đúng chiều là POS Profile -> Property, không phải
    ngược lại). Chạy ở validate() (không phải before_submit) để giá trị
    cũng đúng ngay từ bản nháp, và tự cập nhật nếu ai đổi pos_profile trước
    khi submit.
    """
    if not doc.get('pos_profile'):
        return
    property = frappe.db.get_value('POS Profile', doc.pos_profile, 'hospitality_property')
    if property:
        doc.hospitality_property = property


WALKIN_CUSTOMER = "Walk in Customer"
GUEST_ACCOUNT_MODE = "Guest Account"
COMPLIMENTARY_MODE = "Complimentary"


def enforce_payment_mode_rules(doc, method=None):
    """
    Hook: POS Invoice (validate)
    TRƯỚC ĐÂY: 4 quy tắc bắt buộc về payment mode (xem
    public/js/pos_payment_control.js's docstring) — (1) có Phòng -> CHỈ
    được "Guest Account"; (2) Customer không phải Walk-in VÀ không có
    Phòng -> CHỈ được "Complimentary"; (3) Walk-in Customer không có Phòng
    -> KHÔNG được "Guest Account"/"Complimentary" — chỉ được thực thi ở
    PHÍA CLIENT (chặn bằng CSS/DOM, chặn click). Server (process_room_charge()
    bên dưới) chỉ đọc "có bao nhiêu tiền gắn Guest Account" để ghi vào
    Folio, KHÔNG hề xác minh lại các quy tắc trên — bất kỳ ai bỏ qua JS
    (devtools, gọi thẳng API, sửa payload trước khi gửi) đều có thể tự do
    trộn payment mode: dùng "Complimentary" cho khách Walk-in không có căn
    cứ (miễn phí đồ ăn/thức uống mà không ai duyệt), hoặc chỉ gắn 1 phần
    nhỏ vào "Guest Account" còn lại thu tiền mặt/thẻ không qua sổ sách —
    thất thoát doanh thu thật, không có dấu vết. Xác minh lại CHÍNH XÁC 3
    quy tắc đó ở server trước khi cho lưu, không tin tưởng riêng phía JS.
    """
    if not doc.get('payments'):
        return

    room = doc.get('hotel_room')
    customer = doc.get('customer')

    if room:
        others = sum(flt(p.amount) for p in doc.payments if p.mode_of_payment != GUEST_ACCOUNT_MODE)
        if others > 0.01:
            frappe.throw(_(
                "Hóa đơn có gắn Phòng ({0}) chỉ được thanh toán qua phương thức 'Guest Account' (ghi vào Folio). "
                "Vui lòng bỏ trống Phòng nếu khách thanh toán bằng phương thức khác."
            ).format(room))
    elif customer and customer != WALKIN_CUSTOMER:
        others = sum(flt(p.amount) for p in doc.payments if p.mode_of_payment != COMPLIMENTARY_MODE)
        if others > 0.01:
            frappe.throw(_(
                "Khách hàng {0} (không gắn Phòng) chỉ được thanh toán qua phương thức 'Complimentary'. "
                "Vui lòng chọn Phòng nếu khách đang lưu trú thật, hoặc đổi Customer thành 'Walk in Customer' nếu "
                "thanh toán bằng tiền thật."
            ).format(customer))
    elif customer == WALKIN_CUSTOMER and not room:
        blocked = sum(flt(p.amount) for p in doc.payments
                       if p.mode_of_payment in (GUEST_ACCOUNT_MODE, COMPLIMENTARY_MODE))
        if blocked > 0.01:
            frappe.throw(_(
                "Khách 'Walk in Customer' không gắn Phòng không được thanh toán qua 'Guest Account' hoặc "
                "'Complimentary'."
            ))


def process_room_charge(doc, method=None):
    """
    Hook: POS Invoice (on_submit)
    Logic: Breaks down the POS Invoice and posts EACH item to the Guest Folio.
    """
    
    if doc.get('fnb_version') == 'FNB v1':
        from hospitality_core.hospitality_core.api.fnb.pos import post_room_charge
        return post_room_charge(doc)
    # 1. Calculate how much of this invoice is being charged to the room
    room_charge_payment = 0
    for pay in doc.payments:
        if pay.mode_of_payment == "Guest Account":
            room_charge_payment += flt(pay.amount)
            
    if room_charge_payment <= 0:
        return

    # 2. Get the Room and Active Folio
    if not doc.get("hotel_room"):
        # FALLBACK: Try to find an active folio for this customer
        customer = doc.get("customer")
        if customer:
            # 1. Try finding via direct company link on Folio
            folios = frappe.get_all("Guest Folio", filters={
                "status": "Open",
                "company": customer
            }, fields=["room", "name"])
            
            # 2. Try finding via Guest link if no direct company folio
            if not folios:
                guests = frappe.get_all("Guest", filters={"customer": customer}, fields=["name"])
                if guests:
                    folios = frappe.get_all("Guest Folio", filters={
                        "status": "Open",
                        "guest": ["in", [g.name for g in guests]]
                    }, fields=["room", "name"])
            
            if len(folios) == 1:
                doc.hotel_room = folios[0].room
                # Update the document to persist the room back to DB
                frappe.db.set_value(doc.doctype, doc.name, "hotel_room", doc.hotel_room)
                display_room = get_room_number(doc.hotel_room)
                frappe.msgprint(_("Auto-linked Room {0} from active Folio {1}").format(display_room, folios[0].name))
            elif len(folios) > 1:
                 frappe.throw(_("Multiple active folios found for this customer ({0}). Please select a Room Number manually.").format(customer))
                 
    if not doc.get("hotel_room"):
        frappe.throw(_("Please select a Hotel Room for the Room Charge."))

    resolved_room = resolve_hotel_room(doc.hotel_room)
    display_room = get_room_number(resolved_room) or doc.hotel_room
    folio_name = frappe.db.get_value("Guest Folio", 
        {"room": resolved_room, "status": "Open"}, "name"
    )
    
    if not folio_name:
        frappe.throw(_("No open Folio found for Room {0}.").format(display_room))

    # 3. Determine the ratio (in case of split payments like half cash / half room charge)
    # This ensures the sales price on the folio matches the portion charged to the room
    invoice_total = flt(doc.grand_total)
    ratio = room_charge_payment / invoice_total if invoice_total > 0 else 1

    # 4. Determine Bill To logic (Company vs Group vs Guest)
    bill_to = "Guest"
    res_name = frappe.db.get_value("Guest Folio", folio_name, "reservation")
    if res_name:
        # Check if POS Posting is allowed for this reservation
        res_details = frappe.db.get_value(
            "Hotel Reservation", res_name,
            ["is_company_guest", "is_group_guest", "allow_pos_posting"], as_dict=True
        )

        if not res_details:
            frappe.throw(_("Reservation {0} linked to Folio {1} could not be found.").format(res_name, folio_name))

        if not res_details.allow_pos_posting:
            frappe.throw(_("Room {0} is closed for POS Posting.").format(display_room))

        if res_details.is_company_guest:
            bill_to = "Company"
        elif res_details.is_group_guest:
            bill_to = "Group"

    # 5. POST TO FOLIO (Grouped or Individual)
    pos_profile = (doc.get("pos_profile") or "").strip().lower()

    # Check if we should group the transaction.
    # NOTE: no dedicated "outlet grouping" setting exists yet in Hospitality
    # Accounting Settings — matching is case/whitespace-insensitive so a minor
    # rename of one of these profiles doesn't silently break grouping.
    group_item = None
    group_desc = None

    if pos_profile in ["restaurant", "bush bar kitchen"]:
        group_item = "Food"
        group_desc = f"Food (POS: {doc.name})"
    elif pos_profile in ["fountain bar", "bush bar drinks"]:
        group_item = "Beverages"
        group_desc = f"Beverages (POS: {doc.name})"

    if group_item:
        # Group everything into one Folio Transaction
        total_posted_amount = 0
        for item in doc.items:
            total_posted_amount += flt(item.amount) * ratio
            
        txn = frappe.get_doc({
            "doctype": "Folio Transaction",
            "parent": folio_name,
            "parenttype": "Guest Folio",
            "parentfield": "transactions",
            "posting_date": doc.posting_date,
            "item": group_item,
            "description": group_desc,
            "qty": 1,
            "amount": total_posted_amount,
            "bill_to": bill_to,
            "reference_doctype": "POS Invoice",
            "reference_name": doc.name,
            "is_invoiced": 1
        })
        txn.insert(ignore_permissions=True)

        if bill_to == "Company":
            mirror_to_company_folio(txn)
    else:
        # POST EACH ITEM INDIVIDUALLY
        for item in doc.items:
            posted_amount = flt(item.amount) * ratio
            
            txn = frappe.get_doc({
                "doctype": "Folio Transaction",
                "parent": folio_name,
                "parenttype": "Guest Folio",
                "parentfield": "transactions",
                "posting_date": doc.posting_date,
                "item": item.item_code,
                "description": f"{item.item_name} (POS: {doc.name})",
                "qty": item.qty,
                "amount": posted_amount,
                "bill_to": bill_to,
                "reference_doctype": "POS Invoice",
                "reference_name": doc.name,
                "is_invoiced": 1
            })
            txn.insert(ignore_permissions=True)

            if bill_to == "Company":
                mirror_to_company_folio(txn)

    # 6. Refresh the Folio Balance
    from hospitality_core.hospitality_core.api.folio import sync_folio_balance
    sync_folio_balance(frappe.get_doc("Guest Folio", folio_name))

    frappe.msgprint(_("Posted {0} items from POS to Folio {1}").format(len(doc.items), folio_name))

def void_room_charge(doc, method=None):
    """
    Hook: POS Invoice (on_cancel)
    Logic: Deletes all folio transactions linked to this POS Invoice.
    Requirement: "the transaction should be located and the row deleted"
    """
    if doc.get('fnb_version') == 'FNB v1':
        from hospitality_core.hospitality_core.api.fnb.pos import void_room_charge as void_fnb_charge
        return void_fnb_charge(doc)
    # 1. Find all Folio Transactions linked to this POS Invoice
    transactions = frappe.get_all("Folio Transaction", 
        filters={"reference_doctype": "POS Invoice", "reference_name": doc.name},
        fields=["name", "parent"]
    )

    if not transactions:
        return

    affected_folios = set()
    for txn in transactions:
        affected_folios.add(txn.parent)
        
        # 2. Find mirror transactions
        mirror_txns = frappe.get_all("Folio Transaction",
            filters={"reference_doctype": "Folio Transaction", "reference_name": txn.name},
            fields=["name", "parent"]
        )
        for m_txn in mirror_txns:
            affected_folios.add(m_txn.parent)
            frappe.delete_doc("Folio Transaction", m_txn.name, ignore_permissions=True)

        # Delete the original transaction
        frappe.delete_doc("Folio Transaction", txn.name, ignore_permissions=True)

    # 3. Sync all affected folios
    from hospitality_core.hospitality_core.api.folio import sync_folio_balance
    for folio_name in affected_folios:
        if frappe.db.exists("Guest Folio", folio_name):
            sync_folio_balance(frappe.get_doc("Guest Folio", folio_name))

    frappe.msgprint(_("Removed {0} items from Folio(s) due to POS Invoice cancellation.").format(len(transactions)))

@frappe.whitelist()
def get_guest_details_from_room(room_number):
    """
    Fetches the Customer linked to the currently active (Open) Guest Folio for a given room.
    """
    if not frappe.has_permission("Guest Folio", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    if not room_number:
        return {}

    resolved_room = resolve_hotel_room(room_number)

    # Find the Open Folio for this room
    folio = frappe.db.get_value("Guest Folio", 
        {"room": resolved_room, "status": "Open"}, 
        ["name", "reservation"], 
        as_dict=True
    )

    if not folio:
        return {"error": _("No active check-in found for Room {0}").format(room_number)}

    # Get the Customer from the Reservation
    if not folio.reservation:
        return {"error": _("No reservation linked to the active folio.")}

    # Fetch Guest and Company details from Reservation
    res_details = frappe.db.get_value("Hotel Reservation", folio.reservation, 
        ["guest", "is_company_guest", "company"], as_dict=True)
    
    if not res_details:
        return {"error": _("Reservation not found.")}

    customer = None
    customer_name = ""

    if res_details.is_company_guest and res_details.company:
        customer = res_details.company
    elif res_details.guest:
        customer = frappe.db.get_value("Guest", res_details.guest, "customer")
    
    if not customer:
        return {"error": _("No ERPNext Customer linked to the Guest/Reservation.")}
        
    # Always prefer showing the actual guest name in POS UI
    if res_details.guest:
        guest_customer = frappe.db.get_value("Guest", res_details.guest, "customer")
        if guest_customer:
            customer = guest_customer
            
    customer_name = frappe.db.get_value("Customer", customer, "customer_name")

    return {
        "customer": customer,
        "customer_name": customer_name,
        "folio": folio.name
    }

@frappe.whitelist()
def close_all_open_pos_sessions():
    """
    Closes all open POS sessions by creating and submitting a POS Closing Entry for each.
    """
    from hospitality_core.hospitality_core.api.folio_operations import _check_supervisor
    _check_supervisor()

    open_entries = frappe.get_all("POS Opening Entry", filters={"status": "Open"})
    
    from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import make_closing_entry_from_opening
    
    count = 0
    for entry in open_entries:
        try:
            opening_doc = frappe.get_doc("POS Opening Entry", entry.name)
            closing_doc = make_closing_entry_from_opening(opening_doc)
            
            # For each payment reconciliation, set closing_amount = expected_amount to balance it
            for pay in closing_doc.payment_reconciliation:
                pay.closing_amount = pay.expected_amount
                
            closing_doc.insert(ignore_permissions=True)
            closing_doc.submit()
            count += 1
        except Exception as e:
            frappe.log_error(f"Failed to close POS Opening Entry {entry.name}: {str(e)}", "Auto Close POS Sessions")
            
    return count
