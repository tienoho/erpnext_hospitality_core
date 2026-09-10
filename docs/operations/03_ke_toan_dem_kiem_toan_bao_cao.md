# SOP Kế Toán, Đêm Kiểm Toán & Báo Cáo Quản Lý

> Dành cho: Kế toán, Kiểm toán viên đêm, Quản lý/Điều hành. Đọc
> [`00_tong_quan_he_thong.md`](00_tong_quan_he_thong.md) trước nếu chưa quen hệ thống.

## Mục lục
1. [Guest Folio — sổ công nợ của khách](#1-guest-folio)
2. [City Ledger — công nợ công ty/đại lý](#2-city-ledger)
3. [Đêm Kiểm Toán (Night Audit)](#3-đêm-kiểm-toán-night-audit)
4. [Hóa đơn điện tử (HĐĐT)](#4-hóa-đơn-điện-tử-hđđt)
5. [Danh mục báo cáo đóng ca/tháng](#5-danh-mục-báo-cáo-đóng-catháng)
6. [Duyệt chi phí (Hospitality Expense)](#6-duyệt-chi-phí-hospitality-expense)
7. [Khai báo tạm trú công an](#7-khai-báo-tạm-trú-công-an)

---

## 1. Guest Folio

Folio là sổ công nợ của 1 lượt lưu trú (hoặc 1 tài khoản Công ty/Đoàn dùng
chung — gọi là **Master Folio**). Vòng đời trạng thái:

```
Provisional → Open → Closed
                  ↘ Cancelled
```

**Không đóng được Folio nếu còn dư nợ** (`outstanding_balance` > 0) — với
khách Công ty/Đoàn, chỉ phần khách TỰ CHI TRẢ (`bill_to = Guest`) cần về 0,
phần Công ty/Đoàn chịu đã được tự động chuyển sang City Ledger/Master Folio.

### Các nút thao tác trên form Guest Folio

**Nhóm "Thanh Toán"**:
- **Ghi Nhận Thanh Toán** — dialog hiện sẵn tên khách/phòng/số dư còn nợ, chỉ
  cần nhập Số Tiền + Hình Thức Thanh Toán + Quầy Lễ Tân → **Submit Payment**.
- **Hoàn Tiền Cho Khách** — hoàn lại tiền đã thu thừa/đặt cọc dư.
- **Thanh Toán Cho Công Ty** — chỉ dùng trên Master Folio Công ty/Đoàn, chỉ
  khi Folio đang Mở.
- **Ghi Nhận Giao Dịch Ghi Nợ** — ghi nợ thủ công trực tiếp (chỉ trên Master
  Folio Công ty).

**Nhóm "Hóa Đơn"**: Tạo Hóa Đơn Bán Hàng (Invoice) · Phát Hành HĐĐT (NĐ 123).

**Nhóm "Điều Chuyển"**: 🔀 Tách Bill Đoàn Tour · Chuyển Giao Dịch (Move Bill)
· Tách Giao Dịch (Split Amount).

> Mỗi lần ghi nhận thanh toán/hoàn tiền, hệ thống tạo 1 chứng từ Payment Entry
> THẬT (không chỉ ghi chú) — số dư Folio tự cập nhật ngay sau khi Submit.

### Tách/Gộp giao dịch (`api/folio_operations.py`)
- **Tách giao dịch** (Split): tách 1 dòng phí chung thành nhiều dòng, có thể
  chuyển sang Folio khác — chỉ vai trò `Frontdesk Supervisor`/`Hospitality
  Manager`/`System Manager`. Riêng các dòng phí PHÒNG (đã qua engine tính giá
  rate plan) KHÔNG tách bằng chức năng này — dùng "Void Pricing Charge" thay
  thế (liên hệ Quản lý nếu cần).
- **Gộp Folio** (Merge): chuyển toàn bộ giao dịch từ 1 Folio nguồn (đang Mở)
  sang Folio đích (đang Mở) rồi đóng Folio nguồn — dùng khi lỡ tạo trùng 2
  Folio cho cùng 1 khách.

## 2. City Ledger

Áp dụng cho khách đặt qua Công ty/Đại lý du lịch có hạn mức tín dụng
(`credit_limit`). Hệ thống tự tính mức độ rủi ro:

| Mức | Điều kiện | Ý nghĩa |
|---|---|---|
| 🟢 **XANH (GREEN)** | Dùng ≤ 80% hạn mức | An toàn |
| 🟡 **VÀNG (YELLOW)** | Dùng 80–100% hạn mức | Cảnh báo, cần theo dõi |
| 🔴 **ĐỎ (RED)** | Vượt 100% hạn mức | **Vượt trần tín dụng — hệ thống KHÓA việc nhận đặt phòng/check-in đoàn mới của công ty này** cho tới khi thu bớt công nợ |

Nếu công ty chưa cấu hình hạn mức tín dụng, hệ thống mặc định coi là XANH.

### Báo cáo tuổi nợ (AR Aging Summary)
Tính tuổi nợ theo số ngày kể từ ngày MỞ Folio Công ty/Đoàn (không phải theo
từng hóa đơn rời — vì đây là mô hình số dư liên tục), chia 4 bậc: **0-30
Ngày**, **31-60 Ngày**, **61-90 Ngày**, **Trên 90 Ngày**, cộng dòng Tổng Nợ.
Dùng để nhắc thu hồi công nợ định kỳ hàng tuần/tháng.

## 3. Đêm Kiểm Toán (Night Audit)

Chạy tự động (theo lịch, khoảng 14:00 mỗi ngày) hoặc chạy tay khi cần. Mỗi
lần chạy thực hiện đúng 5 bước, theo thứ tự:

1. **Hủy no-show**: đặt phòng còn `Reserved` mà đã quá `Ngày Đến` → tự hủy,
   hoàn cọc đúng số tiền vào sổ tín dụng khách (nếu có đặt cọc trước).
2. **Xử lý ở quá hạn (overstay)**: khách `Checked In` mà `Ngày Đi` đã tới/qua
   → tự gia hạn thêm 1 ngày (ghi rõ lý do trong lịch sử đặt phòng).
3. **Tính tiền phòng**: tự tính tiền đêm cho mọi phòng đang có khách — tự
   động BỎ QUA phòng đã tính tiền hôm đó rồi (không tính trùng).
4. **Đối chiếu**: so khớp trạng thái Phòng ↔ Đặt phòng ↔ Folio — phát hiện
   (không tự sửa) các trường hợp lệch, VD phòng "Đang ở" mà không có đặt
   phòng `Checked In` tương ứng.
5. **Ghi log**: tạo 1 bản ghi **Night Audit Log** — đây là bằng chứng kiểm
   toán, không thể sửa/xóa.

### Việc cần làm mỗi sáng: kiểm tra Night Audit Log
Mở bản ghi Night Audit Log mới nhất, kiểm tra các trường:

| Trường | Cần chú ý khi nào |
|---|---|
| `Số No-Show Đã Hủy` | Đối chiếu với thực tế lễ tân báo cáo trong ca |
| `Số Phòng Overstay` | Xác nhận đã liên hệ khách gia hạn/thu thêm tiền |
| `Số Phòng Đã Tính Tiền` | Đối chiếu số phòng đang ở thực tế |
| `Số Lệch Đối Chiếu Room/Reservation/Folio` + chi tiết | **> 0 nghĩa là có bất thường cần xử lý thủ công ngay** — đọc chi tiết đi kèm để biết chính xác phòng/đặt phòng nào |
| `Số Lỗi Xảy Ra` + chi tiết | > 0 nghĩa là 1 phần của quy trình audit gặp lỗi kỹ thuật — báo IT |

## 4. Hóa đơn điện tử (HĐĐT)

### Luồng phát hành thủ công (đang dùng hiện tại)
Trên Sales Invoice đã Nộp (Submit) → menu **HĐĐT** → **"Phát hành Hóa đơn
Điện tử"** → xác nhận → hệ thống trả về Số Hóa Đơn, Mã Tra Cứu, Mã CQT. Thanh
chỉ báo màu **xanh lá** = hóa đơn thật đã phát hành; màu **cam** kèm cảnh báo
"⚠️ HĐĐT THỬ NGHIỆM (Sandbox...)" = đang ở môi trường thử nghiệm.

> **Lưu ý hiện trạng quan trọng**: app hóa đơn điện tử chuyên dụng
> (`vietnam_einvoice`, hỗ trợ đầy đủ MISA/Viettel/VNPT) hiện **CHƯA được cài
> đặt trên site vận hành thật** — hệ thống đang dùng bộ phát hành **Mock**
> (giả lập) của chính `hospitality_core`, nghĩa là số hóa đơn/mã tra cứu hiện
> tại là **GIẢ**, CHƯA thật sự gửi lên Cơ quan Thuế. Không dùng số hóa đơn từ
> hệ thống hiện tại làm căn cứ pháp lý thật cho tới khi IT xác nhận đã cài đặt
> và cấu hình xong nhà cung cấp HĐĐT thật (MISA/Viettel/VNPT).

### 2 cờ tự động (khi đã có nhà cung cấp thật, dành cho Kế toán trưởng cấu hình)
- **`auto_issue_on_submit`**: tự phát hành HĐĐT ngay khi Nộp Sales Invoice
  thường — mặc định TẮT. **Lưu ý**: bật cờ này thì sẽ không còn hóa đơn "đã
  Nộp nhưng chưa phát hành" nào để làm căn cứ lập Hóa Đơn Điều Chỉnh/Thay Thế
  sau này nếu phát hiện sai sót — cân nhắc kỹ trước khi bật.
- **`auto_issue_on_pos`**: tự phát hành HĐ Máy Tính Tiền (MTT) ngay khi thu
  ngân Nộp POS Invoice — mặc định TẮT với công ty mới (an toàn, tránh phát
  hành nhầm hóa đơn thử nghiệm trông giống thật). Giao dịch khách ghi nợ về
  phòng (`Guest Account`) LUÔN được bỏ qua ở bước này để tránh trùng thuế —
  sẽ gộp vào hóa đơn phòng khi khách trả phòng.

## 5. Danh mục báo cáo đóng ca/tháng

| Báo cáo | Mục đích |
|---|---|
| `Frontdesk End of Day Report` | Tổng kết cuối ngày của lễ tân |
| `POS Sales Summary` | Doanh thu POS theo ca/ngày |
| `Financial Activity Summary` | Tổng hợp thu chi liên quan đóng ca POS |
| `Daily Payment Collection` | Toàn bộ khoản thu (Payment Entry) trong kỳ |
| `Room Only Sales` | Doanh thu THUẦN tiền phòng theo từng đặt phòng |
| `Gross Revenue Report` | Doanh thu gộp theo phòng/hạng phòng/quầy lễ tân, kèm ADR |
| `Monthly Revenue by Room Type` | Doanh thu phòng theo tháng x hạng phòng |
| `OTA Commission Report` | Doanh thu + hoa hồng phải trả theo từng kênh OTA |
| `Hospitality Expense Report` | Chi phí đã ghi nhận theo hạng mục/nhà cung cấp |
| `Taxes and Charges Report` | Đối soát đầy đủ thuế GTGT/Phí dịch vụ/Thuế tiêu thụ theo sổ cái GL — **dùng báo cáo này để đối soát thuế đầy đủ, không dùng Frontdesk EOD** |
| `Hotel Performance Analytics` | Công suất phòng, ADR, RevPAR theo ngày |

## 6. Duyệt chi phí (Hospitality Expense)

Quy trình phê duyệt (`workflow_state`):

```
Draft (Nháp) --[Submit for Approval]--> Pending Approval --[Approve]--> Approved
                                                          --[Reject]--> Rejected
```

- Vai trò `Hospitality User` tạo nháp và bấm **"Submit for Approval"**.
- Chỉ vai trò `Hospitality Manager` (hoặc `System Manager`) mới bấm được
  **"Approve"**/**"Reject"**.
- Khi được **Approve**, hệ thống tự ghi sổ kế toán (GL) — không cần thao tác
  thêm.
- Có thể liên kết trực tiếp tới 1 `Hotel Maintenance Request` để ghi chi phí
  sửa chữa đúng theo yêu cầu bảo trì tương ứng.

## 7. Khai báo tạm trú công an

### Cấu hình bắt buộc trước khi dùng (`Hospitality Police Settings`)
Phải điền đủ: **Mã số thuế**, **Địa chỉ cơ sở lưu trú**, **Tên đơn vị công
an quản lý**, **Tỉnh/Thành phố**, **Mã cơ sở lưu trú** (do Công an cấp) —
thiếu bất kỳ trường nào, hệ thống báo lỗi rõ ràng ngay khi xuất báo cáo.

### Các định dạng xuất
| Xuất | Đối tượng | Định dạng |
|---|---|---|
| Khai Báo Tạm Trú (CSV/XLSX) | TẤT CẢ khách đang lưu trú | 15 cột (Họ Tên, Giới tính, Ngày sinh, Quốc tịch, Giấy tờ, SĐT, Địa chỉ, Phòng, Ngày đến/đi, Mục đích...) |
| Khai Báo XNC Quảng Ninh (XLSX/XML) | CHỈ khách nước ngoài | 11-13 cột đúng chuẩn Cổng Xuất Nhập Cảnh Quảng Ninh (giới tính mã 1/2, quốc tịch mã ISO-3) |
| Báo cáo `Police Guest Registration Report` | Xem nhanh trên Desk, có cảnh báo "THIẾU SỐ GIẤY TỜ" nếu khách chưa có CCCD/hộ chiếu | — |

Vai trò được phép xuất: `System Manager`, `Hospitality Manager`,
`Hospitality User`, `Frontdesk Supervisor`, `Frontdesk User`, `Auditor`.
