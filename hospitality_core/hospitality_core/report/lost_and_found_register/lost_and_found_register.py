import frappe
from frappe import _
from hospitality_core.hospitality_core.api.report_scope import allowed_properties_for_report

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": _("ID"), "fieldname": "name", "fieldtype": "Link", "options": "Lost and Found Item", "width": 120},
        {"label": _("Date Found"), "fieldname": "found_date", "fieldtype": "Date", "width": 100},
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 150},
        {"label": _("Found In"), "fieldname": "found_location", "fieldtype": "Data", "width": 120, "description": "Room or Area"},
        {"label": _("Found By"), "fieldname": "finder_name", "fieldtype": "Data", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 80},
        {"label": _("Claimed By"), "fieldname": "claimant_info", "fieldtype": "Data", "width": 180},
        {"label": _("Date Claimed"), "fieldname": "claimed_date", "fieldtype": "Date", "width": 100}
    ]

    conditions = "1=1"
    params = {}

    if filters.get("from_date") and filters.get("to_date"):
        conditions += " AND lnf.found_date BETWEEN %(from_date)s AND %(to_date)s"
        params["from_date"] = filters.get("from_date")
        params["to_date"] = filters.get("to_date")

    if filters.get("status"):
        conditions += " AND lnf.status = %(status)s"
        params["status"] = filters.get("status")

    allowed_properties = allowed_properties_for_report()
    if allowed_properties is not None:
        conditions += " AND lnf.property IN %(_properties)s"
        params["_properties"] = allowed_properties or [""]

    # TRƯỚC ĐÂY: JOIN `tabEmployee` ON lnf.finder = emp.name — nhưng
    # `Lost and Found Item.finder` là field Data (TÊN NHẬP TAY TỰ DO), KHÔNG
    # PHẢI Link tới Employee (Employee.name là mã tự sinh dạng "HR-EMP-00001",
    # không bao giờ khớp 1 cái tên gõ tay) — JOIN này gần như KHÔNG BAO GIỜ
    # khớp với dữ liệu thật, khiến cột "Found By" luôn hiện RỖNG dù nhân
    # viên đã ghi rõ tên người tìm thấy. Dùng thẳng lnf.finder (đã là tên
    # người, không cần join gì cả).
    sql = f"""
        SELECT
            lnf.name,
            lnf.found_date,
            lnf.item_name,
            lnf.found_location,
            lnf.finder as finder_name,
            lnf.status,
            lnf.claimant_info,
            lnf.claimed_date
        FROM
            `tabLost and Found Item` lnf
        WHERE
            {conditions}
        ORDER BY
            lnf.found_date DESC
    """
    
    data = frappe.db.sql(sql, params, as_dict=True)
    
    return columns, data