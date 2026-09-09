"""Cài schema hỗ trợ; mapping dữ liệu vận hành thực hiện tường minh qua wizard."""
import frappe


def execute():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    from hospitality_core.setup_script.composite_item_setup import setup_composite_item_fields
    setup_composite_item_fields()
    # TRƯỚC ĐÂY: einvoice.py đọc/ghi 5 field (einvoice_status/provider/number/
    # lookup_code/issued_on) trên Sales Invoice, nhưng chúng CHỈ được tạo bởi
    # setup_einvoice_fields.py — 1 script chạy tay ("Run once via: bench ...
    # execute ...run"), KHÔNG hề được hooks.py gọi ở after_install/after_migrate.
    # Trên site cài mới/staging/khôi phục thảm họa, 5 field này không tồn tại
    # — mọi lần phát hành/kiểm tra trạng thái hóa đơn điện tử sẽ đọc/ghi vào
    # field không có thật (Frappe âm thầm bỏ qua khi ghi, trả None khi đọc).
    # Gọi lại đúng hàm run() đã viết sẵn (idempotent, tự kiểm tra field đã
    # tồn tại chưa) thay vì đợi ai đó nhớ chạy tay.
    from hospitality_core.setup_einvoice_fields import run as setup_einvoice_fields
    setup_einvoice_fields()
    # TRƯỚC ĐÂY: toàn bộ DocType "Folio Ledger Adjustment" (không chỉ 1 field)
    # chỉ được tạo bởi create_ledger_adjustment_doctype.py — script KHÔNG hề
    # được hooks.py/setup.py gọi ở đâu cả. Trong khi đó hooks.py đã wire sẵn
    # doc_events["Folio Ledger Adjustment"] (on_submit/on_cancel →
    # api/folio.py's process_ledger_adjustment/cancel_ledger_adjustment) và
    # api/folio.py chủ động tạo Folio Transaction tham chiếu doctype này làm
    # reference_doctype. Trên site cài mới/staging/khôi phục thảm họa, cả
    # DOCTYPE không tồn tại — tính năng điều chỉnh sổ cái thủ công sẽ crash
    # "DocType Folio Ledger Adjustment not found" ngay lần đầu dùng, không
    # phải chỉ mất field. Hàm execute() đã tự kiểm tra tồn tại (idempotent),
    # gọi lại an toàn mỗi lần migrate.
    from hospitality_core.create_ledger_adjustment_doctype import execute as create_ledger_adjustment_doctype
    create_ledger_adjustment_doctype()
    common = [dict(fieldname='hospitality_property',label='Hospitality Property',fieldtype='Link',
                   options='Hospitality Property',insert_after='company'),
              dict(fieldname='hospitality_folio',label='Guest Folio',fieldtype='Link',options='Guest Folio'),
              dict(fieldname='hospitality_accounting_version',label='Hospitality Accounting Version',
                   fieldtype='Data',read_only=1,no_copy=1)]
    create_custom_fields({dt: common for dt in ['Sales Invoice','POS Invoice','Payment Entry','Journal Entry']}, update=True)
    create_custom_fields({'Sales Invoice Item':[
        dict(fieldname='hospitality_posting',label='Hospitality Charge Posting',fieldtype='Link',options='Hospitality Charge Posting',read_only=1)],
        # TRƯỚC ĐÂY: api/payment_bridge.py ghi 3 field này (room_number,
        # hotel_reception, cashier) vào MỌI Payment Entry nó tạo — nhưng
        # KHÔNG CÓ NƠI NÀO trong app từng tạo chúng qua cơ chế cài
        # đặt/migrate thật sự. `room_number` chỉ có trong 1 script mồ côi
        # (add_room_to_pe.py) không được hooks.py gọi; `hotel_reception`
        # chỉ được tạo (bởi setup_pos_report.py, cũng không được gọi, còn
        # hardcode chạy tay nhắm 1 site cụ thể) trên Mode of Payment — SAI
        # doctype, không phải Payment Entry; `cashier` không có nơi tạo nào
        # cả. Trên 1 site cài mới/staging/khôi phục thảm họa, cả 3 field
        # này không tồn tại — Frappe âm thầm bỏ qua field lạ khi insert(),
        # nghĩa là dữ liệu (số phòng, quầy lễ tân, thu ngân) bị MẤT TRẮNG
        # không một dấu hiệu nào, không phải chỉ trên site hiện tại (nơi có
        # thể ai đó đã âm thầm thêm tay qua Customize Form) mà trên MỌI site
        # mới. Dùng đúng cơ chế create_custom_fields() đã được migrate gọi
        # để đảm bảo tái lập được trên bất kỳ site nào.
        'Payment Entry':[
            dict(fieldname='hospitality_event_key',label='Hospitality Event Key',fieldtype='Data',unique=1,read_only=1),
            dict(fieldname='room_number',label='Room Number',fieldtype='Data',insert_after='party_name'),
            dict(fieldname='hotel_reception',label='Hotel Reception',fieldtype='Link',options='Hotel Reception'),
            dict(fieldname='cashier',label='Cashier',fieldtype='Link',options='User',read_only=1)],
        'GL Entry':[dict(fieldname='hospitality_property',label='Hospitality Property',fieldtype='Link',options='Hospitality Property',read_only=1)],
        # Mapping THẬT giữa POS Profile và Property — 1 property có thể có
        # NHIỀU outlet POS (nhà hàng, bar, spa, quầy lễ tân...), nên field
        # này đặt trên POS PROFILE (nhiều-Profile → 1-Property), KHÔNG phải
        # 1 field đơn "pos_profile" trên Hospitality Property Settings
        # (field đó chỉ là "outlet mặc định", không đủ để tra ngược property
        # cho MỌI outlet). Đây là nguồn chân lý duy nhất để: (1) lọc
        # sales_report.py's POS Closing Entry theo property, (2) gán
        # hospitality_property lên POS Invoice (xem doc_events["POS
        # Invoice"] mới trong hooks.py).
        'POS Profile':[dict(fieldname='hospitality_property',label='Hospitality Property',fieldtype='Link',options='Hospitality Property')]},update=True)
    for dt,columns in [('Hotel Room',['property','room_number']),('Hotel Room Type',['property','room_type_name'])]:
        frappe.db.add_unique(dt,columns,constraint_name='unique_property_label')
    # NULL property cho phép giữ bản ghi chưa ánh xạ; không giả định Company/currency lịch sử.
    for dt in ['Hotel Reservation','Guest Folio','Hotel Group Booking','Guest Balance Ledger','Folio Transaction']:
        frappe.db.sql(f"UPDATE `tab{dt}` SET accounting_version='Legacy' WHERE COALESCE(accounting_version,'')=''")
    for dt in ['Hotel Reservation','Guest Folio']:
        frappe.db.sql(f"UPDATE `tab{dt}` SET billing_customer=company WHERE COALESCE(billing_customer,'')='' AND COALESCE(company,'')!=''")
    if not frappe.db.exists('Accounting Dimension',{'document_type':'Hospitality Property'}):
        doc=frappe.get_doc(dict(doctype='Accounting Dimension',document_type='Hospitality Property',
            label='Hospitality Property',fieldname='hospitality_property'))
        doc.insert(ignore_permissions=True)
    # ERPNext dùng dimension ngay trong các truy vấn Budget/GL. Không để
    # migrate kết thúc khi cột còn đang chờ worker; đồng thời sửa lần chạy dở.
    from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import make_dimension_in_accounting_doctypes
    dimension = frappe.get_doc('Accounting Dimension', {'document_type': 'Hospitality Property'})
    make_dimension_in_accounting_doctypes(dimension)
    # property_accounting.py's create_invoice() gộp NHIỀU Hospitality Charge
    # Posting (1 charge gốc dương + 0..n điều chỉnh LOS/manual có thể âm)
    # vào CÙNG 1 Sales Invoice — xác nhận THẬT qua test sống trên Docker:
    # ERPNext's status_updater.py's validate_qty() CẤM tuyệt đối dòng qty<0
    # trên hóa đơn không phải is_return (không có cách tắt riêng cho 1
    # chứng từ), nên create_invoice() nay dùng qty=1 cố định + rate MANG
    # DẤU thay vì qty=-1/rate=abs() như trước — nhưng ERPNext cũng mặc định
    # CẤM rate âm trừ khi bật cờ này (Selling Settings, áp dụng TOÀN SITE).
    # Chấp nhận đánh đổi có cân nhắc: dòng có rate âm ở đây LUÔN do chính
    # code này tự dựng (không phải người dùng gõ tay), và is_negative_grand_
    # total_allowed() của ERPNext vẫn CHẶN grand_total<0 cho Sales Invoice
    # bất kể cờ này (chỉ ảnh hưởng Sales/Purchase Order) — nên bật cờ không
    # mở đường cho 1 hóa đơn có tổng tiền âm lọt qua ở bất kỳ luồng nào khác.
    frappe.db.set_single_value('Selling Settings', 'allow_negative_rates_for_items', 1)
