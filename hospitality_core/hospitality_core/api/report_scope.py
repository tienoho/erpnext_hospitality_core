"""Trợ giúp lọc báo cáo/dashboard theo property.

TẠI SAO CẦN FILE NÀY: property_scope.py's `permission_query_conditions`/
`has_permission` (đăng ký trong hooks.py) chỉ áp dụng cho query ORM
(frappe.get_list/get_all, list view, report builder) — KHÔNG tự động áp dụng
cho `frappe.db.sql()` thô. Toàn bộ Script Report + dashboard_data.py trong
app này dùng SQL thô, viết từ trước khi hệ thống multi-property (Property v2)
tồn tại. Một khi có từ 2 Hospitality Property "enabled" trở lên, các báo cáo
này sẽ ÂM THẦM trộn dữ liệu tài chính của TẤT CẢ cơ sở lại với nhau, không có
cách nào lọc theo property — một user chỉ được cấp quyền xem 1 cơ sở vẫn có
thể thấy số liệu của cơ sở khác qua báo cáo.

Cách dùng: gọi `allowed_properties_for_report()` để lấy danh sách property
user hiện tại được phép xem (None nghĩa là "không cần lọc" — hệ thống chưa
cài/chưa kích hoạt/user là quản trị), rồi tự thêm điều kiện
`<alias>.property IN %(...)s` phù hợp với phong cách tham số (positional hay
named) của từng câu SQL sẵn có trong mỗi báo cáo.
"""
import frappe


def allowed_properties_for_report(user=None):
    """Trả về None nếu KHÔNG cần lọc (hệ thống property chưa cài/chưa có
    property nào "enabled"/user là quản trị) — báo cáo giữ nguyên hành vi
    hiện tại, không đổi gì. Trả về 1 list (có thể rỗng) các tên property được
    phép xem nếu CẦN lọc — báo cáo phải thêm điều kiện
    `<alias>.property IN (...)` bằng list này (rỗng nghĩa là user không được
    xem cơ sở nào, báo cáo phải trả về không có dòng nào)."""
    try:
        from hospitality_core.hospitality_core.api.property_scope import installed, manager, allowed_properties
    except ImportError:
        return None
    if not installed() or manager(user) or not frappe.db.exists('Hospitality Property', {'enabled': 1}):
        return None
    return allowed_properties(user)
