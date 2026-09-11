# Kịch Bản Demo Đầy Đủ Các Luồng Nghiệp Vụ — Hospitality Core PMS

> Dành cho: Người trình bày Demo (Tổ Dự Án ERP) và người hỗ trợ kỹ thuật đứng
> máy. Đọc [`00_tong_quan_he_thong.md`](00_tong_quan_he_thong.md) trước nếu
> chưa quen hệ thống. Kịch bản này mô phỏng **1 ngày vận hành đầy đủ** của
> Tuần Châu Resort — từ lúc khách đặt phòng tới lúc kiểm toán đêm chốt sổ — để
> người xem thấy được tính LIÊN THÔNG THỜI GIAN THỰC là điểm khác biệt lớn
> nhất so với Smile PMS cũ (3 phần mềm rời rạc).
>
> **Tổng thời lượng đề xuất**: 45-60 phút demo + 15 phút hỏi đáp.

---

## 0. Chuẩn bị trước Demo (làm trước ít nhất 1 ngày)

### 0.1. Checklist kỹ thuật (đội IT thực hiện — xem chi tiết [`04_van_hanh_ky_thuat_it.md`](04_van_hanh_ky_thuat_it.md))
- [ ] Xác nhận server demo (`dev-erp.tuanchaugroup.com.vn` hoặc môi trường tương đương) đang chạy ổn định, đã `bench migrate` với đúng phiên bản mã nguồn mới nhất.
- [ ] Chạy thử toàn bộ 1 lượt kịch bản này TRÊN ĐÚNG SERVER SẼ DÙNG DEMO ít nhất 1 lần trước — không demo lần đầu trực tiếp trước lãnh đạo.
- [ ] Backup dữ liệu server demo NGAY TRƯỚC buổi demo (để có thể khôi phục nếu demo làm hỏng dữ liệu mẫu).
- [ ] Chuẩn bị sẵn 2 màn hình/thiết bị: 1 máy tính (Desk chuẩn) + 1 điện thoại/tablet (để demo Buồng Di Động, Tape Chart cảm ứng).
- [ ] Kiểm tra kết nối mạng ổn định tại phòng demo — pop-up in tự động và VietQR cần gọi API, mạng chậm sẽ làm demo trông tệ.
- [ ] Tắt các thông báo/pop-up không liên quan trên trình duyệt (chặn pop-up của trình duyệt cần được CHO PHÉP riêng cho domain hệ thống — xem mục in tự động ở `04_van_hanh_ky_thuat_it.md`).

### 0.2. Dữ liệu mẫu cần dựng sẵn
| Đối tượng | Gợi ý | Ghi chú |
|---|---|---|
| 1 Khách cá nhân demo | "Nguyễn Văn Demo" | Có sẵn SĐT/email để test Omni-Search |
| 1 Khách công ty/đại lý | "Công ty Du lịch ABC" | Có hạn mức tín dụng để demo City Ledger màu Xanh/Vàng |
| 1 Đoàn khách demo | "Đoàn Công ty XYZ — 5 phòng" | Để demo Group Booking, mass check-in |
| 2-3 phòng trống thật | Loại phòng khác nhau (Deluxe, Suite...) | Đảm bảo KHÔNG trùng phòng đang có khách thật |
| 1 Item F&B mẫu | "Trà gừng mật ong" hoặc món bất kỳ | Đã gắn giá + item group |
| Cấu hình `Hospitality Police Settings` | Điền đủ trước | Tránh lỗi khi demo xuất khai báo công an |
| Cấu hình `Hospitality Surcharge Settings` | Bật đúng khung giờ | Để phụ thu sớm/muộn kích hoạt đúng lúc demo |
| 1 Guest Folio có dư nợ nhỏ | ~200.000đ | Để demo VietQR + Ghi Nhận Thanh Toán |

> **Mẹo**: chọn giờ demo sao cho khớp đúng khung "check-in sớm" hoặc "check-out
> muộn" theo `Hospitality Surcharge Settings` để phụ thu tự kích hoạt thật khi
> demo — thuyết phục hơn nhiều so với giải thích suông.

### 0.3. Câu mở đầu gợi ý
> "Trước khi vào chi tiết từng chức năng, điểm khác biệt lớn nhất của hệ thống
> mới so với Smile PMS là: **toàn bộ 1 cơ sở dữ liệu duy nhất, thời gian
> thực**. Khi tôi ghi 1 giao dịch ở Lễ tân, nó xuất hiện ngay lập tức ở Kế
> toán — không cần đợi 'chạy đêm' như trước. Tôi sẽ demo đúng điều đó bằng
> cách đi theo 1 ngày vận hành thật của khách sạn."

---

## CẢNH 1 — Lễ Tân & Đặt Phòng (10 phút)

### 1.1. Front Desk Console — màn hình làm việc trung tâm
**Thao tác**: Mở trang "Front Desk Console".
**Nói gì**: Chỉ vào 4 thẻ KPI (Khách Sắp Đến / Khách Sắp Đi / Đang Lưu Trú / Phòng Khả Dụng) — "Đây là bức tranh toàn cảnh khách sạn, cập nhật thời gian thực, không cần đợi báo cáo cuối ngày."
**Demo Omni-Search**: Gõ thử số điện thoại của khách demo → chỉ ra kết quả hiện ra ngay lập tức, kèm gợi ý "chấp nhận cả số phòng, SĐT, CCCD/Hộ chiếu, mã đặt phòng OTA".

### 1.2. Tape Chart — sơ đồ buồng trực quan
**Thao tác**: Mở "Sơ Đồ Buồng" (Tape Chart).
**Nói gì**: "Đây thay thế Tape Chart cũ của Smile — kéo-thả trực tiếp." Bấm vào 1 ô phòng trống → dialog "Tạo Đặt Phòng Nhanh" hiện ra.
**Điểm nhấn**: Kéo-thả 1 khối đặt phòng `Reserved` sang phòng khác trước mặt khán giả — chuyển ngay không cần lưu form.

### 1.3. Tạo đặt phòng đầy đủ
**Thao tác**: Từ dialog nhanh → "Mở Form Chi Tiết" → điền Guest/Room Type/Room/Ngày đến-đi/Rate Plan.
**Nói gì**: Nhấn mạnh Rate Plan tự động áp giá theo mùa vụ + giảm giá theo số đêm (LOS) — "hệ thống tự tính, lễ tân không cần tra bảng giá giấy".

### 1.4. Quét CCCD/Hộ chiếu tạo khách nhanh
**Thao tác**: Bấm "Quét CCCD / Passport" trên Console → dán sẵn 1 đoạn văn bản mẫu (chuẩn bị trước, xem [`01_le_tan_va_dat_phong.md`](01_le_tan_va_dat_phong.md#10-quét-cccdhộ-chiếu-tạo-khách-nhanh)) → Parse → xem trước thông tin → Create Guest.
**Lưu ý QUAN TRỌNG khi demo**: đây là bước DÁN VĂN BẢN đã có sẵn (từ máy quét/OCR ngoài), **KHÔNG PHẢI chụp ảnh trực tiếp bằng camera rồi tự động đọc** — nếu bị hỏi "chụp ảnh được không", trả lời trung thực: "Phần phân tích dữ liệu đã sẵn sàng đầy đủ, phần kết nối trực tiếp với camera/API OCR đang chờ chọn nhà cung cấp (FPT.AI/Google Vision) — dự kiến hoàn thành ở giai đoạn sau."

---

## CẢNH 2 — Check-in (có Phụ Thu) (7 phút)

### 2.1. Check-in bình thường
**Thao tác**: Mở đặt phòng `Reserved` đã tạo → bấm "Check In".
**Nói gì**: "Ngay khi check-in, hệ thống tự mở Folio và tính tiền đêm đầu tiên — không cần thao tác thủ công."

### 2.2. Check-in sớm (nếu đúng khung giờ đã chuẩn bị)
**Thao tác**: Với 1 đặt phòng khác, bấm Check In vào đúng khung giờ trước 14:00.
**Nói gì**: Hộp thoại "⏰ Phát Hiện Nhận Phòng Sớm" hiện ra tự động — "Hệ thống TỰ PHÁT HIỆN, lễ tân không cần nhớ bảng phụ thu." Demo cả 2 lựa chọn: "Áp Dụng Phụ Thu" và "Miễn Phụ Thu" (chọn 1 lý do miễn, VD "VIP/Thân thiết").

### 2.3. Khách trong danh sách đen (tùy chọn, nếu muốn nhấn mạnh kiểm soát rủi ro)
**Thao tác**: Thử tạo đặt phòng cho 1 Guest đã đánh dấu `Blacklisted` (chuẩn bị trước).
**Nói gì**: "Hệ thống chặn ngay, bắt buộc Giám sát phê duyệt + ghi lý do — mọi thao tác này lưu vết vĩnh viễn."

---

## CẢNH 3 — Buồng Phòng & Bảo Trì (7 phút)

### 3.1. Bảng Điều Phối Buồng Phòng (máy tính)
**Thao tác**: Mở "Housekeeping Board". Bấm nút chuyển trạng thái 1 phòng: Cần dọn → Bắt Đầu Dọn → Dọn Xong → Duyệt Sạch.
**Nói gì**: Nhấn mạnh **an toàn dữ liệu**: "Nếu phòng đang có khách ở, hệ thống KHÔNG BAO GIỜ cho đánh dấu Sạch/Đã KT nhầm — tự động khóa lại."

### 3.2. Buồng Di Động (điện thoại)
**Thao tác**: Trên điện thoại/tablet, mở trang buồng di động → đổi trạng thái 1 phòng khác.
**Nói gì**: "Nhân viên buồng phòng không cần quay lại quầy lễ tân báo cáo — cập nhật ngay tại chỗ, Tape Chart đổi màu tức thì."

### 3.3. Báo hỏng/Bảo trì
**Thao tác**: Trên điện thoại, báo hỏng 1 phòng (chọn loại sự cố, mô tả, chụp ảnh nếu có).
**Nói gì**: "Phòng tự động chuyển 'Khóa/Sửa' — không thể bán nhầm phòng đang hỏng." Chuyển sang máy tính, mở `Hotel Maintenance Request` vừa tạo, cập nhật trạng thái "Completed" (bắt buộc ghi chú xử lý) → phòng tự giải phóng về "Cần dọn".

---

## CẢNH 4 — F&B / POS & Ghi Nợ Phòng (8 phút)

### 4.1. Bán hàng tại quầy
**Thao tác**: Mở POS Invoice mới, chọn Item F&B mẫu.
**Nói gì**: Nếu có module F&B Cost Control — nhấn mạnh: "Mỗi món bán ra tự động trừ đúng định mức nguyên liệu, tính Food Cost % theo thời gian thực."

### 4.2. Ghi nợ về phòng khách (Charge to Room) — ĐIỂM NHẤN QUAN TRỌNG NHẤT
**Thao tác**: Trên POS Invoice, gắn số phòng của khách đang lưu trú (đã check-in ở Cảnh 2) → chọn hình thức thanh toán **"Guest Account"** → Submit.
**Nói gì**: "Đây chính là điểm khác biệt cốt lõi so với Smile — Smile phải chờ Night Audit thủ công cuối ngày mới đẩy số liệu này về phòng. Ở đây, TÔI SẼ CHUYỂN NGAY SANG MÀN HÌNH FOLIO CỦA KHÁCH ĐỂ CHỨNG MINH."
**Chuyển màn hình**: Mở lại Guest Folio của khách → chỉ ra dòng giao dịch F&B VỪA XUẤT HIỆN ngay lập tức trong Outstanding Balance.

### 4.3. Demo quy tắc an toàn thanh toán (tùy chọn, nếu có thời gian)
**Thao tác**: Thử chọn "Guest Account" cho 1 hóa đơn KHÔNG gắn phòng (khách vãng lai) → hệ thống báo lỗi chặn ngay.
**Nói gì**: "Hệ thống tự kiểm tra ở cả giao diện lẫn máy chủ — không thể lách qua để ghi nợ khống."

---

## CẢNH 5 — Thanh Toán & VietQR (5 phút)

**Thao tác**: Trên Guest Folio đã có dư nợ (chuẩn bị sẵn ~200.000đ), bấm "⚡ Tạo VietQR Nhanh" từ Front Desk Console (hoặc trực tiếp từ Folio) → hệ thống tự điền đúng số dư + số phòng → hiện mã QR.
**Nói gì**: "Khách chỉ cần quét bằng app ngân hàng bất kỳ — không cần máy POS thẻ riêng." (Dùng điện thoại demo quét thử mã QR để khán giả thấy đúng số tiền/nội dung tự động.)
**Sau đó**: Bấm "Ghi Nhận Thanh Toán" → nhập số tiền → Submit → chỉ ra Outstanding Balance về 0 ngay lập tức.

---

## CẢNH 6 — Check-out (có Phụ Thu + Chặn Nợ) (7 phút)

### 6.1. Check-out bình thường (khách đã thanh toán đủ ở Cảnh 5)
**Thao tác**: Bấm "Check Out" trên đặt phòng.
**Nói gì**: "Vì đã thanh toán đủ ở bước trước, hệ thống cho check-out ngay. Phòng tự động chuyển 'Bẩn' để buồng phòng biết dọn."

### 6.2. Demo CHẶN check-out khi còn nợ — ĐIỂM NHẤN KIỂM SOÁT RỦI RO
**Thao tác**: Thử check-out 1 đặt phòng KHÁC còn dư nợ (chưa thanh toán).
**Nói gì**: "Hệ thống CHẶN CỨNG, không cho lễ tân bỏ sót công nợ khách — đây là lỗ hổng thường gặp nhất ở các hệ thống cũ."

### 6.3. Check-out muộn (phụ thu)
**Thao tác**: Nếu đúng khung giờ đã chuẩn bị, demo hộp thoại "⏰ Phát Hiện Trả Phòng Muộn" tương tự Cảnh 2.

---

## CẢNH 7 — Đặt Đoàn (Group Booking) (8 phút, có thể rút gọn nếu thiếu thời gian)

**Thao tác**: Mở Đoàn demo đã chuẩn bị ("Đoàn Công ty XYZ") → bấm "Bulk Reserve" để đặt hàng loạt 5 phòng cùng lúc.
**Nói gì**: "Không cần đặt tay từng phòng như Smile — chọn hạng phòng + số lượng, hệ thống tự gán."
**Tiếp theo**: Bấm "Check In Group" → toàn bộ khách trong đoàn được check-in cùng lúc.
**Điểm nhấn công nợ**: Mở Master Folio của đoàn, chỉ ra toàn bộ chi tiêu của cả đoàn dồn về 1 nơi duy nhất để công ty/đại lý thanh toán tập trung.

---

## CẢNH 8 — Đêm Kiểm Toán (Night Audit) (5 phút)

**Thao tác**: Chạy thủ công Night Audit (hoặc chỉ vào Night Audit Log của lần chạy tự động gần nhất nếu không muốn chạy trực tiếp trước khán giả).
**Nói gì**: "Đây là công việc đêm hoàn toàn tự động: tự hủy khách không đến (no-show) kèm hoàn cọc, tự gia hạn khách ở quá hạn, tự tính tiền phòng đêm mới, và tự ĐỐI CHIẾU chéo Phòng-Đặt phòng-Folio để phát hiện bất thường." Mở 1 Night Audit Log mẫu, chỉ vào các số liệu: Số No-Show, Số Overstay, Số Phòng Đã Tính Tiền, Số Lệch Đối Chiếu.
**Điểm nhấn**: "Toàn bộ lịch sử được lưu lại — khác với hệ thống cũ đôi khi mất dữ liệu ngày hôm trước."

---

## CẢNH 9 — Hóa Đơn Điện Tử (5 phút) — CẦN NÓI RÕ ĐANG Ở CHẾ ĐỘ THỬ NGHIỆM

**Thao tác**: Trên 1 Sales Invoice đã Submit, mở menu HĐĐT → "Phát hành Hóa đơn Điện tử".
**Nói gì — BẮT BUỘC nói rõ, không né tránh**: "Đây đang chạy ở chế độ Sandbox/Thử nghiệm — thấy chỉ báo màu **cam** '⚠️ HĐĐT THỬ NGHIỆM'. Số hóa đơn này CHƯA gửi thật lên Cơ quan Thuế. Khi kết nối nhà cung cấp thật (MISA/Viettel/VNPT), chỉ báo sẽ chuyển XANH và số liệu là hóa đơn thật — hạ tầng kỹ thuật đã sẵn sàng, chỉ còn chờ hợp đồng nhà cung cấp."
**Lý do PHẢI nói rõ điều này**: tránh lãnh đạo hiểu nhầm đây là hóa đơn thật đã tuân thủ pháp lý — rủi ro pháp lý/uy tín nếu để hiểu nhầm.

---

## CẢNH 10 — Báo Cáo & Điều Hành (5 phút)

**Thao tác**: Mở lần lượt: `Frontdesk End of Day Report`, `Gross Revenue Report` (ADR/RevPAR/Occupancy), `City Ledger` (chỉ màu Xanh/Vàng/Đỏ của khách công ty demo).
**Nói gì**: "Toàn bộ số liệu này Tổng Giám Đốc có thể xem trực tiếp trên điện thoại, không cần chờ kế toán tổng hợp Excel."

---

## Phụ Lục A — Câu hỏi thường gặp & cách trả lời trung thực

| Câu hỏi có thể gặp | Trả lời khuyến nghị |
|---|---|
| "Khóa thẻ từ hoạt động chưa?" | "Phần mềm đã sẵn sàng gửi lệnh, nhưng phần kết nối vật lý với đầu đọc thẻ (Hune/Orbita/VingCard) cần SDK chính hãng — đang làm việc với nhà cung cấp, dự kiến hoàn thành trước Go-Live. Trong lúc chờ, có phương án dự phòng dùng phần mềm ghi thẻ độc lập của hãng khóa." |
| "Kết nối Agoda/Booking.com chưa?" | "Chiều NHẬN đặt phòng từ OTA đã hoạt động tốt. Chiều ĐẨY giá/phòng trống lên OTA cần hợp đồng Channel Manager (Channex/SiteMinder) — đây là quyết định kinh doanh, chưa triển khai." |
| "Hóa đơn điện tử này có gửi thuế chưa?" | "Chưa — đang Sandbox như đã nói ở Cảnh 9. Cần cài đặt + hợp đồng nhà cung cấp thật." |
| "Có dùng được VNPAY không?" | "Hiện tại dùng VietQR (chuyển khoản ngân hàng qua mã QR chuẩn quốc gia NAPAS 247), không phải cổng thanh toán VNPAY riêng — VietQR không mất phí giao dịch, phù hợp resort." |
| "Chấm công/lương nhân viên demo được không?" | "Đây thuộc phân hệ HRMS, sẽ demo riêng ở buổi khác." |

## Phụ Lục B — Nếu có sự cố kỹ thuật giữa buổi demo
- Trang không tải/lỗi 500 → refresh 1 lần; nếu vẫn lỗi, chuyển sang màn hình dự phòng (ảnh chụp/video quay sẵn kịch bản tương tự) thay vì cố sửa lỗi trước mặt khán giả.
- Pop-up in bị chặn → xem [`04_van_hanh_ky_thuat_it.md`](04_van_hanh_ky_thuat_it.md) mục xử lý.
- Không tìm thấy dữ liệu mẫu → có sẵn danh sách mục 0.2 in giấy mang theo phòng demo để dò tên chính xác.
