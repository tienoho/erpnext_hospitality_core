// Copyright (c) 2026, Gift Braimah and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Report", {
	refresh(frm) {
        // Sales Report was formerly a Single doctype (one record for the whole
        // system); it's now a regular submittable doctype named per
        // company+date so each day's EOD report is kept as its own history
        // record instead of overwriting the previous one. "Generate Report" is
        // available on a brand-new (unsaved) doc too — generate_report()
        // calls self.save() internally, which inserts it — and stays
        // available while still a draft so it can be re-run to correct
        // itself; it's hidden once Submitted (matching generate_report()'s
        // own server-side guard) AND once Cancelled (docstatus 2) — Frappe
        // itself refuses any write to a cancelled document, so showing the
        // button there would just lead to a confusing error instead of a
        // clean Amend path.
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button("Generate Report", () => {
                if (!frm.doc.company || !frm.doc.from_date_time || !frm.doc.to_date_time) {
                    frappe.msgprint(__("Please set Company, From Date & Time and To Date & Time first."));
                    return;
                }
                frappe.call({
                    doc: frm.doc,
                    method: "generate_report",
                    freeze: true,
                    freeze_message: "Generating End of Day Sales Report...",
                    callback: function(r) {
                        // Khi không tìm thấy Closing Entry nào, generate_report()
                        // KHÔNG gọi self.save() — nếu đây là bản ghi mới chưa
                        // từng lưu, nó chưa hề tồn tại trên server, nên
                        // frm.reload_doc() sẽ báo lỗi "not found". Chỉ reload
                        // khi server xác nhận đã thực sự lưu (r.message.saved).
                        if (!r.exc && r.message && r.message.saved) {
                            frm.reload_doc();
                        }
                    }
                });
            }).addClass("btn-primary");
        }

        if (!frm.is_new()) {
            frm.add_custom_button("Print Report", () => {
                frm.print_doc();
            });
        }
	}
});
