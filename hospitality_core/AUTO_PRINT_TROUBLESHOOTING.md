# Auto-Print Troubleshooting Guide

> **Cập nhật lại**: tài liệu cũ mô tả kiến trúc in ẤN SERVER-SIDE qua CUPS/`lp` và
> gọi thẳng một hàm server `auto_print_pos_invoice()` — hàm đó **không còn tồn
> tại**. Kiến trúc thật hiện tại là **in phía CLIENT (trình duyệt)**: server chỉ
> cung cấp cấu hình (bật/tắt, số bản, print format) qua 1 API đọc-thôi, còn việc
> mở PDF và gọi lệnh in là do JavaScript chạy trên máy trạm thực hiện.

## Kiến trúc thật

- **Server** (`hospitality_core/hospitality_core/api/auto_print.py`): chỉ có
  đúng 1 hàm `get_print_settings()` (`@frappe.whitelist()`), đọc 3 field từ
  Single `Hospitality Accounting Settings` (`enable_auto_print`,
  `print_copies`, `receipt_print_format`) và trả về dict
  `{enabled, copies, print_format}`. Không có bất kỳ code server nào gọi tới
  máy in — không có CUPS, không có `lp`/`lpstat`/`lpoptions`.
- **Client** (2 Client Script JS, đăng ký qua `hooks.py`'s `app_include_js`):
  - `hospitality_core/public/js/pos_invoice_auto_print.js` — hook `after_save`
    trên form **POS Invoice**.
  - `hospitality_core/public/js/payment_entry_auto_print.js` — tương tự cho
    **Payment Entry**.
  Khi form được lưu ở trạng thái Submitted (`docstatus===1`), JS gọi
  `frappe.call(...get_print_settings)`; nếu `enabled=true`, nó mở 1 tab/cửa sổ
  trình duyệt mới trỏ tới `download_pdf` (route chuẩn của Frappe để render
  print format ra PDF), đợi PDF tải xong rồi tự gọi `window.print()` — đây
  chính là hộp thoại in CHUẨN của trình duyệt, dùng máy in mặc định CỦA MÁY
  TRẠM đang mở trình duyệt đó, không phải máy in cấu hình trên server.

## Sự cố: In tự động không hoạt động sau khi bật trong Settings

### Các bước xử lý:

1. **Xác nhận cấu hình đã bật đúng**
   - Vào: Hospitality Accounting Settings
   - Xác nhận đã tick "Enable Automatic Receipt Printing" (`enable_auto_print`)
   - Ghi nhớ giá trị "Number of Copies to Print" (`print_copies`) và
     print format đã chọn (`receipt_print_format`)

2. **Kiểm tra trình duyệt có chặn pop-up không** (nguyên nhân phổ biến nhất)
   - JS mở PDF bằng `window.open(...)` — nếu trình duyệt chặn pop-up, cửa sổ
     sẽ không mở và JS tự hiển thị `msgprint` "Pop-up Blocked" yêu cầu người
     dùng cho phép pop-up cho site này.
   - Vào cài đặt trình duyệt (Chrome: biểu tượng pop-up-blocked trên thanh địa
     chỉ, hoặc Settings → Privacy and security → Site settings → Pop-ups) và
     cho phép pop-up cho đúng domain của site.

3. **Kiểm tra Console của trình duyệt** (F12 → tab Console) ngay sau khi submit
   - Log mong đợi: `Auto-print enabled: printing N copies` rồi
     `Opening print dialog...` — nếu KHÔNG thấy dòng đầu, `get_print_settings()`
     trả `enabled=false` hoặc lỗi gọi API (xem bước 4).
   - Nếu thấy log nhưng không thấy hộp thoại in: kiểm tra máy in MẶC ĐỊNH của
     hệ điều hành/trình duyệt trên chính máy trạm đó (Cài đặt in của Windows/
     macOS, hoặc cài đặt mặc định của Chrome) — đây là bước tương đương
     `lpstat -d` cũ, nhưng thực hiện Ở MÁY TRẠM, không phải server.

4. **Kiểm tra Error Log** (nếu `get_print_settings()` lỗi)
   - Vào: Error Log list, lọc tiêu đề "Auto Print: Settings Error"
   - Hàm này tự bọc try/except — lỗi đọc `Hospitality Accounting Settings`
     (VD field bị đổi tên/xóa) sẽ log ở đây và trả về `enabled=False` an toàn
     thay vì crash, khiến in tự động ÂM THẦM không chạy mà không báo lỗi rõ
     ràng cho người dùng cuối — đây là nơi đầu tiên cần xem khi "bật rồi mà
     không thấy gì xảy ra".

5. **Kiểm tra Client Script đã được tải chưa**
   - Xác nhận `hooks.py`'s `app_include_js` có liệt kê đúng
     `pos_invoice_auto_print.js`/`payment_entry_auto_print.js`.
   - Nếu vừa deploy code mới, chạy `bench build --app hospitality_core` rồi
     hard-refresh trình duyệt (Ctrl+Shift+R) — khác với bản cũ, KHÔNG cần
     `bench restart` để JS có hiệu lực (chỉ cần build lại asset + refresh
     trình duyệt), vì đây là thay đổi phía client, không phải import Python
     mới cần nạp lại tiến trình server.

### Các lỗi thường gặp

**Lỗi**: Hộp thoại in không mở, không có thông báo gì
**Nguyên nhân/Xử lý**: Nhiều khả năng pop-up bị chặn nhưng `window.open()`
trả về `null` một cách "im lặng" ở một số trình duyệt cũ hơn — kiểm tra icon
chặn pop-up trên thanh địa chỉ.

**Lỗi**: PDF mở ra nhưng hộp thoại in không tự bật
**Nguyên nhân/Xử lý**: `print_window.onload` (JS) có thể không bắn đúng thời
điểm nếu trình duyệt render PDF bằng plugin/viewer riêng thay vì tab HTML
thường — người dùng có thể tự bấm Ctrl+P/nút in trong chính PDF viewer đó.

**Lỗi**: PDF báo lỗi/không tạo được
**Nguyên nhân/Xử lý**: Kiểm tra print format cấu hình trong
`receipt_print_format` có thực sự tồn tại và hợp lệ (chưa bị xóa/đổi tên).

### Kiểm thử thủ công qua bench console

Vì `get_print_settings()` là hàm ĐỌC THÔI (không có tác dụng phụ), có thể gọi
trực tiếp để xác nhận cấu hình server trả về đúng, TRƯỚC KHI nghi ngờ phía
client:

```python
bench --site <site-name> console

# Trong console:
import frappe
from hospitality_core.hospitality_core.api.auto_print import get_print_settings

print(get_print_settings())
# Kỳ vọng: {'enabled': True, 'copies': <số bản>, 'print_format': '<tên format>'}
```

Nếu kết quả đúng như mong đợi nhưng vẫn không in được, vấn đề chắc chắn nằm ở
PHÍA CLIENT (pop-up bị chặn, máy in mặc định của máy trạm, hoặc JS chưa được
tải) — không phải phía server.
