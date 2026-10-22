# Kiến trúc demo

```text
MOOCCubeX files
      │
      ▼
Python download_data → pipeline → data/processed CSV
                                      │
                                      ▼
                         Spring DataImporter (batch upsert)
                                      │
                         PostgreSQL + Flyway schema
                                      │
React/Vite ◀──── JSON API ─── Spring controller/service
   │                              ▲
   └── /api dev proxy ────────────┘
                                      │
                                SearchService

data/processed ───── Python validation tuning → locked config
                └── Python final test → CSV, SVG, Markdown report
```

## Thành phần

- `scripts/download_data.py`: tải các file chính thức cho domain được chọn, hỗ trợ resume, yêu cầu xác nhận riêng qua flag trước khi tải lịch sử lớn.
- `src/ingest.py`, `src/pipeline.py`: parse streaming, chuẩn hóa timestamp UTC, làm sạch và log lỗi, nối ID nguyên dạng, split thời gian và tạo thống kê train.
- `src/planner.py`: learner state và thuật toán tham chiếu Python; `src/experiment.py`: baseline, validation và test.
- `backend`: Spring Boot API, repository JDBC, service, search và Flyway migration. `DataImporter` đọc CSV theo batch 1000 và dùng upsert, khóa tương tác theo `log_id`.
- `frontend`: React, lựa chọn learner/target, mastery hoặc unknown, lộ trình và điểm giải thích.
- `docs/data_audit.md`: hiện trạng nguồn và payload. Không đưa dữ liệu tải lớn vào Git.

## API

- Hợp đồng request/response và quy ước thống nhất với frontend: [api.md](api.md).
- `GET /api/health`: trạng thái API.
- `GET /api/learners`, `GET /api/concepts`: lựa chọn trong demo.
- `GET /api/learners/{id}/state`: tử số, mẫu số, mastery/unknown theo dữ liệu có.
- `POST /api/recommendations`: nhận `learnerId`, `targetId` và tham số tùy chọn; trả status, từng bước, `P/N/D/R/H`, lý do và trạng thái tìm kiếm.
- `POST /api/interactions`: ghi tương tác thực tế có timestamp và kết quả; state sau đó được tính lại từ dữ liệu thật.

Schema ở `backend/src/main/resources/db/migration/V1__schema.sql`. Bảng `course` không được thêm vì phạm vi chọn là một domain và nguồn hiện có không cung cấp ánh xạ khóa học cần thiết cho bài toán này.

## Các giới hạn triển khai

Môi trường được kiểm tra không có PostgreSQL đang chạy và Docker daemon chưa sẵn sàng, nên kết nối API tới PostgreSQL chưa được chạy xuyên suốt ở đây. Khi payload dữ liệu chưa có, endpoint có thể khởi động nhưng chưa có learner thực để trình diễn. Tài liệu audit ghi chính xác những gì đã kiểm tra và những gì chưa thể đo.
