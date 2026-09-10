# Tổng Quan Hệ Thống — Hospitality Core PMS (Tuần Châu Resort)

> Bộ tài liệu vận hành gồm 5 file, đọc theo đúng vai trò công việc của bạn:
>
> | File | Dành cho |
> |---|---|
> | **00_tong_quan_he_thong.md** (file này) | Mọi nhân viên — đọc trước tiên |
> | [`01_le_tan_va_dat_phong.md`](01_le_tan_va_dat_phong.md) | Lễ tân, Giám sát Lễ tân |
> | [`02_buong_phong_bao_tri_pos.md`](02_buong_phong_bao_tri_pos.md) | Buồng phòng, Kỹ thuật/Bảo trì, Thu ngân Nhà hàng/POS |
> | [`03_ke_toan_dem_kiem_toan_bao_cao.md`](03_ke_toan_dem_kiem_toan_bao_cao.md) | Kế toán, Kiểm toán đêm, Quản lý/Điều hành |
> | [`04_van_hanh_ky_thuat_it.md`](04_van_hanh_ky_thuat_it.md) | Đội IT/Vận hành hệ thống (kỹ thuật, không dành cho nghiệp vụ) |

## Hệ thống này là gì?

**Hospitality Core** là phân hệ quản lý khách sạn (PMS — Property Management
System) xây trên nền ERPNext/Frappe, thay thế Smile PMS cho **Tuần Châu
Resort**. Toàn bộ nghiệp vụ khách sạn — đặt phòng, check-in/out, folio khách,
buồng phòng, F&B, kế toán, đêm kiểm toán, báo cáo, hóa đơn điện tử, khai báo
tạm trú công an — đều chạy trên cùng 1 hệ thống, dùng chung dữ liệu, không
cần đối chiếu thủ công giữa nhiều phần mềm rời rạc như trước.

Hệ thống truy cập qua trình duyệt web tại địa chỉ nội bộ do IT cung cấp (đăng
nhập bằng email + mật khẩu được cấp).

## Bản đồ module chính

```
┌─────────────────────────────────────────────────────────────┐
│                     TRANG "HOSPITALITY"                      │
│         (menu bên trái, sau khi đăng nhập → workspace)        │
├───────────────┬───────────────┬───────────────┬───────────────┤
│  Front Desk   │  Housekeeping │   F&B / POS   │   Kế toán &   │
│    Console    │     Board     │               │  Báo cáo      │
├───────────────┼───────────────┼───────────────┼───────────────┤
│ Tape Chart    │  Buồng Di Động│  POS Invoice  │ Guest Folio   │
│ Đặt phòng     │  (mobile PWA) │  F&B Ticket   │ City Ledger   │
│ Check-in/out  │  Bảo trì      │               │ Night Audit   │
│ Khai báo CA   │  Đồ thất lạc  │               │ HĐĐT          │
└───────────────┴───────────────┴───────────────┴───────────────┘
```

## Vai trò & phân quyền (Roles)

Hệ thống phân quyền theo **Vai trò (Role)** gán cho từng tài khoản — 1 người
có thể có nhiều vai trò. Vai trò càng cao càng thấy/làm được nhiều thao tác
nhạy cảm hơn (hủy đặt phòng, phê duyệt chi phí, ghi đè khách Blacklist...).

| Vai trò | Phạm vi điển hình |
|---|---|
| **Hospitality User** | Vai trò cơ bản — tạo đặt phòng, dọn phòng, báo hỏng, bán hàng POS, tạo Hospitality Expense (nháp) |
| **Frontdesk Supervisor** | + Hủy đặt phòng, chuyển phòng (Move Room), ghi đè khách Blacklist, tách/gộp folio, tách bill đoàn tour |
| **Hospitality Manager** | + Phê duyệt/Từ chối Hospitality Expense, xem toàn bộ báo cáo quản lý |
| **FNB Operator / FNB Supervisor / FNB Storekeeper / FNB Cost Controller / FNB Finance Approver** | Các vai trò chuyên biệt cho module F&B Cost Control (bếp, kho, thu mua, kiểm soát giá vốn) |
| **Accounts Manager / Stock Manager** | Vai trò kế toán/kho chuẩn của ERPNext, dùng chung cho các thao tác tài chính/tồn kho nền tảng |
| **System Manager** | Toàn quyền — dành cho quản trị hệ thống, KHÔNG cấp cho nhân viên vận hành thông thường |

> Nếu đăng nhập mà KHÔNG thấy nút/menu được mô tả trong 3 tài liệu SOP, khả
> năng cao là tài khoản chưa được gán đúng vai trò — liên hệ Quản lý/IT để bổ
> sung, đừng tự ý xin cấp `System Manager`.

## Quy ước xuyên suốt bộ tài liệu

- **Property (Cơ sở)**: nếu Tập đoàn vận hành nhiều cơ sở trên cùng hệ thống,
  mỗi tài khoản chỉ thấy dữ liệu của (các) cơ sở được cấp quyền — không tự
  thấy được cơ sở khác.
- **Ngày kinh doanh (business date)**: một số báo cáo/ca làm việc tính theo
  "ngày kinh doanh" (có thể lệch với ngày lịch nếu ca làm việc kéo qua nửa
  đêm), không phải lúc nào cũng là ngày dương lịch hiện tại — xem chi tiết ở
  tài liệu tương ứng.
- **Folio**: là "sổ theo dõi công nợ" của 1 lượt lưu trú hoặc 1 công ty/đoàn —
  mọi khoản phí (tiền phòng, dịch vụ, phụ thu) và thanh toán đều ghi vào đây,
  số dư còn lại gọi là **Outstanding Balance**.
- Mọi màn hình có nút màu ĐỎ hoặc yêu cầu nhập lý do (VD ghi đè Blacklist, hủy
  đặt phòng) đều được HỆ THỐNG GHI LẠI LỊCH SỬ (audit trail) — không xóa được,
  chỉ có thể bổ sung ghi chú.

## Sự cố / câu hỏi khi thao tác

- Lỗi nghiệp vụ (không hiểu vì sao hệ thống chặn 1 thao tác, số liệu báo cáo
  trông sai) → hỏi Giám sát/Quản lý trực tiếp trước, đối chiếu đúng tài liệu
  nghiệp vụ tương ứng.
- Lỗi kỹ thuật (trang không tải được, lỗi 500, mất kết nối) → báo đội IT, xem
  [`04_van_hanh_ky_thuat_it.md`](04_van_hanh_ky_thuat_it.md).
