# Báo cáo công việc Trí Anh

## Tóm tắt

Đã xây dựng bản triển khai đầu tiên cho Query Understanding và Retrieval
Evaluation theo schema/interface trong `core/`. Hai module gọi LLM thông qua
`BaseLLM`, kiểm tra JSON đầu ra bằng Pydantic và báo `LLMError` khi đầu ra sai.
Evaluator xử lý retrieval rỗng theo hướng thiếu căn cứ mà không gọi LLM.

Đây là bản nền có thể kiểm thử độc lập; chưa được benchmark trên dữ liệu pháp
luật thật và chưa tích hợp với retriever/orchestrator thật.

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
  và recall dựa trên reference IDs; faithfulness, answer relevancy và factual
  correctness tổng hợp các nhãn/similarity judgments có sẵn.
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

- **Luân:** thống nhất taxonomy intent và các metadata key được phép đi tiếp
  vào metadata filtering; xác nhận các strategy override evaluator được phép
  đề xuất; tích hợp evaluator vào orchestration.
- **Đức Anh:** cung cấp corpus/chunk pháp luật mẫu và metadata chuẩn để tạo
  evaluation dataset có căn cứ, gán nhãn đúng nguồn.
- **Luân/nhóm phụ trách LLM:** chốt provider, model, context window và adapter
  LLM thật. Các giá trị cấu hình model/provider hiện vẫn chưa được chốt trong
  `configs/llm.yml`.
- **Nhóm:** định nghĩa rubric gán nhãn relevance và sufficiency, bộ câu hỏi
  kiểm thử, expected relevant chunk/document IDs và tiêu chí nghiệm thu.
- **Benchmark thật:** chưa chạy; hiện chỉ có unit tests và metric functions,
  chưa có dataset/corpus gán nhãn. Kết quả benchmark không thể được suy ra từ
  các test giả lập.
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

- Feature branch: `feature/query-understanding-evaluation`.
- Fix review đã được push trong commit `61d5fee`.
- Pull request hiện tại: [#2](https://github.com/luannt1010/dsp-vietnamese-legal-rag/pull/2).
   Commit fix và cập nhật báo cáo được push lên cùng branch nên cập nhật PR này;
   không tạo PR trùng lặp.

## Kiểm thử

Các bài test được viết theo `unittest`; sau khi sửa góp ý đã chạy thành công
19 tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Pylance workspace check trên `src/` và `tests/unit/` cũng không phát hiện lỗi.
