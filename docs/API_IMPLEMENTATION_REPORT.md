# Báo cáo triển khai FastAPI — 07/11/2026

## Phạm vi đã hoàn thành

Backend đặt trong `src/api`, frontend chưa thay đổi. Điểm khởi chạy:
`python -m src.api` hoặc `uvicorn src.api.main:app`. Hướng dẫn cài, cấu hình,
request/response và vận hành tại [API.md](API.md).

| Endpoint | Chức năng |
| --- | --- |
| `GET /health/live` | Kiểm tra process HTTP |
| `GET /health/ready` | Runtime đã nạp và nhận công việc |
| `GET /api/v1/corpus` | Snapshot, revision thực tế, chủ đề và thống kê |
| `POST /api/v1/questions` | Hỏi đáp qua toàn bộ RAG pipeline |

Swagger/ReDoc/OpenAPI có sẵn ở `/docs`, `/redoc`, `/openapi.json`.

## Tái sử dụng và tổ chức code

- Router xử lý HTTP; `RAGService` quản lý admission và dựng public response;
  lifecycle sở hữu một runtime cho mỗi ASGI worker.
- Dùng nguyên `src.runtime.open_runtime`, factory, `run_with_trace` và các
  schema `QueryRequest`, `LegalAnswer`, `RetrievedChunk`, `PipelineStatus`.
- Không đổi thuật toán retrieval, evaluator, context, generation, verifier,
  feedback hoặc deadline. Không thêm loader cấu hình song song.
- Bổ sung duy nhất `api.max_concurrent_requests` vào Settings chung; mặc định 1.
  Dependency FastAPI/Uvicorn nằm trong hai file dependency hiện có;
  development extra bổ sung HTTPX để chạy TestClient.
- API sao chép settings và tắt auto-prepare: corpus/index phải chuẩn bị bằng
  CLI trước. Runtime được mở ở startup, đóng ở shutdown; không tạo lại theo request.

## Hành vi API

- Query không rỗng, tối đa 4.000 ký tự; từ chối field lạ và conversation ID khác
  null vì chưa có conversational memory.
- Chỉ trả answer của pipeline sau verification. Sources là context đã duyệt;
  không trả draft, analysis, evaluator reasoning hoặc chi tiết provider.
- Giữ nguyên fallback của orchestrator. Completed và insufficient_evidence
  trả 200; failed trả 502; timed_out trả 504.
- Runtime chưa sẵn sàng hoặc hết slot trả 503. Lỗi validation trả 422;
  lỗi bất ngờ trả 500 với mã lỗi an toàn.
- Inference chạy trong thread pool; admission kiểm tra trước khi cấp thread.
  Slot vẫn giữ tới khi worker hoàn tất nếu caller bị hủy.
- Request ID do server tạo, có trong header/body hỏi đáp/lỗi và log.
  Log mặc định không ghi question/source; CORS theo allowlist, kể cả lỗi 500.
- Corpus summary được tính một lần lúc startup và không lộ settings,
  credentials hoặc đường dẫn local.

## Kiểm chứng đã thực hiện

| Kiểm chứng | Kết quả |
| --- | --- |
| `pytest tests/api -q` | 35 passed |
| `pytest -q` | 401 passed, 10 skipped, 246 subtests passed |
| Compile API và tests | Đạt |
| `git diff --check` | Không có lỗi whitespace |

35 test API bao phủ input/JSON sai, boundary độ dài, public response,
fallback/timeout/verification failure, unexpected exception, correlation/log
privacy, busy admission, capacity 2, hủy caller, lifecycle và cleanup,
CORS, probes, corpus, settings precedence, OpenAPI và luồng qua orchestration
thật với fixture LLM/data.

Mười test database được skip theo cơ chế opt-in `RAG_RUN_DB_TESTS` hiện có.
Có một cảnh báo deprecation từ Starlette TestClient về HTTPX; test vẫn pass.
Trên máy Windows này sandbox chặn socket nội bộ của asyncio; kiểm thử TestClient
được chạy ngoài sandbox, không thay logic app để né vấn đề môi trường.

## Smoke với model và corpus thật

Đã gọi API qua ASGI TestClient với `open_runtime` thật, Ollama thật, tokenizer,
BM25, ONNX reranker và corpus ba chủ đề. Vector/graph được cấu hình **in-memory
một cách tường minh** cho lượt smoke; không tự fallback từ database lỗi.

- Corpus `4d70694000eb63e3`: 647 văn bản, 14.708 leaf chunks.
- Revision `a1b6860c821b7142ffe2385178af4e4bb6f86aff`.
- Health/live, health/ready và corpus đều trả 200.
- Câu hỏi về phạm vi Luật Giao thông đường thủy nội địa số 23/2004/QH11:
  HTTP 200, `completed`, 1 vòng, 4 citations, 5 nguồn context.
- Thời gian gọi pipeline và dựng response: khoảng 114,7 giây.
- Request ID khớp body/header; response không có draft.
- Artifact local: `.runtime/api-live-smoke/summary.json` và `response.json`;
  được gitignore. Runtime được đóng khi kết thúc TestClient.

Đây là smoke tích hợp, không phải benchmark chất lượng hay đo tải.
Lượt doctor trên PostgreSQL timeout; Docker Desktop không khởi động được
daemon trong phiên này. Vì vậy chưa xác nhận API với pgvector/Neo4j thật
trong đợt triển khai này. Production path vẫn dùng nguyên backend từ config;
profile demo mặc định tiếp tục chọn pgvector/Neo4j và không tự chuyển in-memory.

## Giới hạn của phiên bản

Mỗi request độc lập; chưa có đăng nhập, persistent history, streaming tiến độ,
job queue hoặc API quản trị ingestion. Readiness phản ánh runtime đã nạp,
không ping dependency liên tục. Tăng worker nhân runtime/bộ nhớ và tổng
concurrency; cần đo tải trước khi tăng. Confidence giữ nguyên chính sách
chưa hiệu chuẩn của pipeline hiện tại.
