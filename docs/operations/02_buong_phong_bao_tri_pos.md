# SOP Buồng Phòng, Bảo Trì & Thu Ngân F&B/POS

> Dành cho: Nhân viên Buồng phòng, Giám sát Buồng phòng, Kỹ thuật/Bảo trì,
> Thu ngân Nhà hàng/Quầy bar/POS. Đọc
> [`00_tong_quan_he_thong.md`](00_tong_quan_he_thong.md) trước nếu chưa quen hệ thống.

## Mục lục
1. [Bảng Điều Phối Buồng Phòng (máy tính, dành cho Giám sát)](#1-bảng-điều-phối-buồng-phòng)
2. [Buồng Di Động (điện thoại/PWA, dành cho nhân viên dọn phòng)](#2-buồng-di-động-pwa)
3. [Báo hỏng / Yêu cầu bảo trì](#3-báo-hỏng--yêu-cầu-bảo-trì)
4. [Ghi phí Minibar](#4-ghi-phí-minibar)
5. [Đồ thất lạc (Lost & Found)](#5-đồ-thất-lạc-lost--found)
6. [Bán hàng tại quầy POS (F&B)](#6-bán-hàng-tại-quầy-pos-fb)
7. [Quy tắc hình thức thanh toán tại POS](#7-quy-tắc-hình-thức-thanh-toán-tại-pos)
8. [Ghi nợ về phòng khách (Guest Account)](#8-ghi-nợ-về-phòng-khách-guest-account)

---

## 1. Bảng Điều Phối Buồng Phòng

Mở trang **"Bảng Điều Phối Buồng Phòng (Housekeeping Board)"** — dùng cho
Giám sát buồng phòng theo dõi TOÀN BỘ khách sạn trên 1 màn hình.

### Trạng thái phòng & màu sắc
| Trạng thái | Nhãn hiển thị | Màu |
|---|---|---|
| `Available` | Sạch | Xanh lá |
| `Dirty` | Cần dọn | Đỏ |
| `Cleaning` | Đang dọn | Vàng |
| `Inspected` | Đã KT | Xanh cyan |
| `Occupied` | Đang ở | Tím/Indigo |
| `Out of Order` | Khóa/Sửa | Xám |

### Nút thao tác từng phòng (1 chạm, tự chuyển đúng bước tiếp theo)
| Trạng thái hiện tại | Nút | Chuyển sang |
|---|---|---|
| Cần dọn | **Bắt Đầu Dọn** | Đang dọn |
| Đang dọn | **Dọn Xong** | Đã KT |
| Đã KT | **Duyệt Sạch** | Sạch |
| Sạch | **Báo Bẩn** | Cần dọn |
| Đang ở | **Yêu Cầu Dọn** | Cần dọn |
| Khóa/Sửa | *(Đang Khóa — không thao tác trực tiếp, xem mục 3)* | — |

### Thao tác hàng loạt
Chọn nhiều phòng (tick chọn từng ô, hoặc **"Chọn Phòng Bẩn"** để chọn hết
phòng đang Cần dọn, **"Tất Cả"** để chọn hết phòng đang hiển thị) → thanh
thao tác nổi hiện ra với 3 lựa chọn: **Đánh Dấu Sạch**, **Đã Kiểm Tra**, **Cần
Dọn**, hoặc **Bỏ chọn**. Hệ thống luôn hỏi xác nhận trước khi áp dụng hàng
loạt.

> **An toàn tự động**: nếu cố đánh dấu 1 phòng "Sạch"/"Đã KT" trong khi khách
> VẪN ĐANG check-in tại phòng đó, hệ thống TỰ ĐỘNG giữ nguyên trạng thái
> "Đang ở" — không cho vô tình biến phòng có khách thành phòng trống bán được.

## 2. Buồng Di Động (PWA)

Truy cập qua điện thoại/máy tính bảng — dùng cho nhân viên dọn phòng trực
tiếp tại hiện trường. Các trạng thái có thể chọn: **Cần dọn → Đang dọn → Đã
KT → Sạch** (không có tùy chọn "Đang ở" trên bản di động — trạng thái đó chỉ
do hệ thống tự gán khi khách check-in). Có thể nhập số phòng trực tiếp (không
cần quét mã).

Cùng cơ chế an toàn như bản máy tính: không thể vô tình đánh dấu "Sạch" một
phòng đang có khách.

## 3. Báo hỏng / Yêu cầu bảo trì

Từ Buồng Di Động (hoặc form `Hotel Maintenance Request` trên máy tính), điền:

| Trường | Ghi chú |
|---|---|
| `Phòng` | Bắt buộc |
| `Loại Sự Cố` (issue_type) | Chọn 1: **Plumbing** (nước), **Electrical** (điện), **HVAC** (điều hòa), **Furniture** (nội thất), **Cleaning** (vệ sinh), **Other** (khác) |
| `Mô Tả Sự Cố` | Bắt buộc, mô tả càng chi tiết càng giúp kỹ thuật xử lý nhanh |
| `Ảnh` | Tùy chọn, đính kèm ảnh hiện trạng |

Sau khi tạo, hệ thống **tự động chuyển phòng sang "Khóa/Sửa" (Out of
Order)** — trừ khi phòng đang có khách "Đang ở" (không bao giờ ghi đè phòng
có khách).

### Xử lý của Kỹ thuật/Bảo trì
Mở đúng yêu cầu, cập nhật `Trạng Thái`: **Reported** (Đã báo) → **In
Progress** (Đang xử lý) → **Completed** (Hoàn tất) hoặc **Cancelled** (Hủy).
- **Bắt buộc điền `Resolution Notes`** (ghi chú xử lý) trước khi chuyển sang
  Completed — hệ thống chặn nếu bỏ trống.
- Khi chuyển sang **Completed** hoặc **Cancelled**: nếu không còn yêu cầu bảo
  trì nào khác đang mở cho phòng đó, hệ thống tự giải phóng phòng về trạng
  thái **Cần dọn** (Buồng phòng dọn lại trước khi bán tiếp).
- Nút **"Log Expense"** trên form: ghi nhận chi phí sửa chữa thật (linh
  kiện/nhân công) vào `Hospitality Expense` liên kết với đúng yêu cầu này.

## 4. Ghi phí Minibar

Từ Buồng Di Động, chọn phòng → nhập danh sách món đã dùng (tên món, số
lượng, thành tiền) → hệ thống tự ghi vào Folio của khách đang lưu trú tại
phòng đó.

**Điều kiện bắt buộc**: phòng phải đang có khách `Checked In` VÀ Folio đang ở
trạng thái Mở — nếu không, hệ thống báo rõ "Không tìm thấy đặt phòng đang lưu
trú có Folio mở cho Phòng {số phòng}" thay vì ghi nhầm.

## 5. Đồ thất lạc (Lost & Found)

Khi nhặt được đồ khách bỏ quên, tạo bản ghi mới với: `Tên Đồ Vật`, `Vị Trí
Tìm Thấy`, `Người Tìm Thấy` (mặc định là chính người đang đăng nhập).

Tra cứu lại sau này qua báo cáo **"Lost and Found Register"** — lọc theo
khoảng ngày tìm thấy (mặc định 90 ngày gần nhất) và trạng thái: **Found**
(còn giữ) / **Claimed** (đã trả khách) / **Disposed** (đã thanh lý/hủy).

## 6. Bán hàng tại quầy POS (F&B)

Quy trình bán 1 món/đơn hàng qua hệ thống ticket:

1. **Gửi phiếu** (Send Ticket) — chỉ gửi được khi phiếu còn ở trạng thái
   nháp; hệ thống tự kiểm tra tồn kho nguyên liệu trước khi gửi xuống bếp.
2. Bếp/quầy xử lý theo 3 thao tác:
   - **Prepare** (Chuẩn bị) — trừ nguyên liệu/tồn kho.
   - **Serve** (Phục vụ) — đánh dấu đã phục vụ số lượng tương ứng.
   - **Cancel** (Hủy) — chỉ hủy được phần CHƯA chuẩn bị; phần đã chuẩn bị rồi
     phải xử lý qua quy trình hao hụt (Waste), không dùng Cancel.

Mỗi thao tác đều có mã yêu cầu riêng chống bấm trùng (bấm 2 lần liên tiếp do
mạng chậm sẽ không bị trừ kho/tính tiền 2 lần).

## 7. Quy tắc hình thức thanh toán tại POS

Hệ thống ép buộc đúng 1 trong 3 tình huống sau (kiểm tra CẢ ở màn hình lẫn ở
server, không thể lách qua giao diện):

| Tình huống | Hình thức thanh toán bắt buộc |
|---|---|
| Hóa đơn có gắn **Số Phòng** | CHỈ được thanh toán qua **`Guest Account`** (ghi nợ về phòng) |
| Khách hàng là Công ty/Đại lý/Đoàn, KHÔNG gắn phòng | CHỈ được thanh toán qua **`Complimentary`** |
| Khách vãng lai (`Walk in Customer`), KHÔNG gắn phòng | KHÔNG được dùng `Guest Account` lẫn `Complimentary` — phải trả tiền mặt/thẻ/chuyển khoản thật |

Nếu chọn sai, hệ thống báo lỗi rõ ràng ngay khi Submit hóa đơn — không cho
lách qua.

## 8. Ghi nợ về phòng khách (Guest Account)

Khi khách dùng dịch vụ nhà hàng/bar và muốn ghi nợ về phòng:

1. Chọn hình thức thanh toán **`Guest Account`** trên POS Invoice.
2. Nếu hóa đơn CHƯA gắn sẵn số phòng, hệ thống cố tự tìm đúng 1 Folio đang mở
   theo tên khách/công ty — nếu tìm thấy nhiều hơn 1 hoặc không thấy, thu
   ngân phải TỰ CHỌN đúng số phòng.
3. Hệ thống tự tìm Folio đang mở của phòng đó — nếu phòng chưa có Folio mở
   (VD khách đã trả phòng), hệ thống báo lỗi "No open Folio found for Room
   {phòng}" — không ghi nợ được, cần thu ngân đổi hình thức thanh toán khác.
4. Một số phòng/đặt phòng bị khóa "không cho ghi nợ POS" (`allow_pos_posting`
   = tắt) — nếu gặp thông báo lỗi này, liên hệ Lễ tân/Quản lý xử lý.
5. Sau khi ghi nợ thành công, hệ thống hiện thông báo số món + tên Folio đã
   ghi ("Posted {n} items from POS to Folio {folio}").

**Hủy hóa đơn đã ghi nợ**: nếu cần hủy 1 POS Invoice đã ghi nợ về phòng, hệ
thống TỰ ĐỘNG xóa đúng phần đã ghi trên Folio và tính lại số dư — không cần
thao tác thủ công thêm trên Folio.
