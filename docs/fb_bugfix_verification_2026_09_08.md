# Kiểm tra lỗi F&B — 08/09/2026

Phạm vi: sửa các lỗi đã xác minh trong xuất nguyên liệu, tồn cuối ngày, ước tính giá vốn và ghi hàng trực tiếp vào Folio. Chưa triển khai module F&B Cost Control đầy đủ. Không sửa chứng từ production hoặc tự bù tồn lịch sử.

## Nguyên nhân và bản sửa

| Lỗi đã xác minh | Bằng chứng và phạm vi sửa tối thiểu |
|---|---|
| Hai dòng cùng món xuất thiếu nguyên liệu | Khóa cũ chỉ dùng hóa đơn + món. `composite_item_utils.py` thêm mã dòng nguồn và loại hóa đơn, khóa dòng hóa đơn trước khi kiểm tra/ghi. `composite_item_setup.py` thêm Custom Field `Stock Entry.custom_source_invoice_item`. Nguồn cũ thiếu mã dòng bị chặn khi retry để đối soát. |
| Quy đổi nguyên liệu hai lần | Lượng lấy từ BOM.stock_qty nhưng còn mang UOM/hệ số cũ. Nay Stock Entry nhận stock UOM và hệ số 1. Giữ ngày giờ chứng từ bằng set_posting_time. |
| Tồn cuối ngày lấy tồn hiện tại/lặp kho | `sales_report.py` thay Bin bằng các Item có Stock Ledger tới to_date_time, dùng get_stock_balance tại thời điểm đó, gom các POS Profile chung kho. |
| Giá vốn chỉ có tổng mẻ, không rõ kho/currency | `item_recipe.py` tính server từ định giá kho tại thời điểm chọn; chia theo Quantity Produced; trả currency của Company sở hữu kho. JS dùng hộp thoại chuẩn Frappe, bỏ phản hồi cũ và chặn công thức chưa lưu. |
| Thiếu quy đổi vẫn mặc định 1 | Chặn khi thiếu UOM conversion; kiểm tra sản lượng và lượng nguyên liệu dương, hữu hạn. |
| Ghi Item tồn kho trực tiếp vào Folio không xuất kho | `folio_transaction.py` chặn giao dịch mới không có nguồn; `guest_folio.py` gọi cùng kiểm tra khi lưu bảng con. Dùng POS chuyển phí vào Folio. Không bật lại hàm deduct_inventory cũ vì chưa có vòng đời hủy/split đầy đủ. |

## Kiểm tra đã thực hiện

- Site riêng `hospitality-v2.test`, MariaDB và ERPNext thực; dữ liệu từng ca được rollback.
- `tools/run_fb_integration.py`: 9 ca đạt sau review (8 ca chạy cùng lượt, ca Delivery Note bổ sung chạy riêng). Bộ test dùng fixture Company/đặt phòng trong `run_property_integration.py`; thêm main guard để import không tự chạy toàn bộ suite khác.
- Hóa đơn bán 2 + 3 suất cùng món, công thức 500 g cho 2 suất: xuất đúng 1,25 kg; tồn 10 → 8,75; retry không đổi; hủy về 10. Stock Entry submit và Stock Ledger thật.
- Tồn hôm trước 10, nhập thêm 5 hôm sau: báo cáo chốt hôm trước vẫn 10 và kho chỉ xuất hiện một lần khi hai POS Profile cùng kho. Riêng ánh xạ hai tên POS Profile dùng mock; Stock Ledger và hàm tồn theo thời điểm là thật.
- Công thức 500 g, giá kho 100.000/kg, sản lượng 2: chi phí mẻ 50.000 VND, mỗi suất 25.000 VND. Thiếu quy đổi bị từ chối.
- Ghi hàng thẳng vào Folio bị từ chối cả khi insert child trực tiếp và lưu qua parent.
- 38 ca Python hồi quy đạt. Test JS giá vốn và rate preview đạt. Parse JS bằng `new Function(...)`, Python AST và `git diff --check` đạt.
- Test Guest 360 hiện lỗi mock thiếu `flt`, ngoài phạm vi F&B; không sửa mã Guest 360 trong đợt này.

## Chưa xác minh / triển khai

- Chưa chạy UI POS trên trình duyệt thật; JS giá vốn được kiểm tra bằng Node VM. CSS dùng dialog chuẩn Frappe, không sửa CSS; PHP không áp dụng.
- Chưa stress-test hai worker đồng thời; chống trùng hiện dựa trên khóa hóa đơn và locking read.
- Chưa nghiệm thu hoàn hàng sau thay đổi công thức, BOM nhiều tầng và batch/serial. Đã kiểm tra đơn vị bán khác đơn vị tồn: 1 gói = 2 phần.
- Chưa mở luồng xuất kho riêng từ Folio; biện pháp hiện tại chặn giao dịch thiếu nguồn để tránh lệch kho.
- Chưa sửa/bù tồn sai trong chứng từ cũ. Cần đối soát riêng trước mọi điều chỉnh lịch sử.
- Khi đưa mã lên site đích phải chạy migration để tạo Custom Field mã dòng nguồn trước khi sử dụng hook mới. Migration đã nối script schema; chỉ chạy cập nhật schema trên site test trong đợt này.

Mức chắc chắn: cao với các ca cụ thể đã qua database; chưa đủ để tuyên bố toàn bộ chu trình F&B đã nghiệm thu production.

## Review bổ sung cùng ngày

Bốn ca mới đã tái hiện lỗi trước khi sửa trên database thật:

| Nguyên nhân đã xác minh | Bằng chứng trước sửa | Phạm vi sửa tối thiểu và xác minh sau sửa |
|---|---|---|
| Hook dùng invoice item.qty thay vì stock_qty | Bán 1 gói = 2 phần, tồn 9,75 thay vì 9,5 kg | `composite_item_utils.py` truyền stock_qty do ERPNext tính; test bán đúng 0,5 kg và hủy hoàn về 10 kg. |
| Hủy phụ thuộc cờ composite hiện tại | Sau bỏ cờ qua Item.save, hóa đơn hủy nhưng tồn vẫn 8,75 kg | Nhánh hủy dò Stock Entry đã liên kết nguồn trước khi kiểm tra Item Master; test tồn về 10 và không còn phiếu xuất submit của hóa đơn. |
| Guard Folio bỏ qua mọi dòng cũ | Lưu dịch vụ rồi đổi thành FB-RAW qua parent.save vẫn thành công | `folio_transaction.py` so sánh dữ liệu đã lưu; kiểm tra lại dòng thay đổi và khóa mặt hàng/số lượng/nguồn của dòng tồn kho. Dòng lịch sử không đổi vẫn lưu được. |
| Hóa đơn submit được coi là đã xuất hàng | Sales Invoice update_stock=0, không Stock Ledger vẫn được Folio chấp nhận | Với stock item, kiểm tra Stock Ledger không bị hủy theo dòng hóa đơn hoặc dòng Delivery Note liên kết. Test không có xuất kho bị chặn; có xuất kho hoặc Delivery Note thật được chấp nhận. |

Không thay đổi chứng từ lịch sử hoặc production. Các phép tái hiện và test mới dùng site cô lập, rollback sau từng ca. Các lỗi timestamp ở lượt thử ban đầu được xác định là fixture giữ Item/Folio cũ sau hook cập nhật; đã reload trước thao tác để kiểm tra đúng nghiệp vụ, không vá ứng dụng theo lỗi fixture.

Đã chạy lại 38 test Python, hai file test JS giá vốn/preview, Python AST, JS `new Function(...)` và `git diff --check`. Chưa kiểm tra quyền của từng vai trò POS trên trình duyệt, stress đồng thời, hoặc toàn bộ vòng đời hoàn hàng/split/routing; các ca nguồn Folio mới được kiểm tra trong luồng legacy.
