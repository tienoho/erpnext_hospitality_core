# Copyright (c) 2026, Gift Braimah and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from math import isfinite


class ItemRecipe(Document):
	def validate(self):
		"""Validate recipe before saving"""
		self.validate_composite_item()
		self.validate_ingredients()
		self.calculate_stock_quantities()
	
	def validate_composite_item(self):
		"""Ensure the item is marked as composite"""
		if not frappe.db.get_value("Item", self.item, "is_composite_item"):
			frappe.throw(_("Item {0} must be marked as 'Composite Item' to create a recipe").format(self.item))
	
	def validate_ingredients(self):
		"""Validate ingredient items"""
		if not self.ingredients:
			frappe.throw(_("At least one ingredient is required"))
		if not isfinite(flt(self.quantity)) or flt(self.quantity) <= 0:
			frappe.throw(_('Sản lượng công thức phải dương và hữu hạn.'))
		for row in self.ingredients:
			if not isfinite(flt(row.qty)) or flt(row.qty) <= 0:
				frappe.throw(_('Lượng nguyên liệu phải dương và hữu hạn.'))
		
		# Check for duplicate ingredients
		ingredient_items = [d.ingredient_item for d in self.ingredients]
		if len(ingredient_items) != len(set(ingredient_items)):
			frappe.throw(_("Duplicate ingredients are not allowed"))
		
		# Check for circular reference (item cannot be its own ingredient)
		if self.item in ingredient_items:
			frappe.throw(_("Item {0} cannot be an ingredient of itself").format(self.item))

		self.validate_no_transitive_circular_reference(ingredient_items)

	def validate_no_transitive_circular_reference(self, ingredient_items):
		"""Walk each ingredient's own recipe (if any) to catch multi-hop cycles,
		e.g. A's recipe uses B, and B's recipe uses A back."""
		visited = set()
		stack = list(ingredient_items)
		while stack:
			current = stack.pop()
			if current == self.item:
				frappe.throw(_("Circular recipe reference detected: {0} indirectly includes itself as an ingredient").format(self.item))
			if current in visited:
				continue
			visited.add(current)
			sub_recipe = frappe.db.get_value("Item Recipe", {"item": current}, "name")
			if sub_recipe:
				stack.extend(
					d.ingredient_item for d in frappe.get_all(
						"Recipe Ingredient", filters={"parent": sub_recipe}, fields=["ingredient_item"]
					)
				)
	
	def calculate_stock_quantities(self):
		"""Calculate stock quantities for ingredients"""
		for ingredient in self.ingredients:
			if not ingredient.ingredient_item:
				continue
			
			# Fetch stock UOM from item
			stock_uom = frappe.db.get_value("Item", ingredient.ingredient_item, "stock_uom")
			ingredient.stock_uom = stock_uom
			
			# Calculate stock quantity based on UOM conversion
			if ingredient.uom == stock_uom:
				ingredient.stock_qty = ingredient.qty
			else:
				# Get conversion factor
				conversion_factor = get_uom_conversion_factor(
					ingredient.ingredient_item,
					ingredient.uom,
					stock_uom
				)
				ingredient.stock_qty = flt(ingredient.qty) * flt(conversion_factor)
	
	def on_update(self):
		"""Create or update BOM after save"""
		self.sync_bom()
	
	def on_trash(self):
		"""Delete linked BOM when recipe is deleted"""
		if self.bom:
			try:
				bom_doc = frappe.get_doc("BOM", self.bom)
				if bom_doc.docstatus == 1:
					bom_doc.cancel()
				frappe.delete_doc("BOM", self.bom, force=1)
			except Exception as e:
				frappe.log_error(f"Error deleting BOM {self.bom}: {str(e)}")
	
	def sync_bom(self):
		"""Synchronize recipe with ERPNext BOM"""
		if self.bom:
			# Update existing BOM
			self.update_bom()
		else:
			# Create new BOM
			self.create_bom()

	def create_bom(self, company=None):
		"""
		Create a new BOM for this recipe.

		TRƯỚC ĐÂY: luôn dùng company MẶC ĐỊNH TOÀN CỤC — an toàn khi site chỉ
		có 1 company, nhưng 1 BOM DUY NHẤT không thể phục vụ đúng nhiều
		company cùng bán 1 composite item (BOM thuộc ĐÚNG 1 company theo
		thiết kế gốc của ERPNext). `company` giờ có thể truyền vào để tạo
		BOM cho 1 company CỤ THỂ (dùng bởi composite_item_utils.py's
		get_active_bom() khi công ty của hóa đơn khác company của BOM mặc
		định) — chỉ cập nhật self.bom (BOM "mặc định" hiển thị trên form)
		khi tạo cho company mặc định ban đầu, không ghi đè khi tạo bản sao
		cho company khác.
		"""
		default_company = frappe.defaults.get_defaults().get("company") or frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {}, "name")
		target_company = company or default_company

		bom = frappe.new_doc("BOM")
		bom.item = self.item
		bom.quantity = self.quantity
		bom.uom = self.uom
		bom.is_active = self.is_active
		# Chỉ đặt is_default=1 cho BOM của company MẶC ĐỊNH (không xác minh
		# được liệu ERPNext tự giới hạn "mặc định duy nhất" theo (item,
		# company) hay chỉ theo item — nếu là vế sau, tạo thêm 1 BOM
		# is_default=1 cho company khác có thể vô tình đổi Item.default_bom/
		# is_default của BOM company gốc, ảnh hưởng các luồng khác không
		# liên quan (VD get_available_to_make() gọi không kèm company).
		# get_active_bom() tự tra theo (item, company) trực tiếp, không dựa
		# vào is_default, nên không cần field này = 1 cho bản sao company
		# khác vẫn hoạt động đúng.
		bom.is_default = 1 if target_company == default_company else 0
		bom.company = target_company
		# TRƯỚC ĐÂY: không set currency tường minh — BOM.currency là field
		# bắt buộc nhưng Frappe chỉ tự điền từ default TOÀN SITE (Global
		# Defaults.default_currency, gắn với company MẶC ĐỊNH), không phải
		# theo company của CHÍNH BOM này. Với BOM tạo cho company KHÁC
		# company mặc định (dùng tiền tệ khác), BOM sẽ âm thầm mang SAI tiền
		# tệ (theo company mặc định) thay vì tiền tệ thật của company đó.
		bom.currency = frappe.get_cached_value('Company', target_company, 'default_currency')

		# Add ingredients as BOM items
		for ingredient in self.ingredients:
			bom.append("items", {
				"item_code": ingredient.ingredient_item,
				"qty": ingredient.qty,
				"uom": ingredient.uom,
				"stock_qty": ingredient.stock_qty,
				"stock_uom": ingredient.stock_uom,
				"rate": frappe.db.get_value("Item", ingredient.ingredient_item, "valuation_rate") or 0
			})

		bom.insert(ignore_permissions=True)
		bom.submit()

		# TRƯỚC ĐÂY: tin rằng is_default=0 lúc insert là đủ để tránh
		# manage_default_bom() promote nhầm — đọc trực tiếp
		# erpnext/manufacturing/doctype/bom/bom.py xác nhận có 1 khe hẹp:
		# nếu tại thời điểm CHÍNH XÁC lúc submit, item này KHÔNG CÒN bất kỳ
		# BOM active+submitted nào khác (VD đang giữa lúc update_bom() hủy
		# BOM cũ để tạo bản mới), manage_default_bom() sẽ TỰ ĐỘNG promote
		# BOM company khác này thành is_default=1 VÀ ghi đè Item.default_bom
		# — bất kể company nào. Kiểm tra lại NGAY SAU submit; nếu lỡ bị
		# promote sai company, tự sửa lại thay vì để sai âm thầm.
		if target_company != default_company:
			bom.reload()
			if bom.is_default:
				frappe.db.set_value('BOM', bom.name, 'is_default', 0)
				default_bom_for_item = frappe.get_all('BOM',
					filters={'item': self.item, 'company': default_company, 'is_active': 1, 'docstatus': 1},
					order_by='creation desc', limit=1, pluck='name')
				frappe.db.set_value('Item', self.item, 'default_bom', default_bom_for_item[0] if default_bom_for_item else None)

		# Store BOM reference — chỉ khi đây là BOM cho company mặc định (BOM
		# "chính" hiển thị trên form Item Recipe); BOM tạo riêng cho company
		# khác được tra cứu trực tiếp qua BOM.item+BOM.company, không cần
		# lưu thêm field nào trên Item Recipe.
		if not company or company == default_company:
			self.db_set("bom", bom.name, update_modified=False)
		return bom.name
	
	def update_bom(self):
		"""Update existing BOM"""
		try:
			bom = frappe.get_doc("BOM", self.bom)
			
			# If it's submitted, we must cancel it.
			# If it's cancelled, we can't save it. In both cases, create a new one.
			if bom.docstatus > 0:
				if bom.docstatus == 1:
					bom.cancel()
				
				# Create a new version
				self.create_bom()
				return
			
			# If it's still in draft (docstatus 0), update it
			bom.quantity = self.quantity
			bom.uom = self.uom
			bom.is_active = self.is_active
			
			# Clear and re-add items
			bom.set("items", [])
			for ingredient in self.ingredients:
				bom.append("items", {
					"item_code": ingredient.ingredient_item,
					"qty": ingredient.qty,
					"uom": ingredient.uom,
					"stock_qty": ingredient.stock_qty,
					"stock_uom": ingredient.stock_uom,
					"rate": frappe.db.get_value("Item", ingredient.ingredient_item, "valuation_rate") or 0
				})
			
			bom.save(ignore_permissions=True)
			bom.submit()
			
		except Exception as e:
			frappe.log_error(f"Error updating BOM {self.bom}: {str(e)}")
			frappe.throw(_("Failed to update BOM. Please check error log."))


def get_uom_conversion_factor(item_code, from_uom, to_uom):
	"""Get UOM conversion factor"""
	if from_uom == to_uom:
		return 1.0
	
	# Check if conversion exists
	conversion = frappe.db.get_value(
		"UOM Conversion Detail",
		{"parent": item_code, "uom": from_uom},
		"conversion_factor"
	)
	
	if conversion:
		return flt(conversion)
	
	frappe.throw(_('Thiếu quy đổi UOM {0} sang {1} cho nguyên liệu {2}.').format(from_uom, to_uom, item_code))


@frappe.whitelist()
def estimate_recipe_cost(recipe_name, warehouse, at):
	from frappe.utils import get_datetime
	from erpnext.stock.utils import get_stock_balance
	recipe = frappe.get_doc('Item Recipe', recipe_name)
	recipe.check_permission('read')
	wh = frappe.get_doc('Warehouse', warehouse)
	wh.check_permission('read')
	if wh.is_group or wh.disabled:
		frappe.throw(_('Chọn kho chi tiết đang hoạt động.'))
	# Quyền giá trị tồn kho cần đủ cả kho và pháp nhân, không chỉ Item Recipe.
	frappe.get_doc('Company', wh.company).check_permission('read')
	cutoff = get_datetime(at)
	recipe.validate_ingredients()
	recipe.calculate_stock_quantities()
	costs = []
	for row in recipe.ingredients:
		qty, rate = get_stock_balance(row.ingredient_item, warehouse, cutoff.date(), cutoff.time(), with_valuation_rate=True)
		if rate <= 0:
			frappe.throw(_('Chưa có giá trị tồn kho dương cho {0} tại thời điểm đã chọn; không thể ước tính đủ giá vốn.').format(row.ingredient_item))
		costs.append(dict(item=row.ingredient_item, stock_qty=row.stock_qty, stock_uom=row.stock_uom,
			valuation_rate=rate, amount=flt(row.stock_qty)*rate))
	total = sum(row['amount'] for row in costs)
	return dict(batch_cost=total, unit_cost=total/flt(recipe.quantity), quantity=recipe.quantity,
		uom=recipe.uom, warehouse=warehouse, at=str(cutoff),
		currency=frappe.get_cached_value('Company', wh.company, 'default_currency'), ingredients=costs)
