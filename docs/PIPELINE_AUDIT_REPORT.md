# Báo cáo rà soát và sửa lỗi pipeline — 03/11/2026

## Phạm vi

Rà soát đường chạy CLI từ query analysis, metadata filtering, retrieval/graph,
evaluation/feedback đến context, generation và citation verification; kiểm tra
cấu hình, cache/index, deadline và trace. Không mở rộng sang API, benchmark hay
triển khai. Giữ các contract sẵn có; chỉ bổ sung trường trace có default để đọc
được kết quả cũ.

Corpus kiểm tra là ba topic **Giao thông, vận tải; Khoa học, công nghệ; Giáo dục,
đào tạo**, từ `tmquan/phapdien-moj-gov-vn`, revision
`a1b6860c821b7142ffe2385178af4e4bb6f86aff`: 7.425 điều thuộc 647 văn bản,
14.708 embedded leaves, corpus ID `4d70694000eb63e3`. Chạy Ollama, pgvector và
Neo4j thật, bật BM25, vector, graph và ONNX reranker.

## Lỗi tìm được và cách sửa

| Vấn đề | Thay đổi |
| --- | --- |
| Generation hết output budget hoặc chép sai citation | Model xuất draft gồm answer và số nguồn. Code dựng citation từ metadata/nội dung nguồn nguyên vẹn; verifier vẫn kiểm tra căn cứ. Generator dùng Qwen3.5:4b, output budget 2.048 token; các agent khác dùng 2b. Phân biệt lỗi hết output và vượt context window. |
| Agent suy diễn sai hard filter, có lúc sinh `document_type: []` làm mất toàn bộ kết quả | Analyzer chỉ tạo hard filter khi câu hỏi gốc nêu rõ nhãn có trong corpus. LLM phụ trách rewrite/intent/entities/keywords. Cụm chung “pháp luật” không ép chỉ tìm văn bản Luật. Filter do caller truyền vẫn giữ semantics strict, kể cả danh sách rỗng. |
| Evaluator vượt cửa sổ model dù retrieval đã cắt top-k | Dùng chung hàm giữ quan hệ có đủ endpoint/evidence sau lọc và cắt top-k. Payload judge giữ toàn bộ nội dung nguồn nhưng bỏ provenance dài không cần thiết. Replay trace lỗi giảm prompt từ 8.113 xuống 3.103 token; trước đó cộng overhead 128 và output 768 vượt window 8.192. |
| Ollama `/api/embed` trả HTTP 500 | Đã đối chiếu server log: BGE runner lỗi CUDA khi warmup. Profile demo đặt embedding `device: cpu`, adapter truyền `num_gpu: 0`; giữ nguyên model, dimension và normalization. Không âm thầm đổi model/backend. |
| Lỗi HTTP tạm thời chưa được retry nhất quán | Dùng chung retry có giới hạn cho connection/timeout và HTTP 429/500/502/503/504, nằm trong deadline hiện tại. Không retry lỗi cấu hình/quyền truy cập hay JSON sai. |
| Context có thể thiếu phần điều kiện; verifier tốn token vì lặp quotation | Context chọn ancestor nguyên vẹn lớn nhất còn vừa budget, kiểm tra cycle và cùng văn bản. Verifier kiểm tra identity/quote bằng code trước, rồi chỉ gửi mỗi nguồn được dẫn một lần để đánh giá claim. |
| Một số cấu hình chưa tác động đúng đường chạy | Áp dụng timeout riêng của retrieval trong deadline tổng; kiểm tra prompt version/file/template trước khi nhận câu hỏi. Fingerprint physical vector index gồm cả tham số xây HNSW/IVFFlat, tránh dùng nhầm index cũ khi đổi cấu hình. Auto-prepare chỉ ghi store còn thiếu. |
| Khó truy nguyên lỗi và feedback không hợp lệ | Trace thêm query gốc, analysis và filters thực dùng. Structured schema phản ánh các trạng thái feedback hợp lệ và giới hạn strategy; orchestrator vẫn validate trước khi chạy. Logging dùng level trong config, `--debug` ưu tiên cao hơn. |

Tái sử dụng schema, tokenizer, adapter và composition root hiện có. Logic kiểm
tra quan hệ và chuẩn bị evidence cho judge được dùng chung; không thêm fuzzy
matching, tự sửa quote hoặc bỏ gate kiểm chứng để đạt trạng thái thành công.

## Kết quả kiểm tra

- **315 tests và 246 subtests pass**, gồm kiểm thử thực với pgvector/Neo4j:
  ba metric × ba kiểu vector index, graph/filter và cô lập dữ liệu test.
- Bổ sung hồi quy cho filter sai, graph evidence sau top-k, token payload,
  thiết bị embedding, retry/deadline, prompt version, fingerprint index và
  schema feedback. Kiểm tra concurrency giữ filters theo từng request.
- Chạy **hai lượt độc lập, mỗi lượt 10/10 ca đạt trạng thái kỳ vọng** trên corpus
  ba topic: 9 câu trả `completed`, 1 câu không có dữ liệu trả
  `insufficient_evidence`. Lượt cuối có câu cần 2–3 vòng feedback và vẫn hoàn tất.
  Các câu lỗi người dùng báo, nghĩa vụ người sản xuất và phân biệt tiêu chuẩn/
  quy chuẩn đều nằm trong bộ chạy này.
- `compileall` và `git diff --check` đạt.

Log hồi quy: `.runtime/audit-tests-final.log`. Trace từng ca và kết quả lượt
cuối: `.runtime/pipeline-smoke-final/summary.json`. Đây là artifact local được
gitignore, không phải dataset/benchmark mới.

Chạy lại từ root repository, sau khi Ollama và hai database sẵn sàng:

```powershell
$env:RAG_RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.smoke_pipeline
```

Smoke script yêu cầu đủ ba topic trên, dùng cùng loader/config/runtime của CLI
và lưu kết quả từng ca ngay sau khi chạy. Đổi YAML/code cần thoát chat cũ bằng
`/exit` rồi mở lại `python -m scripts.demo chat`.

## Giới hạn

Kết quả xác nhận các lỗi đã tái hiện và độ nhất quán của profile demo trên máy
hiện tại. Chưa chứng minh chất lượng pháp lý hoặc độ ổn định cho mọi câu hỏi,
model, backend và tổ hợp cấu hình. Model vẫn có thể chọn nguồn chưa đủ, trả
output không hợp lệ hoặc hết thời gian; pipeline tiếp tục trả fallback thay vì
câu trả lời chưa xác minh. Nguồn Pháp điển chưa đủ metadata để tự kết luận mọi
văn bản còn hiệu lực. Chưa có benchmark để khẳng định cấu hình là tối ưu.

Tham chiếu cho tùy chọn embedding:
[Ollama embed API](https://docs.ollama.com/api/embed),
[Ollama runner options](https://github.com/ollama/ollama/blob/main/api/types.go).
