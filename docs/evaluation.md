# Thiết kế thực nghiệm

## Chia thời gian và tránh rò rỉ

Pipeline chia tương tác theo timestamp, không theo dòng. Timestamp bằng nhau không bị tách qua hai split. Train dùng để tính độ khó; validation chọn `tau`, số tương tác tối thiểu và trọng số; test chỉ chạy với cấu hình `experiment_config.json` đã khóa trên validation. Learner state tại cutoff chỉ tổng hợp sự kiện có `submitted_at < cutoff`. Target phải truyền cố định trước test hoặc được chọn từ graph prerequisite mà không xem tương lai.

Ground truth là tập concept xuất hiện trong cửa sổ tương lai `horizon_days` sau cutoff, trong split validation hoặc test tương ứng. Sự kiện tương lai không quan sát được không có nghĩa concept đó vô ích. Nếu ground truth rỗng, Precision/Recall/NDCG là NA và learner đó không tham gia grid tuning. Kết quả có route ngắn hơn K dùng số bước thực có cho mẫu số Precision; Recall chia tổng concept ground truth.

## Phương pháp so sánh

- **Fixed Eligible** chọn ID concept nhỏ nhất trong các ứng viên hợp lệ ở mỗi bước.
- **Random Eligible** chọn ngẫu nhiên trong đúng tập ứng viên hợp lệ; chạy nhiều seed được cấu hình.
- **Best-First + Heuristic** sử dụng graph, learner state, giả định hoàn thành trong kế hoạch và cấu hình được chọn trên validation.

Cả ba dùng cùng target, learner state, tập concept tổ tiên, prerequisite cứng và giả định một bước kế hoạch đã hoàn thành. Fixed/Random là baseline tham lam từng bước; Best-First dùng OPEN giữ nhánh trạng thái. `expanded_states` của Best-First là số trạng thái lấy khỏi OPEN; baseline là số lựa chọn eligible được thực hiện, vì vậy runtime và số mở rộng cần đọc với định nghĩa vận hành này.

## Chỉ số

- Path ranking: Precision@K, Recall@K, NDCG@K.
- Constraint: tỷ lệ prerequisite bị vi phạm trên các cạnh prerequisite của các bước; pipeline giữ lộ trình hợp lệ nên chỉ số dự kiến bằng 0.
- Khả năng hoàn thành target: tỷ lệ `reached` hoặc `target_already_mastered`.
- Hiệu năng: runtime và số trạng thái mở rộng.
- Xếp hạng bước tiếp theo được ghi riêng trong `summary_next_step.csv`; không gộp chung với metric cả lộ trình.

Tóm tắt báo cáo độ lệch chuẩn giữa learner và giữa seed Random riêng. Các dòng per-learner giữ `run_seed` để có thể tái lập.

## Giới hạn diễn giải

Tương tác tiếp theo bị chi phối bởi lựa chọn người học, nội dung khóa học và khả năng quan sát. Đây là đánh giá hồi cứu thứ tự/lộ trình, không phải thử nghiệm có đối chứng về kết quả học. Nó không chứng minh thuật toán cải thiện điểm số hoặc việc học.

## Kết quả thực nghiệm đã chạy

Kết quả được sinh từ payload MOOCCubeX đã tải và pipeline tại `data/processed/`; không dùng dữ liệu giả. Split theo thời gian có 1,258 train, 270 validation, 270 test. Test gồm 373 learner có lịch sử trước test cutoff. Cửa sổ ground truth là 14 ngày, `K=5`, seed 42 và 20 seed Random.

Target được khóa trước khi xem test: trong các concept có interaction train, chọn concept có tập prerequisite ancestor lớn nhất theo graph; hòa thì chọn ID tăng dần. Target là `K_系统启动_计算机科学与技术` với 88 concept trong closure. Validation chọn `tau=0.5`, tối thiểu 1 interaction, trọng số `(wP,wN,wD,wR)=(0,0.1,0.4,0.5)`. NDCG@5 trên validation bằng 0.0 với 5 learner có ground truth; điểm bằng nhau nên tie-break cấu hình, không phải bằng chứng trọng số có ưu thế.

| Phương pháp | Precision@5 / Recall@5 / NDCG@5 (learner có ground truth) | Vi phạm prerequisite | Đạt mục tiêu | Runtime trung bình (ms) | Trạng thái mở rộng trung bình |
|---|---:|---:|---:|---:|---:|
| Fixed Eligible | 0 / 0 / 0 (n=5) | 0 | 1.000 | 3.32 | 78.52 |
| Random Eligible, 20 seed | 0 / 0 / 0 (5 learner, 100 lượt) | 0 | 1.000 | 3.32 | 78.52 |
| Best-First + Heuristic | 0 / 0 / 0 (n=5) | 0 | 0.107 | 1,895.39 | 3,640.55 |

Fixed đạt `reached` cho 333 learner và `target_already_mastered` cho 40. Random có cùng hai trạng thái qua các seed. Best-First đạt `target_already_mastered` cho 40 learner; 333 learner còn lại hết ngân sách (10,000 trạng thái hoặc 2,000 ms). Các route trả về không vi phạm cạnh prerequisite. `summary_next_step.csv` có accuracy 0 cho 5 learner có ground truth.

## Giới hạn và diễn giải

Chỉ 5/373 learner có interaction quan sát được trong cửa sổ test 14 ngày; các concept tương lai không quan sát không được xem là bằng chứng chúng vô ích. Ba phương pháp đều có ranking metrics 0 trên nhóm nhỏ này, nên chưa có căn cứ kết luận phương pháp nào xếp hạng tốt hơn. Best-First thường chạm ngân sách với target có 88 ancestor do OPEN phải giữ nhiều thứ tự kế hoạch; đây là giới hạn runtime trên cấu hình đã chạy. Thử nghiệm là đánh giá lịch sử, không đo learning gain, không chứng minh tăng kết quả học và không chứng minh tối ưu toàn cục.

File kết quả: `data/processed/per_learner_results.csv`, `summary_results.csv`, `summary_next_step.csv`, `results_ndcg.svg`, `validation_grid.csv`, `experiment_config.json` và `experiment_report.md`. Chạy lại với `python -m src.experiment --data data/processed --mode test`; cấu hình khóa từ validation được giữ trong `experiment_config.json`.
