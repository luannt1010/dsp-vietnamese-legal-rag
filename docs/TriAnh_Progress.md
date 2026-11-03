# Báo cáo công việc Trí Anh

## Tóm tắt

Đã xây dựng bản triển khai đầu tiên cho Query Understanding và Retrieval
Evaluation theo schema/interface trong `core/`. Hai module gọi LLM thông qua
`BaseLLM`, kiểm tra JSON đầu ra bằng Pydantic và báo `LLMError` khi đầu ra sai.
Evaluator xử lý retrieval rỗng theo hướng thiếu căn cứ mà không gọi LLM.

Các module đã được tích hợp vào đường chạy orchestration/demo mới nhất. Báo
cáo audit ghi nhận smoke test với dịch vụ thật, nhưng chưa có benchmark chất
lượng trên bộ câu hỏi pháp lý đã gán nhãn; smoke test không thay thế ground
truth hoặc đánh giá chất lượng.

## Đã hoàn thành

- `src/query_understanding/`: Query Analyzer sử dụng `BaseQueryAnalyzer`,
  trả `QueryAnalysisResult` và luôn giữ câu hỏi gốc chính xác từ request.
- `src/evaluation/`: Retrieval Evaluator sử dụng `BaseEvaluator`,
  trả `RetrievalEvaluationResult`, không tự gọi retrieval và xử lý danh sách
  kết quả rỗng theo hướng `stop`/insufficient.
- `prompts/query_analyzer/v1.txt`: hướng dẫn rewrite thận trọng, intent
  phân loại ban đầu và extraction không suy diễn metadata.
- `prompts/retrieval_evaluator/v1.txt`: tiêu chí relevance/sufficiency,
  quy tắc feedback action và giới hạn vai trò evaluator.
- `src/evaluation/metrics.py`: metrics retrieval gồm Precision@k, Recall@k,
  Average Precision/MAP, Reciprocal Rank/MRR, Hit@k, nDCG@k; context precision
  theo reference IDs hoặc phán đoán độ liên quan từng context, context recall
  theo reference claims, faithfulness, answer relevancy và factual correctness
  tổng hợp các nhãn/similarity judgments có sẵn.
- `src/evaluation/dataset.py`: schema và JSONL loader cho bộ câu hỏi đã gán
  nhãn; kiểm tra evidence/reference claims, answerability, ID trùng, split và
  ngăn một `split_group` xuất hiện ở cả development lẫn test.
- `docs/EVALUATION_DATASET.md`: mô tả cấu trúc dữ liệu, quy trình gán nhãn,
  split và giới hạn hiện tại của benchmark.
- Evaluator hiện nằm trong pipeline orchestration: orchestration lưu từng
  retrieval/evaluation round, áp dụng feedback và chỉ cho generation tiếp tục
  khi đủ căn cứ. Cần xác nhận taxonomy intent và semantics metadata/filter với
  nhóm; đây không còn là blocker cho tích hợp evaluator.
- JSON output của LLM từ chối `NaN`, `Infinity`, `-Infinity`; lỗi decoder như
  integer vượt giới hạn được bọc thành `LLMError` và giữ nguyên nguyên nhân.
- Đã xử lý các góp ý review của tech lead trong commit `61d5fee`
  (`fix: validate LLM JSON and add RAG metrics`):
  - Thêm `parse_constant` để từ chối các giá trị số không hữu hạn trong JSON.
  - Bắt `ValueError` từ decoder và giữ nguyên nguyên nhân với
    `raise LLMError(...) from exc`.
  - Bổ sung regression tests cho `NaN`, `Infinity`, `-Infinity` và integer
    vượt giới hạn chuyển đổi của Python.
  - Bổ sung Precision@k, Average Precision/MAP, MRR, Hit@k, context precision,
    context recall, faithfulness, answer relevancy và factual correctness.
- Unit tests cho hai module và metric, sử dụng `BaseLLM` giả để không cần API
  key hoặc dịch vụ ngoài.
- Cả hai module nhận `prompt_version` khi khởi tạo; mặc định dùng `v1`, khớp
  với `settings.llm.query_analyzer.prompt_version` và
  `settings.llm.retrieval_evaluator.prompt_version`.

Ví dụ wiring khi tạo module:

```python
analyzer = QueryAnalyzer(
    llm=query_analyzer_llm,
    prompt_version=settings.llm.query_analyzer.prompt_version,
)
evaluator = RetrievalEvaluator(
    llm=retrieval_evaluator_llm,
    prompt_version=settings.llm.retrieval_evaluator.prompt_version,
)
```

## Cần phối hợp / chưa hoàn thành

- **Luân/nhóm:** xác nhận taxonomy intent, metadata/filter semantics và
  strategy feedback theo contract/runtime hiện tại; tích hợp evaluator đã
  được mô tả trong orchestration và audit.
- **Đức Anh/nhóm dữ liệu:** chốt corpus snapshot/ID và hỗ trợ xác minh nguồn,
  metadata, hiệu lực/sửa đổi văn bản cho từng record. Corpus pipeline đã có;
  đầu việc còn lại là phiên bản cố định và evidence đáng tin cậy cho benchmark,
  không phải tạo corpus từ đầu.
- **Nhóm phụ trách LLM:** cấu hình demo hiện đã có model cho các vai trò và
  smoke test với Ollama được báo cáo. Benchmark cần khóa revision/model,
  prompt, context window và judge identity trong manifest; đây là yêu cầu tái
  lập, không phải khẳng định adapter LLM thật chưa tồn tại.
- **Nhóm:** định nghĩa rubric gán nhãn relevance và sufficiency, bộ câu hỏi
  kiểm thử, expected relevant chunk/document IDs và tiêu chí nghiệm thu.
- **Benchmark thật:** chưa chạy; hiện chỉ có unit tests và metric functions,
  chưa có evaluation dataset gán nhãn. `data/chunks/phapdien_chunks.json` là
  corpus 100 chunk/12 văn bản, không phải ground truth benchmark. Kết quả
  benchmark không thể được suy ra từ các test giả lập.
- **Benchmark runner:** B0–B4 chưa được triển khai; runner/manifests, lưu
  context/draft, cutoff 20/5, policy khóa feedback, judge và thống kê CI/latency
  còn chờ triển khai riêng.
- **Bộ câu hỏi gán nhãn:** chưa tạo vì cần người trong nhóm kiểm tra câu hỏi,
  đáp án và trích dẫn theo đúng corpus revision; không dùng corpus chunks làm
  nhãn tự động.
- **Phân công evaluation dataset:** technical specification giao Evaluation
  Dataset và Benchmark cho Trí Anh. Trí Anh có thể sở hữu schema, JSONL,
  annotation workflow, IDs/splits và tích hợp benchmark; đáp án/evidence pháp
  lý cần thành viên phụ trách dữ liệu và reviewer thứ hai kiểm tra.
- **Đánh giá prompt/chất lượng model:** chưa thực hiện với provider thật; cần
  cấu hình model, credentials phù hợp và ví dụ pháp lý được nhóm duyệt.

## Rủi ro / quyết định cần chốt

1. Intent labels trong prompt hiện là taxonomy **đề xuất ban đầu**, chưa được
   nhóm phê duyệt.
2. Metadata đầu ra hiện được hướng dẫn giới hạn ở `legal_domain` và
   `document_type` khi có căn cứ; cần xác nhận hai key này khớp filter adapter.
3. Với retrieval không rỗng nhưng thiếu căn cứ, evaluator có thể đề xuất
   `refine_query`, `change_strategy` hoặc `stop`; orchestrator phải kiểm tra
   `max_iterations` và validate strategy sau khi merge.
4. Các metric theo stage chỉ tổng hợp ID, nhãn claim hoặc similarity scores
   đã được gán/tính từ bên ngoài; không tự làm LLM claim extraction,
   entailment hoặc embedding. Định nghĩa tham khảo Ragas:
   https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/

## Trạng thái branch và pull request

- PR #2 trên `feature/query-understanding-evaluation` là PR lịch sử cho phần
  Query Understanding/Evaluation ban đầu; các commit ở đó không đại diện cho
  thay đổi benchmark hiện tại.
- Phần bổ sung dataset/metrics hiện được làm trên branch
  `feature/evaluation-benchmark-support` từ `main`; tại thời điểm ghi báo cáo,
  thay đổi chưa commit/push và chưa có PR. PR mới nên mô tả rõ loader/metrics
  đã làm và các phần dataset có nhãn/runner còn chưa làm.

## Kiểm thử

Ở lần kiểm thử gần nhất sau khi thêm dataset/metrics, đã chạy toàn bộ suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Kết quả ghi nhận ở lần chạy đó: **313 passed, 10 skipped, 246 subtests
passed**. Các báo cáo audit/demo khác ghi nhận các tổng số test khác nhau theo
thời điểm và phạm vi; hãy chạy lại suite trên branch PR và dùng đúng kết quả
đó trong mô tả PR.
