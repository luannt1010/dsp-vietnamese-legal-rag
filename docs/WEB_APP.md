# Web app Vietnamese Legal RAG

## Phạm vi

Ứng dụng React + TypeScript + Vite nằm trong `frontend/`, gọi FastAPI sẵn có.
Không sửa `src/`, `core/`, `configs/` hoặc API contract Python. Frontend không
gọi Ollama, PostgreSQL hoặc Neo4j trực tiếp.

Các chức năng hiện có:

- Hỏi đáp độc lập, tối đa số ký tự quy định trong OpenAPI (hiện 4.000).
- Câu hỏi gợi ý để chỉnh sửa trước khi gửi.
- Markdown cho câu trả lời; hiển thị trạng thái pipeline và disclaimer từ API.
- Thẻ trích dẫn, đoạn nguồn đối chiếu, danh sách context và liên kết nguồn.
- Lịch sử trong bộ nhớ của trang; chuyển qua lại khi một câu hỏi đang xử lý.
- Thông tin corpus, readiness kiểm tra lúc mở trang hoặc khi người dùng tải lại.
- Sao chép câu trả lời kèm trích dẫn; layout desktop và mobile.

Lịch sử không phải conversational memory, không gửi câu trước và không gửi
`conversation_id`. Không lưu lịch sử vào localStorage hoặc một database khác.
Tải lại/đóng trang sẽ mất lịch sử. Frontend không tự log nội dung câu hỏi.

## Chạy trên Windows PowerShell

Yêu cầu Node.js >=22.18 (hoặc 24 LTS) và npm. Backend cần được chuẩn bị theo
[README](../README.md) và [API.md](API.md).

Terminal backend tại root, trong môi trường Python đã kích hoạt:

```powershell
$env:RAG_CONFIG_DIR = (Resolve-Path .\configs).Path
$env:RAG_ENV_FILE = (Resolve-Path .\.env).Path
python -m src.api
```

Terminal frontend:

```powershell
cd D:\dsp-vietnamese-legal-rag\frontend
npm ci
npm run dev
```

Mở `http://127.0.0.1:5173`. Vite bind loopback và dùng port cố định; nếu cổng
đã có process khác thì báo lỗi thay vì âm thầm chọn cổng khác.

Không cần sao chép `.env.example` để dùng cấu hình mặc định. Khi cần, sao chép
thành `frontend/.env.local`, thay giá trị và khởi động lại Vite.

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `API_PROXY_TARGET` | `http://127.0.0.1:8000` | Đích proxy của Vite dev/preview; không đưa vào bundle trình duyệt |
| `VITE_API_BASE_URL` | rỗng | Rỗng gọi cùng origin; hoặc URL gốc backend, không kèm `/api/v1` |
| `VITE_API_TIMEOUT_MS` | `300000` | Deadline chờ response câu hỏi trên trình duyệt |

`VITE_*` là cấu hình public được nhúng lúc build. Không đặt mật khẩu, token
database hoặc credentials backend vào các biến này.

Khuyến nghị dùng proxy cùng origin. Chỉ khi trình duyệt gọi trực tiếp một
origin API khác mới cần cấu hình CORS theo khả năng backend đã có; frontend
không tự thay cấu hình backend.

## Cấu trúc và trách nhiệm

```text
frontend/
  src/
    app/                  # Điều phối ứng dụng và layout
    api/
      generated/          # TypeScript và JSON Schema sinh từ OpenAPI
      contracts.ts        # Validator response và giới hạn query dùng chung
      client.ts           # HTTP, deadline, ErrorResponse, request ID
      questions.ts        # Endpoint hỏi đáp
      corpus.ts           # Endpoint corpus
      health.ts           # Endpoint readiness
      types.ts            # Alias tới type đã sinh
    features/
      questions/          # Form, kết quả, validation, trạng thái request
      sources/            # Trích dẫn, context, ghép nguồn để hiển thị
      history/            # Danh sách câu hỏi trong phiên
      corpus/             # Thông tin dịch vụ và dữ liệu
    components/ui/        # Brand, dialog, Markdown dùng chung
    lib/                  # Format và kiểm tra URL
    styles/               # Design tokens, layout, questions, sources
    test/                 # Setup và fixture tổng hợp dùng chung
  scripts/
    generate-api.mjs       # Sinh/kiểm tra contract từ app Python
    fixture-api.mjs        # HTTP fixture riêng cho QA trình duyệt
```

Component không gọi `fetch` trực tiếp. Các endpoint dùng chung `api/client.ts`.
`useQuestionSession` sở hữu trạng thái inference và lịch sử; `useServiceInfo`
sở hữu corpus/readiness. Các component nhận dữ liệu và callback qua props.
Không thêm global state library khi chưa cần chia sẻ trạng thái rộng hơn.

Markdown được tải theo nhu cầu sau khi có kết quả. Các thành phần bố cục và
chức năng không phụ thuộc vào model, retrieval strategy hoặc cấu hình database.

## Tái sử dụng OpenAPI

```powershell
cd frontend
npm run api:generate
npm run api:check
```

Script import app FastAPI hiện có rồi gọi `app.openapi()`, không khởi chạy ASGI
lifespan, không nạp runtime/model và không kết nối database. Tự chọn Python
trong `.venv` của repository; có thể chỉ định interpreter bằng biến `PYTHON`.

Sinh hai file được theo dõi trong Git:

- `src/api/generated/schema.d.ts`: type TypeScript và đường dẫn API.
- `src/api/generated/contracts.json`: JSON Schema cho validation runtime bằng Ajv.

Không chỉnh hai file này bằng tay. Khi backend sau này đổi contract, sinh lại
rồi kiểm tra các chỗ TypeScript bị ảnh hưởng. `api:check` trả exit code khác 0
nếu contract frontend không còn khớp backend.

Giới hạn độ dài query cũng lấy từ schema đã sinh. Cách đếm ký tự dựa trên
Unicode code point để khớp Python, bao gồm ký tự ngoài BMP như emoji.

## Hành vi HTTP

| Kết quả | Hành vi frontend |
| --- | --- |
| `200 / completed` | Hiển thị câu trả lời và trích dẫn |
| `200 / insufficient_evidence` | Hiển thị nguyên fallback, nhãn chưa đủ căn cứ |
| `502 / failed` | Đọc QuestionResponse và hiển thị nguyên fallback |
| `504 / timed_out` | Đọc QuestionResponse và hiển thị nguyên fallback |
| `422` | Hiển thị lỗi và issues từ ErrorResponse |
| `503 / service_busy` | Thông báo bận và Retry-After khi có |
| `503 / service_not_ready` | Thông báo dịch vụ chưa sẵn sàng |
| Lỗi mạng / deadline client | Giữ câu hỏi để xem lại và gửi lại thủ công |
| Response sai contract | Báo sai định dạng, không render như kết quả hợp lệ |

Không tự retry POST. Khóa gửi dùng cả state UI và ref đồng bộ để ngăn thao tác
gửi trùng; chuyển lịch sử không giải phóng khóa. Khóa này chỉ có hiệu lực trong
một trang; capacity limiter backend tiếp tục quyết định tổng số request.

Deadline client mặc định 300 giây, lớn hơn deadline pipeline demo 240 giây.
Timeout proxy Vite có thêm 15 giây đệm. Nếu thay timeout backend sau này, cần
điều chỉnh cấu hình frontend/proxy tương ứng. Timeout trình duyệt hoặc đóng
trang không có nghĩa inference backend đã dừng.

Readiness chỉ là trạng thái runtime tại thời điểm kiểm tra; không đồng nghĩa
mọi model/database đang hoạt động hoặc còn slot inference.

## Hiển thị căn cứ

Frontend giữ riêng `answer.citations` với `sources`. Việc ghép trích dẫn với
context để hiển thị dựa trên document ID, số văn bản, các trường vị trí/source URL
đã cung cấp và đoạn trích nguyên văn, tương ứng quy tắc đối chiếu của backend.
Không ghép chỉ vì cùng văn bản hoặc cùng điều. Nếu không khớp, hiển thị rõ và
vẫn cho xem toàn bộ context. Frontend không thực hiện lại bước kiểm chứng claim.

Không diễn giải retrieval score thành confidence hoặc trình bày confidence
thành phần trăm chính xác. Không xác nhận hiệu lực pháp luật dựa trên snapshot.
Không có đọc toàn văn vì API hiện chỉ trả các đoạn nguồn.

Markdown không chạy HTML thô, không tải ảnh được nhúng trong câu trả lời.
Link nguồn chỉ cho HTTP/HTTPS, loại URL chứa credentials và mở tab mới với
`noopener noreferrer`. Dialog dùng modal native có Escape/focus; form có label,
thông báo lỗi và hỗ trợ Enter/Shift+Enter, tôn trọng IME.

## Kiểm thử và QA bằng fixture

```powershell
npm test
npm run build
npm run format:check
npm run api:check
```

Tests dùng Vitest, Testing Library và jsdom. Bộ fixture là dữ liệu tổng hợp,
không phải câu trả lời pháp luật. Có thể mở cùng fixture qua HTTP riêng:

Terminal fixture:

```powershell
cd frontend
npm run test:fixture-api
```

Terminal frontend QA riêng:

```powershell
cd frontend
$env:API_PROXY_TARGET = 'http://127.0.0.1:8010'
npm run dev
```

Nhập câu bất kỳ để nhận kết quả minh họa. Các từ khóa `busy`, `failed`,
`timeout`, `thiếu căn cứ` chọn các response tương ứng. Đây là lựa chọn tường minh
cho QA, không có fallback tự động khi API thật lỗi. Không chạy đồng thời hai
Vite server trên cùng cổng.

Kết thúc QA bằng Ctrl+C trong cả hai terminal. Xóa override trong terminal
frontend trước khi chạy lại với API thật:

```powershell
Remove-Item Env:API_PROXY_TARGET
npm run dev
```

Trên một số môi trường sandbox Windows, Vitest bị chặn thao tác rename trong
thư mục tạm. Chạy test ở terminal PowerShell thông thường nếu gặp lỗi EPERM này.

## Build và phục vụ

```powershell
npm run build
npm run preview
```

Build nằm trong `frontend/dist/`; preview ở `http://127.0.0.1:4173` và cũng có
proxy local. Preview phục vụ kiểm tra bản build.

Khi triển khai thực tế, static server phục vụ `dist/`; reverse proxy cùng domain
chuyển `/api/` và `/health/` tới FastAPI, response timeout lớn hơn deadline client.
Chỉ upload `dist/`, không upload repository, `.runtime`, dữ liệu hay credentials.
Các script fixture, Python và node_modules không nằm trong output build.

Ứng dụng hiện phục vụ local/internal theo phạm vi API sẵn có. Đăng nhập, lịch sử
theo tài khoản, conversational memory, bộ lọc query, streaming và quản trị ingestion
cần thiết kế API bổ sung khi phát triển các giai đoạn sau.
