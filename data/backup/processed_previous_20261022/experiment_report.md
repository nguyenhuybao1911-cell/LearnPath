# Báo cáo đánh giá LearnPath

- Target cố định trước test: `K_系统启动_计算机科学与技术`.
- Test cutoff: `2020-08-27T08:12:18.000000+00:00`; cửa sổ ground truth: 14 ngày.
- K = 5; Precision@K chia cho `min(K, độ dài route)`; ground truth rỗng cho metric ranking = NA.
- Target chỉ chọn từ graph prerequisite; learner state tại cutoff chỉ dùng các tương tác có timestamp nhỏ hơn cutoff.
- Nhánh kế hoạch giả định concept đã thêm được hoàn thành; không cập nhật mastery quan sát.
- Các tương tác tương lai không quan sát không được coi là bằng chứng concept không hữu ích. Kết quả lịch sử không chứng minh learning gain.
- Random Eligible chạy nhiều seed; báo cáo độ lệch chuẩn giữa learner và giữa các seed ở các cột riêng.
- Fixed Eligible chọn ID nhỏ nhất trong tập hợp lệ hiện tại; Random Eligible chọn ngẫu nhiên trong cùng tập; Best-First dùng cấu hình khóa từ validation.
