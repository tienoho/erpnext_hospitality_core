# Copyright (c) 2026, Gift Braimah and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

class SalesReport(Document):
    """
    QUAN TRỌNG VỀ PHẠM VI: đây là báo cáo đóng ca CHỈ RIÊNG mảng POS/F&B
    (nguồn dữ liệu duy nhất là POS Closing Entry) — KHÔNG bao gồm doanh thu
    phòng (Guest Folio/Folio Transaction). Đây là quyết định phạm vi có chủ
    đích, không phải thiếu sót: doanh thu phòng đã có báo cáo riêng
    (room_only_sales, monthly_revenue_by_room_type, city_ledger...), và
    chính vòng đời có Submit/Cancel/Amend của DocType này khớp đúng quy
    trình ký duyệt đóng ca thu ngân POS, khác hẳn quy trình đối soát doanh
    thu phòng (qua Night Audit). VÌ VẬY: `vat_amount`/`service_charge`/
    `consumption_tax`/`total_taxes` ở đây KHÔNG PHẢI số dư đầy đủ của 3 tài
    khoản GL thuế tương ứng — số dư GL thật còn bao gồm cả phần thuế phát
    sinh từ charge phòng (ghi qua api/accounting.py, độc lập với DocType
    này). Muốn đối soát ĐẦY ĐỦ thuế toàn khách sạn (phòng + POS) với GL,
    DÙNG BÁO CÁO "Taxes And Charges Report" (report/taxes_and_charges_report)
    — báo cáo đó đọc TRỰC TIẾP GL Entry theo 3 tài khoản thuế đã cấu hình,
    không lọc theo voucher_type, nên tự động bao gồm CẢ 2 nguồn (phòng qua
    accounting.py, POS qua reclassify_pos_taxes trong CÙNG file) — đây mới
    là công cụ đối soát đúng, không phải báo cáo Sales Report này.
    """
    def autoname(self):
        # Trước đây doctype này là Single (đúng 1 bản ghi cho toàn hệ thống) dù
        # dữ liệu thực chất là báo cáo cuối ngày theo từng company+khoảng ngày —
        # mỗi lần tạo báo cáo mới sẽ xóa mất báo cáo trước đó, không có lịch sử
        # kiểm toán. Nay là DocType thường: tự đặt tên tự mô tả theo company +
        # ngày để dễ nhận biết trong danh sách, đồng thời khiến việc tạo 2 báo
        # cáo cho CÙNG company+ngày tự nhiên báo lỗi trùng tên thay vì âm thầm
        # ghi đè. Dùng autoname() (không phải before_insert()) để khớp đúng cơ
        # chế Frappe thực sự gọi khi xác định tên bản ghi mới (set_new_name()
        # gọi run_method("autoname") — xem quy ước tương tự tại
        # GuestFolio.autoname() trong cùng app này) và không can thiệp vào tên
        # do Frappe tự đặt khi Amend (dạng "{tên gốc}-1").
        if self.amended_from:
            return
        from frappe.utils import getdate
        date_str = getdate(self.from_date_time).strftime("%Y-%m-%d") if self.from_date_time else frappe.utils.nowdate()
        company_abbr = frappe.db.get_value("Company", self.company, "abbr") if self.company else None
        new_name = f"EOD-{company_abbr or self.company or 'NA'}-{date_str}"

        # Báo lỗi rõ ràng thay vì để insert thất bại với lỗi trùng khóa CSDL
        # khó hiểu — đây cũng chính là cách chặn tạo 2 báo cáo cho cùng
        # company+ngày mà comment ở trên nhắc tới.
        if frappe.db.exists("Sales Report", new_name):
            frappe.throw(frappe._(
                "Đã tồn tại báo cáo Sales Report cho {0} ngày {1} (mã {2}). "
                "Vui lòng mở báo cáo đó để chỉnh sửa/tạo lại thay vì tạo bản ghi mới."
            ).format(self.company, date_str, new_name))

        self.name = new_name

    def validate(self):
        # Tên bản ghi được tính 1 LẦN DUY NHẤT lúc insert (xem autoname()) từ
        # company + from_date_time — autoname() không chạy lại khi save() một
        # bản ghi đã tồn tại, nên nếu cho phép đổi 2 trường này sau khi đã lưu,
        # tên bản ghi (VD "EOD-TCG-2026-03-12") sẽ không còn khớp với dữ liệu
        # thật bên trong. Bắt buộc tạo báo cáo mới nếu cần company/ngày khác.
        if not self.is_new():
            if self.has_value_changed("company"):
                frappe.throw(frappe._("Không thể đổi Company sau khi đã lưu báo cáo — vui lòng tạo một bản ghi Sales Report mới."))
            if self.has_value_changed("from_date_time"):
                frappe.throw(frappe._("Không thể đổi From Date & Time sau khi đã lưu báo cáo — vui lòng tạo một bản ghi Sales Report mới."))

    @frappe.whitelist()
    def generate_report(self):
        if self.docstatus == 1:
            frappe.throw(frappe._("Báo cáo này đã được chốt (Submitted) — không thể tạo lại. Vui lòng Hủy (Cancel) và Amend nếu cần điều chỉnh."))

        self.clear_existing_data()

        closing_entries = self.get_closing_entries()
        if not closing_entries:
            frappe.msgprint("No POS Closing Entries found for the selected criteria.")
            # QUAN TRỌNG: khi đây là bản ghi MỚI chưa từng lưu (trước đây là
            # Single nên luôn "tồn tại" sẵn, không sao) và không có Closing
            # Entry nào, hàm này return sớm mà KHÔNG gọi self.save() — với
            # DocType thường bây giờ, nghĩa là bản ghi thực sự CHƯA từng được
            # tạo trên server. Phải báo cho client biết để không gọi
            # frm.reload_doc() trên một tên bản ghi tạm (new-sales-report-...)
            # chưa hề tồn tại, gây lỗi "not found" khó hiểu.
            return {"success": False, "saved": not self.is_new()}

        closing_entry_names = tuple([e.name for e in closing_entries])

        self.aggregate_kpis(closing_entries)
        self.aggregate_invoices(closing_entry_names)
        self.aggregate_payments(closing_entry_names)
        self.flag_discrepancies(closing_entries)
        
        # Extract Cashiers Full Names
        unique_users = list({e.user for e in closing_entries if e.get("user")})
        cashier_names = []
        for u in unique_users:
            full_name = frappe.db.get_value("User", u, "full_name") or u
            cashier_names.append(full_name)
        self.cashiers = ", ".join(cashier_names)
        
        if self.include_stock_balances:
            self.aggregate_stock_balances(closing_entries)
        
        self.save()
        frappe.msgprint("Report Generated Successfully")
        return {"success": True, "saved": True, "name": self.name}

    def clear_existing_data(self):
        self.set("eod_item_sales", [])
        self.set("eod_item_group_sales", [])
        self.set("eod_payment_summary", [])
        self.set("eod_expense_breakdown", [])
        self.set("eod_discrepancies", [])
        self.set("eod_stock_balance", [])
        self.cashiers = ""
        self.total_expected_amount = 0.0
        self.total_actual_amount = 0.0
        self.total_difference = 0.0
        self.vat_amount = 0.0
        self.service_charge = 0.0
        self.consumption_tax = 0.0
        self.net_sales = 0.0
        self.total_taxes = 0.0
        self.total_transactions = 0
        
    def get_closing_entries(self):
        # TRƯỚC ĐÂY: cắt from_date_time/to_date_time (Datetime) về Date thuần
        # rồi lọc posting_date BETWEEN (bao gồm CẢ 2 đầu mút) — ca đóng POS
        # không thẳng theo nửa đêm (nhân viên chốt ca muộn sau 0h, rất phổ
        # biến ở nhà hàng/bar phục vụ khuya) khiến 2 báo cáo EOD liền kề có
        # thể cùng đếm trùng closing entry của "ngày biên". Dùng đúng
        # period_start_date/period_end_date (Datetime, khoảng thời gian
        # THẬT của ca đóng — field chuẩn của POS Closing Entry trong
        # ERPNext) để so khớp nửa-mở với đúng khoảng from_date_time/
        # to_date_time của báo cáo này — 1 ca đóng chỉ thuộc về ĐÚNG 1 báo
        # cáo, không phụ thuộc việc nó rơi vào ngày dương lịch nào.
        # Chú ý: cả 2 vế đều dùng bất đẳng thức NGHIÊM NGẶT (< / >), không
        # phải >= — dùng >= ở vế period_end_date trước đây tạo lệch bất đối
        # xứng: 1 ca đóng có period_end_date TRÙNG KHỚP CHÍNH XÁC ranh giới
        # giữa 2 báo cáo liền kề (VD kết thúc đúng lúc window_end của báo
        # cáo A = window_start của báo cáo B) sẽ thỏa mãn CẢ 2 điều kiện,
        # bị đếm trùng vào cả báo cáo A lẫn B. Dùng nghiêm ngặt cả 2 vế đảm
        # bảo 1 ca chỉ thuộc đúng 1 cửa sổ nửa-mở duy nhất.
        filters = {
            "company": self.company,
            "period_start_date": ("<", self.to_date_time),
            "period_end_date": (">", self.from_date_time),
            "docstatus": 1
        }

        # TRƯỚC ĐÂY: Sales Report nằm trong SCOPED (property_scope.py) nhưng
        # không hề lọc theo self.property — mọi property dùng chung 1
        # company sẽ bị trộn lẫn số liệu. POS Closing Entry không có field
        # property riêng, nhưng POS Profile thì có (field hospitality_property
        # mới, xem migrations/property_v2.py) — 1 property có thể có nhiều
        # POS Profile/outlet, nên lọc gián tiếp qua danh sách profile thuộc
        # đúng property này. Nếu người dùng CŨNG chọn thủ công 1 danh sách
        # pos_profiles cụ thể, lấy GIAO của 2 danh sách (không để cái sau
        # ghi đè mất cái trước).
        allowed_profiles = None
        if self.pos_profiles:
            allowed_profiles = {row.pos_profile for row in self.pos_profiles}
        if self.get('property'):
            property_profiles = set(frappe.get_all("POS Profile",
                filters={"hospitality_property": self.property}, pluck="name"))
            allowed_profiles = property_profiles if allowed_profiles is None else (allowed_profiles & property_profiles)
        if allowed_profiles is not None:
            filters["pos_profile"] = ("in", list(allowed_profiles) or [""])

        return frappe.get_all("POS Closing Entry", filters=filters, fields=["name", "pos_profile", "grand_total", "net_total", "total_quantity", "user"])
        
    def aggregate_kpis(self, closing_entries):
        closing_entry_names = tuple([e.name for e in closing_entries])
        totals = frappe.db.sql("""
            SELECT SUM(expected_amount) as expected, SUM(closing_amount) as actual, SUM(difference) as diff
            FROM `tabPOS Closing Entry Detail`
            WHERE parent IN %s
        """, (closing_entry_names,), as_dict=True)[0]
        
        self.total_expected_amount = flt(totals.get("expected"))
        self.total_actual_amount = flt(totals.get("actual"))
        self.total_difference = flt(totals.get("diff"))

        settings = frappe.get_cached_doc("Hospitality Accounting Settings")
        vat_account = getattr(settings, "vat_account", None)
        service_account = getattr(settings, "service_charge_account", None)
        consumption_account = getattr(settings, "consumption_tax_account", None)

        if vat_account or service_account or consumption_account:
            # Use the actual tax lines posted on submitted invoices instead of a
            # flat percentage of total_expected_amount, which ignores tax-exempt
            # items, discounts, and complimentary rooms.
            by_account = self.get_tax_totals_by_account(closing_entry_names)
            self.vat_amount = by_account.get(vat_account, 0.0)
            self.service_charge = by_account.get(service_account, 0.0)
            self.consumption_tax = by_account.get(consumption_account, 0.0)
        else:
            self.vat_amount = self.total_expected_amount * 0.075
            self.service_charge = self.total_expected_amount * 0.10
            self.consumption_tax = self.total_expected_amount * 0.05

        self.net_sales = self.total_expected_amount - (self.vat_amount + self.service_charge + self.consumption_tax)
        # TRƯỚC ĐÂY: total_taxes được tính RIÊNG trong aggregate_invoices()
        # bằng cách cộng thẳng total_taxes_and_charges của MỌI hóa đơn — số
        # này có thể KHÔNG khớp vat_amount+service_charge+consumption_tax ở
        # trên (dùng ở net_sales) nếu hóa đơn có dòng thuế thuộc tài khoản
        # KHÁC 3 tài khoản đã cấu hình. Dùng lại đúng breakdown này làm nguồn
        # duy nhất để total_taxes không bao giờ lệch với net_sales trên cùng
        # 1 báo cáo.
        self.total_taxes = self.vat_amount + self.service_charge + self.consumption_tax

    def get_tax_totals_by_account(self, closing_entry_names):
        invoice_references = frappe.db.sql("""
            SELECT pos_invoice
            FROM `tabPOS Invoice Reference`
            WHERE parent IN %s
        """, (closing_entry_names,), as_dict=True)

        if not invoice_references:
            return {}

        invoice_names = tuple([r.pos_invoice for r in invoice_references])

        tax_rows = frappe.db.sql("""
            SELECT t.account_head,
                SUM(CASE WHEN p.is_return = 1 THEN -t.tax_amount ELSE t.tax_amount END) as amount
            FROM `tabSales Taxes and Charges` t
            JOIN `tabPOS Invoice` p ON t.parent = p.name
            WHERE t.parenttype = 'POS Invoice' AND t.parent IN %s AND p.docstatus = 1
            GROUP BY t.account_head
        """, (invoice_names,), as_dict=True)

        return {r.account_head: flt(r.amount) for r in tax_rows}

    def aggregate_invoices(self, closing_entry_names):
        # Get linked invoices from the child table of POS Closing Entry
        invoice_references = frappe.db.sql("""
            SELECT pos_invoice
            FROM `tabPOS Invoice Reference`
            WHERE parent IN %s
        """, (closing_entry_names,), as_dict=True)
        
        if not invoice_references:
            return
            
        invoice_names = tuple([r.pos_invoice for r in invoice_references])
        
        invoices = frappe.get_all(
            "POS Invoice", 
            filters={"name": ("in", invoice_names), "docstatus": 1},
            fields=["name", "net_total", "total_taxes_and_charges", "is_return"]
        )
        
        self.total_transactions = len(invoices)
        if not invoices:
            return

        submitted_invoice_names = tuple([i.name for i in invoices])

        item_sales = frappe.db.sql("""
            SELECT 
                i.item_code, 
                i.item_name, 
                i.item_group, 
                p.pos_profile, 
                SUM(CASE WHEN p.is_return = 1 THEN -i.qty ELSE i.qty END) as qty, 
                SUM(CASE WHEN p.is_return = 1 THEN -i.net_amount ELSE i.net_amount END) as amount
            FROM `tabPOS Invoice Item` i
            JOIN `tabPOS Invoice` p ON p.name = i.parent
            WHERE p.name IN %s
            GROUP BY i.item_code, p.pos_profile
        """, (submitted_invoice_names,), as_dict=True)
        
        for item in item_sales:
            self.append("eod_item_sales", {
                "pos_profile": item.pos_profile,
                "item_code": item.item_code,
                "item_name": item.item_name,
                "qty_sold": item.qty,
                "amount": item.amount
            })
            
        group_sales = frappe.db.sql("""
            SELECT 
                i.item_group, 
                SUM(CASE WHEN p.is_return = 1 THEN -i.qty ELSE i.qty END) as qty, 
                SUM(CASE WHEN p.is_return = 1 THEN -i.net_amount ELSE i.net_amount END) as amount
            FROM `tabPOS Invoice Item` i
            JOIN `tabPOS Invoice` p ON p.name = i.parent
            WHERE p.name IN %s
            GROUP BY i.item_group
        """, (submitted_invoice_names,), as_dict=True)
        
        for group in group_sales:
            self.append("eod_item_group_sales", {
                "item_group": group.item_group,
                "qty_sold": group.qty,
                "amount": group.amount
            })

    def aggregate_payments(self, closing_entry_names):
        payments = frappe.db.sql("""
            SELECT mode_of_payment, SUM(expected_amount) as expected, SUM(closing_amount) as actual, SUM(difference) as diff
            FROM `tabPOS Closing Entry Detail`
            WHERE parent IN %s
            GROUP BY mode_of_payment
        """, (closing_entry_names,), as_dict=True)
        
        for p in payments:
            self.append("eod_payment_summary", {
                "payment_mode": p.mode_of_payment,
                "expected_amount": p.expected,
                "actual_amount": p.actual,
                "difference": p.diff
            })

    def flag_discrepancies(self, closing_entries):
        # We record every closing entry used in the report, including those with zero difference
        # This table serves as the "Associated Closing Entries" list
        
        closing_entry_names = tuple([e.name for e in closing_entries])
        differences = frappe.db.sql("""
            SELECT parent, SUM(difference) as diff
            FROM `tabPOS Closing Entry Detail`
            WHERE parent IN %s
            GROUP BY parent
        """, (closing_entry_names,), as_dict=True)
        
        diff_map = {d.parent: d.diff for d in differences}
        
        for entry in closing_entries:
            self.append("eod_discrepancies", {
                "pos_closing_entry": entry.name,
                "pos_profile": entry.pos_profile,
                "difference": diff_map.get(entry.name, 0.0)
            })

    def aggregate_stock_balances(self, closing_entries):
        from frappe.utils import get_datetime
        from erpnext.stock.utils import get_stock_balance

        cutoff = get_datetime(self.to_date_time)
        profiles_by_warehouse = {}
        for profile in sorted({e.pos_profile for e in closing_entries if e.pos_profile}):
            warehouse = frappe.db.get_value("POS Profile", profile, "warehouse")
            if warehouse:
                profiles_by_warehouse.setdefault(warehouse, []).append(profile)

        for warehouse, profiles in profiles_by_warehouse.items():
            if frappe.db.get_value('Warehouse', warehouse, 'company') != self.company:
                frappe.throw(frappe._('Kho POS không thuộc pháp nhân của báo cáo.'))
            stock_rows = frappe.db.sql("""
                SELECT DISTINCT s.item_code, i.item_name, i.item_group, i.stock_uom AS uom
                FROM `tabStock Ledger Entry` s
                JOIN `tabItem` i ON i.name=s.item_code
                WHERE s.warehouse=%s AND s.is_cancelled=0
                  AND TIMESTAMP(s.posting_date, s.posting_time) <= %s
                ORDER BY i.item_group, i.item_name
            """, (warehouse, cutoff), as_dict=True)
            for row in stock_rows:
                balance = get_stock_balance(row.item_code, warehouse, cutoff.date(), cutoff.time())
                if not balance:
                    continue
                self.append("eod_stock_balance", {
                    "pos_profile": ", ".join(profiles), "warehouse": warehouse,
                    "item_code": row.item_code, "item_name": row.item_name,
                    "item_group": row.item_group, "uom": row.uom,
                    "balance_qty": flt(balance)
                })
