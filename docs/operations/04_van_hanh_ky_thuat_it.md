# Tài liệu Vận hành Kỹ thuật — Hospitality Core (dành cho đội IT/Vận hành hệ thống)

> **Phạm vi tài liệu này**: các thao tác kỹ thuật ĐẶC THÙ của app `hospitality_core`
> (và app vệ tinh `vietnam_einvoice`) — môi trường Docker dev, cách chạy bộ kiểm
> thử hồi quy, các lỗi/sự cố cụ thể đã gặp và cách xử lý, checklist khi
> migrate/nâng cấp. Tài liệu này **KHÔNG thay thế** sổ tay triển khai Production
> toàn Tập đoàn đã có sẵn:
> - [`HUONG_DAN_TRIEN_KHAI_DEV_UAT_PRODUCTION.md`](../../../HUONG_DAN_TRIEN_KHAI_DEV_UAT_PRODUCTION.md) — quy trình triển khai DEV/UAT/Production cho toàn hệ thống TCG.
> - [`docs/PRODUCTION_DEPLOYMENT_RUNBOOK.md`](../../../docs/PRODUCTION_DEPLOYMENT_RUNBOOK.md) — kiến trúc đa công ty, ma trận tài khoản/phân quyền, kịch bản `deploy_tcg_production.py`.
>
> Đọc 2 tài liệu trên trước nếu công việc là triển khai/onboard Production thật.
> Tài liệu này dành cho việc phát triển/kiểm thử/vá lỗi hàng ngày trên
> `hospitality_core`.

---

## 1. Kiến trúc môi trường Dev (Docker)

Stack dev nằm ở `docker-compose.dev.yml` (thư mục gốc `D:\TCG-project\frappe`),
gồm 4 service:

| Service | Image | Vai trò |
|---|---|---|
| `mariadb` | `mariadb:11.8` | Database, `utf8mb4`, mật khẩu root `123` (chỉ dùng dev, KHÔNG dùng lại cho Production) |
| `redis-cache` | `redis:alpine` | Cache (session, `frappe.db.get_default`, v.v.) |
| `redis-queue` | `redis:alpine` | Hàng đợi background job + socketio |
| `frappe` | `frappe/bench:latest` | Container chạy `bench`, mount toàn bộ mã nguồn qua volume |

Container `frappe` mount trực tiếp mã nguồn từ host vào bench (không copy) —
sửa file trên host (VD qua Claude Code/VS Code) có hiệu lực ngay trong
container, không cần rebuild image:

```yaml
volumes:
  - ./erpnext_hospitality_core:/workspace/frappe-bench/apps/hospitality_core:cached
  - ./erpnext_vietnam_einvoice:/workspace/frappe-bench/apps/vietnam_einvoice:cached
```

Site duy nhất trên bench dev: **`localhost`** (`frappe-bench/sites/localhost`).
**Lưu ý quan trọng**: site `localhost` KHÔNG phải site test trống — nó mang theo
dữ liệu demo/thật của property **"TCR-RESORT"** (đã gộp từ 1 site test riêng
`hospitality-v2.test` theo yêu cầu người dùng để tránh phân tán dữ liệu). Mọi
test/script chạy trên site này phải tính tới việc dữ liệu có sẵn — xem mục 4.

Apps đã cài trên site (`sites/apps.txt`): `frappe`, `crm`, `erpnext`,
`hospitality_core`, `hrms`, `vietnam_einvoice`.

### Lệnh khởi động/kiểm tra cơ bản

```bash
# Khởi động toàn bộ stack
docker compose -f docker-compose.dev.yml up -d

# Kiểm tra trạng thái (đều phải "Up")
docker compose -f docker-compose.dev.yml ps

# Vào shell container frappe
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc "cd /workspace/frappe-bench/sites && bash"

# Kiểm tra DB kết nối được (chạy trong container, ĐÚNG thư mục sites/)
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc \
  "cd /workspace/frappe-bench/sites && /workspace/frappe-bench/env/bin/python -c \"
import frappe
frappe.init(site='localhost'); frappe.connect()
print('DB OK:', frappe.db.count('DocType'))
\""
```

> **Lỗi thường gặp**: chạy lệnh `frappe.init()` mà KHÔNG `cd` vào đúng
> `/workspace/frappe-bench/sites` trước sẽ báo `OSError: b'./apps.txt' Not
> Found` — không phải lỗi cấu hình, chỉ là sai thư mục làm việc.

### Clear cache / rebuild sau khi đổi field ảo, hooks, hoặc JS

```bash
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc \
  "cd /workspace/frappe-bench && bench --site localhost clear-cache"

# Sau khi đổi doctype JSON (thêm field mới) — PHẢI reload-doctype để đồng bộ
# vào DocType meta (JSON sửa không tự áp dụng):
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc \
  "cd /workspace/frappe-bench && bench --site localhost reload-doctype 'Tên DocType'"

# Sau khi đổi JS client-side (Client Script, page JS) — build lại asset:
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc \
  "cd /workspace/frappe-bench && bench build --app hospitality_core"
# rồi hard-refresh trình duyệt (Ctrl+Shift+R) — KHÔNG cần bench restart cho
# thay đổi JS thuần túy.
```

---

## 2. Chạy bộ kiểm thử hồi quy sống (live, chạy trên DB thật qua Docker)

`hospitality_core` KHÔNG dùng `bench run-tests` chuẩn cho phần lớn kiểm thử
tích hợp — do khối lượng nghiệp vụ lớn (đặt phòng, folio, kế toán, F&B), đội
phát triển đã xây riêng **24 script độc lập** dưới `tools/`, mỗi script tự
`unittest`, tự dựng fixture, tự rollback sau mỗi ca (trừ vài trường hợp đặc
biệt — xem mục 4). Chạy TRỰC TIẾP bằng Python trong container, KHÔNG qua
`bench run-tests`:

```bash
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc \
  "cd /workspace/frappe-bench/sites && \
   /workspace/frappe-bench/env/bin/python /workspace/frappe-bench/apps/hospitality_core/tools/run_property_integration.py -v"
```

### Danh mục 19 file kiểm thử hồi quy chính (chạy TUẦN TỰ, không song song — xem cảnh báo mục 4)

| File | Phạm vi |
|---|---|
| `run_property_integration.py` | Property v2 core: đặt phòng/check-in/check-out/rate plan/đa tiền tệ |
| `run_group_booking_tests.py` | Đặt đoàn, phòng ảo Master Payer, mass check-in/out, đặt cọc |
| `run_night_audit_tests.py` | Night Audit: no-show, overstay, tính tiền, đối chiếu Room/Reservation/Folio |
| `run_police_declaration_tests.py` | Khai báo tạm trú công an (CSV/XLSX/XML) |
| `run_city_ledger_financial_control_tests.py` | Công nợ công ty (City Ledger), hủy giao dịch tài chính |
| `run_surcharge_room_move_tests.py` | Phụ thu sớm/muộn, chuyển phòng |
| `run_guest_crm_loyalty_tests.py` | Gộp khách (merge_guest), điểm/hạng thành viên |
| `run_housekeeping_tests.py` | Buồng phòng (desktop+mobile), bảo trì, đồ thất lạc |
| `run_folio_operations_tests.py` | Gộp folio, tách tour, omni-search |
| `run_vietqr_id_scanner_tests.py` | Sinh mã VietQR, quét CCCD/hộ chiếu (OCR/QR/MRZ) |
| `run_property_setup_tests.py` | Wizard ánh xạ property (Property v2 cutover) |
| `run_financial_reports_tests.py` | City Ledger, AR Aging, Monthly Revenue, Gross Revenue, OTA Commission, Taxes & Charges |
| `run_operational_reports_tests.py` | 21 báo cáo vận hành còn lại (arrivals/departures/house list/room availability...) |
| `run_pos_reports_tests.py` | 3 báo cáo phụ thuộc POS Invoice (fixture CÔ LẬP — xem mục 4) |
| `run_fnb_control_integration.py` | F&B Cost Control: outlet, recipe, kiểm kê, chuyển kho |
| `run_fb_integration.py` | Tích hợp F&B cũ (BOM/EOD) |
| `run_fnb_procurement_costing_tests.py` | Mua hàng, nhận hàng, định mức giá cost |
| `run_docker_verification.py` | Kịch bản Property v2 end-to-end (POS thường, thanh toán, HĐĐT Mock) |
| `run_employee_link_tests.py` | Tích hợp HRMS (resolve User→Employee cho báo cáo) |

**Kỳ vọng hiện tại (tham chiếu, cập nhật lần cuối trong phiên review lớn nhất)**:
tổng **312 ca kiểm thử, 0 lỗi** khi chạy tuần tự đầy đủ 19 file (2 skip an toàn
có ghi chú trong code, không phải lỗi). Nếu chạy lại thấy số liệu khác — đọc kỹ
mục 4 trước khi kết luận là hồi quy thật.

### Script chạy sweep tuần tự đầy đủ (mẫu dùng lại được)

```bash
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc '
cd /workspace/frappe-bench/sites
PY=/workspace/frappe-bench/env/bin/python
APP=/workspace/frappe-bench/apps/hospitality_core/tools
for f in run_property_integration run_group_booking_tests run_night_audit_tests \
         run_police_declaration_tests run_city_ledger_financial_control_tests \
         run_surcharge_room_move_tests run_guest_crm_loyalty_tests run_housekeeping_tests \
         run_folio_operations_tests run_vietqr_id_scanner_tests run_property_setup_tests \
         run_financial_reports_tests run_operational_reports_tests run_pos_reports_tests \
         run_fnb_control_integration run_fb_integration run_fnb_procurement_costing_tests \
         run_docker_verification run_employee_link_tests; do
  echo "===$f==="
  $PY $APP/$f.py 2>&1 | tail -8
done'
```

### Kiểm thử thuần Python/JS (không cần DB, chạy nhanh)

```bash
cd erpnext_hospitality_core
python -m unittest discover -s tests -p "test_*.py" -v   # 38 ca — logic tính giá, loyalty, GL guard thuần túy
node --test tests/*.test.cjs                               # 4 file JS — escape HTML, format tiền tệ
git diff --check                                            # chỉ cảnh báo CRLF (Windows), không phải lỗi thật
```

---

## 3. Backup / Restore (dev)

```bash
# Backup đầy đủ (DB + file đính kèm + cấu hình site) — chạy trong container
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc \
  "cd /workspace/frappe-bench && bench --site localhost backup --with-files"
# File backup nằm tại: frappe-bench/sites/localhost/private/backups/

# Restore (THAY THẾ toàn bộ DB hiện tại — xác nhận trước khi chạy)
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc \
  "cd /workspace/frappe-bench && bench --site localhost restore <đường-dẫn-file-sql.gz> --with-private-files <files.tar> --with-public-files <files.tar>"
```

**Quan trọng đối với PMS**: `Guest Folio`/`Folio Transaction`/`GL Entry` là dữ
liệu TÀI CHÍNH — backup trước MỌI thao tác có rủi ro (migrate lớn, thử nghiệm
migration script, xóa hàng loạt qua `cleanup.py`). Production thật dùng quy
trình backup riêng theo `docs/PRODUCTION_DEPLOYMENT_RUNBOOK.md` — mục này chỉ
áp dụng cho máy dev.

---

## 4. Sổ tay sự cố đã biết (Known Issues Playbook)

Đây là các sự cố THẬT đã xảy ra trong quá trình phát triển/kiểm thử, kèm cách
nhận diện và xử lý — tránh lặp lại thời gian điều tra.

### 4.1. "Cold cache" flake ngay sau khi container restart

**Triệu chứng**: 1-2 test đầu tiên chạy NGAY SAU KHI container `frappe`/`mariadb`
vừa khởi động lại (uptime vài giây/vài chục giây) báo lỗi lạ (`AssertionError`
về giá trị cache/default không khớp), nhưng chạy lại NGAY LẬP TỨC (không đổi
gì) thì xanh trở lại.

**Xử lý**: chạy lại 1 lần. Nếu vẫn lỗi sau 2 lần chạy liên tiếp, đó KHÔNG phải
flake — điều tra thật.

### 4.2. Redis cache staleness sau nhiều lần `bench reinstall`

**Triệu chứng**: `AssertionError` dạng "stored vs cached khác nhau" ở đúng dòng
diagnostic tự vệ của fixture test (VD `preview.selling_price_list` khác
`frappe.db.get_single_value(cache=False)`).

**Nguyên nhân**: `bench reinstall` xóa MariaDB nhưng KHÔNG flush Redis —
`redis-cache`/`redis-queue` là 2 service Docker RIÊNG, tồn tại độc lập.

**Xử lý** (leo thang nếu bước trước không đủ):
```bash
docker compose -f docker-compose.dev.yml exec -T frappe bash -lc \
  "bench --site localhost clear-cache"
# Nếu vẫn còn:
docker compose -f docker-compose.dev.yml exec redis-cache redis-cli FLUSHALL
docker compose -f docker-compose.dev.yml exec redis-queue redis-cli FLUSHALL
```
Sau FLUSHALL, file test ĐẦU TIÊN chạy lại có thể dính đúng 1 lần "cold cache"
flake (mục 4.1) — chạy lại 1 lần nữa là hết.

### 4.3. Site `localhost` mang dữ liệu có sẵn — KHÔNG phải site sạch

Property **"TCR-RESORT"** có ~40+ Hotel Reservation demo/thật sẵn có trên site
này. **Mọi test báo cáo mới viết PHẢI**:
- Lọc kết quả theo room/reservation/tên bản ghi CỤ THỂ của chính fixture (không
  lọc chỉ theo item/loại chung chung — VD không dùng
  `next(c for c in charges if c['item']=='ROOM-RENT')` mà phải thêm điều kiện
  `and c['room']==self.reservation.room`), **HOẶC**
- Đo CHÊNH LỆCH trước/sau khi thêm fixture (`before = ...; ...; after = ...;
  assertEqual(after-before, ...)`) thay vì so giá trị tuyệt đối.

Không tuân thủ điều này đã từng gây ra các con số sai lệch RẤT LỚN (hàng chục
triệu đồng) khi viết test mới — không phải bug sản phẩm, mà là test giả định
sai về site sạch.

### 4.4. `POS Invoice`/`POS Closing Entry`/`Company` (khi tạo mới)/`void_transaction()` gọi `frappe.db.commit()` THẬT bên trong

**Đây là lớp rủi ro nghiêm trọng nhất khi viết test mới.** Các hàm/luồng sau
TỰ ĐỘNG commit dữ liệu ra khỏi transaction hiện tại, bất kể test có lỗi hay
không — `frappe.db.rollback()` ở `tearDown()` KHÔNG hoàn tác lại được:
- `POSInvoice.submit()`/`POS Closing Entry.submit()` (cơ chế ghi sổ GL an toàn
  riêng của POS trong ERPNext).
- ERPNext's `Company` doctype khi tạo MỚI (tự bootstrap chart-of-accounts, gọi
  `frappe.db.commit()` nội bộ).
- `financial_control.py`'s `void_transaction()` (có chủ đích, đảm bảo hủy
  POS Closing Entry/Payment Entry không rollback dở dang).

**Hậu quả nếu không biết**: fixture test dùng tên CỐ ĐỊNH (Price List, Company,
Property...) trùng với file test khác sẽ để lại rác VĨNH VIỄN trên site,
khiến các lần chạy SAU đó crash "Duplicate entry" — đã xảy ra thật nhiều lần,
mỗi lần phải `bench reinstall` toàn bộ site + cài lại 3 app.

**Quy tắc bắt buộc khi viết test đụng tới các luồng trên**:
1. Dựng fixture (company/property/price-list/account) **hoàn toàn riêng**,
   không tên nào trùng bất kỳ file test khác (xem `run_pos_reports_tests.py`'s
   `fixture()` — Company `'POS Report Test Co'`, Property `'PRT-TEST'` — làm
   mẫu).
2. Bất kỳ Single doctype TOÀN SITE nào bị test đó cấu hình
   (`Hospitality Accounting Settings` là ví dụ điển hình — đọc bởi
   `accounting.py`'s hàm ghi GL Legacy) phải được **gán lại KHÔNG điều kiện**
   theo company hiện tại mỗi lần dùng — dùng lại helper
   `run_docker_verification.py`'s `ensure_legacy_accounting_settings(company)`,
   KHÔNG viết kiểu "chỉ điền nếu còn trống".
3. KHÔNG BAO GIỜ chạy các file test loại này SONG SONG (2 tiến trình cùng lúc)
   — đã gây deadlock/lỗi rải rác giả do tranh chấp khóa DB. Luôn chạy TUẦN TỰ.

### 4.5. Flake múi giờ "ngay sau nửa đêm giờ site" (Asia/Ho_Chi_Minh)

**Triệu chứng**: `KeyError: 'Waste'`/`KeyError: 'Buffet'` hoặc lệch ngày 1 hôm
trong vài test F&B Cost Control (dùng `nowdate()` để tính khung ngày truy vấn).

**Nguyên nhân**: container chạy đúng vào khung giờ ngay sau 00:00 giờ hệ thống
— `frappe.utils.nowdate()` (theo lịch) đã sang ngày mới, nhưng
`api/fnb/common.py`'s `business_date()` (có cutoff riêng cho "ngày kinh doanh"
khách sạn) vẫn còn tính là ngày hôm trước. Đây là timing flake tồn tại từ
trước, không phải hồi quy do code sửa gần đây.

**Xử lý**: chạy lại sau khi qua giờ cắt ngày kinh doanh cấu hình (mặc định
thường vài giờ sau nửa đêm). Không cần sửa code.

### 4.6. C: drive đầy khiến Docker Desktop crash

**Triệu chứng**: `docker compose` báo lỗi kết nối, Docker Desktop tự tắt/không
khởi động lại được sau khi máy host cạn dung lượng ổ hệ thống.

**Xử lý AN TOÀN** (chỉ dọn cache/temp, KHÔNG đụng data thật):
```powershell
# Dọn cache package manager (an toàn, tự tải lại khi cần)
npm cache clean --force
yarn cache clean
pnpm store prune
dotnet nuget locals all --clear

# Dọn Windows Temp (KHÔNG dùng Remove-Item -Recurse trên toàn bộ %TEMP% nếu
# có phiên Claude Code/công cụ khác đang chạy — có thể xóa nhầm thư mục
# scratch đang dùng của chính phiên đó)
```
KHÔNG đụng: thư mục dữ liệu Docker Desktop's own (`\wsl$`/VHDX), dữ liệu ứng
dụng khác (Claude Desktop, Zalo...), `pagefile.sys` (đổi kích thước pagefile
là "modifying system settings" — cần người dùng tự làm).

Sau khi dọn xong, khởi động lại Docker Desktop (thường cần chấp thuận UAC thủ
công) rồi `docker compose -f docker-compose.dev.yml up -d`.

### 4.7. Vòng đời hủy chứng từ — pattern chung khi thêm hàm tạo GL Entry mới

Nếu viết thêm 1 doctype/hook mới tự tạo `GL Entry` thô (không qua
`make_gl_entries()` chuẩn), PHẢI:
- Thêm cặp field `debit_in_account_currency`/`credit_in_account_currency`
  (không chỉ `debit`/`credit`) — ERPNext's `get_balance_on()` tính theo cặp
  field "_in_account_currency", thiếu sẽ khiến số dư LUÔN ra 0.
- Nếu doctype cha là **POS Invoice**: thêm doctype đó vào
  `ignore_linked_doctypes` của chính POS Invoice qua 1 hook `on_cancel` đăng
  ký SAU CÙNG trong `hooks.py` (xem
  `accounting.py`'s `allow_cancel_of_pos_invoice_with_manual_gl_entries`) —
  `POSInvoice.on_cancel()` (ERPNext core) tự đặt lại danh sách này, không kế
  thừa `SalesInvoice.on_cancel()`'s danh sách đầy đủ.
- GL Entry giữ `docstatus=1` VĨNH VIỄN (chỉ đổi `is_cancelled`) — mọi doctype
  tự tạo GL Entry thô cần tự thêm `"GL Entry"` vào
  `self.ignore_linked_doctypes` trong chính `on_cancel()` của nó, nếu không sẽ
  không bao giờ hủy được (`LinkExistsError`).

---

## 5. Checklist migrate/nâng cấp

```bash
# 1. Backup trước (bắt buộc, xem mục 3)
bench --site localhost backup --with-files

# 2. Cài app mới (nếu site chưa có vietnam_einvoice)
bench --site localhost install-app vietnam_einvoice

# 3. Build asset (JS/CSS mới)
bench build --app hospitality_core --app vietnam_einvoice

# 4. Migrate — tự động chạy after_migrate: property_v2.py (bootstrap Property
#    v2 schema, GỌI KÈM setup_einvoice_fields()/create_ledger_adjustment_doctype()
#    bên trong) rồi fnb_v1.py (F&B Cost Control schema)
bench --site localhost migrate

# 5. Nếu đang UPGRADE từ schema Room Rate Plan CŨ (rate/valid_from/valid_to
#    đơn giản) sang schema Season+LOS mới — chạy 1 LẦN, idempotent, an toàn
#    lặp lại:
bench --site localhost execute hospitality_core.migrations.rate_plan_v2.execute
```

**Lưu ý "Orphaned DocType"**: `bench migrate`'s `remove_orphan_doctypes()` sẽ
**TỰ ĐỘNG XÓA** bản ghi DocType khỏi DB nếu `get_controller()` không tìm thấy
đúng class Python tương ứng — kể cả DocType đã tồn tại từ trước, không phải
mới. Nguyên nhân thường gặp: sai quy tắc đặt tên class (Frappe suy ra tên
class bằng cách CHỈ bỏ khoảng trắng khỏi DocType name, KHÔNG tự viết hoa —
VD DocType "Lost and Found Item" phải có class `LostandFoundItem`, không phải
`LostAndFoundItem`). Nếu sau `migrate` thấy log "Orphaned DocType(s) found" —
dừng lại, kiểm tra tên class TRƯỚC KHI migrate lần nữa (lần 2 sẽ xóa thật nếu
không sửa).

---

## 6. Liên hệ / Tài liệu tham khảo khác

- Nghiệp vụ Lễ tân/Đặt phòng: [`01_le_tan_va_dat_phong.md`](01_le_tan_va_dat_phong.md)
- Nghiệp vụ Buồng phòng/Bảo trì/F&B: [`02_buong_phong_bao_tri_pos.md`](02_buong_phong_bao_tri_pos.md)
- Nghiệp vụ Kế toán/Đêm kiểm toán/Báo cáo: [`03_ke_toan_dem_kiem_toan_bao_cao.md`](03_ke_toan_dem_kiem_toan_bao_cao.md)
- Hóa đơn điện tử (chi tiết provider/config): [`erpnext_vietnam_einvoice/docs/`](../../../erpnext_vietnam_einvoice/docs/)
- F&B Cost Control (chi tiết kỹ thuật nội bộ): [`docs/fnb_cost_control_implementation_2026_09_08.md`](../fnb_cost_control_implementation_2026_09_08.md)
