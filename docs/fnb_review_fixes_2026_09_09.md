# Sửa lỗi review F&B ngày 09/09/2026

Phạm vi: 12 mục review trong task; không sửa số dư/chứng từ lịch sử, không kích hoạt production.

## Nguyên nhân và phạm vi sửa

| Mục | Bằng chứng và xử lý |
|---|---|
| 1 | SLE/Bin không đi qua điều kiện kho. Thêm quyền đọc document/list theo Warehouse Control; kiểm tra file đính kèm nguồn tương ứng. |
| 2 | Guard chỉ xét report tham chiếu SLE. Bổ sung toàn bộ module Stock, cả Prepared Report. Chỉ tin bộ lọc Company/Warehouse của Stock Balance, Stock Ledger, Stock Projected Qty đã đối chiếu; report khác bị chặn nếu có kho ngoài quyền. |
| 3 | Nhánh Issue của POS bỏ qua Delivery Note. Không tạo Issue khi dòng có cả delivery_note và dn_detail; ERPNext tiếp tục kiểm tra liên kết giao hàng. |
| 4 | Repost không xét ngày khóa F&B. Kiểm tra lúc submit và trước worker chuyển In Progress; phạm vi Company do định giá lan qua chuyển kho/sản xuất. Kiểm kê không bắt đầu khi còn job định giá. |
| 5 | Đính chính review: Receipt thường bị ERPNext buộc cùng UOM/currency với PO; return được phép khác UOM. Lỗi xác minh thêm: dung sai xét riêng từng dòng và không kiểm tra lại lúc submit. Cộng theo dòng PO dưới khóa database, quy giá/lượng theo conversion factor, kiểm tra lại trước submit. |
| 6–7 | Pause chặn nhận nốt/return/waste nhưng deactivate không xét trung chuyển. Cho phép xử lý các nghiệp vụ tồn đọng khi pause, chặn deactivate tới khi nhận đủ hàng. |
| 8 | Outlet enabled có thể sửa trực tiếp sau deactivate. Chặn thay đổi trên hồ sơ đã lưu, cung cấp activate_outlet kiểm tra cấu hình và công thức. |
| 9 | on_update chỉ thêm mapping mới. Khóa đổi kho trên cấu hình đã tạo để không sinh thêm mapping tồn dư. Không tự xóa mapping lịch sử hoặc mapping cũ chưa xác minh. |
| 10 | Đếm chỉ lấy Bin và cấm dòng ngoài snapshot. API add_found_item lấy baseline phía server, ghi người/lý do, bắt hai lượt đếm lại. Giá hàng mới chưa có giá sổ cần người duyệt nhập rõ; lưu trong chứng từ Stock Reconciliation. |
| 11 | Batch chọn tường minh không kiểm tra tổng. Cộng theo Item/batch rồi đối chiếu tồn khả dụng trước tạo Stock Entry, độc lập với cờ cho phép âm kho của ERPNext. |
| 12 | Không có điều chỉnh vật lý của POS return. Thêm Return Correction vào FNB Waste Record: nguồn là sự kiện Return POS, cần người khác duyệt, giới hạn Item/lô/lượng chưa điều chỉnh, khóa chống trùng, tạo Material Issue. Giữ nguyên phần tiền của POS return. |

## Giao diện

Thêm nút pause/resume/deactivate/activate outlet và khai báo hàng tìm thấy. Dùng dialog Desk, kiểm tra tên/modified/dirty trước gửi callback. Không có PHP; CSS app chỉ tác động bản in, không cần sửa CSS dialog.

## Kiểm chứng

- Bộ nền `run_fnb_control_integration.py`: 16/16 qua database trong lượt sửa.
- Bộ mới `run_fnb_review_regressions.py`: lần ổn định đầu 9/9 qua. Lượt cuối có 10 ca: 9 qua, ca quyền dừng ở fixture Account với QueryDeadlockError (1020), trước khi chạy mã kiểm tra quyền. Cùng lúc có tiến trình test Folio trên cùng site.
- Chạy lại ca quyền và bộ procurement bị fixture dùng chung chặn ở `preview.selling_price_list != Integration Selling`; fixture này đã thay đổi bởi luồng khác trong lúc làm việc. Đã dừng đúng tiến trình procurement của task này để tránh tiếp tục tranh chấp site; chưa có kết quả bộ procurement cuối.
- `tests/fnb_control.test.cjs`, parse JS bằng `new Function`, JSON schema và `git diff --check` đã qua.
- Python F&B và script regression đã compile thành công.

Giới hạn: chưa kiểm tra giao diện bằng trình duyệt thật, HTTP/export/file end-to-end và đua nhiều worker của các patch mới. Ca POS + Delivery Note hiện kiểm tra nhánh tiêu hao với dependency kho được mock; không thay thế nghiệm thu cả form Delivery Note → POS. Site test đang được task khác sử dụng nên phải phân biệt lỗi môi trường khi chạy lại. Không tuyên bố toàn bộ Cost Control đã được nghiệm thu production.
