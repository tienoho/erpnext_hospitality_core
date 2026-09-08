"""Chuyển bảng giá cũ một lần; không đoán hay sửa tiền phòng lịch sử."""

import json

import frappe


def execute():
    columns = set(frappe.db.get_table_columns('Room Rate Plan'))
    if {'rate', 'valid_from', 'valid_to'} <= columns:
        rows = frappe.db.sql('SELECT name, rate, valid_from, valid_to FROM `tabRoom Rate Plan`', as_dict=True)
        for row in rows:
            plan = frappe.get_doc('Room Rate Plan', row.name)
            if plan.seasons or not row.valid_from or not row.valid_to:
                continue
            plan.append('seasons', dict(season_name='Giá chuyển từ bảng cũ', valid_from=row.valid_from,
                valid_to=row.valid_to, weekday_rate=row.rate or 0, weekend_rate=row.rate or 0))
            plan.save(ignore_permissions=True)

    # Lưu nguồn sao chép riêng, không bị mất khi reference_doctype chuyển thành Sales Invoice.
    frappe.db.sql('''UPDATE `tabFolio Transaction` SET mirror_source=reference_name
        WHERE reference_doctype='Folio Transaction' AND COALESCE(mirror_source, '')='' ''')

    from hospitality_core.hospitality_core.api.rate_plan import snapshot_for
    for row in frappe.get_all('Hotel Reservation', filters={'status': ['in', ['Reserved', 'Checked In']]},
                              fields=['name', 'rate_plan', 'room_type', 'rate_snapshot']):
        if row.rate_snapshot:
            continue
        if row.room_type == 'Virtual':
            row.rate_plan = None
            frappe.db.set_value('Hotel Reservation', row.name, 'rate_plan', None, update_modified=False)
        try:
            snapshot = snapshot_for(row.rate_plan, row.room_type)
        except frappe.ValidationError:
            # Không tự đổi bảng giá sai hạng/đã tắt: cần quản lý xác định lại.
            frappe.log_error(title='Rate Plan Migration', message=f'Đặt phòng {row.name}: cần kiểm tra bảng giá trước khi tính tiền.')
            continue
        frappe.db.set_value('Hotel Reservation', row.name, 'rate_snapshot',
                           json.dumps(snapshot, ensure_ascii=False), update_modified=False)
