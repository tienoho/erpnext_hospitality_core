import frappe
from frappe import _
from frappe.utils import flt

from hospitality_core.hospitality_core.api.folio import sync_folio_balance


def _check_supervisor():
    allowed = ["Frontdesk Supervisor", "Hospitality Manager", "System Manager"]
    user_roles = frappe.get_roles() if hasattr(frappe, "get_roles") else []
    if not (any(r in user_roles for r in allowed) or frappe.session.user == "Administrator"):
        frappe.throw(_("Access Denied. Only Frontdesk Supervisors, Hospitality Managers, and Administrators can perform this action."))


@frappe.whitelist()
def split_transaction(transaction_name, splits):
    """
    Splits a single Folio Transaction (e.g. a shared group dinner bill) into
    several new transactions, optionally routed to different open folios.

    `splits` is a list of {"folio": <Guest Folio>, "amount": <portion>} and
    must sum to the original transaction's amount. The original transaction
    is voided (not deleted) so the audit trail stays intact.
    """
    _check_supervisor()

    if isinstance(splits, str):
        import json
        splits = json.loads(splits)

    if not splits or len(splits) < 2:
        frappe.throw(_("Provide at least two splits."))

    original = frappe.get_doc("Folio Transaction", transaction_name)
    if original.is_void:
        frappe.throw(_("Cannot split a voided transaction."))
    if original.is_invoiced:
        frappe.throw(_("Cannot split an already invoiced transaction."))

    total_split = sum(flt(s.get("amount")) for s in splits)
    if abs(total_split - flt(original.amount)) > 0.01:
        frappe.throw(_("Split amounts ({0}) must add up to the original amount ({1}).").format(
            frappe.format(total_split, "Currency"), frappe.format(original.amount, "Currency")
        ))

    affected_folios = {original.parent}
    new_transactions = []

    for split in splits:
        target_folio = split.get("folio") or original.parent
        target_doc = frappe.get_doc("Guest Folio", target_folio)
        if target_doc.status != "Open":
            frappe.throw(_("Target Folio {0} must be Open.").format(target_folio))

        new_txn = frappe.get_doc({
            "doctype": "Folio Transaction",
            "parent": target_folio,
            "parenttype": "Guest Folio",
            "parentfield": "transactions",
            "posting_date": original.posting_date,
            "item": original.item,
            "description": f"{original.description} [Split from {original.name}]",
            "qty": 1,
            "amount": flt(split.get("amount")),
            "bill_to": original.bill_to,
            "reference_doctype": "Folio Transaction",
            "reference_name": original.name,
            "is_void": 0,
        })
        new_txn.insert(ignore_permissions=True)
        new_transactions.append(new_txn.name)
        affected_folios.add(target_folio)

    # Void the original so totals aren't double-counted, but keep it for audit.
    frappe.db.set_value("Folio Transaction", original.name, {
        "is_void": 1,
        "void_reason": _("Split into {0}").format(", ".join(new_transactions)),
    })

    for folio_name in affected_folios:
        sync_folio_balance(frappe.get_doc("Guest Folio", folio_name))

    frappe.msgprint(_("Transaction split into {0} entries.").format(len(new_transactions)))
    return new_transactions


@frappe.whitelist()
def merge_folios(source_folio, target_folio):
    """
    Merges an open folio into another (e.g. combining two room folios for a
    couple checking out together). Moves every non-invoiced, non-void
    transaction across using the existing audited `move_transactions` path,
    then closes the source folio.
    """
    _check_supervisor()

    if source_folio == target_folio:
        frappe.throw(_("Source and target folio cannot be the same."))

    source_doc = frappe.get_doc("Guest Folio", source_folio)
    target_doc = frappe.get_doc("Guest Folio", target_folio)

    if source_doc.status != "Open":
        frappe.throw(_("Source Folio must be Open."))
    if target_doc.status != "Open":
        frappe.throw(_("Target Folio must be Open."))

    txn_names = frappe.get_all(
        "Folio Transaction",
        filters={"parent": source_folio, "is_void": 0, "is_invoiced": 0},
        pluck="name",
    )

    if txn_names:
        from hospitality_core.hospitality_core.api.folio import move_transactions
        move_transactions(txn_names, target_folio)

    frappe.db.set_value("Guest Folio", source_folio, "status", "Closed")
    source_doc.add_comment("Info", _("Folio merged into {0} by {1}.").format(target_folio, frappe.session.user))
    target_doc.add_comment("Info", _("Folio {0} merged into this folio.").format(source_folio))

    frappe.msgprint(_("Folio {0} merged into {1}.").format(source_folio, target_folio))
    return target_folio


@frappe.whitelist()
def omni_search(query):
    """
    Front Desk omni-search: looks up guests / reservations by name, phone,
    room number, ID number (CCCD/passport), or OTA booking reference.
    """
    query = (query or "").strip()
    if not query or len(query) < 2:
        return []

    like = f"%{query}%"
    results = frappe.db.sql(
        """
        SELECT
            res.name as reservation, res.status, res.room, res.arrival_date, res.departure_date,
            res.external_booking_id,
            g.full_name as guest_name, g.mobile_no, g.identification_no
        FROM `tabHotel Reservation` res
        LEFT JOIN `tabGuest` g ON res.guest = g.name
        WHERE res.status IN ('Reserved', 'Checked In')
        AND (
            g.full_name LIKE %(like)s OR
            g.mobile_no LIKE %(like)s OR
            g.identification_no LIKE %(like)s OR
            res.room LIKE %(like)s OR
            res.name LIKE %(like)s OR
            res.external_booking_id LIKE %(like)s
        )
        ORDER BY res.arrival_date DESC
        LIMIT 20
        """,
        {"like": like},
        as_dict=True,
    )
    return results


@frappe.whitelist()
def get_split_tour_preview(folio_name):
    """
    Phân tích tự động các giao dịch trên Folio thành 2 nhóm phục vụ Lễ tân đối soát:
    - Nhóm 1: Tiền phòng (Accommodation) -> Giữ lại Master Folio cho Đại lý/Công ty thanh toán.
    - Nhóm 2: Dịch vụ cá nhân (Minibar, Nhà hàng, Giặt là, Spa) -> Chuyển sang Sub-Folio cho Khách tự trả.
    """
    folio = frappe.get_doc("Guest Folio", folio_name)
    
    room_charges = []
    incidental_charges = []

    room_total = 0.0
    incidental_total = 0.0

    for t in folio.transactions:
        if t.is_void or t.is_invoiced:
            continue

        item_code = (t.item or "").upper()
        desc = (t.description or "").lower()
        amt = flt(t.amount)

        # Tiêu chí nhận diện tiền phòng
        is_room = (
            item_code in ("ROOM-RENT", "ROOM_CHARGE", "ACCOMMODATION") or
            "room rent" in desc or
            "tiền phòng" in desc or
            "phòng" in desc
        )

        row_data = {
            "name": t.name,
            "posting_date": str(t.posting_date),
            "item": t.item,
            "description": t.description,
            "amount": amt,
            "formatted_amount": frappe.format(amt, {"fieldtype": "Currency"}),
            "bill_to": t.bill_to
        }

        if is_room:
            room_charges.append(row_data)
            room_total += amt
        else:
            incidental_charges.append(row_data)
            incidental_total += amt

    return {
        "folio": folio_name,
        "guest": folio.guest,
        "room": folio.room,
        "company": folio.company,
        "room_charges": room_charges,
        "room_total": room_total,
        "formatted_room_total": frappe.format(room_total, {"fieldtype": "Currency"}),
        "incidental_charges": incidental_charges,
        "incidental_total": incidental_total,
        "formatted_incidental_total": frappe.format(incidental_total, {"fieldtype": "Currency"}),
        "grand_total": room_total + incidental_total,
        "formatted_grand_total": frappe.format(room_total + incidental_total, {"fieldtype": "Currency"})
    }


@frappe.whitelist()
def execute_split_tour_folio(source_folio, target_folio, move_txns):
    """
    Thi hành chuyển các giao dịch dịch vụ cá nhân đã chọn từ Master Folio sang Sub-Folio.
    Tái sử dụng hàm move_transactions() chuẩn có audit trail của hệ thống.
    """
    _check_supervisor()

    if isinstance(move_txns, str):
        import json
        move_txns = json.loads(move_txns)

    if not move_txns:
        frappe.throw(_("Vui lòng chọn ít nhất một giao dịch dịch vụ để chuyển."))

    if source_folio == target_folio:
        frappe.throw(_("Folio nguồn và Folio đích không được trùng nhau."))

    from hospitality_core.hospitality_core.api.folio import move_transactions
    move_transactions(move_txns, target_folio)

    return {
        "success": True,
        "moved_count": len(move_txns),
        "source_folio": source_folio,
        "target_folio": target_folio,
        "message": _("Đã tách thành công {0} giao dịch dịch vụ sang Folio {1}.").format(len(move_txns), target_folio)
    }

