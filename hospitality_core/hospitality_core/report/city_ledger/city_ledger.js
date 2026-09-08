frappe.query_reports["City Ledger"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": __("Customer (Company)"),
            "fieldtype": "Link",
            "options": "Customer",
            "reqd": 0
        }
    ],
    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        // Highlight old debts (> 30 days)
        if (column.fieldname === "age" && data && data.age > 30) {
            value = `<span style="color:red; font-weight:bold;">${value}</span>`;
        }
        
        // Highlight credit balances in green — report's actual column for
        // this is "excess_payment" (Credit Balance), a non-negative amount;
        // "outstanding_balance" isn't a column this report returns at all.
        if (column.fieldname === "excess_payment" && data && data.excess_payment > 0) {
            value = `<span style="color:green;">${value}</span>`;
        }

        return value;
    }
};