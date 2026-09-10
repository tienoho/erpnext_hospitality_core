# Hướng Dẫn Triển Khai & Vận Hành Hardware Bridge Service (v2.1)
**Hệ Thống Quản Lý Khóa Thẻ Từ Khách Sạn — Tuần Châu Resort Hạ Long**
*Công ty Cổ phần Nghỉ dưỡng Đảo Tuần Châu*

---

## 1. Giới Thiệu Tổng Quan

**Hardware Bridge Service** là dịch vụ vi mô (Local Microservice) chạy ngầm trực tiếp trên các máy tính Windows tại quầy Lễ tân Tuần Châu Resort. Dịch vụ này đóng vai trò cầu nối trung gian giữa giao diện **Frappe Web Desk / Hospitality Core** (chạy trên trình duyệt qua kết nối bảo mật HTTPS) với các thiết bị phần cứng ngoại vi (Đầu ghi/đọc thẻ từ RFID/IC Card Encoders kết nối qua cổng USB / COM ảo).

### Sơ đồ luồng dữ liệu:
```
[ Frappe Web Desk (HTTPS) ]
         │ (fetch HTTP / CORS + Chromium PNA)
         ▼
[ Local Hardware Bridge: http://127.0.0.1:8765 ]
         │ (ctypes / Win32 API)
         ├──> [ DLL Nhà Cung Cấp Khóa: Hune, Orbita, Adel, BeTech... ]
         │           │
         │           ▼ (USB Virtual COM / RS232)
         │    [ Thiết Bị Đầu Ghi Thẻ Từ Tại Quầy Lễ Tân ]
         │
         └──> [ Smart Simulator Engine ] (Tự động kích hoạt khi chưa có phần cứng)
```

---

## 2. Cấu Trúc Thư Mục

```
hardware_bridge/
├── server.py                 # Core Service HTTP đa luồng (Multi-Threaded REST API)
├── run_bridge.bat            # Khởi chạy dịch vụ ở chế độ Debug / Console (có hiện màn hình)
├── run_bridge_silent.vbs     # Khởi chạy dịch vụ CHẠY NGẦM HOÀN TOÀN (khuyên dùng cho Lễ tân)
├── stop_bridge.bat           # Dừng dịch vụ và giải phóng cổng 8765
├── install_autostart.bat     # Cài đặt tự động chạy ngầm cùng Windows mỗi khi bật máy
├── uninstall_autostart.bat   # Gỡ bỏ dịch vụ khỏi Windows Startup
├── test_bridge.py            # Bộ kiểm thử tự động toàn diện 6/6 API endpoints
├── config.json               # File lưu trữ cấu hình bền vững (tự sinh khi cấu hình)
├── bridge.log                # Nhật ký hoạt động chi tiết (UTF-8)
└── README.md                 # Tài liệu kỹ thuật & Hướng dẫn vận hành này
```

---

## 3. Các Tính Năng Đột Phá Trên Bản v2.1

1. **Chromium Private Network Access (PNA) & Full CORS:**
   - Hỗ trợ đầy đủ header `Access-Control-Allow-Private-Network: true` và `Access-Control-Max-Age: 86400`.
   - Đảm bảo trình duyệt Chrome, Edge đời mới khi truy cập ERP qua HTTPS (`https://erp.tuanchaugroup.com`) gọi vào `http://127.0.0.1:8765` không bao giờ bị chặn Mixed Content.

2. **Tự Động Phát Hiện Xung Đột Kiến Trúc (32-bit vs 64-bit):**
   - Tự động đọc Header PE của file DLL để xác định kiến trúc (`x86` hay `x64`).
   - Nếu phát hiện DLL là 32-bit (rất phổ biến ở SDK khóa Hune, Orbita, Adel) nhưng máy tính đang chạy Python 64-bit, hệ thống sẽ log cảnh báo rõ ràng bằng tiếng Việt và hiển thị nguyên nhân trong API `/api/status`, thay vì để Windows văng lỗi khó hiểu `[WinError 193]`.

3. **Tự Động Quét Cổng COM Không Cần Cài Thêm Thư Viện:**
   - Sử dụng Windows Registry (`HARDWARE\DEVICEMAP\SERIALCOMM`) tích hợp sẵn trong Python (`winreg`).
   - Endpoint `GET /api/ports` cho phép giao diện Lễ tân quét và chọn đúng cổng COM của đầu đọc USB mà không cần cài đặt thêm gói `pyserial`.

4. **Bảo Vệ Chống Báo Thành Công Giả (Anti Fake Success):**
   - Khi đã nạp DLL thật nhưng chưa có hàm SDK ghi thẻ thực tế, Bridge từ chối và báo lỗi rõ ràng `success: False`.
   - Ngăn chặn triệt để sự cố Lễ tân tưởng đã ghi thẻ thành công nhưng thẻ thực tế vẫn trống, khiến khách không mở được cửa phòng.

5. **Lưu Cấu Hình Bền Vững (`config.json`):**
   - Mọi thay đổi cổng COM, hãng khóa qua API `/api/lock/configure` đều được tự động lưu vào đĩa cứng, không bị mất khi khởi động lại máy tính.

---

## 4. Hướng Dẫn Cài Đặt Tại Quầy Lễ Tân

### Bước 1: Yêu cầu môi trường Python trên máy Lễ tân
- Cài đặt Python 3.10+ (Khuyến nghị: **Python 32-bit (x86)** nếu sử dụng DLL khóa cửa của Hune, Orbita hoặc Adel, vì 90% SDK của các hãng này được biên dịch dạng 32-bit).
- Tích chọn **"Add Python to PATH"** trong quá trình cài đặt.

### Bước 2: Nạp thư viện DLL của hãng khóa (Nếu có phần cứng thật)
Copy file `.dll` do nhà cung cấp khóa bàn giao vào thư mục `hardware_bridge/` theo quy tắc đặt tên:
- Hune: `HuneLock.dll`
- Orbita: `OrbitaLock.dll`
- Adel: `AdelLock.dll`
- BeTech: `BeTechLock.dll`
*(Nếu không có file DLL, hệ thống sẽ tự động chuyển sang chế độ Mô phỏng / Simulator phục vụ đào tạo và kiểm thử).*

### Bước 3: Cài đặt tự khởi động cùng Windows
1. Chuột phải vào file `install_autostart.bat` -> Chọn **Run as administrator** (hoặc mở trực tiếp).
2. Hệ thống sẽ tự động tạo lối tắt ngầm `TuanChau_Hardware_Bridge.lnk` trong thư mục Startup của Windows.
3. Từ nay, mỗi khi nhân viên Lễ tân bật máy tính, dịch vụ sẽ **tự động chạy ngầm** mà không làm phiền màn hình làm việc.

### Bước 4: Kiểm tra nhanh
- Mở trình duyệt và truy cập: `http://127.0.0.1:8765/api/status`
- Kết quả trả về JSON có `"status": "online"` là dịch vụ đang hoạt động hoàn hảo.

---

## 5. Danh Sách API Endpoints

| Phương Thức | Đường Dẫn | Chức Năng | Ghi Chú |
|---|---|---|---|
| `GET` | `/api/status` | Kiểm tra tình trạng hoạt động | Trả về thông tin Python bitness, DLL bitness, cổng COM, hãng khóa |
| `GET` | `/api/ports` | Danh sách các cổng COM | Tự động quét từ Windows Registry |
| `GET` | `/api/lock/read_card` | Đọc dữ liệu thẻ phòng | Đọc số phòng, mã UID, hạn thẻ từ đầu đọc |
| `POST` | `/api/lock/encode_card` | Ghi thẻ phòng cho khách | Tham số: `room_no`, `checkin_time`, `checkout_time`, `guest_name`, `is_duplicate` |
| `POST` | `/api/lock/clear_card` | Xóa và thu hồi thẻ phòng | Trả thẻ về trạng thái trắng/thu hồi |
| `POST` | `/api/lock/configure` | Thay đổi cấu hình Bridge | Cập nhật `vendor`, `port`, `simulation_mode` và lưu vào `config.json` |

---

## 6. Vận Hành & Xử Lý Sự Cố (Troubleshooting)

### Sự cố 1: Lễ tân bấm "Ghi thẻ" trên ERP nhưng báo "Không thể kết nối Đầu đọc thẻ"
- **Nguyên nhân:** Dịch vụ Bridge chưa được bật hoặc cổng 8765 bị chặn.
- **Khắc phục:** 
  1. Chạy file `run_bridge.bat` để xem log trực tiếp trên màn hình.
  2. Nếu cổng 8765 bị kẹt, chạy file `stop_bridge.bat` rồi mở lại `run_bridge_silent.vbs`.

### Sự cố 2: Đã copy file DLL nhưng Bridge vẫn báo "Simulation Mode: True"
- **Nguyên nhân:** Xung đột kiến trúc bit (Python 64-bit không thể load DLL 32-bit).
- **Khắc phục:**
  1. Mở `http://127.0.0.1:8765/api/status` và kiểm tra trường `"architecture_mismatch"`.
  2. Nếu báo `true`, gỡ Python 64-bit trên máy Lễ tân và cài đặt bản **Python 32-bit (Windows x86)**.

### Sự cố 3: Máy tính đổi cổng USB cắm đầu đọc
- **Khắc phục:** 
  1. Truy cập `http://127.0.0.1:8765/api/ports` để xem cổng COM mới (ví dụ: `COM4`).
  2. Cập nhật cổng mới qua giao diện cài đặt khách sạn trên ERP hoặc sửa trực tiếp trong `config.json`.
