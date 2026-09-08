import frappe
try:
    from frappe.model.document import Document
except Exception:
    class Document:
        pass


class HotelRoom(Document):
    pass


def resolve_hotel_room(room_identifier, property=None):
    """
    Hỗ trợ giải quyết số phòng thực tế (VD: '101', '202') hoặc ID hash của Hotel Room
    thành docname chính xác của bản ghi Hotel Room trong database.
    """
    if not room_identifier:
        return None
    raw = str(room_identifier).strip()
    if frappe.db.exists("Hotel Room", raw):
        return raw
    filters = {"room_number": raw}
    if property:
        filters["property"] = property
    docname = frappe.db.get_value("Hotel Room", filters, "name")
    return docname or raw


def get_room_number(room_identifier):
    """
    Lấy số phòng hiển thị thân thiện (room_number) từ docname hash hoặc ngược lại.
    """
    if not room_identifier:
        return ""
    raw = str(room_identifier).strip()
    return frappe.db.get_value("Hotel Room", raw, "room_number") or raw
