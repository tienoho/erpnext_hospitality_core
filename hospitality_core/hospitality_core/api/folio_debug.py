import frappe
from frappe import _

@frappe.whitelist()
def debug_folio_totals(folio_name):
    """
    Diagnostic tool to see raw SQL vs field values.
    """
    if not frappe.has_permission("Guest Folio", "read", doc=folio_name):
        frappe.throw(_("Not permitted to view Folio {0}.").format(folio_name), frappe.PermissionError)

    # 1. Try to find the exact table name
    table_name = "tabFolio Transaction"
    
    totals = frappe.db.sql(f"""
        SELECT 
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as charges,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as payments
        FROM `{table_name}`
        WHERE parent = %s AND is_void = 0
    """, (folio_name,), as_dict=True)[0]
    
    doc = frappe.get_doc("Guest Folio", folio_name)
    
    # Get all transactions for comparison
    txns = frappe.db.get_all("Folio Transaction", 
        filters={"parent": folio_name, "is_void": 0},
        fields=["name", "item", "description", "amount", "bill_to"]
    )
    
    return {
        "folio_name": folio_name,
        "table_used": table_name,
        "sql_totals": totals,
        "doc_fields": {
            "total_charges": doc.total_charges,
            "total_payments": doc.total_payments,
            "outstanding_balance": doc.outstanding_balance,
            "status": doc.status
        },
        "transactions_count": len(txns),
        "transactions_detail": txns
    }
