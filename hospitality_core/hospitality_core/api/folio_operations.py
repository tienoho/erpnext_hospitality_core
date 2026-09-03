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
