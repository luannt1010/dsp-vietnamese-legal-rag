# Vietnamese Legal RAG — Web app

Frontend React + TypeScript + Vite, sử dụng API FastAPI hiện có. Không cần sửa
backend hoặc cấu hình CORS khi dùng Vite proxy mặc định.

## Chạy local

Cần Node.js **22.18+** hoặc **24 LTS**, npm và backend đã chuẩn bị theo README
ở root repository.

Terminal 1, tại root project, kích hoạt môi trường Python rồi chạy API như cũ:

```powershell
$env:RAG_CONFIG_DIR = (Resolve-Path .\configs).Path
$env:RAG_ENV_FILE = (Resolve-Path .\.env).Path
python -m src.api
```

Terminal 2:

```powershell
cd D:\dsp-vietnamese-legal-rag\frontend
npm ci
npm run dev
```

Mở **http://127.0.0.1:5173**. `/api` và `/health` được Vite chuyển tiếp tới
`http://127.0.0.1:8000`. Nếu backend chưa chạy, giao diện vẫn mở và thông báo
chưa kết nối; không tự thay bằng dữ liệu mẫu.

## Kiểm tra

```powershell
npm test
npm run build
npm run api:check
npm run format:check
```

`api:check` và `api:generate` cần môi trường Python đã cài dependencies của project;
không cần chạy API, model hay database. File contract đã sinh được commit cùng
frontend nên chạy web/build thông thường chỉ cần Node.js.

Xem [tài liệu kiến trúc, cấu hình và triển khai](../docs/WEB_APP.md) và
[báo cáo triển khai](../docs/WEB_APP_IMPLEMENTATION_REPORT.md).
