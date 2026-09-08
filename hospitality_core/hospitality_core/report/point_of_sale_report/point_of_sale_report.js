frappe.query_reports["Point of Sale Report"] = {
	"filters": [
		{
			"fieldname": "pos_profile",
			"label": __("POS Profile"),
			"fieldtype": "Link",
			"options": "POS Profile",
			"reqd": 1
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		}
	],
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// Report has no "item_code" column at all (only item_name/qty_sold/
		// amount) and the total/section-header rows use translated text
		// ("<b>Total</b>", "<b>Collected by Payment Method</b>"), never the
		// literal string "<b>TOTALS</b>" — so this never matched. Detect any
		// such row generically instead of hardcoding one untranslated string.
		if (data && data.item_name && data.item_name.indexOf("<b>") === 0) {
			value = "<b>" + value + "</b>";
		}
		return value;
	}
};
