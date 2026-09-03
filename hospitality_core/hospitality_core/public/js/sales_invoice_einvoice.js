// Adds the "Phát hành Hóa đơn Điện tử" (Issue E-Invoice) button to submitted
// Sales Invoices raised from a Guest Folio. See hospitality_core.api.einvoice
// for the provider adapter (Mock by default until VNPT/Viettel/MISA
// credentials are configured in Hospitality Accounting Settings).
frappe.ui.form.on('Sales Invoice', {
    refresh: function (frm) {
        if (frm.doc.docstatus !== 1) return;

        if (frm.doc.einvoice_status === 'Issued') {
            frm.dashboard.add_indicator(
                __('E-Invoice: {0} ({1})', [frm.doc.einvoice_number, frm.doc.einvoice_provider]),
                'green'
            );
            return;
        }

        frm.add_custom_button(__('Phát hành Hóa đơn Điện tử'), function () {
            frappe.confirm(
                __('Issue an electronic invoice (TT78/NĐ123) for this Sales Invoice via {0}?', [frm.doc.einvoice_provider || 'the configured provider']),
                function () {
                    frappe.call({
                        method: 'hospitality_core.hospitality_core.api.einvoice.issue_einvoice',
                        args: { sales_invoice: frm.doc.name },
                        freeze: true,
                        callback: function (r) {
                            if (!r.exc && r.message) {
                                frappe.msgprint({
                                    title: __('E-Invoice Issued'),
                                    message: __('Invoice No. {0}<br>Lookup Code: {1}', [r.message.einvoice_number, r.message.einvoice_lookup_code]),
                                    indicator: 'green'
                                });
                                frm.reload_doc();
                            }
                        }
                    });
                }
            );
        }, __('Actions'));
    }
});
