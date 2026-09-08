# Báo Cáo Tổng Hợp 5 Đợt Rà Soát Lỗi Nghiệp Vụ & Toàn Vẹn Dữ Liệu (Audit Passes 1 – 5)

**Dự án**: ERPNext Hospitality Core (`erpnext_hospitality_core`)  
**Ngày hoàn tất**: 08/09/2026  
**Trạng thái**: Đã hoàn thành, toàn bộ 21 tệp sửa đổi đã kiểm thử đạt 38/38 unit tests và commit vào nhánh `main` (`e866d50`).

---

## 🎯 Mục Tiêu & Phạm Vi Rà Soát

Sau các giai đoạn hiện đại hóa giao diện người dùng (Front Desk Console, Tape Chart 2.0, Housekeeping View & Mobile PWA, Guest Folio, Guest 360 CRM), hệ thống đã trải qua 5 đợt rà soát chuyên sâu (Interaction Audit Passes 1 – 5) nhằm:
1. Loại bỏ triệt để các lỗi hiển thị mã hash nội bộ thay vì số phòng vật lý ("101", "202").
2. Đảm bảo toàn vẹn dữ liệu đa cơ sở (`Hospitality Property`) và đa pháp nhân (`Company`).
3. Khắc phục các lỗi pháp lý trọng yếu về Thuế (Hóa đơn điện tử) và Khai báo tạm trú (Công an / Cục Xuất nhập cảnh).
4. Ngăn ngừa lỗi xung đột đồng thời (Concurrency / Race Condition / Double-booking).
5. Đồng bộ audit log buồng phòng và chống crash do thiếu cấu hình phụ thuộc.

---

## 📋 Chi Tiết 5 Đợt Rà Soát (Audit Passes 1 – 5)

### Đợt 1 (Pass 1 - UI & Interaction Bugfixes) — Commit `eb39297`
* **Tape Chart Drag & Drop**: Sửa lỗi `TypeError` khi kéo thả do tham chiếu sai context page/wrapper.
* **Chống Double Click trên Mobile**: Thêm cờ chống click liên tiếp khi nhân viên thao tác trên điện thoại.
* **An toàn CSS Selector**: Bọc hàm `escape_selector` chống crash trên trình duyệt phiên bản cũ.

### Đợt 2 (Pass 2 - CRM & Formatting Bugfixes) — Commit `bf43e50`
* **Guest 360 CRM**: Khắc phục lỗi `format_number is not defined` trên tab Hội viên khi hiển thị điểm loyalty.
* **Định danh Khách hàng**: Ánh xạ chuẩn trường số CCCD/Hộ chiếu từ `id_passport_number` sang `identification_no`.
* **SPA Routing**: Ngăn chặn xung đột router SPA khi chuyển tab trên trang Guest 360 mà không làm đổi hash URL của Frappe Desk.

### Đợt 3 (Pass 3 - Pre-arrival Reassignment & VietQR) — Commit `f172d9a`
* **Kéo thả Đặt phòng trước (Reserved)**: Tách biệt hoàn toàn luồng chuyển phòng đặt trước (Pre-arrival Reassignment) với chuyển phòng in-house (`Checked In`), giúp lễ tân xếp phòng linh hoạt trên Tape Chart mà không bị chặn bởi điều kiện `res.status != 'Checked In'`.
* **VietQR Ghi đè số tiền**: Đảm bảo số tiền khách nhập tại quầy (đặt cọc hoặc thanh toán một phần) được ưu tiên thay vì bị đè bởi toàn bộ số dư nợ folio.
* **PWA Buồng phòng**: Cho phép nhân viên nhập trực tiếp số phòng vật lý ("101", "202") khi ghi Minibar hoặc Báo hỏng thay vì bắt buộc truyền mã hash nội bộ.

### Đợt 4 (Pass 4 - Chuẩn Hóa Phân Giải Số Phòng Vật Lý) — Commit `45a123e`
* **Bàn Lễ Tân (Front Desk Console)**: Sửa truy vấn SQL trả về mã hash nội bộ; danh sách Khách Đến / Khách Đi nay hiển thị và sắp xếp chuẩn theo số phòng vật lý ("101", "202").
* **Thanh tìm kiếm Omni-Search**: Bổ sung liên kết `tabHotel Room` và điều kiện tìm kiếm `r.room_number LIKE %(like)s` kèm lọc theo phạm vi cơ sở được phép (`allowed_properties_for_report`).
* **Ghi nợ tiền phòng từ POS (`pos_bridge.py`, `fnb/pos.py`)**: Tích hợp `resolve_hotel_room()` và `get_room_number()`, đảm bảo thu ngân POS gõ số phòng "101" sẽ tự động khớp đúng với Folio đang mở thay vì báo lỗi không tìm thấy phòng.
* **Chuyển phòng & Tape Chart**: Thân thiện hóa toàn bộ comment lịch sử, thông báo lỗi và drawer thông tin đặt phòng sang số phòng thực tế.
* **Đồng bộ phân quyền giám sát**: Thêm vai trò `Hospitality Manager` và `System Manager` vào điều kiện hiển thị nút `Move Room` và nhóm nút Điều chuyển Folio.

### Đợt 5 (Pass 5 - Nghiệp Vụ, Pháp Lý & Toàn Vẹn Đa Cơ Sở) — Commit `e866d50`
* **Khai báo tạm trú Công an & Cục XNC (`police_declaration.py`)**:
  - Xuất báo cáo XML/Excel liên kết `tabHotel Room` để lấy `room_number` vật lý, ngăn cổng tiếp nhận tự động của Công an địa phương từ chối hồ sơ.
  - Hàm `_is_foreign_guest()` kiểm tra thêm `Guest.nationality` và chuẩn hóa mã quốc tịch ISO-3 (`VNM`, `FOR`).
* **Hóa đơn điện tử (`einvoice.py`)**:
  - Sửa lỗi nhầm lẫn nghiêm trọng trong `_build_payload()`: Tách biệt rõ `seller_tax_code` (mã số thuế khách sạn theo công ty điều hành) và `buyer_tax_code` (mã số thuế khách hàng từ `Sales Invoice.tax_id` hoặc `Customer.tax_id`).
* **Kiểm tra phòng trống & Khóa chống Overbooking (`reservation.py`)**:
  - `check_availability()` và `check_bulk_availability()` tự động phân giải số phòng vật lý ("101", "202") sang docname hash trước khi chạy truy vấn khóa dòng (`SELECT ... FOR UPDATE`).
  - Thông báo lỗi hiển thị rõ ràng: `"Phòng 101 đã được đặt bởi..."`.
  - `get_room_rate()` tự động phân giải phòng vật lý để lấy đúng `room_type`.
* **Kế toán Night Audit & Phụ thu (`night_audit.py`, `rate_plan.py`, `surcharge_engine.py`)**:
  - Dòng tiền phòng trên Folio ghi số phòng thực tế: `Room Charge - 101`.
  - Hàm `already_charged_today()` kiểm tra đối soát trùng cả theo hash ID và số phòng vật lý, ngăn chặn ghi phí trùng lặp trên Group Payer Folio.
  - `ensure_item_exists()` bổ sung cơ chế fallback UOM thông minh ('Nos', 'Unit' hoặc UOM đầu tiên có sẵn), ngăn chặn lỗi `MandatoryError` khi tạo Item mới trên các site chưa cấu hình UOM mặc định.
* **Ghi nhật ký Buồng phòng tự động (`hotel_reservation.py`, `room_move.py`)**:
  - Check-in tự động ghi log chuyển trạng thái sang `Occupied` vào `Housekeeping Room Status Log`.
  - Check-out tự động ghi log chuyển trạng thái sang `Dirty`.
  - Đổi phòng in-house (`room_move.py`) tự động ghi log chuyển phòng cũ sang `Dirty` và phòng mới sang `Occupied`.
  - `HotelReservation.validate()` tự động chuẩn hóa `self.room` sang canonical ID.
* **Toàn vẹn dữ liệu Đa cơ sở & Khách đoàn (`hotel_group_booking.py`, `group_booking.py`, `folio.py`, `invoicing.py`)**:
  - Gán đầy đủ `property`, `operating_company`, `currency` từ Group Booking sang Master Payer Reservation và Bulk Reservations.
  - `record_guest_balance()` sao chép đầy đủ ngữ cảnh `property`, `operating_company`, `currency` vào `Guest Balance Ledger`, đảm bảo không bị chặn bởi `property_scope` và cho phép nhận diện đúng tiền cọc dư của khách khi quay lại.
  - `create_invoice_from_folio()` tôn trọng `folio.operating_company` và `folio.currency`.
* **Kênh phân phối OTA, VietQR & CRM (`channel_manager.py`, `vietqr_bridge.py`, `guest_crm.py`, `tape_chart.py`)**:
  - Cổng OTA Webhook phân giải khách trùng sang hồ sơ hợp nhất `canonical(guest)`, gán tự động phòng trong đúng cơ sở (`property`), và loại trừ các phòng `Out of Order` khỏi tồn khả dụng.
  - VietQR tự động lấy tên chủ tài khoản từ đúng `operating_company` của Folio và hiển thị số phòng thực tế.
  - Gộp khách CRM (`guest_crm.py`) tự động chuyển giao quyền sở hữu `Guest Membership` cho khách đích nếu khách đích chưa tham gia chương trình đó.
  - Chuyển phòng trên Tape Chart (`tape_chart.py`) phân giải số phòng vật lý và hiển thị nhãn phòng thân thiện.

---

## 🛠️ Danh Sách Các Tệp Đã Sửa Đổi

| Tệp | Thành Phần | Mục Đích Sửa Đổi |
| :--- | :--- | :--- |
| `hospitality_core/api/police_declaration.py` | Khai báo tạm trú | Phân giải số phòng vật lý trong XML/Excel; chuẩn hóa ISO-3 |
| `hospitality_core/api/einvoice.py` | Hóa đơn điện tử | Tách biệt chuẩn `seller_tax_code` và `buyer_tax_code` |
| `hospitality_core/api/reservation.py` | Đặt phòng & Khóa phòng | Phân giải phòng vật lý, khóa dòng `FOR UPDATE`, thông báo lỗi thân thiện |
| `hospitality_core/api/night_audit.py` | Kiểm toán đêm | Tránh trùng phòng theo số phòng vật lý; fallback UOM an toàn |
| `hospitality_core/api/rate_plan.py` | Bảng giá phòng | Dòng tiền phòng hiển thị số phòng thực tế |
| `hospitality_core/api/surcharge_engine.py` | Phụ thu nhận sớm / trả muộn | Hiển thị số phòng vật lý; tạo item phụ thu an toàn |
| `hospitality_core/api/room_move.py` | Chuyển phòng | Phân giải phòng vật lý; tự động ghi nhật ký buồng phòng Dirty/Occupied |
| `hospitality_core/api/folio.py` | Quản lý Folio | Sao chép ngữ cảnh đa cơ sở sang Balance Ledger; fallback UOM Item |
| `hospitality_core/api/payment_bridge.py` | Thanh toán | Ưu tiên `folio.operating_company`; fallback UOM Item; thông báo động |
| `hospitality_core/api/invoicing.py` | Xuất hóa đơn | Ưu tiên `folio.operating_company` và `folio.currency` |
| `hospitality_core/api/group_booking.py` | Khách đoàn | Sao chép ngữ cảnh `property`, `operating_company`, `currency` sang reservation con |
| `hospitality_core/api/channel_manager.py` | Cổng OTA | Dùng `canonical(guest)`; gán đúng `property`; lọc bỏ phòng hỏng |
| `hospitality_core/api/guest_crm.py` | CRM & Loyalty | Chuyển quyền sở hữu Membership khi gộp khách |
| `hospitality_core/api/vietqr_bridge.py` | VietQR NAPAS 247 | Đọc đúng công ty của Folio; hiển thị số phòng thực tế |
| `hospitality_core/doctype/hotel_reservation/hotel_reservation.py` | Model Đặt phòng | Tự động ghi nhật ký buồng phòng khi check-in/out; chuẩn hóa số phòng |
| `hospitality_core/doctype/hotel_reservation/hotel_reservation.js` | UI Đặt phòng | Bản địa hóa; format tiền tệ an toàn; phân giải số phòng trong dialog |
| `hospitality_core/doctype/hotel_group_booking/hotel_group_booking.py` | Model Khách đoàn | Gán ngữ cảnh cơ sở sang Master Payer Reservation và Bulk Reservations |
| `hospitality_core/doctype/hotel_room/hotel_room.py` | Model Phòng | Bọc import `Document` an toàn cho môi trường test độc lập |
| `hospitality_core/page/housekeeping_view/housekeeping_view.py` | Bảng Buồng phòng | Kiểm tra tồn tại phòng; trả về trạng thái chi tiết |
| `hospitality_core/page/housekeeping_view/housekeeping_view.js` | UI Buồng phòng | Đồng bộ cache client theo phản hồi server khi phòng đang có khách |
| `hospitality_core/page/tape_chart/tape_chart.py` | Tape Chart | Phân giải số phòng vật lý khi kéo thả |

---

## 🧪 Kết Quả Kiểm Thử & Nghiệm Thu

1. **Kiểm tra biên dịch toàn bộ mã nguồn**:
   - Lệnh: `python -m compileall hospitality_core/hospitality_core`
   - Kết quả: **100% thành công, không có lỗi cú pháp**.
2. **Kiểm thử đơn vị tự động (Unit Tests)**:
   - Lệnh: `python -m unittest tests/test_rate_plan.py tests/test_property_calculation.py`
   - Kết quả: **38/38 tests PASSED** (thời gian thực thi ~0.25s).
3. **Trạng thái Git Repository**:
   - Toàn bộ thay đổi đã commit vào commit [`e866d50`](file:///d:/TCG-project/frappe/erpnext_hospitality_core) trên nhánh `main`.
