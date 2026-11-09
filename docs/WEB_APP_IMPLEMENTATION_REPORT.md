# Báo cáo triển khai frontend — 08/11/2026

## Kết quả

Đã bổ sung web app React + TypeScript + Vite trong `frontend/`, sử dụng HTTP
contract FastAPI hiện có. Không chỉnh sửa backend, pipeline, schema Python,
cấu hình backend, database hoặc endpoint API.

Thay đổi gồm thư mục `frontend/` và hai tài liệu mới:
`docs/WEB_APP.md`, `docs/WEB_APP_IMPLEMENTATION_REPORT.md`.

## Chức năng đã hoàn thành

- Giao diện tiếng Việt cho desktop/mobile, bố cục sidebar, hỏi đáp và panel nguồn.
- Form hỏi đáp, gợi ý điền vào bản nháp, giới hạn ký tự theo OpenAPI, Enter gửi,
  Shift+Enter xuống dòng, hỗ trợ nhập liệu IME và ngăn gửi trùng.
- Trạng thái chờ với thời gian đã chờ; không mô phỏng tiến độ pipeline.
- Hiển thị nguyên nội dung backend trả, phân biệt completed, insufficient_evidence,
  failed và timed_out; xử lý ErrorResponse, bận, chưa sẵn sàng và lỗi mạng.
- Đọc JSON trên cả HTTP 502/504 để giữ fallback của pipeline.
- Thẻ trích dẫn và đoạn context đối chiếu theo các trường citation cùng đoạn trích
  nguyên văn; phân biệt trích dẫn với context bổ sung.
- Liên kết nguồn HTTP/HTTPS, loại URL chứa credentials; Markdown không thực thi
  HTML thô hoặc tải ảnh nhúng trong output model.
- Lịch sử câu hỏi trong bộ nhớ trang, chuyển lịch sử không hủy request đang chạy.
- Sao chép câu trả lời và trích dẫn; xem corpus, snapshot và readiness.
- Dialog nguồn và điều hướng trên mobile, Escape/focus modal native, label form,
  skip link và chế độ giảm chuyển động.

## Tổ chức và tái sử dụng

- `app/AppLayout.tsx` sở hữu bố cục; `app/App.tsx` điều phối các feature.
- `api/client.ts` gom HTTP, timeout, lỗi, Retry-After và request ID; không tự retry POST.
- `api/types.ts` sử dụng type sinh từ OpenAPI, không khai báo lại schema Python.
- `api/generated/contracts.json` sinh từ chính schema backend và được Ajv dùng
  để kiểm tra response khi chạy; giới hạn query cũng lấy từ schema này.
- `features/questions/hooks/useQuestionSession.ts` gom inference và lịch sử.
- `features/corpus/hooks/useServiceInfo.ts` gom kiểm tra dịch vụ/corpus.
- `features/sources/utils.ts` gom thao tác hiển thị vị trí và ghép citation/source,
  tương ứng các trường đối chiếu backend đã cung cấp; không kiểm chứng claim ở frontend.
- Các component dùng chung đặt trong `components/ui`; format và URL trong `lib`.
- Markdown được tách thành chunk tải khi cần. Code được định dạng bằng Prettier.
- Có lockfile, `.env.example`, script kiểm tra drift của API và fixture HTTP riêng
  chỉ dùng cho QA. Chạy ứng dụng mặc định không sử dụng dữ liệu giả lập.

## Kiểm chứng

| Kiểm tra | Kết quả |
| --- | --- |
| `npm test` | 43 tests passed, 5 files |
| `npm run build` | TypeScript và Vite production build đạt |
| `npm run api:check` | TypeScript/JSON Schema khớp OpenAPI backend |
| `npm run format:check` | Đạt |
| HTTP frontend local | Trả 200 |
| Trình duyệt desktop 1280 × 720 | Gợi ý, hỏi đáp, trích dẫn, context và lịch sử hoạt động với fixture |
| Trình duyệt mobile 390 × 844 | Dialog nguồn và menu/lịch sử hoạt động; không tràn ngang |
| Trình duyệt hẹp 320 × 640 | Không tràn ngang |
| HTTP fixture 503 / busy | Hiển thị thông báo, Retry-After và request ID, giữ câu hỏi |
| HTTP fixture 504 / timed_out | Hiển thị nguyên fallback và nhãn hết thời gian |

Tests bao phủ response sai contract, fallback 200/502/504, ErrorResponse 422/503,
Retry-After, lỗi mạng, timeout lúc chờ headers hoặc đọc body, không tự retry,
validation Unicode, chuyển lịch sử khi đang xử lý, không lưu lịch sử qua remount,
hiển thị/copy/nguồn/corpus/mobile, URL và Markdown an toàn.

Vitest được chạy ngoài sandbox sau khi môi trường sandbox Windows báo EPERM
ở thao tác rename file cache tạm. Không đổi logic ứng dụng để né lỗi môi trường.

Build cuối có JS chính khoảng 402,70 kB (gzip 126,19 kB), Markdown 167,83 kB
(gzip 51,04 kB), CSS 23,46 kB (gzip 5,99 kB). Không có cảnh báo chunk lớn.

Ảnh kiểm tra local nằm trong `.runtime/frontend-home.jpg`,
`.runtime/frontend-desktop.jpg`, `.runtime/frontend-mobile.jpg`; các ảnh này dùng
fixture tổng hợp, không phải kết quả pháp luật thật. `.runtime/` tiếp tục được
Git ignore. Các dịch vụ QA đã được dừng sau kiểm tra.

## Giới hạn kiểm chứng và phạm vi

API thật không chạy trên cổng 8000 trong phiên triển khai. Đã kiểm tra giao diện
khi API chưa kết nối và kiểm tra HTTP với fixture đúng contract, nhưng chưa chạy
smoke frontend → FastAPI → Ollama/pgvector/Neo4j thật. Các kết quả trên không
thay thế benchmark chất lượng pháp lý hoặc kiểm thử tải của pipeline.

Mỗi câu hỏi độc lập; chưa có tài khoản, lịch sử lưu lâu dài, conversational memory,
streaming, lọc query, đọc toàn văn hoặc quản trị ingestion. Confidence không được
trình bày thành phần trăm chính xác và snapshot không được diễn giải là xác nhận
hiệu lực pháp luật hiện tại.

## Chạy bàn giao

Backend chạy như trước theo [API.md](API.md). Terminal frontend:

```powershell
cd D:\dsp-vietnamese-legal-rag\frontend
npm ci
npm run dev
```

Mở `http://127.0.0.1:5173`. Cấu hình mặc định proxy tới API cổng 8000,
không yêu cầu sửa backend/CORS. Hướng dẫn chi tiết: [WEB_APP.md](WEB_APP.md).
