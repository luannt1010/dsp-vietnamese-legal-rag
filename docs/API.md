# FastAPI — Vietnamese Legal RAG

Trạng thái triển khai và bằng chứng kiểm thử: [báo cáo API](API_IMPLEMENTATION_REPORT.md).

API nằm trong `src/api`. Luồng gọi là router → `RAGService` →
`RAGPipeline.run_with_trace`; dùng nguyên `open_runtime`, config loader,
`LegalAnswer`, `RetrievedChunk` và trạng thái orchestration hiện có.
API không tự viết lại retrieval, feedback, deadline hay citation verification.

## Cài và chạy

Chạy từ root repository trong Windows PowerShell, với môi trường Python đã
kích hoạt theo [README](../README.md):

```powershell
python -m pip install -e ".[dev]"
powershell -ExecutionPolicy Bypass -File .\scripts\start_demo_databases.ps1
python -m scripts.demo doctor
python -m scripts.demo prepare
python -m src.api
```

Ollama và model cần sẵn sàng theo hướng dẫn demo. API mặc định dùng
`configs/demo`, đọc credentials từ `.runtime/demo.env`, lắng nghe
`http://127.0.0.1:8000`. Swagger: `http://127.0.0.1:8000/docs`, ReDoc:
`http://127.0.0.1:8000/redoc`, contract: `http://127.0.0.1:8000/openapi.json`.

`python -m src.api` áp dụng `api.host`, `api.port`, `logging.level` và tắt
access log mặc định để tránh log query string. Log API giữ request ID, route
template, status, thời gian và mã lỗi; không log câu hỏi/nội dung nguồn.
DEBUG có thể chứa traceback/chi tiết provider; chỉ dùng khi debug cục bộ.

Có thể chạy Uvicorn trực tiếp:

```powershell
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Khi chạy trực tiếp, host/port/logging theo option Uvicorn. Import app chỉ load
cấu hình, không kết nối database hoặc nạp model. Runtime mở một lần khi ASGI
startup, đóng khi shutdown. API luôn đặt `auto_prepare=False` trên bản sao cấu
hình, kể cả demo dùng `true`: thiếu corpus/index làm startup thất bại; chạy
`prepare` rồi khởi động lại. Không ingest hoặc ghi index trong HTTP request.

## Cấu hình

Không có loader hay `api.yml` riêng. Dùng section `api` trong `config.yml` và
override `RAG__...` của [cấu hình chung](CONFIGURATION.md).

```powershell
$env:RAG_CONFIG_DIR = 'D:\dsp-vietnamese-legal-rag\configs\demo'
$env:RAG_ENV_FILE = 'D:\dsp-vietnamese-legal-rag\.runtime\demo.env'
$env:RAG__API__HOST = '127.0.0.1'
$env:RAG__API__PORT = '8000'
$env:RAG__API__CORS_ORIGINS = '["http://localhost:5173"]'
$env:RAG__API__MAX_CONCURRENT_REQUESTS = '1'
python -m src.api
```

Thứ tự ưu tiên: model defaults < YAML < dotenv được chọn < process environment.
Đọc dotenv không sửa process environment. CORS mặc định tắt, chỉ cho origin
được cấu hình, GET/POST và Content-Type; frontend đọc được X-Request-ID và
Retry-After. CORS không phải cơ chế xác thực.

## Endpoint

| Method | Path | Vai trò |
| --- | --- | --- |
| GET | `/health/live` | Process đang phục vụ HTTP |
| GET | `/health/ready` | Runtime đã nạp, đang nhận công việc |
| GET | `/api/v1/corpus` | Snapshot ID, revision, topic/subject thực tế và số lượng |
| POST | `/api/v1/questions` | Xử lý một câu hỏi độc lập |

Readiness không gọi model hoặc ping database mỗi request, không khẳng định
mọi dependency còn hoạt động sau startup. Khi downstream lỗi, question endpoint
trả outcome pipeline tương ứng. Runtime bận vẫn ready; question mới nhận 503.

### Hỏi đáp

```powershell
$payload = @{ query = 'Người học có những quyền gì theo Luật Giáo dục?' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/questions' -Method Post `
  -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($payload))
```

Request kế thừa `QueryRequest`, giới hạn `query` tối đa 4.000 ký tự sau trim,
không nhận field lạ. `conversation_id` chỉ nhận null hoặc bỏ qua; ID khác null
bị từ chối vì pipeline chưa có conversational memory. Không mở các tham số
benchmark, model, strategy hoặc đường dẫn file cho HTTP caller.

Response ví dụ dưới đây chỉ minh họa schema, không phải kết quả pháp lý thật:

```json
{
  "request_id": "server-generated-id",
  "status": "insufficient_evidence",
  "answer": {
    "answer": "Chưa đủ căn cứ từ các nguồn đã truy xuất để trả lời câu hỏi này.",
    "citations": [],
    "confidence": 0.0,
    "disclaimer": "Chưa có kết luận pháp lý được xác minh cho câu hỏi này."
  },
  "sources": [],
  "corpus_id": "snapshot-id",
  "rounds": 1,
  "duration_ms": 1234.5,
  "failure": null
}
```

Kết quả completed thật phải qua citation verifier hiện có và có citations.
`sources` là các `RetrievedChunk` được giữ trong context đã duyệt, gồm nội dung,
metadata và vị trí để frontend mở nguồn. Không phải mọi source trong context
đều được dẫn; citation nằm trong `answer.citations`. Score retrieval không phải
answer confidence. Confidence hiện chưa được hiệu chuẩn, giữ nguyên từ pipeline.

Không trả draft, reasoning, rewritten query, toàn bộ rounds hoặc raw provider
error. Khi fallback, giữ nguyên LegalAnswer do orchestrator tạo, sources rỗng;
`failure` nếu có chỉ gồm stage và code. Không streaming bản nháp trước verification.
`duration_ms` đo lời gọi pipeline và dựng public response, không bao gồm network,
startup hoặc thời gian nhận body. Log HTTP đo thời gian xử lý request rộng hơn.

### Status và lỗi

| HTTP | Body | Ý nghĩa |
| --- | --- | --- |
| 200 | QuestionResponse / completed | Đáp án đã qua verification |
| 200 | QuestionResponse / insufficient_evidence | Câu hỏi hợp lệ, chưa đủ căn cứ |
| 422 | ErrorResponse / invalid_request | Request không hợp lệ |
| 502 | QuestionResponse / failed | Pipeline/provider/verification thất bại |
| 503 | ErrorResponse / service_busy | Hết slot inference; Retry-After: 1 |
| 503 | ErrorResponse / service_not_ready | Runtime chưa nhận công việc |
| 504 | QuestionResponse / timed_out | Deadline pipeline đã hết |
| 500 | ErrorResponse / internal_error | Lỗi bất ngờ, chi tiết không trả ra client |

HTTP client phải đọc JSON trên cả 502/504 để hiển thị fallback đúng. Không tự
retry POST một cách vô hạn; request không có idempotency cache.

```json
{
  "request_id": "server-generated-id",
  "error": {
    "code": "invalid_request",
    "message": "Dữ liệu yêu cầu không hợp lệ.",
    "issues": [{"location": ["body", "query"], "code": "missing", "message": "Field required"}]
  }
}
```

X-Request-ID do server sinh cho request ứng dụng, trùng ID trong response hỏi
đáp/lỗi và log API. Không tin ID do client cung cấp. Validation không trả input
hoặc ctx của Pydantic. Response đặt Cache-Control: no-store.

## Đồng thời, deadline và mở rộng

Inference đồng bộ được chạy trong thread pool, không chặn event loop. Capacity
limiter chặn trước khi đưa vào pool; mặc định một câu hỏi/worker để phù hợp model
local. Vượt giới hạn nhận ngay 503, không tạo hàng đợi vô hạn. Slot chỉ được trả
khi worker kết thúc, kể cả client ngắt trong quá trình xử lý.

Deadline/retry nằm trong pipeline và adapter hiện có. API không tạo timeout giả
để bỏ thread đang chạy. Thời gian trả thực tế vẫn phụ thuộc timeout của adapter.
Client/proxy cần response timeout dài hơn `pipeline.timeout_s` với khoảng đệm.

Mỗi Uvicorn worker có runtime, corpus, reranker, pool và limiter riêng; tổng tải
có thể tới workers × max_concurrent_requests. Tăng worker sẽ nhân bộ nhớ; nhiều
worker vẫn chia sẻ Ollama phía sau. Bắt đầu một worker, đo tải và tính an toàn
đồng thời của adapter/model trước khi tăng. Khi cần phục vụ tải lớn hoặc job bền
vững, bổ sung worker queue ở lớp service thay vì sửa logic RAG.

Bản này phục vụ local/internal, chưa triển khai đăng nhập, persistent history,
job queue hoặc API quản trị ingestion. Mặc định bind loopback; nếu công khai
dịch vụ cần lớp xác thực và vận hành phù hợp.

## Kiểm thử

```powershell
python -m pytest tests/api -q
python -m pytest -q
```

Tests HTTP inject fixture runtime, kiểm tra contract, input sai, fallback,
capacity, lifecycle, CORS, OpenAPI và một luồng qua orchestration thật với LLM/data
fixture. Không thay thế benchmark chất lượng hoặc smoke trên model/database thật.

Thiết kế lifecycle và xử lý lỗi theo tài liệu chính thức:
[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[concurrency](https://fastapi.tiangolo.com/async/),
[handling errors](https://fastapi.tiangolo.com/tutorial/handling-errors/).
