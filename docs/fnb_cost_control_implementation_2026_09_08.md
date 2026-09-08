# F&B Cost Control — triển khai và giới hạn nghiệm thu

Ngày kiểm tra: 08/09/2026. **Chưa phát hành cho vận hành thực tế.**

## Nền mã và phạm vi

- Nền đầu đợt: `59b5b6fcf921fa27ddcd23499ee8faf0d587203a`.
- Trong lúc triển khai, workspace nhận thêm các commit `bf43e50`, `f172d9a`, `45a123e` từ luồng khác. Các thay đổi đó được giữ nguyên. Nhánh F&B trong `pos_bridge.py` đã nằm trong commit `45a123e`.
- ERPNext được đọc trực tiếp trong workspace: 16.34.1.
- Database kiểm thử: site riêng `hospitality-v2.test`, container `hospitality-v2-test`. Chưa ánh xạ hoặc kích hoạt dữ liệu production.
- Tên kỹ thuật dùng `FNB`, giao diện dùng F&B; tên controller DocType cần là định danh Python hợp lệ.

## Đã có trong mã

| Phần | Cơ chế hiện tại |
|---|---|
| Cấu hình | 19 DocType mới; Settings theo Property, Outlet và mapping POS/kho; kiểm tra Company, tài khoản, cost center; không suy cơ sở từ tên kho hoặc user default. |
| Quyền | Mở rộng phạm vi chứng từ FNB và các chứng từ mua/kho; kiểm tra quyền ở API; quyền đọc/list Warehouse dùng mapping FNB Warehouse Control. |
| Công thức | Phiên bản có khoảng hiệu lực, phê duyệt khác người lập, BOM và snapshot; dừng ở bán thành phẩm có tồn; công thức con dùng snapshot đã duyệt. Nhập mẫu thành bản địa phương Draft, khóa nguồn chống nhập trùng. |
| Nhu cầu | Đề xuất từ định mức món có tồn và thực đơn phiên; hiển thị khả dụng, yêu cầu còn chờ, hàng đang giao, tồn kho tổng và thiếu mua. Người dùng xác nhận để tạo Material Request Purchase hoặc Material Transfer. |
| Cấp/nhận | Duyệt nội dung MR/PO/PR; chuyển qua kho Transit bằng Stock Entry chuẩn; giao và nhận từng phần có khóa nguồn; người nhận khác người xuất. Phiếu giao chuẩn hóa về stock UOM để tránh trộn đơn vị trong nhận từng phần của ERPNext. |
| Bếp | Phiếu phục vụ, gửi bếp, chế biến/phục vụ/hủy từng phần; giữ hàng tồn; chế biến theo snapshot tạo Material Issue; mẻ tạo Manufacture. Có mẫu in FNB Kitchen Ticket. |
| POS | Phân bổ dòng phiếu bếp vào dòng hóa đơn, kiểm tra lượng phục vụ còn lại; món đã xuất từ bếp không xuất lại; Stock Item qua POS xuất ngay bằng Stock Entry; Sales Invoice trực tiếp dùng SLE native. |
| Hợp nhất POS | Đối chiếu Merge Log, POS/dòng nguồn, Company/currency/Property và lượng. Không xuất lại kho ở Sales Invoice hợp nhất. Luồng FNB mới không dùng công thức thuế cố định 1.225 hoặc hook chuyển doanh thu POS sang cấu hình Single. |
| Staff/complimentary | Cần người hưởng và người duyệt khác người lập; có xuất kho kể cả hàng có tồn; kết thúc phiếu khi phục vụ đủ, không tạo hóa đơn doanh thu giả. |
| Buffet/tiệc | Phiên có thực đơn chuẩn mỗi suất, khách dự kiến/thực dùng, ngân sách; cấp thực tế, bổ sung, thu hồi theo nguồn. API sử dụng quyền lợi bữa sáng từng phần. |
| Hao hụt/hoàn | Mất hàng tồn tạo Material Issue; bỏ món đã chế biến chỉ phân loại lại chi phí; thu hồi phiên có kiểm tra nguồn/lượng/lô. Hoàn tiền tách khỏi hoàn vật lý; hoàn vật lý cần duyệt. |
| Kiểm kê | Khóa warehouse bằng row lock, chặn submit/cancel qua hook; snapshot tồn có permlevel riêng; hai lượt đếm khác người, duyệt khác người lập/đếm đầu; sinh Stock Reconciliation, mở khóa có lý do. |
| Báo cáo | Tổng hợp từ SLE bản vị, không cộng lại chuyển kho/sản xuất; phân loại staff/complimentary/buffet/waste; giá chuẩn công thức, chi phí/suất và chênh lượng của phiên. Doanh thu dùng cùng khoảng ngày kinh doanh với tiêu hao. |
| Giao diện | Workspace/page F&B, hàng đợi, form và dialog nghiệp vụ; chọn lượng giao/nhận, phân bổ phiếu bếp, lập nhu cầu; chống phản hồi cũ và thao tác khi form chưa lưu. |

## Điều chỉnh thiết kế sau khi đọc ERPNext

`POS Invoice.on_submit()` của ERPNext 16.34.1 không tự ghi SLE/GL như giả định trong chú thích cũ của app. Vì vậy FNB v1 dùng Stock Entry chuẩn để ghi kho tức thời cho Stock Item qua POS, đặt `update_stock=0` và để Sales Invoice hợp nhất ghi nhận doanh thu. Test thật phải kiểm tra cả trước và sau hợp nhất; chỉ kiểm tra POS submit là chưa đủ.

Trong chuyển hàng qua Transit, native mapper gán UOM của Material Request vào trường tạm `stock_uom`, còn lượng đã nhận được cập nhật bằng `transfer_qty`. FNB lấy stock UOM từ Item Master và chuẩn hóa phiếu giao về hệ số 1. MR vẫn giữ UOM yêu cầu ban đầu.

## Các điều kiện vẫn chưa đủ để nghiệm thu toàn bộ kế hoạch

Các mục dưới đây là phần **chưa hoàn tất hoặc chưa được xác minh**, không được suy từ việc đã có schema/API:

1. Kiểm thử đồng thời bằng hai connection/worker: hai POS tranh tồn cuối, hai lần chế biến, hai lần nhận, bắt đầu kiểm kê cùng submit.
2. Ma trận mua hàng đầy đủ: nhiều dòng cùng PO, nhận vượt/thiếu, UOM và currency khác nhau, trả nhà cung cấp, Landed Cost, cảnh báo giá mua và giá chuẩn theo kỳ.
3. Kiểm thử VND/USD, POS Guest Account → Folio/master Folio → thu tiền và GL; hợp nhất hóa đơn hoàn, hủy sau hợp nhất và đối soát tài khoản nhận tiền. Test POS tiền mặt chưa thay thế các ca này.
4. Kiểm tra mọi báo cáo SQL native/export/file và các đường stock/valuation job; đối soát GL/SLE đầy đủ, không chỉ tổng giá trị SLE.
5. Kiểm kê Item/lô phát hiện thực tế nhưng chưa có trong snapshot; phân biệt rõ các quyền xem tồn ngoài màn hình đếm; nghiệp vụ hàng hết hạn và lô bị khóa.
6. Hoàn thiện wizard kiểm tra sẵn sàng, kiểm kê đầu kỳ và dữ liệu mapping có xác nhận trước cutover. Hiện API activate có cổng cấu hình site, nhưng chưa thay thế toàn bộ checklist này.
7. Báo cáo chênh lệch lượng/giá/yield đầy đủ, Food/Beverage theo nhóm, mua hàng/nhà cung cấp/hạn dùng; phiên bản đối soát lại sau định giá lại kỳ đã chốt.
8. Nhận chuyển giữa hai Property cùng Company theo cả hai chiều phân tích; luồng hiện có phục vụ cấp kho tổng → outlet trong một Property.
9. Nghiệm thu browser/CSS/màn hình hẹp, in thực tế và người dùng hoàn tất từ yêu cầu mua đến chốt kỳ. PHP không áp dụng.

`fnb_release_verified` và `fnb_period_close_verified` là cổng chặn sử dụng trước nghiệm thu. Không bật trên site vận hành chỉ vì các test con đã qua. Không tự tạo tỷ lệ thương mại, tài khoản hay mapping thật.

## Cách kiểm tra

Chỉ trên site test riêng:

```text
docker exec -w /home/frappe/test-bench/sites hospitality-v2-test /home/frappe/test-bench/env/bin/python /source/hospitality_core/tools/run_fnb_control_integration.py
docker exec -w /home/frappe/test-bench/sites hospitality-v2-test /home/frappe/test-bench/env/bin/python /source/hospitality_core/tools/run_fb_integration.py
python -m unittest discover -s tests -p test_*.py
node --test tests/fnb_control.test.cjs tests/recipe_cost.test.cjs tests/rate_preview.test.cjs
git diff --check
```

Khi thay đổi hooks/schema, đồng bộ site và xóa cache trước khi chạy. Không sửa mã đang được tiến trình test nạp. Kiểm tra Python AST, parse JS bằng `new Function(...)` và parse JSON bổ sung cho test hành vi.

## Kết quả được xác minh

- 38 test Python hồi quy và 3 file test JS: qua.
- AST 49 file Python thuộc FNB và parse 19 schema: qua.
- `new Function(...)` cho hai file JS FNB và `git diff --check`: qua.
- Bộ database mới: **16/16 qua, 192,723 giây**, log `/home/frappe/test-bench/logs/fnb-control-full.log`. Bao gồm phiếu bếp/phân bổ, staff, giữ hàng, quyền chéo cơ sở, công thức/import/snapshot con, mẻ, hao hụt, phiên/thu hồi, kiểm kê thường/lô, duyệt MR, chuyển từng phần khác UOM, hoàn vật lý SI, POS tiền mặt và hợp nhất.
- 9 ca database F&B cũ đã được kiểm tra lại qua hai lượt: 6 ca đầu qua trước khi tiến trình bị chủ động ngắt để lấy stack; 3 ca còn lại chạy riêng đều qua trong 32,903 giây. Lượt đầu ở `/home/frappe/test-bench/logs/fnb-legacy-final.log` có `KeyboardInterrupt` trong quá trình dựng fixture ca thứ 7, không phải kết quả 9/9 của một lượt hoàn chỉnh. Không phát hiện assertion thất bại trong 9 ca này.
- ERPNext phát cảnh báo deprecation cho đường tương thích batch cũ; ca kiểm kê batch vẫn qua. Cần kiểm thử thêm và chuyển dần sang Serial and Batch Bundle native trước phát hành dài hạn.
- Chưa chạy nghiệm thu browser hay production pilot.
