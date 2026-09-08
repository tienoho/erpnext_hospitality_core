import frappe
from frappe import _
from frappe.utils import flt

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

    TRƯỚC ĐÂY (2 lần liền, cả 2 lần đều dựa trên giả định SAI chưa từng đọc
    trực tiếp `pos_invoice.py` thật của ERPNext 16.34.1): hàm này set
    `doc.update_stock = 1` ở before_validate, với lý do "core tự lo SLE+GL
    lúc on_submit() y hệt Sales Invoice, khớp idiom
    `disable_stock_for_consolidated_pos_sales_invoice` đã dùng".

    ĐÃ XÁC MINH TRỰC TIẾP mã nguồn thật
    (`erpnext/accounts/doctype/pos_invoice/pos_invoice.py`) và phát hiện giả
    định trên SAI HOÀN TOÀN cho riêng POS Invoice: `POSInvoice.validate()`
    gọi `super(SalesInvoice, self).validate()` — dùng cú pháp Python nhảy
    THẲNG qua `SalesInvoice.validate()` để gọi `SellingController.validate()`
    (ông của SalesInvoice) — và `POSInvoice.on_submit()` KHÔNG hề gọi
    `super().on_submit()` ở bất kỳ dạng nào. Cả 2 override này chặn đứng
    hoàn toàn logic của `SalesInvoice.on_submit()` (dòng ~493-509 file thật:
    `if self.update_stock == 1: ... self.update_stock_ledger(); ...
    self.make_gl_entries()`) — nơi DUY NHẤT trong toàn bộ codebase ERPNext xử
    lý field `update_stock`. Kết quả: set `update_stock=1` trên POS Invoice
    KHÔNG CÓ TÁC DỤNG GÌ — không tạo Stock Ledger Entry, không tạo GL Entry,
    dù giá trị field vẫn được lưu đúng vào DB.

    Hậu quả THẬT của lần sửa trước (không phải giả thuyết): mọi Item
    `is_stock_item=1` (không phải composite) bán qua POS Invoice hoàn toàn
    KHÔNG bị trừ kho — tệ hơn cả lỗi ban đầu (lỗi cũ ít nhất còn trừ kho
    đúng, chỉ sai GL; lần sửa trước làm CẢ HAI đều sai — tồn kho báo cáo
    sai, sổ sách cũng không có gì). `composite_item_utils.py`'s comment giải
    thích lý do chặn Item vừa composite vừa stock ("1 lần chính nó qua Stock
    Ledger chuẩn... vì stock.py đã set update_stock=1") cũng dựa trên đúng
    giả định sai này — bản thân việc chặn đó vẫn ĐÚNG cho Sales Invoice
    thường (nơi update_stock=1 thật sự có tác dụng), chỉ riêng lời giải
    thích không còn đúng cho nhánh POS Invoice.

    Sửa TẬN GỐC lần này: KHÔNG còn ép `update_stock=1` (vô nghĩa với POS
    Invoice, chỉ gây hiểu nhầm khi đọc dữ liệu sau này) — để field này ở giá
    trị tự nhiên từ POS Profile. Thay vào đó, dùng hàm mới
    `deduct_stock_items_for_pos_invoice()` (đăng ký ở on_submit/on_cancel)
    tự tạo Stock Entry THẬT cho từng Item `is_stock_item=1` không phải
    composite — đúng cơ chế `Stock Entry.submit()` (StockController's own
    on_submit) đã CHỨNG MINH hoạt động đúng trong chính app này (dùng y hệt
    idiom `create_ingredient_consumption_entry()` của
    `composite_item_utils.py` đã áp dụng cho nguyên liệu composite từ trước).

    Hàm này giữ lại làm no-op có chủ đích (không xóa hẳn, vì hooks.py có thể
    còn tham chiếu qua bản build cũ) — không set gì cả.
    """
    return


def deduct_stock_items_for_pos_invoice(doc, method=None):
    """
    Hook: POS Invoice (on_submit/on_cancel).

    Trừ/hoàn kho THẬT cho từng dòng Item `is_stock_item=1` (không phải
    composite — composite đã có `composite_item_utils.py` xử lý nguyên liệu
    riêng) bán trực tiếp qua POS Invoice — xem chú thích tại
    `enable_stock_update_for_pos_invoice()` để biết lý do `update_stock=1`
    không có tác dụng cho POS Invoice, khiến các Item này TRƯỚC ĐÂY hoàn
    toàn không bị trừ kho.

    Bỏ qua hóa đơn do FNB Cost Control quản lý (`fnb_version=='FNB v1'`) —
    module đó đã tự tạo Stock Entry riêng qua `api/fnb/pos.py`'s
    `post_stock()`, tạo ở đây nữa sẽ trừ kho HAI LẦN.

    Dùng đúng field `custom_source_invoice`/`custom_invoice_type` (đã có sẵn
    trên Stock Entry qua `composite_item_setup.py`) làm khóa chống ghi
    trùng/idempotent, để trống `custom_composite_item` (Item nào KHÔNG phải
    composite) để phân biệt với Stock Entry của nguyên liệu composite.
    """
    if doc.doctype != "POS Invoice" or doc.get("fnb_version") == "FNB v1":
        return

    is_cancel = doc.docstatus == 2

    existing = frappe.get_all("Stock Entry", filters={
        "custom_source_invoice": doc.name,
        "custom_invoice_type": doc.doctype,
        "custom_composite_item": ["in", ["", None]],
        "docstatus": 1,
    }, pluck="name")

    if is_cancel:
        for name in existing:
            entry = frappe.get_doc("Stock Entry", name)
            if entry.docstatus == 1:
                entry.cancel()
        return

    if existing:
        # Đã ghi kho cho hóa đơn này (retry/gọi lại on_submit) — không trừ trùng.
        return

    rows = []
    for item in doc.items:
        flags = frappe.db.get_value("Item", item.item_code, ["is_stock_item", "is_composite_item"], as_dict=True)
        if flags and flags.is_stock_item and not flags.is_composite_item:
            rows.append(item)

    if not rows:
        return

    # Hóa đơn hoàn hàng (is_return=1): quy ước ERPNext ghi qty/amount ÂM trên
    # dòng item để phản chiếu đúng hóa đơn gốc — nếu tạo "Material Issue" với
    # qty âm, Stock Entry Item sẽ từ chối (bắt buộc qty > 0). Đổi sang
    # "Material Receipt" (nhập lại kho) với qty dương cho đúng chiều hoàn trả.
    is_return = bool(doc.get("is_return"))
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt" if is_return else "Material Issue"
    se.purpose = "Material Receipt" if is_return else "Material Issue"
    se.company = doc.company
    se.posting_date = doc.posting_date
    se.posting_time = doc.posting_time
    se.set_posting_time = 1
    se.custom_source_invoice = doc.name
    se.custom_invoice_type = doc.doctype

    cost_center = frappe.get_cached_value("Company", doc.company, "cost_center")
    for row in rows:
        if not row.warehouse:
            frappe.throw(_("Item {0} trên POS Invoice thiếu Warehouse — không thể ghi kho.").format(row.item_code))
        warehouse_field = "t_warehouse" if is_return else "s_warehouse"
        se.append("items", {
            "item_code": row.item_code,
            "qty": abs(flt(row.stock_qty)),
            "uom": row.stock_uom or row.uom,
            warehouse_field: row.warehouse,
            "cost_center": cost_center,
        })

    se.insert(ignore_permissions=True)
    se.submit()


def disable_stock_for_consolidated_pos_sales_invoice(doc, method=None):
    """POS stock is posted on POS Invoice submit, not during POS Closing consolidation."""
    if doc.doctype != "Sales Invoice":
        return

    has_pos_invoice_rows = any(item.get("pos_invoice") for item in doc.get("items", []))
    if doc.get("is_consolidated") or has_pos_invoice_rows:
        doc.update_stock = 0
