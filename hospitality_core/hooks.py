app_name = "hospitality_core"
app_title = "Hospitality Core"
app_publisher = "Gift Braimah"
app_description = "Hotel Management Module"
app_email = "braimahgifted@gmail.com"
app_license = "gpl-2.0"

app_include_js = [
    "/assets/hospitality_core/js/hospitality_analytics_final.js",
    "/assets/hospitality_core/js/pos_room_selection.js",
    "/assets/hospitality_core/js/pos_invoice_auto_print.js",
    "/assets/hospitality_core/js/payment_entry_auto_print.js",
    "/assets/hospitality_core/js/pos_payment_control.js",
    "/assets/hospitality_core/js/keycard_encoder_bridge.js"
]

app_include_css = [
    "/assets/hospitality_core/css/print_format.css"
]

# `sales_invoice_einvoice.js` lives at
# hospitality_core/hospitality_core/public/js/sales_invoice_einvoice.js (the
# module-inner public/ folder), NOT hospitality_core/public/js/ (the app-level
# folder that `bench build` bundles into /assets/hospitality_core/js/). Listing
# it in app_include_js above referenced a file bench build could never find,
# so this legacy fallback button/indicator never actually loaded on any page.
# doctype_js resolves its path relative to frappe.get_app_path() (the
# module-inner folder), which matches where the file already sits — fixing
# the reference instead of moving the file, and loading it only on the Sales
# Invoice form instead of globally on every desk page.
doctype_js = {
    "Sales Invoice": "public/js/sales_invoice_einvoice.js"
}


# Document Events
doc_events = {
    "Guest Folio": {
        "on_update": "hospitality_core.hospitality_core.api.folio.sync_folio_balance"
    },
    "Folio Transaction": {
        "on_update": [
            "hospitality_core.hospitality_core.api.folio.sync_folio_balance",
            "hospitality_core.hospitality_core.api.accounting.make_gl_entries_for_folio_transaction"
        ],
        "on_trash": "hospitality_core.hospitality_core.api.folio.sync_folio_balance"
    },
    "POS Invoice": {
        "before_validate": [
            "hospitality_core.hospitality_core.api.stock.enable_stock_update_for_pos_invoice"
        ],
        "validate": [
            "hospitality_core.hospitality_core.api.pos_bridge.assign_hospitality_property",
            "hospitality_core.hospitality_core.api.pos_bridge.enforce_payment_mode_rules"
        ],
        "on_submit": [
            "hospitality_core.hospitality_core.api.pos_bridge.process_room_charge",
            "hospitality_core.hospitality_core.api.accounting.redirect_pos_income_to_suspense",
            "hospitality_core.hospitality_core.api.accounting.reclassify_pos_taxes",
            "hospitality_core.api.composite_item_utils.process_composite_items_in_invoice"
        ],
        "on_cancel": [
            "hospitality_core.hospitality_core.api.pos_bridge.void_room_charge",
            "hospitality_core.hospitality_core.api.accounting.redirect_pos_income_to_suspense",
            "hospitality_core.hospitality_core.api.accounting.reclassify_pos_taxes",
            "hospitality_core.api.composite_item_utils.process_composite_items_in_invoice"
        ]
    },
    "Payment Entry": {
        "before_insert": "hospitality_core.hospitality_core.api.payment_bridge.adjust_payment_date",
        "on_submit": "hospitality_core.hospitality_core.api.payment_bridge.process_payment_entry",
        "on_cancel": "hospitality_core.hospitality_core.api.payment_bridge.process_payment_entry"
    },
    "Sales Invoice": {
        "before_submit": "hospitality_core.hospitality_core.api.stock.disable_stock_for_consolidated_pos_sales_invoice",
        "on_submit": "hospitality_core.api.composite_item_utils.process_composite_items_in_invoice",
        "on_cancel": "hospitality_core.api.composite_item_utils.process_composite_items_in_invoice"
    },
    "Folio Ledger Adjustment": {
        "on_submit": "hospitality_core.hospitality_core.api.folio.process_ledger_adjustment",
        "on_cancel": "hospitality_core.hospitality_core.api.folio.cancel_ledger_adjustment"
    }
}

after_install = "hospitality_core.setup.after_install"

# Scheduled Tasks
# changed daily audit to run at 2 PM (14:00) per requirements
scheduler_events = {
    "cron": {
        "0 14 * * *": [
            "hospitality_core.hospitality_core.api.night_audit.run_daily_audit"
        ],
        "0 8 * * *": [
            "hospitality_core.hospitality_core.api.pos_bridge.close_all_open_pos_sessions"
        ]
    }
}

# Fixtures
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "Hospitality Core"]]},
    {"dt": "Property Setter", "filters": [["module", "=", "Hospitality Core"]]}
]

# Phạm vi v2 được kiểm tra trước controller và áp dụng cho cả REST lẫn Desk.
from hospitality_core.hospitality_core.api.property_scope import SCOPED, COMPANY_SCOPED, CORE_SCOPED

permission_query_conditions = {"*": "hospitality_core.hospitality_core.api.property_scope.conditions"}
has_permission = {dt: "hospitality_core.hospitality_core.api.property_scope.has_permission"
    for dt in SCOPED | COMPANY_SCOPED | CORE_SCOPED | {"Hospitality Property", "Guest Preference", "File"}}
doc_events["*"] = {
    "before_validate": "hospitality_core.hospitality_core.api.property_scope.validate_document",
    "on_trash": "hospitality_core.hospitality_core.api.property_scope.prevent_trash",
}

def _add_event(doctype, event, handler):
    old = doc_events.setdefault(doctype, {}).get(event, [])
    doc_events[doctype][event] = ([old] if isinstance(old, str) else old) + [handler]

_add_event("Sales Invoice", "validate", "hospitality_core.hospitality_core.api.property_accounting.validate_invoice")
_add_event("Sales Invoice", "on_submit", "hospitality_core.hospitality_core.api.property_accounting.invoice_submitted")
_add_event("Sales Invoice", "on_cancel", "hospitality_core.hospitality_core.api.property_accounting.invoice_cancelled")
_add_event("Sales Invoice", "on_trash", "hospitality_core.hospitality_core.api.property_accounting.invoice_cancelled")
# Đảo bút toán GL đã ghi lúc phát sinh charge (accounting.py) khi hóa đơn
# Legacy (invoicing.py's create_invoice_from_folio()) được submit chính
# thức — chặn double-post doanh thu khi phát hành hóa đơn điện tử qua
# einvoice.py's issue_einvoice_from_folio() (tự động submit hóa đơn này).
_add_event("Sales Invoice", "on_submit", "hospitality_core.hospitality_core.api.accounting.reverse_charge_time_gl_on_invoice_submit")
_add_event("Sales Invoice", "on_cancel", "hospitality_core.hospitality_core.api.accounting.reverse_charge_time_gl_on_invoice_submit")
_add_event("Payment Entry", "on_submit", "hospitality_core.hospitality_core.api.property_accounting.payment_updated")
_add_event("Payment Entry", "on_cancel", "hospitality_core.hospitality_core.api.property_accounting.payment_updated")

after_migrate = ["hospitality_core.migrations.property_v2.execute"]
scheduler_events.setdefault("hourly", []).append("hospitality_core.hospitality_core.api.guest_loyalty.scheduled")
