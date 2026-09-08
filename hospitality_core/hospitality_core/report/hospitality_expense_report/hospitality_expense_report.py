# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{"label": _("Expense ID"), "fieldname": "name", "fieldtype": "Link", "options": "Hospitality Expense", "width": 140},
		{"label": _("Date"), "fieldname": "expense_date", "fieldtype": "Date", "width": 110},
		{"label": _("Category"), "fieldname": "expense_category", "fieldtype": "Link", "options": "Expense Category", "width": 150},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("Reception"), "fieldname": "hotel_reception", "fieldtype": "Link", "options": "Hotel Reception", "width": 140},
		{"label": _("Maintenance Request"), "fieldname": "maintenance_request", "fieldtype": "Link", "options": "Hotel Maintenance Request", "width": 160},
		{"label": _("Net Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Total Taxes"), "fieldname": "total_taxes", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Workflow State"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 130},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1}
	]

def get_data(filters):
	conditions = get_conditions(filters)
	filters['currency'] = frappe.get_cached_value('Company', filters.get("company"), 'default_currency')
	
	data = frappe.db.sql(f"""
		SELECT 
			name,
			expense_date,
			expense_category,
			supplier,
			hotel_reception,
			maintenance_request,
			amount,
			total_taxes,
			grand_total,
			workflow_state,
			%(currency)s as currency
		FROM `tabHospitality Expense`
		WHERE {conditions}
		ORDER BY expense_date DESC, name DESC
	""", filters, as_dict=1)
	
	return data

def get_conditions(filters):
	# Match frontdesk_end_of_day_report.py's expense query: only Submitted
	# expenses count toward totals — a Draft hasn't been approved yet and can
	# still be edited/deleted, so including it here disagrees with that report.
	conditions = ["docstatus = 1"]
	
	if filters.get("from_date"):
		conditions.append("expense_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("expense_date <= %(to_date)s")
	if filters.get("expense_category"):
		conditions.append("expense_category = %(expense_category)s")
	if filters.get("supplier"):
		conditions.append("supplier = %(supplier)s")
	if filters.get("hotel_reception"):
		conditions.append("hotel_reception = %(hotel_reception)s")
	if filters.get("workflow_state"):
		conditions.append("workflow_state = %(workflow_state)s")

	allowed_properties = allowed_properties_for_report()
	if allowed_properties is not None:
		conditions.append("property IN %(_properties)s")
		filters["_properties"] = allowed_properties or [""]

	return " AND ".join(conditions)
