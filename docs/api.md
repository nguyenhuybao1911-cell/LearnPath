# Hợp đồng API LearnPath — Ngày 1

Base URL local: `http://localhost:8080/api`. JSON dùng camelCase, timestamp ISO-8601 UTC. Các ví dụ dưới đây minh họa cấu trúc request/response; giá trị `<...>` là placeholder, không phải learner hay số liệu dataset thật.

## Phạm vi và quy ước đã chốt

- Một domain: Computer Science (`cs`) theo quan hệ prerequisite MOOCCubeX.
- API chỉ trả ID learner, không trả dữ liệu nhận dạng cá nhân.
- `A → B` nghĩa A là prerequisite của B.
- Mastery tính từ interaction có `submitted_at < asOf`; concept chưa có event trả `mastery: null`, `status: "unknown"`.
- Defaults đề xuất lộ trình: `tau=0.5`, `minInteractions=1`, weights `(wP,wN,wD,wR)=(0,0.1,0.4,0.5)`, `maxStates=10000`, `timeLimitMs=2000`; khớp cấu hình được chọn trên validation trong `data/processed/experiment_config.json`. NDCG@5 validation là 0 với 5 learner có nhãn, nên đây là cấu hình thử nghiệm đã khóa, chưa phải ngưỡng giáo dục hay bằng chứng cấu hình tốt hơn.
- Trạng thái tìm kiếm: `reached`, `target_already_mastered`, `no_path`, `budget_exhausted`.

## `GET /health`

Kiểm tra API và số concept đã nạp.

```json
{"status":"ok","concepts":0}
```

## `GET /learners`

Trả danh sách tối đa 500 learner ID theo thứ tự tăng dần.

```json
["<learner-id-1>", "<learner-id-2>"]
```

## `GET /concepts`

Trả concept ID và tên để chọn target.

```json
[{"id":"<concept-id>","name":"<concept-name>"}]
```

## `GET /learners/{learnerId}/state?asOf=<ISO-8601>`

`asOf` tùy chọn, mặc định giờ hiện tại của backend. Mỗi concept có `correct`, `total`, `mastery`, `status` và `asOf`. Các số đếm/mastery để `null` khi chưa có event.

```json
[
  {"conceptId":"<concept-with-history>","conceptName":"<name>","correct":2,"total":3,"mastery":0.6667,"status":"observed","asOf":"2026-10-21T00:00:00Z"},
  {"conceptId":"<concept-without-history>","conceptName":"<name>","correct":null,"total":null,"mastery":null,"status":"unknown","asOf":"2026-10-21T00:00:00Z"}
]
```

## `POST /recommendations`

Bắt buộc `learnerId`, `targetId`. `asOf`, `tau`, `minInteractions`, `wP/wN/wD/wR`, `maxStates`, `timeLimitMs` tùy chọn. Các weights phải không âm và tổng bằng 1.

```json
{
  "learnerId":"<learner-id>", "targetId":"<target-concept-id>",
  "asOf":"2026-10-21T00:00:00Z", "tau":0.5, "minInteractions":1,
  "wP":0, "wN":0.1, "wD":0.4, "wR":0.5,
  "maxStates":10000, "timeLimitMs":2000
}
```

Response có `status`, `message`, `expanded`, `peakOpen` và `steps`. Mỗi bước trả concept cùng các thành phần điểm heuristic và giải thích. Khi không tìm thấy đường hoặc target đã thành thạo, `steps` rỗng.

```json
{
  "learnerId":"<learner-id>", "targetId":"<target-concept-id>", "status":"reached",
  "steps":[{
    "conceptId":"<concept-id>", "conceptName":"<name>",
    "scores":{"p":1,"n":0.5,"d":0.8,"r":0.5,"h":0.645,"mastery":0.5,"explanation":"<lý do>"}
  }],
  "expanded":2,"peakOpen":1,"message":"<trạng thái tìm kiếm>"
}
```

## `POST /interactions`

Endpoint ghi một interaction thật. `logId` là khóa chống ghi trùng; `attempts` chỉ lưu metadata, không nhân thành nhiều interaction. `problemId` cần tồn tại trong bảng `problem`.

```json
{
  "learnerId":"<learner-id>", "problemId":"<problem-id>", "logId":"<event-id>",
  "correct":true, "score":1, "attempts":1, "submittedAt":"2026-10-21T00:00:00Z"
}
```

Response là `{"status":"inserted"}` hoặc `{"status":"duplicate_log_id"}`. Learner state được tính từ interaction thực khi gọi API state/recommend tiếp theo.

## Lỗi

- `400`: request không hợp lệ, thiếu trường bắt buộc hoặc weights không hợp lệ; body gồm `status` và `message`.
- `500`: lỗi server hoặc database; body báo lỗi chung, không trả stack trace.

## Bảng PostgreSQL

`learner`, `interaction`, `concept`, `problem`, `problem_concept`, `prerequisite` là các bảng dữ liệu lõi. `learner_state` và `concept_difficulty` lưu snapshot/thống kê có nguồn; `recommendation` và `recommendation_step` lưu kết quả/giải thích; `data_summary` lưu metadata pipeline. Flyway tạo schema từ `backend/src/main/resources/db/migration/V1__schema.sql`.
