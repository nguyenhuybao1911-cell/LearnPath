# LearnPath

Demo cá nhân hóa lộ trình học theo Greedy Best-First Search và hàm heuristic. Backend Java 21/Spring Boot kết nối PostgreSQL; giao diện React/Vite; pipeline và đánh giá dữ liệu dùng Python. Hệ thống giải thích điểm thành phần và không khẳng định tìm được tối ưu toàn cục hay làm tăng kết quả học.

## Tiến độ đã làm và kiểm tra

- Đã hoàn thành kiểm tra nguồn dữ liệu, pipeline và nạp bộ CS: 7.975 interaction, 608 learner, 39.292 concept trong catalog; train/validation/test lần lượt 5.582/1.196/1.197.
- Đã chạy 26 kiểm thử Python và rà soát các file dữ liệu sau khi làm sạch. File unmatched được đọc hết và kiểm CRC trước khi xóa; raw và file tạm đã dọn để tiết kiệm dung lượng.
- Đã kiểm tra PostgreSQL/API trên database riêng `learnpath_candidate_20261022`; nạp hai lần không tăng số dòng. Database cũ không bị thay đổi.
- Phần đã hoàn thành trong phạm vi phân công: dữ liệu ngày 1–2 của An và ngày 2 của Bảo. Các phần việc các ngày sau chưa được tính là hoàn thành.

Chi tiết số liệu và giới hạn nằm trong [báo cáo kiểm tra dữ liệu](docs/data_audit.md) và [báo cáo Word](docs/bao_cao_tien_do_xu_ly_data.docx).

## Trạng thái dữ liệu đã kiểm tra (22/10/2026)

Nguồn sự kiện là MOOCCubeX, phạm vi Computer Science (`cs`). Bộ dữ liệu hiện tại có 39.292 concept trong catalog, 2.292 bài có liên kết concept, 608 learner và 7.975 interaction nối chính xác vào phạm vi CS. Chia theo thời gian: 5.582 train, 1.196 validation, 1.197 test. Như vậy train vượt mốc sàng lọc 2.000 interaction của đề tài; con số này không tự chứng minh khả năng khái quát hóa. Có 321 concept từng xuất hiện trong lịch sử nhưng chỉ 156 concept có lịch sử train. Concept chưa có lịch sử được giữ trạng thái unknown.

Lịch sử gốc có 133.384.333 dòng hợp lệ. Chỉ 34.834 dòng nối được với concept ở bất kỳ lĩnh vực nào; 7.975 thuộc CS. Tỷ lệ nối toàn bộ là 0,0261%, nên dữ liệu vẫn thưa. Tên concept giữ tiếng Trung nguyên bản UTF-8; nếu PowerShell hiển thị sai, hãy mở CSV bằng Excel từ UTF-8 hoặc dùng Python/VS Code với encoding UTF-8. Báo cáo đầy đủ: [kiểm tra dữ liệu](docs/data_audit.md), [báo cáo Word](docs/bao_cao_tien_do_xu_ly_data.docx).

Các file thí nghiệm cũ nếu có trong bản dự phòng được tạo trên tập 1.798 interaction trước lần sửa phạm vi concept, không dùng làm kết quả của bộ hiện tại. Phần đánh giá so sánh cần được chạy lại trên bộ mới trước khi trích kết quả.

## Chạy ứng dụng trên Windows / VS Code

Cần Python 3.11+, JDK 21, Maven 3.9+, Node.js 22+ và Docker Desktop. Mở hai terminal PowerShell trong VS Code tại thư mục gốc.

### 1. Khởi động PostgreSQL

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d postgres
docker compose ps
```

Chờ service `postgres` hiển thị `healthy`. Nếu dùng database đã có dữ liệu cũ, nên tạo database demo mới để tránh giữ lại những dòng không thuộc bộ hiện tại. Ví dụ, tạo một lần:

```powershell
docker exec learnpath-postgres-1 psql -U learnpath -d postgres -c "CREATE DATABASE learnpath_data;"
```

### 2. Chạy backend và nạp dữ liệu

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
$env:DATABASE_URL = 'jdbc:postgresql://localhost:5432/learnpath_data'
$env:DB_USER = 'learnpath'
$env:DB_PASSWORD = 'learnpath'
$env:IMPORT_DIR = (Resolve-Path .\data\processed).Path
Set-Location .\backend
mvn spring-boot:run
```

Lần đầu Flyway tạo schema rồi importer nạp CSV theo batch. Giữ terminal này mở. Kiểm tra từ terminal khác:

```powershell
Invoke-RestMethod http://localhost:8080/api/health
```

Kỳ vọng `status: ok` và `concepts: 39292`.

### 3. Chạy frontend

```powershell
Set-Location .\frontend
npm ci
npm run dev
```

Mở địa chỉ Vite, thường là `http://localhost:5173`. Chọn learner và concept mục tiêu. Nếu `npm ci` báo `EPERM` trên Windows, dừng tiến trình Vite/Node đang dùng `frontend/node_modules`, đóng terminal đó rồi thử lại; không xóa dữ liệu dự án.

Dừng backend/frontend bằng `Ctrl+C`. PostgreSQL có thể để chạy; dừng riêng bằng `docker compose stop postgres`. Không dùng `docker compose down -v` trừ khi muốn xóa volume database.

## Pipeline dữ liệu

Đầu ra đã xử lý có trong `data/processed/`. Pipeline đọc JSONL theo luồng, dùng ID nguyên văn, không nhân bản theo `attempts`, giữ mỗi `log_id` riêng, và chia dữ liệu theo thời gian. Learner state tại cutoff chỉ dùng tương tác đã quan sát; độ khó chỉ lấy từ train. Một event nối nhiều concept đóng góp một kết quả cho từng concept liên quan; không tạo thêm log event.

Lệnh tái tạo từ nguồn chính thức (cần khoảng 23 GB tải xuống tạm thời và thêm dung lượng cho đầu ra):

```powershell
python -m scripts.download_data --domain cs
python -m scripts.download_data --domain math
python -m scripts.download_data --domain psy
python -m scripts.download_data --domain cs --include-interactions
python -m scripts.profile_data_coverage --raw data/raw/mooccubex --minimum-train-interactions 2000
python -m src.pipeline --raw data/raw/mooccubex --output data/processed --staging data/staging --domain cs --seed 42
python -m scripts.verify_processed_data --data data/processed --profile data/processed/domain_coverage_profile.json
python -m unittest discover -s tests -v
```

Sau khi kiểm tra checksum, pipeline, API/import và bản sao dự phòng, raw (22.908.424.980 byte), staging tạm và `records_unmatched.csv.gz` (896.212.883 byte) đã được xóa. File unmatched đã được đọc tới EOF, kiểm CRC và xác nhận 133.349.499 dòng trước khi xóa; số đếm vẫn nằm trong `data_summary.json`. Raw tải lại được bằng lệnh trên; checksum được lưu trong source manifest. Bản cũ 62.001.522 byte được giữ ở `data/backup/processed_previous_20261022/`. Không commit raw, backup, Docker volume, `.env`, `node_modules` hoặc file build.

Với bộ đã dọn hiện tại, chạy verifier bằng `--allow-unmatched-removed`. Nếu vừa chạy lại pipeline và file unmatched còn tồn tại, bỏ cờ này để verifier đọc file tới EOF và kiểm CRC.

## Phạm vi hiện tại và giới hạn

- Các quan hệ prerequisite dùng cạnh được chú thích `ground_truth = 1`; `c1 → c2` nghĩa c1 là tiên quyết của c2. Nhãn dự đoán được giữ riêng, không xem là ground truth.
- Catalog 39.292 concept không đồng nghĩa mỗi concept đều có lịch sử. Số interaction nối thưa và phân bố không đều giữa learner/concept.
- Mastery là tỷ lệ đúng trong các tương tác đã quan sát tới thời điểm xác định; unknown không bị coi là mastery bằng 0.
- Mốc 2.000 là yêu cầu sàng lọc của đồ án, không thay thế kiểm định độc lập và không phải bằng chứng learning gain.
- Kiểm tra dữ liệu/API không đồng nghĩa đã hoàn thành thực nghiệm so sánh trên phiên bản dataset mới.
- Nguồn, commit, schema đầu vào, phép nối và các mục bị loại được ghi ở [docs/data_audit.md](docs/data_audit.md).
