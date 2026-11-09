# Vietnamese Legal RAG — Full Web Application

Ứng dụng hỏi đáp pháp luật tiếng Việt chạy đầy đủ từ React frontend qua
FastAPI tới pipeline RAG, Ollama, PostgreSQL/pgvector và Neo4j. Frontend hiển thị
câu trả lời, trích dẫn và nguồn; mỗi câu hỏi được xử lý độc lập.

Cấu hình đang dùng nằm trong **`configs/`**, credentials nằm trong **`.env`
tại root**. Bốn online LLM roles dùng `qwen3.5:2b`; embedding dùng BGE-M3.

## 1. Chuẩn bị môi trường

Cần Git, Python >=3.10 (khuyến nghị 3.12), Docker Desktop, Ollama và
Node.js >=22.18. Chạy lệnh PowerShell từ root repository.

```powershell
git clone https://github.com/luannt1010/dsp-vietnamese-legal-rag.git
cd dsp-vietnamese-legal-rag
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ollama pull bge-m3
ollama pull qwen3.5:2b
```

Có thể dùng Conda thay venv. Giữ môi trường Python đã kích hoạt khi chạy API
hoặc chuẩn bị index. Nếu Ollama chưa phục vụ, mở `ollama serve` ở terminal riêng.

## 2. Database và credentials

Mở Docker Desktop rồi chạy utility tạo/khởi động database hiện có:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_demo_databases.ps1
if (-not (Test-Path .\.env)) {
    Copy-Item .\.runtime\demo.env .\.env
}
```

Tên script được giữ để tương thích. Ứng dụng sử dụng root `configs/` và `.env`.
Script tạo credentials ngẫu nhiên ở `.runtime/demo.env` khi thiết lập lần đầu.
Khi dùng lại database, giữ đúng mật khẩu đã gắn với volume và không ghi đè
`.env` hiện có.

| Dịch vụ | Container | Địa chỉ local |
| --- | --- | --- |
| PostgreSQL + pgvector | `legalrag-pgvector` | `127.0.0.1:15432` |
| Neo4j Bolt | `legalrag-neo4j` | `bolt://127.0.0.1:17687` |
| Neo4j Browser | cùng container | `http://127.0.0.1:17474` |
| Ollama | ứng dụng trên máy | `http://127.0.0.1:11434` |

Nếu container cũ đang dừng còn dùng port bị Windows chặn, đổi port bằng
`-PostgresPort 15432 -RecreateStoppedContainers`. Utility giữ container cũ làm
backup và dùng lại named volume. Đồng bộ port tương ứng trong root `.env`.

## 3. Chọn dữ liệu và chuẩn bị index

Chọn `data_pipeline.source.topics` / `subjects` trong
`configs/data_pipeline.yml`. Cấu hình hiện tại gồm giao thông, vận tải;
khoa học, công nghệ; giáo dục, đào tạo.

```powershell
$env:RAG_CONFIG_DIR = (Resolve-Path .\configs).Path
$env:RAG_ENV_FILE = (Resolve-Path .\.env).Path
python -c "from dotenv import load_dotenv; load_dotenv('.env', encoding='utf-8-sig'); from core.config import load_settings; from src.runtime import prepare_indexes; prepare_indexes(load_settings('configs'))"
```

Lần đầu cần tải dữ liệu/model/tokenizer và tạo embeddings, indexes. Các lần
sau tái sử dụng cache tương thích. API phục vụ các index đã chuẩn bị.

## 4. Chạy backend và frontend

Terminal backend tại root, với môi trường Python đã kích hoạt:

```powershell
$env:RAG_CONFIG_DIR = (Resolve-Path .\configs).Path
$env:RAG_ENV_FILE = (Resolve-Path .\.env).Path
python -m src.api
```

API: `http://127.0.0.1:8000`, Swagger: `http://127.0.0.1:8000/docs`.
Các selector được truyền rõ ràng vì entry point API còn giữ mặc định legacy.

Terminal frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Mở **http://127.0.0.1:5173**. Vite proxy `/api` và `/health` tới FastAPI.
Không cần đưa credentials backend vào frontend hoặc thay đổi API contract.

## 5. Build và truy cập qua ngrok

Giữ backend chạy. Từ thư mục `frontend`:

```powershell
npm run build
npm run preview -- --host 127.0.0.1
```

Mở terminal khác để truy cập từ xa:

```powershell
ngrok http 4173
```

Nếu Vite yêu cầu cho phép hostname tunnel, thêm hostname của bạn qua biến
`__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` trước khi khởi động preview. Ví dụ:
`$env:__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS = 'your-host.ngrok-free.app'`.
Máy local, backend, database, Ollama và tunnel cần tiếp tục hoạt động.

## 6. Kiểm tra

Tại root, chọn cùng `RAG_CONFIG_DIR` / `RAG_ENV_FILE` như khi mở API:

```powershell
python -m pytest -q
powershell -ExecutionPolicy Bypass -File .\tests\test_database_launcher.ps1
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run api:check
npm --prefix frontend run format:check
```

Tests thông thường dùng fixture, không cần chạy inference hoặc database thật.
Database integration tests chỉ chạy khi đặt `RAG_RUN_DB_TESTS=1`.

## 7. Benchmark và tài liệu

Bộ development ba chủ đề có 45 câu hỏi tại
`data/evaluation/new/three_topics_pilot.development.v1.jsonl`. Khi chạy benchmark,
truyền rõ `--config-dir configs --env-file .env` cho `run` và `score`.
`score --retrieval-only` không gọi quality judge. Judge 2B mặc định không thể
chấm generator 2B nếu `allow_same_model=false`; cần chọn judge khác trước khi
chấm semantic quality.

Kết quả lịch sử dùng cấu hình online 2B/4B, khác cấu hình web hiện tại toàn 2B.
Development set chưa phải held-out test; completion không đồng nghĩa đúng pháp lý.

- [Frontend: kiến trúc và cấu hình](docs/WEB_APP.md)
- [Báo cáo triển khai frontend](docs/WEB_APP_IMPLEMENTATION_REPORT.md)
- [API và HTTP contract](docs/API.md)
- [Config loader và overrides](docs/CONFIGURATION.md)
- [Metric definitions và vận hành benchmark](docs/BENCHMARK.md)
- [Bộ câu hỏi development](data/evaluation/new/README.md)

Theo `.gitignore`, báo cáo/slide local (`final_report_slide/`, `reports/`),
artifact xuất (`output/`), credentials và runtime/cache không được push lên GitHub.
