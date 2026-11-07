# Báo cáo RAG Orchestration

## Mục tiêu và phạm vi

Đã triển khai tầng điều phối theo mục 1.2, 6 của
[đặc tả](vietnamese_law_rag_technical_spec.md), các quy tắc trong
[INTERFACES.md](INTERFACES.md) và [hình pipeline](../legal_pipiline.png).
Data Pipeline/ingestion chạy trước; orchestration xử lý câu hỏi trên nguồn
đã index, không tự thu thập dữ liệu hoặc xây database trong từng request.

Luồng chính:

`Query Analyzer → Metadata Filter → Router → Retrieval Service → Context Builder → Evaluation → Answer Generator → Citation Verifier → Final Answer`

Context Builder chạy trong mỗi vòng trước Evaluation. Evaluator nhận đúng các
nguồn đã đóng gói mà generator sẽ dùng; không phê duyệt top-k rồi bỏ mất căn cứ
do ngân sách token ở bước sau. Trace vẫn giữ ranking retrieval gốc để chấm các
metric retrieval, đồng thời giữ context của vòng cuối kể cả khi bị từ chối.
Trong mỗi vòng, context được reset trước retrieval để lỗi ở vòng sau không trả
nhầm context của vòng trước. Đầu vào model evaluator chỉ có câu hỏi gốc;
query viết lại vẫn lưu trong trace/request cho retrieval và debug, không được
dùng làm yêu cầu bổ sung khi chấm đủ căn cứ.

Khi thiếu căn cứ, evaluator đề xuất refine query hoặc đổi strategy; pipeline
thực hiện đề xuất và **gọi lại Router** trước vòng retrieval tiếp theo.

## Các phần đã xây dựng

| File | Vai trò |
| --- | --- |
| `src/orchestration/rag_pipeline.py` | Điều phối, feedback loop, gate generation, fallback |
| `src/orchestration/pipeline_factory.py` | Nối các implementation có sẵn và adapter được inject |
| `core/schemas/orchestration.py` | `RetrievalRound`, `PipelineResult`, status và thông tin bước lỗi |
| `core/deadline.py` | Chia sẻ thời gian còn lại trong phạm vi từng request |
| `examples/orchestration_demo.py` | Demo chạy local với dữ liệu/LLM giả lập |
| `tests/test_orchestration.py` | Kiểm thử luồng, fallback, trace, deadline và request đồng thời |

Tái sử dụng `MetadataFilter`, `RetrievalRouter`, `RetrievalService`,
`RetrievalSettings.validate_strategy`, các schema và exception dùng chung.
Không viết lại BM25/vector/RRF/reranking/graph/context/citation logic.

## Hành vi chính

- Query Analyzer và Metadata Filter chạy một lần; giữ nguyên câu hỏi gốc
  cho evaluation/context/generation. Refine chỉ đổi query retrieval, giữ bộ
  lọc và entities đã xác định để không tự mở rộng phạm vi.
- `max_iterations` là tổng số vòng retrieval/evaluation, mặc định 3.
  `continue` nghĩa là sang generation; `stop` dừng sớm và trả thiếu căn cứ.
- Partial strategy override được merge rồi validate lại cả schema và hard
  limits; các key đã override được giữ qua các vòng và lần refine tiếp theo.
- Chỉ generation khi có hit và evaluation vừa relevant vừa sufficient.
  Context rỗng cũng không được đưa vào generator.
- Citation verification bắt buộc trước khi trả answer thành công. Nếu lỗi,
  không trả answer chưa xác minh hoặc tự loại citation để cho qua.
- `failure_details` phân biệt `citation_source_mismatch`, `unsupported_answer_claims`
  và `claim_support_check_failed`; `cause_type` chỉ rõ lỗi provider/parse bị bọc.
  Lý do verifier nằm trong artifact cục bộ, không ghi vào log warning. Log warning
  chỉ ghi stage, loại lỗi và mã lỗi; CLI benchmark cũng in mã lỗi dưới mẫu failed.
  Khi không có chi tiết, field mới được bỏ khỏi serialization để fingerprint của
  artifact cũ không đổi khi đọc lại.
- Fallback không gọi generator/verifier; trả thông báo hệ thống, citations
  rỗng, confidence 0. Không chuyển retrieval score/evaluation confidence thành
  answer confidence hoặc tự tắt filter/nhánh retrieval để thử lại khi lỗi.
- Lỗi nghiệp vụ/provider theo contract, `ValueError` và timeout được xử lý
  thành fallback; lỗi lập trình như `AttributeError` vẫn được truyền lên.

## Sử dụng và lịch sử từng request

`create_pipeline(settings, ...)` nhận adapter LLM cho analysis/evaluation/
verification, answer generator, tokenizer và các retriever/reranker được chọn.
Provider/model/credentials được cấu hình trước ở composition root. Với dịch
vụ thật, gọi `settings.validate_runtime()` trước khi khởi tạo các adapter.

```python
from core.schemas import QueryRequest

# pipeline được tạo bằng create_pipeline(...) hoặc inject trực tiếp vào RAGPipeline.
answer = pipeline.run(QueryRequest(query="Câu hỏi pháp luật"))
result = pipeline.run_with_trace(QueryRequest(query="Câu hỏi cần kiểm tra lịch sử"))
```

Hai API trên thực thi một request riêng mỗi lần gọi. `run` trả `LegalAnswer`;
`run_with_trace` trả thêm status (`completed`, `insufficient_evidence`,
`failed`, `timed_out`), danh sách rounds và `failure_stage`/`error_type` nếu lỗi.
Mỗi round giữ query, strategy, retrieval result và evaluation gồm reason;
bước chưa hoàn thành có field tương ứng là `None`.

`PipelineResult` còn giữ query gốc, analysis và filters thực dùng. Các field
này có default để trace cũ vẫn đọc được. Khi analysis chưa hoàn tất, giá trị
tương ứng là `None`; không lưu raw provider error trong trace.

History nằm trong kết quả của từng request, không có `last_history` dùng chung.
Service/API có thể serialize và lưu `PipelineResult` ở nơi phù hợp. History
chứa nội dung query/nguồn; pipeline không tự ghi chúng ra log. Log lỗi mặc
định chỉ chứa tên bước và loại exception, không in raw provider error.

## Deadline và giới hạn hiện tại

Deadline dùng `monotonic`, được kiểm tra trước/sau từng module; kết quả trả
về muộn bị loại và các bước tiếp theo không được chạy. Context deadline được
reset sau request và độc lập giữa các request đồng thời.

Mỗi lượt retrieval có scope deadline lồng từ `retrieval.timeout_s`, không vượt
deadline tổng. Cùng ngân sách đó áp dụng cho embedding, DB và reranking khi
adapter có hỗ trợ timeout/kiểm tra deadline.

Adapter cần đọc `core.deadline.remaining_timeout(configured_timeout_s)` trước
**mỗi call/retry** và dùng giá trị đó cho timeout client; scope lồng nhau không
thể kéo dài deadline cha. Adapter tự giới hạn retry trong ngân sách chung.

Interface hiện đồng bộ, không có cơ chế hủy call đang chạy. Vì vậy thời gian
phản hồi thực tế vẫn phụ thuộc adapter thực thi timeout; pipeline không tạo
thread nền để giả lập hủy hoặc hứa hard timeout cho call không hợp tác.

Composition root thật nằm ở `src/runtime.py`: ghép Ollama cho bốn vai trò,
embedding, pgvector, Neo4j, tokenizer và reranker vào factory hiện có. CLI ở
`scripts/demo.py`; xem [DEMO.md](DEMO.md) để chạy. Factory vẫn nhận dependency
được inject và không âm thầm thay bằng mock. FastAPI trong `src/api` dùng lại
runtime/factory này; xem [HTTP contract và cách chạy](API.md).

## Kết quả kiểm thử

```powershell
.\.venv\Scripts\python.exe -m examples.orchestration_demo
.\.venv\Scripts\python.exe -m pytest tests/test_orchestration.py -q
```

Demo đã chạy thành công, dùng BM25/filter/router/context/citation matching
thật với fixture LLM và mock generator có sẵn. `len` chỉ là bộ đếm giả lập,
không dùng để đếm token production hoặc đánh giá chất lượng pháp luật.

24 test orchestration pass, bao gồm feedback, strategy limits, thiếu căn cứ,
provider/citation lỗi, dữ liệu bị sửa, trace isolation, deadline và concurrent
requests. Kiểm tra hồi quy: **170 test pass**, gồm kiểm tra serialize các schema
orchestration mới; `git diff --check` không có lỗi whitespace.

Các con số trên ghi nhận mốc triển khai orchestration ban đầu với fixture.
Lần tích hợp demo mới đã cài đủ loader dependencies và chạy toàn bộ suite,
DB integration cùng model thật; kết quả tại
[báo cáo demo](DEMO_IMPLEMENTATION_REPORT.md). Chưa làm benchmark chất lượng.
