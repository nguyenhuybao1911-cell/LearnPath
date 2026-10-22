# Báo cáo kiểm tra nguồn và độ bao phủ dữ liệu

**Ngày kiểm tra:** 22/10/2026  
**Phạm vi:** MOOCCubeX, chọn Computer Science (`cs`) theo quy tắc ID/lĩnh vực chính xác. TEMPO-DQ được kiểm tra để xác định có thể thay thế lịch sử sự kiện hay không.  
**Mục đích:** xác định dữ liệu thật trong checkout và payload tải chính thức; không coi mã xử lý hay dữ liệu tổng hợp là event-level history.

## 1. Nguồn và phiên bản

| Repository | URL | Branch / commit đã kiểm tra | Ghi chú |
|---|---|---|---|
| MOOCCubeX | https://github.com/THU-KEG/MOOCCubeX | `main`, `ff6fb71304b4eaadde51956b7977d49c72a3ac1e` | Checkout có mã và tài liệu schema. Payload LFS được tải riêng từ host chính thức. |
| TEMPO-DQ-Framework | https://github.com/datachain-uit/TEMPO-DQ-Framework | `ngocbanch`, `3d9975cb11af4aed2efdfc79c046821111a324ff` | Notebook và hướng dẫn xử lý; file LO/CQ thực tế không có trong checkout. |
| Payload MOOCCubeX | https://lfs.aminer.cn/misc/moocdata/data/mooccube2/ | Manifest SHA-256 trong `data/processed/source_manifest.json` | Lịch sử 22.453.311.654 byte có SHA-256 `dd0d771f73263a218aaccf7340333627ef13e5f2ec4bc235ad0b339a13112e90`, khớp checksum sau tải. |

Branch/commit là trạng thái mã nguồn được audit; chúng không chứng minh payload nằm sẵn trong Git clone. Không thấy file LFS pointer thay cho payload. Các file cần thiết được downloader lấy riêng từ URL LFS chính thức. TEMPO hướng tới Kaggle/Drive cho dữ liệu processed; các file đó không nằm trong checkout.

## 2. File đầu vào, định dạng và trường thực tế

Các payload dưới đây đã có trong `data/raw/mooccubex/` trước khi dọn. Kích thước tính bằng byte; SHA-256 lưu trong manifest đầu ra.

| File | Byte | Định dạng thực tế | Trường đã quan sát |
|---|---:|---|---|
| `relations/user-problem.json` | 22,453,311,654 | JSON Lines, một object mỗi dòng | `log_id`, `problem_id`, `user_id`, `is_correct`, `attempts`, `score`, `submit_time` |
| `relations/concept-problem.txt` | 1,294,994 | UTF-8, tab-delimited, hai cột | Concept ID, problem ID; một problem có thể liên kết nhiều concept |
| `entities/concept.json` | 162,964,332 | JSON Lines | `id`, `name`, `context` |
| `prerequisites/cs.json` | 90,196,535 | JSON Lines | `c1`, `c2`, `ground_truth`, `text_predict`, `graph_predict` |
| `prerequisites/math.json` | 61,381,372 | JSON Lines | Cùng schema prerequisite |
| `prerequisites/psy.json` | 139,276,093 | JSON Lines | Cùng schema prerequisite |

Ví dụ lịch sử sau khi ẩn ID: `{"log_id":"<ẩn>","problem_id":"<ẩn>","user_id":"<ẩn>","is_correct":0,"attempts":1,"score":null,"submit_time":"2020-10-27 10:11:56"}`. Ví dụ concept: `{"id":"K_神经部_组织学与胚胎学","name":"神经部","context":[]}`. Ví dụ cạnh CS: `c1="操作命令"`, `c2="重新启动"`, `ground_truth=1`; hai trường dự đoán chứa vector xác suất riêng.

Tài liệu MOOCCubeX mô tả `log_id` là định danh event; ID lịch sử dùng tiền tố `U_` và `Pm_`. Pipeline không cắt tiền tố hoặc viết lại ID. Timestamp đầu vào dạng `YYYY-MM-DD HH:MM:SS`, diễn giải thống nhất là UTC rồi chuẩn hóa ISO-8601 UTC. `is_correct` chỉ nhận 0/1; `score` có thể null. `attempts` được giữ để tham khảo, không nhân số dòng. Các `log_id` khác nhau cùng learner/problem vẫn là interaction riêng; chỉ loại ID lưu trùng.

## 3. Kết quả kiểm tra TEMPO-DQ

Checkout có README và notebook xử lý như `user_problem_processing.ipynb`, `user_problem_time_series.ipynb`, `prerocessing_problem.ipynb`. Notebook đọc/ghi đường dẫn Kaggle hoặc Google Drive. Đầu ra LO đã xử lý là tổng hợp theo learner/course và phase, với trường như `average_attempts_4`, `average_ratio_4`, `average_exercise_time_4`, `average_time_between_submissions_4`, `exercise_completion_ratio_4`. Đây không phải event đúng/sai từng problem gắn concept nên không thể dùng thay lịch sử MOOCCubeX trong learner state theo concept.

## 4. Chọn phạm vi và phép nối exact ID

Đã đánh giá ba domain bằng script streaming `scripts/profile_data_coverage.py`; không lấy mẫu ngẫu nhiên làm đứt prerequisite. Catalog domain là hợp của concept có field/hậu tố domain khớp chính xác và endpoint prerequisite ánh xạ duy nhất qua ID/tên nguồn. Không suy luận prerequisite từ độ giống tên. Chọn CS vì có lịch sử nhiều nhất và train vượt 2.000.

| Domain | Concept trong phạm vi | Bài-concept | Cạnh positive chú thích | Interaction exact-join | Train / validation / test | Đạt ≥2.000 train |
|---|---:|---:|---:|---:|---:|---|
| CS | 39,292 | 3,288 | 612 | 7,975 | 5,582 / 1,196 / 1,197 | Có |
| Math | 8,102 | 180 | 293 | 9 | 6 / 1 / 2 | Không |
| Psychology | 8,680 | 641 | 706 | 307 | 214 / 46 / 47 | Không |

CS có 608 learner, 2.292 problem có lịch sử và 321/39.292 concept từng xuất hiện trong ít nhất một event. Chỉ 156 concept có train history; các concept khác vẫn ở catalog để tra cứu prerequisite/target và mang trạng thái `unknown` khi không quan sát. Có 2.630 interaction liên quan nhiều hơn một concept CS. Một event đóng góp kết quả đúng/sai cho từng concept liên kết hợp lệ, không tạo thêm log event.

Trong 133.384.333 event hợp lệ đã quét: 34.834 nối được với concept bất kỳ (0,0261%); 133.349.499 không nối được; 26.859 nối concept ngoài CS; 7.975 nối ít nhất một concept CS (0,00598% tổng event). Tập CS có 0 interaction lỗi và 0 duplicate `log_id` được lưu. Quan hệ problem-concept đầu ra có 3.288 cặp. Prerequisite CS có 492.102 dòng nguồn; 380.072 ánh xạ được cả hai endpoint vào catalog CS; 112.030 thiếu endpoint ánh xạ nên không đưa vào graph đầu ra.

Tỷ lệ nối thấp là giới hạn thật, không che bằng đổi ID. Mốc 2.000 train đáp ứng điều kiện khởi đầu của đồ án, nhưng dữ liệu vẫn thưa theo learner/concept và không đủ để tuyên bố giảm overfitting hoặc khái quát hóa tốt.

## 5. Prerequisite: nhãn, chiều và graph

Schema nguồn có `c1`, `c2`, `ground_truth`, `text_predict`, `graph_predict`. Theo tài liệu MOOCCubeX, `c1 → c2` nghĩa c1 là prerequisite của c2. `ground_truth == 1` là cạnh positive được chú thích; `ground_truth == 0` là nhãn âm. `text_predict` và `graph_predict` là dự đoán xác suất, không phải nhãn chú thích. Output giữ riêng các trường dự đoán; graph đề tài chỉ dùng quan hệ positive được chú thích.

Có 612 cạnh positive CS ánh xạ được. Self-loop/chu trình và endpoint không hợp lệ được ghi lý do trong `records_rejected.csv`; không đảo cạnh để làm graph chạy. Tất cả ID endpoint của các cạnh đưa vào graph đều thuộc catalog CS.

## 6. Chia thời gian và chống leakage

Cấu hình: seed 42; tỷ lệ 70/15/15; sắp theo `submit_time` UTC; event cùng timestamp không bị tách giữa split.

- Train: 2020-05-01 08:13:30 đến 2020-07-02 19:52:28; 5.582 event.
- Validation: 2020-07-02 20:10:05 đến 2020-08-28 08:27:21; 1.196 event.
- Test: 2020-08-28 08:27:39 đến 2020-12-13 08:26:28; 1.197 event.

Learner state snapshot có `as_of=2020-08-28T08:27:39Z` và chỉ dùng lịch sử trước cutoff; độ khó lấy từ train (`1 - tỷ lệ đúng`). Validation/test không dùng tính learner state train hay difficulty. Train correct rate là 0,6705. Ngưỡng mastery/tau không được xem là giá trị chuẩn giáo dục do dataset cung cấp.

## 7. Đầu ra đã xử lý

`data/processed/` có `interactions_clean.csv`, `concepts.csv`, `problems.csv`, `problem_concepts.csv`, `prerequisites.csv`, `learners.csv`, `learner_state.csv`, `concept_difficulty.csv`, `data_summary.csv/.json`, `pipeline_config.json`, `records_rejected.csv`, coverage profile và source manifest. CSV được ghi UTF-8 BOM để Excel Windows đọc đúng chữ Trung. Gzip unmatched được đọc hết để kiểm CRC và đếm 133.349.499 dòng, sau đó xóa (896.212.883 byte) vì không cần cho demo/API; số đếm vẫn lưu trong summary.

Pipeline dùng SQLite staging và đọc interaction theo luồng, không nạp file 22,45 GB vào RAM. Bộ cũ được giữ tại `data/backup/processed_previous_20261022/` để khôi phục; bộ cũ có 1.798 interaction và không còn là bộ hiện hành.

## 8. PostgreSQL/API và kiểm thử

Đã import vào database Docker riêng `learnpath_candidate_20261022`; database trước đó không bị sửa. Import hai lần bằng upsert. Số dòng sau lần nạp thứ hai:

| Bảng | Dòng |
|---|---:|
| learner | 608 |
| concept | 39,292 |
| problem | 2,292 |
| problem_concept | 3,288 |
| prerequisite | 380,072 |
| interaction | 7,975 |
| learner_state | 7,215 |
| concept_difficulty | 156 |

`GET /api/health` trả `status=ok`, `concepts=39292`; learner-state trả 39.292 concept, learner mẫu có 25 concept đã quan sát và concept không có log ở trạng thái unknown. Tên tiếng Trung CSV UTF-8 khớp với response API; chữ sai trên PowerShell là lỗi hiển thị console, không phải file hỏng.

Đã chạy `python -m unittest discover -s tests -v`: 25 test đạt. `scripts/verify_processed_data.py` kiểm tra số dòng, split, exact join, uniqueness, mastery/cutoff, difficulty từ train, prerequisite endpoint và đọc gzip unmatched đến EOF. Test bao gồm giữ lần làm lại, temporal split, unknown mastery, graph lỗi, nhiều prerequisite và OPEN giữ nhánh thay thế.

## 9. Manifest và kết luận

`data/processed/source_manifest.json` lưu URL, dung lượng, SHA-256 và revision nguồn. Sau khi rà soát đầu ra, DB/API và bản dự phòng, payload raw được dọn để giải phóng khoảng 22,8 GB; có thể tải lại bằng script trong README. CSV đã xử lý, manifest, audit và bản dự phòng được giữ.

**Kết luận:** MOOCCubeX có đủ trường và cạnh prerequisite để tạo demo CS với hơn 2.000 interaction trong train; TEMPO-DQ không cung cấp event-level concept history thay thế. Bộ mới tăng đáng kể quy mô so với 1.798 interaction, nhưng exact join vẫn rất thấp và chỉ 156 concept có train history. Dữ liệu đáp ứng kiểm tra pipeline/demo và ngưỡng khởi đầu 2.000; nó không tự chứng minh khái quát hóa, learning gain, hay tính tối ưu toàn cục của lộ trình.
