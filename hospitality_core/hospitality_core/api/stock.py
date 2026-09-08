import frappe
from frappe import _

def deduct_inventory(doc, method=None):
    """
    Hook: Guest Folio (on_update) or Folio Transaction (after_insert).
    Logic: If a new transaction is added for a Stock Item, create a Stock Entry (Material Issue).
    """
    
    if doc.doctype != "Folio Transaction":
        return

    if doc.is_void or doc.amount <= 0:
        return

    # 1. Check if Item is a Stock Item
    is_stock_item = frappe.db.get_value("Item", doc.item, "is_stock_item")
    if not is_stock_item:
        return

    # 2. Get Room Warehouse
    folio = frappe.get_doc("Guest Folio", doc.parent)
    room_warehouse = frappe.db.get_value("Hotel Room", folio.room, "warehouse")

    # Use Company from Folio if available, otherwise User Default
    # Note: Guest Folio doesn't strictly have a 'Company' field for the Hotel Entity,
    # it has 'company' linking to Customer.
    # We should rely on System Defaults or the User's Company for the Hotel's side.
    hotel_company = frappe.defaults.get_user_default("Company")

    if not room_warehouse:
        # TRƯỚC ĐÂY: đọc "default_warehouse" thẳng trên Item — field này
        # KHÔNG TỒN TẠI trên Item (đã xác minh trực tiếp mã nguồn ERPNext
        # thật: field này chỉ có trên bảng con "Item Default", theo từng
        # company) — sẽ ném lỗi DB "Unknown column" ngay khi tới nhánh này
        # (item stock thật mà phòng chưa gán warehouse riêng).
        item_default_warehouse = frappe.db.get_value("Item Default",
            {"parent": doc.item, "parenttype": "Item", "company": hotel_company}, "default_warehouse")
        room_warehouse = item_default_warehouse or frappe.db.get_value("Stock Settings", None, "default_warehouse")
        
    if not room_warehouse:
        frappe.log_error(f"Skipping Stock Deduction for {doc.item}. No Warehouse found for Room {folio.room}", "Hotel Stock Error")
        return
        
    # Validate Warehouse belongs to Company
    wh_company = frappe.db.get_value("Warehouse", room_warehouse, "company")
    if wh_company != hotel_company:
        frappe.log_error(f"Warehouse {room_warehouse} belongs to {wh_company}, expected {hotel_company}", "Hotel Stock Error")
        return

    # 3. Create Stock Entry (Material Issue)
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Issue"
    se.purpose = "Material Issue"
    se.posting_date = doc.posting_date
    se.company = hotel_company
    
    # Add Item
    se.append("items", {
        "item_code": doc.item,
        "qty": doc.qty,
        "uom": frappe.db.get_value("Item", doc.item, "stock_uom"),
        "s_warehouse": room_warehouse,
        "cost_center": frappe.get_cached_value('Company', se.company, 'cost_center')
    })
    
    try:
        se.insert(ignore_permissions=True)
        se.submit()
        frappe.msgprint(_("Consumed {0} from Warehouse {1}").format(doc.item, room_warehouse), alert=True)
        
        # Link Stock Entry to Transaction for reference
        frappe.db.set_value("Folio Transaction", doc.name, {
            "reference_doctype": "Stock Entry",
            "reference_name": se.name
        })
        
    except Exception as e:
        frappe.log_error(f"Failed to deduct stock for {doc.item}: {str(e)}", "Hotel Stock Error")

def enable_stock_update_for_pos_invoice(doc, method=None):
    """
    Hook: POS Invoice (before_validate)

    TRƯỚC ĐÂY: 2 hàm `post_pos_invoice_stock()`/`cancel_pos_invoice_stock()`
    (hook ở on_submit/on_cancel) tự set `doc.update_stock = 1` CHỈ TRONG BỘ
    NHỚ (không lưu xuống DB) rồi tự tay gọi `update_stock_ledger()` — nhưng
    KHÔNG BAO GIỜ trigger lại `make_gl_entries()` cho phần định giá tồn kho
    (Stock-in-Hand/COGS), vì controller GỐC của ERPNext (`SalesInvoice.on_submit()`,
    chạy TRƯỚC hook app-level cùng tên) đã tự gọi `make_gl_entries()` từ
    TRƯỚC ĐÓ, lúc `update_stock` vẫn = 0 (giá trị đã lưu DB) — `get_gl_entries()`
    của ERPNext chỉ thêm dòng GL định giá tồn kho khi `update_stock` = 1
    NGAY TẠI THỜI ĐIỂM ghi GL. Kết quả: Stock Ledger Entry được tạo (tồn
    kho thật đổi), nhưng sổ sách kế toán KHÔNG BAO GIỜ ghi nhận — lệch tồn
    kho vs sổ sách VĨNH VIỄN với công ty bật perpetual inventory.

    Đã xác minh trực tiếp mã nguồn ERPNext (`general_ledger.py`'s
    `make_entry()`) rằng gọi lại `make_gl_entries()` LẦN THỨ 2 để vá thêm
    sẽ KHÔNG an toàn — hàm này insert() vô điều kiện, không có cơ chế
    chống ghi trùng theo voucher, nên sẽ ghi TRÙNG cả Debtors/Income/Thuế
    (core đã ghi 1 lần rồi) — tệ hơn cả lỗi đang sửa.

    Sửa TẬN GỐC: set `update_stock=1` ở before_validate — TRƯỚC KHI
    validate()/on_submit() GỐC của ERPNext chạy — để chính core tự lo TOÀN
    BỘ (validate_warehouse()/update_current_stock() lúc validate(), rồi SLE
    + GL đúng 1 lượt lúc on_submit(), rồi tự đảo đúng cả 2 lúc on_cancel())
    qua đúng luồng nó đã thiết kế và tự kiểm thử — khớp CHÍNH XÁC idiom app
    này đã tự dùng cho Sales Invoice
    (`disable_stock_for_consolidated_pos_sales_invoice`, cũng set
    `update_stock` ở before_submit, TRƯỚC KHI submit chạy, không phải sau).
    Không còn cần 2 hàm post/cancel thủ công nữa — core tự làm đúng cả 2
    chiều một cách đối xứng.

    LƯU Ý VẬN HÀNH: `update_stock=1` khiến `validate_warehouse()` (chạy
    trong validate() gốc của ERPNext) bắt buộc MỌI dòng item của POS
    Invoice phải có warehouse — TRƯỚC ĐÂY luồng thủ công bỏ qua kiểm tra
    này. Đây là siết chặt ĐÚNG Ý (khớp quy tắc ERPNext áp cho mọi hóa đơn
    có cập nhật tồn kho khác), nhưng cần xác nhận mọi Item/POS Profile thật
    đã có warehouse cấu hình trước khi áp dụng, kẻo POS Invoice không lưu
    được vì thiếu warehouse.
    """
    doc.update_stock = 1


def disable_stock_for_consolidated_pos_sales_invoice(doc, method=None):
    """POS stock is posted on POS Invoice submit, not during POS Closing consolidation."""
    if doc.doctype != "Sales Invoice":
        return

    has_pos_invoice_rows = any(item.get("pos_invoice") for item in doc.get("items", []))
    if doc.get("is_consolidated") or has_pos_invoice_rows:
        doc.update_stock = 0
