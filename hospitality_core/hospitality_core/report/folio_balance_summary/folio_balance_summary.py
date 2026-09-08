import frappe
from frappe import _
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    columns = [
        {"label": _("Ledger Type"), "fieldname": "ledger_type", "fieldtype": "Data", "width": 180},
        {"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 250},
        {"label": _("Count"), "fieldname": "count", "fieldtype": "Int", "width": 80},
        {"label": _("Total Receivable"), "fieldname": "balance", "fieldtype": "Currency", "width": 140},
        {"label": _("Total Liability (Credits)"), "fieldname": "liability", "fieldtype": "Currency", "width": 160}
    ]

    data = []

    # Lọc theo property được phép xem — xem report_scope.py để biết lý do.
    allowed_properties = allowed_properties_for_report()
    property_sql = ""
    property_sql_gf = ""
    property_params = ()
    if allowed_properties is not None:
        property_sql = "AND property IN %(_properties)s"
        property_sql_gf = "AND gf.property IN %(_properties)s"
        property_params = {"_properties": allowed_properties or [""]}

    # 1. Calculate Guest Ledger (In-House Private Guests)
    guest_stats = frappe.db.sql(f"""
        SELECT
            COUNT(name) as cnt,
            SUM(CASE WHEN outstanding_balance > 0 THEN outstanding_balance ELSE 0 END) as bal,
            SUM(excess_payment) as liability
        FROM `tabGuest Folio`
        WHERE status = 'Open'
        AND (company IS NULL OR company = '')
        {property_sql}
    """, property_params, as_dict=True)[0]

    data.append({
        "ledger_type": "Guest Ledger",
        "description": "Current In-House Guests (Private Pay)",
        "count": guest_stats.cnt or 0,
        "balance": guest_stats.bal or 0.0,
        "liability": guest_stats.liability or 0.0
    })

    # 2. Calculate City Ledger (Corporate/Direct Bill)
    # A company-billed charge lives on the guest's own folio AND, once mirrored,
    # also on that company's Master Folio (see api/folio.py mirror_to_company_folio).
    # To avoid double-counting the same charge twice, only count a non-master
    # folio when its company has no Master Folio to mirror into yet — matching
    # mirror_to_company_folio()'s own "if no master exists, skip mirroring" rule.
    city_stats = frappe.db.sql(f"""
        SELECT
            COUNT(gf.name) as cnt,
            SUM(CASE WHEN gf.outstanding_balance > 0 THEN gf.outstanding_balance ELSE 0 END) as bal,
            SUM(gf.excess_payment) as liability
        FROM `tabGuest Folio` gf
        WHERE gf.status = 'Open'
        AND gf.company IS NOT NULL
        AND gf.company != ''
        AND (
            gf.is_company_master = 1
            OR NOT EXISTS (
                SELECT 1 FROM `tabGuest Folio` m
                WHERE m.company = gf.company AND m.is_company_master = 1
                AND m.status = 'Open' AND m.name != gf.name
            )
        )
        {property_sql_gf}
    """, property_params, as_dict=True)[0]

    data.append({
        "ledger_type": "City Ledger",
        "description": "Corporate Accounts / Direct Bill Masters",
        "count": city_stats.cnt or 0,
        "balance": city_stats.bal or 0.0,
        "liability": city_stats.liability or 0.0
    })

    # 3. Total
    total_bal = (guest_stats.bal or 0) + (city_stats.bal or 0)
    total_lia = (guest_stats.liability or 0) + (city_stats.liability or 0)
    data.append({
        "ledger_type": "<b>TOTAL</b>",
        "description": "",
        "count": (guest_stats.cnt or 0) + (city_stats.cnt or 0),
        "balance": total_bal,
        "liability": total_lia
    })

    chart = {
        "data": {
            "labels": ["Guest Ledger (Rec)", "Guest Ledger (Lia)", "City Ledger (Rec)", "City Ledger (Lia)"],
            "datasets": [
                {
                    "name": "Balance", 
                    "values": [
                        guest_stats.bal or 0, 
                        guest_stats.liability or 0, 
                        city_stats.bal or 0, 
                        city_stats.liability or 0
                    ]
                }
            ]
        },
        "type": "donut",
        "colors": ["#28a745", "#ffc107", "#007bff", "#dc3545"]
    }

    return columns, data, None, chart