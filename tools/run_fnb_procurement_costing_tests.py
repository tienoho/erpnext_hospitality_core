"""Kịch bản kiểm thử MỚI — luồng mua hàng thật (Purchase Order -> Purchase
Receipt) qua approve_native(), và luồng định mức/tính giá cost (FNB Cost
Standard -> recipe_cost() -> approve_standard()) — CHƯA có test nào che phủ
trong run_fnb_control_integration.py/run_fb_integration.py (xác nhận bằng
grep: approve_native() chỉ được test cho 'Material Request'/'Sales Invoice',
chưa từng test cho 'Purchase Receipt'; recipe_cost()/approve_standard()/FNB
Cost Standard hoàn toàn không xuất hiện trong test nào, chỉ trong 1 tool
sinh schema).

Chạy trên site test riêng, dữ liệu rollback sau mỗi ca (theo đúng quy ước
các script khác trong thư mục này).
"""
import unittest
import frappe
from frappe.utils import nowdate, add_days, now_datetime
from run_fnb_control_integration import CostControlTests
from erpnext.stock.utils import get_stock_balance


class ProcurementCostingTests(CostControlTests):
    def setup_control(self):
        super().setup_control()
        # setup_control() cấp self.operator vai trò System/Stock/Sales/Accounts —
        # KHÔNG có quyền tạo Purchase Order/Purchase Receipt (đúng chuẩn ERPNext:
        # 'Purchase Manager'/'Purchase User' mới có create=1). Không đụng tới
        # setup_control() dùng chung; chỉ cấp thêm quyền cho user riêng của lớp test này.
        frappe.get_doc('User', self.operator).add_roles('Purchase Manager')

    def make_supplier(self):
        name = 'FNB Test Supplier'
        if not frappe.db.exists('Supplier', name):
            frappe.get_doc(dict(doctype='Supplier', supplier_name=name,
                supplier_group=frappe.db.get_value('Supplier Group', {'is_group': 1}))).insert(ignore_permissions=True)
        return name

    def make_po(self, qty=10, rate=100000):
        frappe.set_user(self.operator)
        po = frappe.get_doc(dict(doctype='Purchase Order', supplier=self.make_supplier(), company=self.company,
            fnb_outlet=self.out.name, transaction_date=nowdate(), schedule_date=nowdate(),
            items=[dict(item_code=self.raw.name, qty=qty, rate=rate, uom='FB kg', stock_uom='FB kg',
                conversion_factor=1, warehouse=self.config.main_warehouse, schedule_date=nowdate())]))
        po.insert()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.procurement import approve_native
        approve_native('Purchase Order', po.name)
        po.reload()
        po.submit()
        return po

    def make_pr(self, po, rate=None, qty=None):
        from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
        frappe.set_user(self.operator)
        pr = make_purchase_receipt(po.name)
        if isinstance(pr, dict):
            pr = frappe.get_doc(pr)
        pr.fnb_outlet = self.out.name
        if rate is not None:
            pr.items[0].rate = rate
        if qty is not None:
            pr.items[0].qty = qty
        pr.insert()
        return pr

    # ------------------------------------------------------------------
    # 1) Mua hàng: approve_native('Purchase Receipt', ...) — dung sai giá/SL
    # ------------------------------------------------------------------
    def test_purchase_receipt_within_tolerance_succeeds(self):
        self.setup_control()
        po = self.make_po(qty=10, rate=100000)
        pr = self.make_pr(po, rate=100000, qty=10)
        from hospitality_core.hospitality_core.api.fnb.procurement import approve_native
        frappe.set_user('Administrator')
        approve_native('Purchase Receipt', pr.name)
        pr.reload()
        pr.submit()
        self.assertEqual(get_stock_balance(self.raw.name, self.config.main_warehouse), 10)
        self.assertEqual(pr.fnb_approved_by, 'Administrator')

    def test_purchase_receipt_price_over_tolerance_blocked(self):
        self.setup_control()
        po = self.make_po(qty=10, rate=100000)
        # cfg.price_tolerance_percent=1 (setup_control()) -> 5% vượt hẳn dung sai.
        pr = self.make_pr(po, rate=105000, qty=10)
        from hospitality_core.hospitality_core.api.fnb.procurement import approve_native
        frappe.set_user('Administrator')
        with self.assertRaisesRegex(frappe.ValidationError, 'dung sai'):
            approve_native('Purchase Receipt', pr.name)
        pr.reload()
        self.assertIsNone(pr.get('fnb_approved_by'))
        self.assertEqual(get_stock_balance(self.raw.name, self.config.main_warehouse), 0,
            'Nhận hàng lệch giá quá dung sai không được duyệt -> không được phép submit/đổi tồn kho.')

    def test_purchase_receipt_qty_over_tolerance_blocked(self):
        self.setup_control()
        po = self.make_po(qty=10, rate=100000)
        # cfg.quantity_tolerance_percent=1 -> nhận vượt 5% là vượt hẳn dung sai.
        pr = self.make_pr(po, rate=100000, qty=10.5)
        from hospitality_core.hospitality_core.api.fnb.procurement import approve_native
        frappe.set_user('Administrator')
        with self.assertRaisesRegex(frappe.ValidationError, 'dung sai'):
            approve_native('Purchase Receipt', pr.name)
        pr.reload()
        self.assertIsNone(pr.get('fnb_approved_by'))

    def test_purchase_receipt_within_qty_tolerance_boundary_succeeds(self):
        self.setup_control()
        po = self.make_po(qty=10, rate=100000)
        # 1% dung sai của 10 = 0.1 -> 10.1 vẫn còn trong dung sai của approve_native().
        # LƯU Ý: ERPNext còn có "Over Receipt Allowance" RIÊNG (Stock Settings,
        # mặc định 0%, độc lập với dung sai FNB Settings) — kiểm tra ở on_submit()
        # (status_updater.py's validate_qty()), KHÔNG PHẢI approve_native() —
        # xác nhận thật khi chạy test: pr.submit() bị chính ERPNext chặn dù
        # approve_native() đã duyệt đúng. Không phải bug hospitality_core; nới
        # tạm dung sai gốc ERPNext cho đúng kịch bản đang kiểm (chỉ trong test).
        frappe.db.set_single_value('Stock Settings', 'over_delivery_receipt_allowance', 5)
        pr = self.make_pr(po, rate=100000, qty=10.1)
        from hospitality_core.hospitality_core.api.fnb.procurement import approve_native
        frappe.set_user('Administrator')
        approve_native('Purchase Receipt', pr.name)
        pr.reload()
        pr.submit()
        self.assertAlmostEqual(get_stock_balance(self.raw.name, self.config.main_warehouse), 10.1, places=6)

    def test_purchase_receipt_without_po_link_blocked(self):
        self.setup_control()
        frappe.set_user(self.operator)
        pr = frappe.get_doc(dict(doctype='Purchase Receipt', supplier=self.make_supplier(), company=self.company,
            fnb_outlet=self.out.name, posting_date=nowdate(),
            items=[dict(item_code=self.raw.name, qty=5, rate=100000, uom='FB kg', stock_uom='FB kg',
                conversion_factor=1, warehouse=self.config.main_warehouse)]))
        pr.insert()
        from hospitality_core.hospitality_core.api.fnb.procurement import approve_native
        frappe.set_user('Administrator')
        with self.assertRaisesRegex(frappe.ValidationError, 'Purchase Order'):
            approve_native('Purchase Receipt', pr.name)

    # ------------------------------------------------------------------
    # 2) Định mức + tính giá cost: FNB Cost Standard -> recipe_cost()
    # ------------------------------------------------------------------
    def test_recipe_cost_from_approved_standard(self):
        self.setup_control()
        frappe.set_user(self.operator)
        standard = frappe.get_doc(dict(doctype='FNB Cost Standard', property=self.reservation.property,
            from_date=nowdate(), to_date=add_days(nowdate(), 30),
            prices=[dict(item=self.raw.name, rate=200, price_date=nowdate(),
                source_doctype='Item', source_name=self.raw.name)]))
        standard.insert()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.reports import approve_standard, recipe_cost
        approve_standard(standard.name)
        standard.reload()
        self.assertEqual(standard.status, 'Approved')
        # self.recipe (setup_control()): quantity=2 FB portion, ingredients=[raw 500 FB g].
        # stock_quantity() quy đổi FB g -> FB kg (0.001) trước khi lưu snapshot, nên
        # snapshot ingredient qty thực là 0.5 (kg) * rate 200/kg = 100.
        result = recipe_cost(self.recipe.name, standard.name)
        self.assertAlmostEqual(result['batch_cost'], 100, places=6)
        self.assertAlmostEqual(result['unit_cost'], 50, places=6)
        self.assertEqual(result['currency'], standard.currency)

    def test_recipe_cost_missing_ingredient_price_blocked(self):
        self.setup_control()
        # Tạo Item mới như Administrator (khớp cách self.raw/self.dish được tạo
        # trong setup_stock()) — self.operator không cần vai trò tạo Item cho
        # ca test này, chỉ cần vai trò tạo FNB Cost Standard (System Manager).
        other = frappe.get_doc(dict(doctype='Item', item_code='FNB-OTHER-RAW', item_name='FNB other raw',
            item_group='Services', stock_uom='FB kg', is_stock_item=1)).insert()
        frappe.set_user(self.operator)
        standard = frappe.get_doc(dict(doctype='FNB Cost Standard', property=self.reservation.property,
            from_date=nowdate(), to_date=add_days(nowdate(), 30),
            prices=[dict(item=other.name, rate=999, price_date=nowdate(),
                source_doctype='Item', source_name=other.name)]))
        standard.insert()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.reports import approve_standard, recipe_cost
        approve_standard(standard.name)
        with self.assertRaisesRegex(frappe.ValidationError, 'Thiếu giá chuẩn'):
            recipe_cost(self.recipe.name, standard.name)

    def test_recipe_cost_requires_approved_recipe_and_standard(self):
        self.setup_control()
        frappe.set_user(self.operator)
        standard = frappe.get_doc(dict(doctype='FNB Cost Standard', property=self.reservation.property,
            from_date=nowdate(), to_date=add_days(nowdate(), 30),
            prices=[dict(item=self.raw.name, rate=200, price_date=nowdate(),
                source_doctype='Item', source_name=self.raw.name)]))
        standard.insert()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.reports import recipe_cost
        with self.assertRaisesRegex(frappe.ValidationError, 'đã duyệt'):
            recipe_cost(self.recipe.name, standard.name)  # standard vẫn Draft.

    # ------------------------------------------------------------------
    # 3) deactivate() — vô hiệu hóa vĩnh viễn Outlet/Settings (mới thêm, xem
    #    configuration.py — trước đây enabled=1 không có cách nào tắt hẳn).
    # ------------------------------------------------------------------
    def test_deactivate_requires_pause_first(self):
        self.setup_control()
        from hospitality_core.hospitality_core.api.fnb.configuration import deactivate
        with self.assertRaisesRegex(frappe.ValidationError, 'tạm dừng'):
            deactivate('FNB Outlet', self.out.name, 'Đóng outlet thử nghiệm')
        self.out.reload()
        self.assertEqual(self.out.enabled, 1)

    def test_deactivate_after_pause_succeeds(self):
        self.setup_control()
        from hospitality_core.hospitality_core.api.fnb.configuration import set_paused, deactivate
        set_paused('FNB Outlet', self.out.name, 1, 'Tạm dừng để đóng outlet')
        deactivate('FNB Outlet', self.out.name, 'Đóng outlet vĩnh viễn')
        self.out.reload()
        self.assertEqual(self.out.enabled, 0)
        self.assertEqual(self.out.paused, 0)
        # FNB Settings cùng property vẫn hoạt động bình thường — deactivate 1
        # outlet không ảnh hưởng outlet/cấu hình khác cùng cơ sở.
        settings = frappe.get_doc('FNB Settings', self.reservation.property)
        self.assertEqual(settings.enabled, 1)

    def test_deactivate_settings_requires_pause_first(self):
        self.setup_control()
        from hospitality_core.hospitality_core.api.fnb.configuration import set_paused, deactivate
        with self.assertRaisesRegex(frappe.ValidationError, 'tạm dừng'):
            deactivate('FNB Settings', self.reservation.property, 'Đóng cơ sở thử nghiệm')
        set_paused('FNB Settings', self.reservation.property, 1, 'Tạm dừng để đóng cơ sở')
        deactivate('FNB Settings', self.reservation.property, 'Đóng cơ sở vĩnh viễn')
        settings = frappe.get_doc('FNB Settings', self.reservation.property)
        self.assertEqual(settings.enabled, 0)
        self.assertEqual(settings.paused, 0)


if __name__ == "__main__":
    import sys, json
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ProcurementCostingTests))
        print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))))
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
