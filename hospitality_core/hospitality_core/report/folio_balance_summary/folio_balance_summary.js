frappe.query_reports["Folio Balance Summary"] = {
    // No filters: folio_balance_summary.py's execute() ignores `filters`
    // entirely and always aggregates globally, so a "Company" (hotel
    // property) filter here would be pure UI decoration with zero effect —
    // worse, Guest Folio's own "company" field is actually a Link to
    // Customer (used for corporate/city-ledger billing accounts), not to
    // the ERPNext Company doctype, so wiring this filter straight through
    // would silently return empty results for every selection instead of
    // narrowing by hotel property. Add a real per-property scoping field to
    // Guest Folio first if multi-property deployments need this.
    "filters": [],
    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        if (column.fieldname === "balance" && data && data.balance > 0) {
            value = `<span style="color:red; font-weight:bold;">${value}</span>`;
        }
        return value;
    },
    "onload": function(report) {
        // Add a button to jump to detailed ledgers
        report.page.add_inner_button(__("View Guest Ledger"), function() {
            frappe.set_route("query-report", "Guest Ledger");
        });
        report.page.add_inner_button(__("View City Ledger"), function() {
            frappe.set_route("query-report", "City Ledger");
        });
    }
};