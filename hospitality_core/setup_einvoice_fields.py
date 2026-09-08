"""
One-off provisioning script for the E-Invoice (TT78/NĐ123) integration.
Run once via: bench --site <site> execute hospitality_core.setup_einvoice_fields.run

Adds tracking fields to Sales Invoice (the actual legal VAT invoice document)
so the electronic invoice lookup code / status can be recorded and displayed,
following the same ad-hoc Custom Field pattern already used elsewhere in this
app (see hospitality_core.setup.create_custom_fields for the POS Invoice
precedent).
"""
import frappe


FIELDS = [
    {
        "fieldname": "einvoice_section",
        "label": "Hóa Đơn Điện Tử (E-Invoice)",
        "fieldtype": "Section Break",
        "insert_after": "taxes_and_charges",
        "collapsible": 1,
    },
    {
        "fieldname": "einvoice_status",
        "label": "E-Invoice Status",
        "fieldtype": "Select",
        "options": "\nNot Issued\nIssued\nFailed\nCancelled",
        "default": "Not Issued",
        "insert_after": "einvoice_section",
        "read_only": 1,
        "in_list_view": 1,
        "in_standard_filter": 1,
    },
    {
        "fieldname": "einvoice_provider",
        "label": "Provider",
        "fieldtype": "Data",
        "insert_after": "einvoice_status",
        "read_only": 1,
    },
    {
        "fieldname": "einvoice_column_break",
        "fieldtype": "Column Break",
        "insert_after": "einvoice_provider",
    },
    {
        "fieldname": "einvoice_number",
        "label": "Invoice Number",
        "fieldtype": "Data",
        "insert_after": "einvoice_column_break",
        "read_only": 1,
    },
    {
        "fieldname": "einvoice_lookup_code",
        "label": "Lookup Code (Mã tra cứu)",
        "fieldtype": "Data",
        "insert_after": "einvoice_number",
        "read_only": 1,
    },
    {
        "fieldname": "einvoice_issued_on",
        "label": "Issued On",
        "fieldtype": "Datetime",
        "insert_after": "einvoice_lookup_code",
        "read_only": 1,
    },
]


def run():
    # TRƯỚC ĐÂY: hàm này luôn tự tạo/ghi đè field "einvoice_status" (Select,
    # options hẹp "Not Issued/Issued/Failed/Cancelled") trên Sales Invoice mỗi
    # lần bench migrate — nhưng app erpnext_vietnam_einvoice (khi đã cài) CŨNG
    # tự tạo đúng field CÙNG TÊN "einvoice_status" trên CÙNG doctype với bộ
    # options RỘNG HƠN VÀ KHÁC HẲN ("Draft/Queued/Issued/Cancelled/Adjusted/
    # Replaced" — các giá trị "Queued"/"Draft"/"Adjusted"/"Replaced" mà
    # vietnam_einvoice.einvoice_core thực sự ghi vào field này). Vì
    # create_custom_fields() ghi đè TOÀN BỘ definition (kể cả `options`) của 1
    # Custom Field đã tồn tại, ứng dụng nào chạy after_migrate SAU CÙNG sẽ âm
    # thầm đổi options của field dùng chung này — nếu hospitality_core thắng,
    # dropdown Desk sẽ không hiển thị đúng các trạng thái Queued/Adjusted/
    # Replaced mà vietnam_einvoice đang lưu thật trong DB. api/einvoice.py's
    # issue_einvoice() đã tự ủy quyền (delegate) toàn bộ logic phát hành sang
    # vietnam_einvoice khi app đó có mặt (và JS cũng tự ẩn nút của
    # hospitality_core theo đúng nguyên tắc này) — nên khi vietnam_einvoice đã
    # cài, bộ field/local Mock provider của CHÍNH module này không còn được
    # dùng tới nữa (dead code), và không nên tự tạo/ghi đè field cạnh tranh.
    try:
        import vietnam_einvoice  # noqa: F401
        print("vietnam_einvoice đã cài đặt — bỏ qua, dùng bộ field/logic HĐĐT của app đó.")
        return
    except ImportError:
        pass

    for field in FIELDS:
        if frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": field["fieldname"]}):
            continue
        doc = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Sales Invoice",
            "module": "Hospitality Core",
            **field,
        })
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print("E-Invoice custom fields provisioned on Sales Invoice.")
