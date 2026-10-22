# Day 2 Local Data Processing Implementation Plan

> Kế hoạch này đã được thay thế bởi `2026-10-21-day-2-mooccubex-processing.md` sau khi xác nhận hai checkout chỉ chứa mã/tài liệu và người dùng đồng ý tải payload tối thiểu từ endpoint chính thức.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kiểm kê và xử lý chỉ các file dữ liệu thật đang nằm trong hai clone `data/MOOCCubeX` và `data/TEMPO-DQ-Framework`, tạo đầu ra chuẩn hóa nếu đủ quan hệ thiết yếu và báo thiếu rõ ràng nếu không đủ.

**Architecture:** Thêm một lớp discovery/audit local đứng trước pipeline hiện có. Lớp này phân loại file thật, tài liệu, notebook và output nhúng; chọn adapter theo schema đã xác minh, sau đó mới gọi pipeline chuẩn hóa. Không có bước tải mạng và không dùng output hiển thị trong notebook làm dữ liệu thực nghiệm.

**Tech Stack:** Python 3.13 standard library; pipeline hiện có trong `src/`; PostgreSQL import hiện có trong `backend/`.

**Spec:** `docs/BangPhanCong_An_Bao_1Tuan.docx`, `docs/data_audit.md`, yêu cầu chỉ dùng nội dung local trong hai clone.

## Global Constraints

- Không tải thêm dữ liệu từ GitHub, LFS, Kaggle hoặc Google Drive.
- Không tạo dữ liệu giả để thay thế dữ liệu thực; fixture chỉ nằm trong test tạm thời.
- Không coi output `head()`, `info()` hoặc HTML nhúng trong notebook là bảng dữ liệu đầy đủ.
- Không sửa ID bằng cách cắt tiền tố hoặc đổi tên để ép join.
- Không coi bảng tổng hợp theo learner/course là lịch sử event theo concept.
- Chỉ đánh dấu dataset “đủ” khi có đồng thời interaction, problem–concept, concept và prerequisite cùng hệ ID.

## Dữ liệu và properties bài toán cần

| Nhóm | Bắt buộc | Tùy chọn | Nguồn local hiện quan sát |
|---|---|---|---|
| Interaction | `log_id`, `user_id`, `problem_id`, `is_correct`, `submit_time` | `attempts`, `score`, `course_id`, `exercise_id` | TEMPO notebook mô tả đủ schema interaction, nhưng parquet thật không có trong clone; MOOCCubeX chỉ có tài liệu schema. |
| Problem–concept | `problem_id`, `concept_id` | — | MOOCCubeX mô tả `relations/concept-problem.txt`; file thật không có. TEMPO không có bảng local tương đương. |
| Concept | `id`, `name` | `context`, `field` | MOOCCubeX mô tả `entities/concept.json`; file thật không có. |
| Prerequisite | `c1`, `c2`, `ground_truth` | `text_predict`, `graph_predict` | MOOCCubeX mô tả `prerequisites/cs.json`; file thật không có. |

## Review Focus

- Notebook có output mẫu nhưng file nguồn vắng mặt: inventory phải ghi `embedded_sample_only`, không xuất interaction.
- File trùng tên nằm ở nhiều root: ưu tiên exact path/schema, không chọn theo tên đơn thuần.
- Parquet/CSV có file nhưng thiếu cột bắt buộc: dừng adapter đó và ghi danh sách cột thiếu.
- ID interaction không nối problem–concept: giữ unmatched và báo tỷ lệ, không sửa ID.
- Chỉ có interaction nhưng thiếu concept/prerequisite: cho phép audit/partial staging, không ghi nhãn dataset đủ cho recommendation.

---

### Task 1: Local Source Inventory

**Files:**
- Create: `src/local_sources.py`
- Create: `tests/test_local_sources.py`
- Modify: `docs/data_audit.md`

**Interfaces:**
- Consumes: hai root local `Path`.
- Produces: `discover_sources(roots: list[Path]) -> SourceInventory` và `data/local_source_manifest.csv` gồm path, size, format, classification, detected fields và usability.

- [ ] **Step 1: Viết test thất bại** cho phân loại `real_table`, `documentation`, `processing_code`, `embedded_sample_only`, `external_reference` và xác nhận notebook output không được trả trong `usable_tables`.
- [ ] **Step 2: Chạy** `python -m unittest tests.test_local_sources -v`; mong đợi FAIL vì module chưa tồn tại.
- [ ] **Step 3: Cài đặt discovery chỉ đọc local**, nhận diện CSV/TSV/JSON/JSONL/Parquet theo file thật và đọc notebook JSON để lấy metadata/schema tham khảo riêng.
- [ ] **Step 4: Chạy lại test**; mong đợi PASS.
- [ ] **Step 5: Chạy inventory trên hai clone** và cập nhật `docs/data_audit.md` bằng manifest thực tế, không chép output notebook thành record dataset.

### Task 2: Validate Input Contracts and Select Adapter

**Files:**
- Create: `src/source_contracts.py`
- Create: `tests/test_source_contracts.py`
- Modify: `src/pipeline.py`

**Interfaces:**
- Consumes: `SourceInventory` từ Task 1.
- Produces: `validate_source_bundle(inventory: SourceInventory) -> BundleValidation` với trạng thái `complete`, `partial` hoặc `blocked`, cùng exact paths và missing properties.

- [ ] **Step 1: Viết test thất bại** cho bundle MOOCCubeX đầy đủ, bundle TEMPO chỉ có interaction, file thiếu cột và ID contract không tương thích.
- [ ] **Step 2: Chạy** `python -m unittest tests.test_source_contracts -v`; mong đợi FAIL.
- [ ] **Step 3: Cài đặt contract**: interaction yêu cầu 5 cột cốt lõi; recommendation bundle yêu cầu thêm problem–concept, concept và prerequisite.
- [ ] **Step 4: Thêm `--source-root data` và `--local-only` vào pipeline**; local-only không gọi downloader và ghi `source_validation.json` trước khi xử lý.
- [ ] **Step 5: Chạy test Task 2 và toàn bộ Python tests**; mong đợi PASS.

### Task 3: Normalize Only Verified Local Records

**Files:**
- Modify: `src/ingest.py`
- Modify: `src/pipeline.py`
- Modify: `tests/test_ingest.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: exact paths từ `BundleValidation`.
- Produces khi bundle `complete`: `interactions_clean.csv`, `concepts.csv`, `problem_concepts.csv`, `prerequisites.csv`, `learners.csv`, `problems.csv`, `records_rejected.csv`, `records_unmatched.csv.gz`, `data_summary.json`.
- Produces khi `partial/blocked`: manifest và validation report; không tạo bảng thực nghiệm giả.

- [ ] **Step 1: Viết test thất bại** xác nhận retake khác `log_id` được giữ, duplicate cùng `log_id` bị ghi log, timestamp lỗi bị loại, multi-concept đóng góp một lần mỗi concept và thiếu prerequisite làm pipeline dừng ở `blocked`.
- [ ] **Step 2: Chạy các test ingest/pipeline**; mong đợi test mới FAIL.
- [ ] **Step 3: Tái sử dụng parser streaming hiện có**; chỉ bổ sung adapter field mapping cho file local có schema đã xác minh, không suy diễn từ notebook output.
- [ ] **Step 4: Chạy toàn bộ Python tests**; mong đợi PASS.
- [ ] **Step 5: Chạy pipeline local-only trên hai clone**. Với trạng thái workspace hiện tại, kết quả dự kiến là `blocked` do không có bốn bảng thật; đây là kết quả kiểm tra dữ liệu, không phải lỗi thuật toán.

### Task 4: Load Complete Output into PostgreSQL

**Files:**
- Modify only if contract mismatch is found: `backend/src/main/java/vn/learnpath/service/DataImporter.java`
- Test: `backend/src/test/java/vn/learnpath/service/DataImporterTest.java`
- Modify: `README.md`

**Interfaces:**
- Consumes: output Task 3 chỉ khi `BundleValidation.status == complete`.
- Produces: upsert idempotent vào schema Flyway và báo số dòng từng bảng.

- [ ] **Step 1: Viết test tích hợp importer** bằng fixture test tạm và chạy hai lần; assert row counts không tăng ở lần hai.
- [ ] **Step 2: Chạy test để quan sát FAIL nếu importer chưa đáp ứng contract output mới.**
- [ ] **Step 3: Chỉ sửa importer khi test cho thấy mismatch**, không thay schema nếu CSV hiện tại đã tương thích.
- [ ] **Step 4: Chạy Maven tests và, khi có bundle complete, kiểm tra PostgreSQL counts/join rates qua database local.**
- [ ] **Step 5: Cập nhật README** với lệnh local-only, trạng thái dữ liệu thực tế và các output đã/không tạo được.

## Điều kiện hoàn thành Ngày 2

- Luôn phải có manifest và validation report tái lập được từ hai clone local.
- Chỉ khi tìm thấy đủ bốn nhóm bảng thật mới được công bố bộ dữ liệu đã xử lý, tỷ lệ join và nạp PostgreSQL.
- Theo inventory hiện tại, hai clone chưa chứa file dữ liệu thật; vì vậy kế hoạch dự kiến hoàn thành phần audit/validation và dừng có lý do trước bước normalization/import, trừ khi người dùng chỉ ra một path local khác bên trong hai clone mà kiểm kê chưa thấy.
