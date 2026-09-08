// Copyright (c) 2026, Gift Braimah and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item Recipe', {
    refresh: function (frm) {
        // Add custom buttons
        if (!frm.is_new()) {
            frm.add_custom_button(__('View BOM'), function () {
                if (frm.doc.bom) {
                    frappe.set_route('Form', 'BOM', frm.doc.bom);
                } else {
                    frappe.msgprint(__('BOM not yet created'));
                }
            });

            frm.add_custom_button(__('Calculate Cost'), function () {
                calculate_total_cost(frm);
            });
        }
    },

    item: function (frm) {
        if (frm.doc.item) {
            // Fetch item details
            frappe.db.get_value('Item', frm.doc.item, ['item_name', 'stock_uom', 'is_composite_item'])
                .then(r => {
                    if (r.message) {
                        frm.set_value('item_name', r.message.item_name);
                        frm.set_value('uom', r.message.stock_uom);

                        if (!r.message.is_composite_item) {
                            frappe.msgprint({
                                title: __('Warning'),
                                indicator: 'orange',
                                message: __('Item {0} is not marked as a Composite Item. Please enable it in the Item master.', [frm.doc.item])
                            });
                        }
                    }
                });
        }
    }
});

frappe.ui.form.on('Recipe Ingredient', {
    ingredient_item: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.ingredient_item) {
            // Fetch stock UOM and set default UOM
            frappe.db.get_value('Item', row.ingredient_item, 'stock_uom')
                .then(r => {
                    if (r.message) {
                        frappe.model.set_value(cdt, cdn, 'stock_uom', r.message.stock_uom);
                        if (!row.uom) {
                            frappe.model.set_value(cdt, cdn, 'uom', r.message.stock_uom);
                        }
                    }
                });
        }
    },

    qty: function (frm, cdt, cdn) {
        calculate_stock_qty(frm, cdt, cdn);
    },

    uom: function (frm, cdt, cdn) {
        calculate_stock_qty(frm, cdt, cdn);
    }
});

function calculate_stock_qty(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (row.ingredient_item && row.qty && row.uom && row.stock_uom) {
        if (row.uom === row.stock_uom) {
            frappe.model.set_value(cdt, cdn, 'stock_qty', row.qty);
        } else {
            // Get conversion factor
            frappe.call({
                method: 'erpnext.stock.get_item_details.get_conversion_factor',
                args: {
                    item_code: row.ingredient_item,
                    uom: row.uom
                },
                callback: function (r) {
                    if (r.message) {
                        const stock_qty = flt(row.qty) * flt(r.message.conversion_factor);
                        frappe.model.set_value(cdt, cdn, 'stock_qty', stock_qty);
                    }
                }
            });
        }
    }
}

function calculate_total_cost(frm) {
    if (frm.is_dirty()) {
        frappe.msgprint(__('Vui lòng lưu công thức trước khi tính giá vốn.'));
        return;
    }
    const recipe = frm.doc.name;
    frappe.prompt([
        {fieldname: 'warehouse', label: __('Kho nguyên liệu'), fieldtype: 'Link', options: 'Warehouse', reqd: 1,
            get_query: () => ({filters: {is_group: 0, disabled: 0}})},
        {fieldname: 'at', label: __('Thời điểm định giá'), fieldtype: 'Datetime', reqd: 1,
            default: frappe.datetime.now_datetime()}
    ], (values) => {
        const request = frm._recipe_cost_request = (frm._recipe_cost_request || 0) + 1;
        frappe.call({
            method: 'hospitality_core.hospitality_core.doctype.item_recipe.item_recipe.estimate_recipe_cost',
            args: {recipe_name: recipe, ...values},
            callback: (r) => {
                if (request !== frm._recipe_cost_request || frm.doc.name !== recipe || frm.is_dirty() || !r.message) return;
                const cost = r.message;
                const escape = frappe.utils.escape_html;
                frappe.msgprint({title: __('Ước tính giá vốn'), message:
                    `${__('Chi phí cả mẻ')}: ${format_currency(cost.batch_cost, cost.currency)}<br>` +
                    `${__('Chi phí mỗi đơn vị')}: ${format_currency(cost.unit_cost, cost.currency)}<br>` +
                    `${__('Sản lượng')}: ${escape(String(cost.quantity))} ${escape(cost.uom)}<br>` +
                    `${__('Kho')}: ${escape(cost.warehouse)}<br>${__('Thời điểm')}: ${escape(cost.at)}`});
            }
        });
    }, __('Ước tính giá vốn'), __('Tính'));
}
