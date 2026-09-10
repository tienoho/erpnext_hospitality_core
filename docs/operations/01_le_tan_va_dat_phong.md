# SOP Lễ Tân & Đặt Phòng

> Dành cho: Lễ tân, Giám sát Lễ tân (`Frontdesk Supervisor`). Đọc
> [`00_tong_quan_he_thong.md`](00_tong_quan_he_thong.md) trước nếu chưa quen hệ thống.

## Mục lục
1. [Front Desk Console — màn hình làm việc chính](#1-front-desk-console)
2. [Tape Chart — sơ đồ buồng phòng trực quan](#2-tape-chart)
3. [Tạo đặt phòng mới](#3-tạo-đặt-phòng-mới)
4. [Check-in](#4-check-in)
5. [Check-out](#5-check-out)
6. [Hủy đặt phòng](#6-hủy-đặt-phòng)
7. [Chuyển phòng (Move Room)](#7-chuyển-phòng-move-room)
8. [Đặt đoàn (Group Booking)](#8-đặt-đoàn-group-booking)
9. [Phụ thu sớm/muộn (Surcharge)](#9-phụ-thu-sớmmuộn-surcharge)
10. [Quét CCCD/Hộ chiếu tạo khách nhanh](#10-quét-cccdhộ-chiếu-tạo-khách-nhanh)
11. [Xuất khai báo tạm trú công an (nhanh, từ Front Desk)](#11-xuất-khai-báo-tạm-trú-công-an)
12. [Khách trong danh sách đen (Blacklist)](#12-khách-trong-danh-sách-đen-blacklist)

---

## 1. Front Desk Console

Đây là màn hình mặc định khi bắt đầu ca — mở qua ô tìm kiếm Frappe gõ "Front
Desk Console" hoặc từ trang Hospitality.

### 4 thẻ KPI (bấm vào để lọc danh sách)
| Thẻ | Ý nghĩa |
|---|---|
| **Khách Sắp Đến** | Số đặt phòng `Reserved` cần check-in hôm nay |
| **Khách Sắp Đi** | Số đặt phòng `Checked In` cần check-out hôm nay |
| **Đang Lưu Trú** | Số khách đang ở + % công suất phòng (bấm mở báo cáo "House List") |
| **Phòng Khả Dụng** | Số phòng trống (bấm mở công cụ Tra Cứu Phòng Trống) |

Bấm **"Đặt Lại Bộ Lọc"** để bỏ lọc đang áp dụng.

### Ô Tìm Kiếm Thông Minh (Omni-Search)
Gõ **tên khách, số điện thoại, số phòng, số CCCD/Hộ chiếu, hoặc mã đặt phòng
OTA** — hệ thống tự tìm và gợi ý ngay khi gõ (không cần Enter). Phím tắt:
- `/` — focus vào ô tìm kiếm
- Mũi tên lên/xuống — di chuyển giữa kết quả
- `Enter` — mở đặt phòng đang chọn
- `Esc` — đóng danh sách kết quả

### Các lối tắt (Quick Actions)
Sơ Đồ Buồng (Tape Chart) · Tra Cứu Phòng · Buồng Phòng · Đặt Phòng · Khách
Lưu Trú (House List) · Bảo Trì Phòng · Hồ Sơ Khách 360 · Buồng Di Động.

### Công cụ nhanh khác trên Console
- **⚡ Tạo VietQR Nhanh**: chọn 1 Guest Folio đang mở → tự điền số dư còn nợ +
  số phòng → sinh mã VietQR (chuẩn NAPAS 247) để khách quét chuyển khoản, kèm
  số tài khoản/nội dung chuyển khoản có thể copy.
- **Quét CCCD / Passport**: xem [mục 10](#10-quét-cccdhộ-chiếu-tạo-khách-nhanh).
- **Tách Bill**: tách 1 giao dịch trên folio ra thành nhiều dòng (VD chia hóa
  đơn cho nhóm bạn ở chung phòng).
- **Gộp Folio**: gộp toàn bộ giao dịch từ 1 folio đang mở sang folio khác rồi
  đóng folio nguồn — dùng khi tạo nhầm 2 folio cho cùng 1 khách/đoàn.
- **Menu xuất Excel/CSV khai báo XNC** — xem [mục 11](#11-xuất-khai-báo-tạm-trú-công-an).

---

## 2. Tape Chart

Sơ đồ trực quan: **hàng = phòng** (theo tầng/loại phòng), **cột = ngày**.

### Điều hướng
`◀ Tuần Trước` / `Hôm Nay` / `Tuần Sau ▶`, chọn khoảng xem `7/14/30 Ngày`, lọc
theo Tầng/Loại Phòng. Phím tắt: mũi tên trái/phải = lùi/tiến 7 ngày, `Esc`
đóng ô chi tiết đang mở.

### Kéo-thả đổi phòng (Drag & Drop)
- Kéo khối đặt phòng sang 1 phòng khác → hộp thoại xác nhận "Chuyển đặt phòng
  {...} sang Phòng {...}?".
- Nếu khách CHƯA check-in (`Reserved`): chỉ đổi phòng dự kiến, không tính
  phí gì thêm.
- Nếu khách ĐÃ check-in (`Checked In`): hệ thống chạy đúng luồng **Chuyển
  phòng thật** (xem [mục 7](#7-chuyển-phòng-move-room)) — không dùng kéo-thả
  cho trường hợp này để bỏ qua các bước xác nhận, hãy dùng nút "Chuyển Phòng"
  trên form đặt phòng.
- Thả vào phòng đang Khóa/Sửa (Out of Order) → viền ĐỎ, không cho thả.

### Ô chi tiết nhanh (Quick Drawer)
Bấm vào 1 khối đặt phòng → hiện tên/SĐT khách, trạng thái, số dư folio, nguồn
đặt (OTA/Trực tiếp/Công ty/Đoàn), mã đặt phòng OTA nếu có. Có 2 nút: **"Mở Đặt
Phòng Chi Tiết"** và (nếu đã có folio) **"Mở Folio Thanh Toán"**.

### Tạo đặt phòng nhanh từ ô trống
Bấm vào 1 ô còn trống → dialog "Tạo Đặt Phòng Nhanh - Phòng {số phòng}": chọn
**Khách Hàng** + **Gói Giá (Rate Plan)** → **"Mở Form Chi Tiết"** để hoàn tất
các thông tin còn lại.

### Chú giải màu
Nguồn đặt: OTA (xanh dương), Đoàn/Group (cam), Công ty/Corporate (xanh lá),
Complimentary (tím), Trực tiếp (xám). Trạng thái buồng phòng: Sạch/Bẩn/Đang
dọn/Đã KT/Đang ở/Khóa.

---

## 3. Tạo đặt phòng mới

Mở `Hotel Reservation` mới (từ Tape Chart, Front Desk Console, hoặc menu Đặt
Phòng), điền các trường bắt buộc:

| Trường | Ghi chú |
|---|---|
| `Guest` | Khách hàng — tìm theo tên/SĐT, hoặc tạo mới |
| `Room Type` / `Room` | Loại phòng / số phòng cụ thể |
| `Ngày Đến` / `Ngày Đi` (`arrival_date`/`departure_date`) | Ngày đi phải SAU ngày đến |
| `Rate Plan` | Gói giá áp dụng |

Các trường tùy chọn quan trọng: `Số Trẻ Em` (tối đa 15), `Số Giường Phụ` (tối
đa 4), `Loại Giấy Tờ`/`Số Hộ Chiếu` (nếu khách nước ngoài — `is_alien`),
`Complimentary` (miễn phí), giảm giá (`discount_type`: Số tiền/%), **`Khách
Công Ty`**+chọn Công ty hoặc **`Khách Đoàn`**+chọn Group Booking (nếu áp
dụng), **Nguồn Đặt Phòng** (`booking_source`: Trực tiếp/OTA/Công ty/Đoàn/
Complimentary) + kênh OTA cụ thể nếu có.

---

## 4. Check-in

Trên form đặt phòng đang ở trạng thái `Reserved`, bấm nút **"Check In"**.

- Hệ thống tự kiểm tra khách đến SỚM hơn giờ chuẩn không (mặc định 14:00 —
  xem [mục 9](#9-phụ-thu-sớmmuộn-surcharge)). Nếu có, hiện hộp thoại **"⏰
  Phát Hiện Nhận Phòng Sớm (Early Check-in)"** — chọn:
  - **"✔ Áp Dụng Phụ Thu & Check In"** — thu phụ thu theo đúng bậc, hoặc
  - **"Miễn Phụ Thu & Check In"** — phải chọn 1 lý do miễn: VIP/Thân thiết,
    BGĐ phê duyệt, Lỗi buồng phòng, Theo hợp đồng đại lý, Khác.
- Nếu không phụ thu, hệ thống check-in ngay: chuyển phòng sang **Đang ở**, mở
  Folio, tự tính tiền phòng đêm đầu tiên.
- **Không thể check-in TRƯỚC ngày đến đã đặt** — hệ thống sẽ chặn.

## 5. Check-out

Trên form đặt phòng `Checked In`, bấm **"Check Out"**.

- **Chỉ check-out được ĐÚNG NGÀY `Ngày Đi` đã đặt** — nếu khách muốn ở thêm,
  phải sửa `Ngày Đi` trước (hoặc dùng Đêm Kiểm Toán tự gia hạn nếu quên).
- Tương tự check-in, hệ thống kiểm tra trả phòng MUỘN hơn giờ chuẩn (mặc định
  12:00) và hiện hộp thoại phụ thu tương ứng nếu có.
- **Hệ thống CHẶN check-out nếu còn nợ**:
  - Khách thường: còn dư nợ (`outstanding_balance` > 0) trên Folio cá nhân.
  - Khách Công ty/Đoàn: dư nợ đã tự chuyển sang City Ledger/Master Folio đoàn
    — nhưng nếu Master Folio đoàn còn dư nợ, hệ thống VẪN chặn check-out của
    từng khách trong đoàn cho tới khi xử lý xong công nợ đoàn.
  - Xử lý: thu đủ tiền (xem [mục Guest Folio](03_ke_toan_dem_kiem_toan_bao_cao.md#1-guest-folio)) rồi thử lại.
- Sau khi check-out thành công: phòng chuyển sang **Bẩn** (chờ buồng phòng
  dọn), Folio đóng lại.

## 6. Hủy đặt phòng

Chỉ áp dụng cho đặt phòng đang `Reserved` hoặc `Checked In`. Nút **"Cancel
Reservation"** chỉ hiện với vai trò `Frontdesk Supervisor`/`Hospitality
Manager`/`System Manager`. Hệ thống sẽ hỏi xác nhận, sau đó tự hủy/hoàn tiền
cọc (nếu có) vào sổ tín dụng của khách.

## 7. Chuyển phòng (Move Room)

Chỉ dùng khi khách ĐÃ check-in. Trên form đặt phòng, nút **"Chuyển Phòng"**
(vai trò Giám sát trở lên) mở dialog:

| Trường | Ghi chú |
|---|---|
| `Phòng Mới` | Không được chọn lại phòng hiện tại |
| `Hạng phòng mới` | Tự động điền, chỉ đọc |
| `Bảng giá sau chuyển phòng` | Tùy chọn — nếu bỏ trống, giá sẽ RƠI VỀ GIÁ MẶC ĐỊNH của hạng phòng mới (mất mọi ưu đãi/giá đặc biệt đang áp dụng) — hệ thống sẽ CẢNH BÁO rõ nếu việc này làm khách mất ưu đãi giảm giá theo số đêm (LOS) đang có |

Bấm **"Chuyển Phòng"** để hoàn tất — phòng cũ tự chuyển sang **Bẩn**, phòng
mới sang **Đang ở**.

## 8. Đặt đoàn (Group Booking)

Mở `Hotel Group Booking`, chọn **Người Đại Diện Thanh Toán** (`master_payer`)
rồi chuyển trạng thái sang `Confirmed` — hệ thống tự tạo 1 "phòng ảo" neo
Master Folio của đoàn (**cần IT/Quản lý đã cấu hình sẵn 1 Hạng Phòng "Virtual"
+ 1 phòng thuộc hạng đó** — nếu chưa có, tính năng đoàn sẽ báo lỗi, liên hệ
Quản lý).

Các nút chính trên form:
- **🎁 Kiểm Tra Phòng FOC** — áp dụng phòng miễn phí theo chính sách đoàn.
- **Bulk Reserve** — đặt hàng loạt phòng (chọn khách + hạng phòng + giảm giá +
  tick chọn phòng).
- **Check In Group** / **Check Out Group** — check-in/out HÀNG LOẠT cho mọi
  khách `Reserved`/`Checked In` trong đoàn cùng lúc.
  > Nếu công ty/đại lý đứng sau đoàn đang ở mức tín dụng **ĐỎ** (xem [City
  > Ledger](03_ke_toan_dem_kiem_toan_bao_cao.md#2-city-ledger)), hệ thống sẽ
  > CHẶN "Check In Group" — báo Quản lý xử lý công nợ trước.
- **Đặt cọc đoàn** (`deposit_status`): theo dõi Chưa yêu cầu/Chờ/Đã thu/Miễn —
  việc GHI NHẬN tiền cọc thật (tạo Payment Entry) do Kế toán thực hiện, xem
  [tài liệu Kế toán](03_ke_toan_dem_kiem_toan_bao_cao.md).

## 9. Phụ thu sớm/muộn (Surcharge)

Cấu hình tại `Hospitality Surcharge Settings` (IT/Quản lý thiết lập). Mặc
định: giờ chuẩn nhận phòng **14:00**, trả phòng **12:00**.

| Nhận phòng sớm | Phụ thu |
|---|---|
| Trước 06:00 | 100% giá phòng |
| 06:00 – 09:00 | 50% giá phòng |
| 09:00 – 14:00 | 30% giá phòng |

| Trả phòng muộn | Phụ thu |
|---|---|
| 12:00 – 15:00 | 30% giá phòng |
| 15:00 – 18:00 | 50% giá phòng |
| Sau 18:00 | 100% giá phòng |

Phụ thu được hệ thống TỰ PHÁT HIỆN khi bấm Check-in/Check-out — lễ tân không
cần tự tính tay.

## 10. Quét CCCD/Hộ chiếu tạo khách nhanh

Nút **"Quét CCCD / Passport"** trên Front Desk Console → dán văn bản OCR hoặc
2 dòng MRZ hộ chiếu vào ô → bấm **"Parse"** để xem trước (Họ tên, Số giấy tờ,
Ngày sinh, Quốc tịch) → bấm **"Create Guest"** để tạo hồ sơ Guest tự động.

Hỗ trợ: hộ chiếu (MRZ 2 dòng, bắt đầu `P<`), CCCD quét mã QR (12 số), hoặc
CCCD dán văn bản OCR thô (nhận diện nhãn "Họ và tên"/"Ngày sinh"/"Giới
tính"/"Nơi thường trú"). Với hộ chiếu nước ngoài, hệ thống tự tách đúng
Họ/Tên theo chuẩn quốc tế (ICAO 9303), không đoán theo quy ước Việt Nam.

## 11. Xuất khai báo tạm trú công an

Từ menu trên Front Desk Console (chọn ngày rồi xuất):
- **Xuất Excel/CSV Khai Báo XNC** — danh sách đầy đủ khách đang lưu trú.
- **Xuất Excel Khai Báo Tạm Trú Toàn Đoàn** — dành riêng cho đoàn.

**Trước khi dùng lần đầu**, IT/Quản lý phải điền đủ `Hospitality Police
Settings` (Mã số thuế, Địa chỉ, Tên/Tỉnh-Thành đơn vị công an quản lý, Mã cơ
sở lưu trú) — thiếu 1 trong các trường này, hệ thống sẽ báo lỗi rõ ràng thay
vì xuất file rỗng/sai. Chi tiết đầy đủ các định dạng xuất (bao gồm định dạng
riêng cho Cổng Quảng Ninh) xem [tài liệu Kế toán](03_ke_toan_dem_kiem_toan_bao_cao.md#7-khai-báo-tạm-trú-công-an).

## 12. Khách trong danh sách đen (Blacklist)

Nếu khách được đánh dấu `Blacklisted` (do Quản lý cấu hình trên hồ sơ Guest),
hệ thống CHẶN việc lưu đặt phòng cho khách này — hiện cảnh báo đỏ **"⚠ Khách
Trong Danh Sách Đen (Blacklisted) — Cần Supervisor Phê Duyệt & Ghi Lý Do"**.

Chỉ `Frontdesk Supervisor`/`Hospitality Manager`/`System Manager` mới ghi đè
được, bắt buộc điền **Lý do phê duyệt** (tối thiểu 10 ký tự) — lý do này được
lưu vĩnh viễn vào lịch sử đặt phòng.
