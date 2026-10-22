# Kế hoạch xử lý dữ liệu MOOCCubeX cho Ngày 2

**Mục tiêu:** Tải và xử lý tập tối thiểu của miền Computer Science từ nguồn chính thức để tạo dữ liệu đầu vào thật cho learner state, đồ thị prerequisite và thuật toán tìm lộ trình.

## Phạm vi file

| File | Vai trò | Bắt buộc |
|---|---|---|
| `entities/concept.json` | ID và tên concept | Có |
| `relations/concept-problem.txt` | Nối bài tập với concept | Có |
| `prerequisites/cs.json` | Cạnh prerequisite CS đã chú thích | Có |
| `relations/user-problem.json` | Lịch sử làm bài theo người học | Có |

`user-problem.json` phải tải vì ba file còn lại không chứa kết quả, thời gian hay người học. Endpoint chính thức không cung cấp bản lọc CS phía máy chủ, nên pipeline sẽ đọc tuần tự file khoảng 21 GB và chỉ giữ interaction nối được với bài thuộc phạm vi CS.

## Trình tự thực hiện

- [x] Tải ba file metadata nhỏ trước, có resume bằng file `.part`.
- [x] Kiểm tra định dạng, schema mẫu, ID concept và chiều cạnh prerequisite.
- [x] Tải `user-problem.json`, tiếp tục từ `.part` nếu mạng ngắt.
- [x] Lưu URL, dung lượng thật và SHA-256 vào manifest nguồn.
- [x] Chạy pipeline theo luồng; không nạp toàn bộ JSON vào RAM và không tạo bản sao raw 21 GB.
- [x] Xuất các bảng chuẩn hóa, file rejected/unmatched, temporal split và `data_summary`.
- [x] Kiểm tra tỷ lệ join, multi-concept, duplicate/retake, timestamp và tính toàn vẹn đồ thị.
- [x] Nạp PostgreSQL hai lần để xác nhận import idempotent, rồi kiểm tra API đọc learner state và recommendation.
- [x] Cập nhật `docs/data_audit.md` và README bằng số liệu thật.
- [x] Xóa đúng bốn file raw sau khi toàn bộ cổng kiểm tra trên đạt; giữ manifest và dữ liệu đã xử lý để truy xuất nguồn và chạy demo.

## Cổng an toàn trước khi xóa raw

Chỉ xóa raw khi đồng thời thỏa các điều kiện:

1. Không còn file `.part` và checksum đã được lưu.
2. Pipeline kết thúc thành công, các output bắt buộc tồn tại và đọc được.
3. `data_summary` ghi số dòng từng bước và tỷ lệ join thực tế.
4. PostgreSQL import thành công và lần import thứ hai không tăng số dòng.
5. API trả được danh sách learner/concept và một kết quả recommendation kiểm tra.
6. Báo cáo audit ghi đủ nguồn, schema, ví dụ đã ẩn ID, lỗi loại bỏ và giới hạn.

Nếu bất kỳ cổng nào không đạt, giữ raw để sửa và chạy lại. Khi xóa, xác minh đường dẫn tuyệt đối nằm trong `data/raw/mooccubex` và xóa từng file bằng tên cố định.

## Giới hạn dung lượng

Payload thực tế được xóa sau xử lý để giải phóng khoảng 22.7 GB. Không tải các domain math/psy hoặc các bảng MOOCCubeX không dùng cho demo.
