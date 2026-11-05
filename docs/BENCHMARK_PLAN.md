# Benchmark Hybrid RAG — thiết kế đã chốt

Ngày chốt: 2026-11-03. Đã triển khai runner/scorers/report theo thiết kế này;
hướng dẫn thực thi và các quy ước chi tiết ở `docs/BENCHMARK.md`.
Cấu hình demo vẫn ở `configs/demo`; benchmark có cấu hình riêng ở `configs/benchmark`.

## 1. Ma trận thí nghiệm

| ID | BM25 + Vector / RRF | Graph | Reranker | Số vòng tối đa |
|---|---|---|---|---|
| B0 (baseline) | Có | Không | Không | 1 |
| B1 | Có | Không | Có | 1 |
| B2 | Có | Có | Không | 1 |
| B3 | Có | Có | Có | 1 |
| B4 | Có | Có | Có | 3 |

B0–B3 là benchmark chính. B4 đo thêm lợi ích và chi phí của feedback so với B3.
Với B4, khóa các cờ phương pháp, candidate depth và context cutoff; cho phép
refine query giữa các vòng. Đây là policy riêng của benchmark runner,
khác với demo hiện cho evaluator đổi strategy. Lưu điểm từng vòng và vòng cuối;
không chọn vòng có điểm cao nhất bằng ground truth.

Query analysis, metadata filtering, retrieval sufficiency gate, context builder,
generation và citation verification dùng cùng policy/model/prompt giữa các cấu
hình. Số vòng 1 chỉ tắt việc truy xuất lại, không tắt sufficiency gate.
Cache đầu ra query analysis/filters dùng chung giữa các cấu hình và giữ nguyên
qua các vòng feedback, phù hợp orchestration hiện tại.

## 2. Thông số chung

- Corpus: snapshot của `tmquan/phapdien-moj-gov-vn`, ba topic demo: Giao thông,
  vận tải; Khoa học, công nghệ; Giáo dục, đào tạo. Khóa revision thực tế và
  corpus ID trong manifest; không refresh nguồn trong một đợt benchmark.
- Chunking: hierarchical, 512 token, overlap 64; tokenizer BAAI/bge-m3 và
  revision như demo. Giữ nguyên parent expansion trong context builder.
- Embedding: Ollama bge-m3:latest, 1024 chiều, normalize; lưu digest model thực
  tế vì tag có thể thay đổi.
- Vector store: pgvector HNSW, cosine; m=16, ef_construction=128, ef_search=100.
- BM25: k1=1.2, b=0.75, tokenizer=word, lowercase=true.
- Candidate depth: mỗi nhánh BM25/vector tối đa 20; RRF constant=60; giữ 20
  ứng viên sau fusion. Reranker chấm cùng tập ứng viên này khi được bật.
- Graph khi bật: Neo4j, max_depth=2, max_nodes=100, giữ nguyên cách tạo seeds.
  Graph bổ sung chi phí/candidate trước fusion; báo cáo chi phí riêng.
- Reranker: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1, ONNX quantized,
  revision và cấu hình batch/input như demo.
- Lưu ranking sau fusion/rerank tối đa 20; chỉ top 5 đi vào context builder.
  Hai cutoff được tách qua PipelineRunOptions; demo mặc định giữ hành vi cũ.
- Context: tối đa 4096 token, prompt reserve 1024; cùng cách mở rộng parent,
  khử trùng lặp, giữ nguyên đoạn nguồn và đóng gói.
- Answer generator: qwen3.5:4b, context window 8192, output tối đa 2048 token.
- Query analyzer / citation verifier: qwen3.5:2b.
- Retrieval evaluator: qwen3.5:4b, prompt v2, sau đợt sửa ngày 2026-11-05.
  Cấu hình 2b cũ đã cho phép nhầm căn cứ cùng chủ đề trong kiểm thử bỏ nguồn;
  cần dùng cùng evaluator mới cho toàn bộ B0–B4 và thư mục output mới.
- Temperature=0, think=false, prompt version v1; ghi digest model và hash prompt.
- Timeout: pipeline 240 giây, retrieval mỗi vòng 60 giây; cấu hình retry như demo.
- Giữ nguyên các giá trị giữa thí nghiệm; tuning chỉ trên development set.

## 3. Ba điểm đo

| Tầng | Artifact được chấm | Metrics |
|---|---|---|
| Retriever | Ranking trước context builder | Recall@k, Precision@k, MRR@k, MAP@k, nDCG@k; k=5,10,20 |
| Context | Nội dung và nguồn thực sự được gửi tới answer generator | Context Precision có reference, Context Recall theo reference claims |
| Answer | Câu trả lời cuối, kèm draft trước verification để phân tích lỗi | Faithfulness, Factual Correctness F1 (lưu precision/recall), Answer Relevancy |

Chỉ số chính: Recall@5, nDCG@5; Context Recall; Factual Correctness F1.
Không cộng các metrics thành một điểm tổng tùy ý. nDCG hiện dùng binary relevance;
nếu dùng nhãn nhiều mức phải bổ sung implementation và ghi rõ công thức.

Context Precision phải chấm mức hữu ích của nội dung từng context theo thứ tự
thực tế, không chỉ so ID. Context Recall đo tỷ lệ ý chuẩn được context hỗ trợ.
Faithfulness đối chiếu answer với context, Factual Correctness đối chiếu answer
với reference. Khóa judge, prompt tiếng Việt, embedding dùng chấm relevancy và
phiên bản thư viện; lưu các phán xét thành phần. Judge độc lập với evaluator
đang quyết định luồng chạy và ưu tiên khác model sinh.

## 4. Dataset và báo cáo

- Pilot 30–50 câu để kiểm tra quy trình; mục tiêu ban đầu khoảng 300 câu.
- Dự kiến development 20%, test 80%, tách theo nhóm nguồn/họ câu hỏi.
- Bao phủ tra cứu, tổng hợp nhiều ý, ngoại lệ, nhiều nguồn và thiếu căn cứ.
- Mỗi câu có ID, question, topic/type, answerable, reference answer/claims,
  evidence IDs/spans ổn định và phiên bản văn bản. Ánh xạ evidence sang chunks.
- Kiểm tra nguồn đúng thay thế bằng pooling kết quả nhiều cấu hình. Benchmark
  hiện dùng binary chunk qrels và khử trùng theo chunk_id; mọi leaf chứa quote
  đều relevant. Không diễn giải chunk recall thành recall các ý đáp án.
- Câu không có nguồn đúng không đưa vào retrieval metrics yêu cầu relevant IDs
  khác rỗng; báo cáo riêng từ chối đúng và trả lời thiếu căn cứ.
- Giữ kết quả retrieval/context trước các gate kể cả khi lượt chạy bị từ chối.
  Context không được xây/generation không chạy phải ghi trạng thái, không giả
  tạo artifact. Báo cáo số mẫu có điểm tại mỗi tầng.
- Không bỏ lỗi/timeout/từ chối sai khỏi báo cáo. Báo cáo answer coverage và
  correct-answer yield trên toàn bộ câu answerable, bên cạnh metrics trên các
  câu có answer. Faithfulness không xác định với response không có claim là N/A.
- Judge error là lỗi chấm, không tự quy thành chất lượng answer bằng 0 hoặc 1.
- Chấm thủ công tối thiểu một mẫu phân tầng, ưu tiên ca judge bất đồng/điểm thấp.
- Phần có LLM lặp 3 lần nếu ngân sách cho phép; báo cáo độ biến động giữa lần.
- Mean theo câu hỏi, điểm theo topic/type; delta so với B0, paired bootstrap
  95% CI theo câu hỏi (gom các lần lặp trong cùng câu trước), kiểm soát nhiều
  phép so sánh khi tuyên bố ý nghĩa thống kê. B4 so thêm với B3.
- Báo cáo latency p50/p95, token, số vòng, số lần gọi model, tỷ lệ hoàn tất.
  Ghi phần nào cache/warmup; tách chi phí chuẩn bị index khỏi query latency.

### Inference latency và thời gian xử lý

- End-to-end latency: từ khi pipeline nhận câu hỏi tới khi trả answer/fallback
  sau verification; bao gồm các vòng feedback, retry và backoff thực tế.
- Stage latency: query analysis, metadata filtering, retrieval, evaluation,
  context building, answer generation, citation verification. Trong retrieval
  tách query embedding, BM25, vector search, graph traversal, fusion, reranking.
- Model-call latency: wall-clock từ trước tới sau từng lời gọi embedding,
  reranker hoặc LLM; gắn role, model, round, attempt và trạng thái. Thời gian
  này có thể gồm network/queue/load, không gọi là thời gian tính toán thuần.
- Inference phía backend: lưu thời gian load model, xử lý prompt, sinh token,
  số input/output token khi backend cung cấp; chuẩn hóa duration về milliseconds.
  Tính decode tokens/second từ output tokens và decode duration khi hợp lệ.
  Không có số liệu backend thì để N/A, không suy ra bằng wall-clock.
- Báo cáo answer-generation latency riêng và tổng model-call latency trên mỗi
  query, gồm analysis/evaluation/verification, query embedding và reranker;
  tổng này là chi phí theo lời gọi, không mặc định bằng end-to-end latency.
- Dùng monotonic/perf_counter để đo; báo cáo mean, p50, p95 theo cấu hình,
  kèm số mẫu. Phân tách completed, từ chối, lỗi và timeout; thời gian tới timeout
  không phải thời gian hoàn tất, không gộp vào latency của các câu hoàn tất.
- Tách cold start và warm run; khai báo warmup, concurrency (mặc định 1),
  hardware CPU/GPU/RAM, model quantization, batch size, keep_alive và cache.
  Xáo trộn thứ tự cấu hình giữa các lần lặp để giảm lợi thế do cache/nhiệt máy.
- Cache analysis/filters cho so sánh chất lượng không được làm latency mang nhãn
  end-to-end đầy đủ nếu bỏ qua analysis. Lượt đo hiệu năng phải chạy đủ các bước;
  nếu replay artifact, ghi rõ phạm vi và báo cáo riêng, không cộng thời gian giả.
- Chi phí offline judge Context/Answer, xây index, nạp runtime và warmup ghi
  riêng ngoài query latency; model load phát sinh trong query vẫn được tính.
- Không báo TTFT khi chưa có streaming/instrumentation đo token đầu tiên.

## 5. Trạng thái triển khai

Đã có: runner/presets B0–B4, JSONL validation/evidence resolution, resume,
cutoff ranking 20 riêng với context 5, context/draft snapshots, khóa feedback,
offline structured judge cho context/answer, retrieval metrics tái sử dụng,
paired bootstrap/sign-flip/Holm, báo cáo và stage/model/backend telemetry.

Cần dữ liệu thực: bộ 50 câu có nhãn của người dùng, đối chiếu evidence với
corpus, hiệu chuẩn judge theo người chấm và chạy benchmark thật. Chưa có kết
luận phương pháp nào tốt hơn trước khi hoàn tất các bước đó.

## 6. Cấu hình demo hiện tại (đã resolve env, không kết nối dịch vụ)

`python -m scripts.demo ...` mặc định dùng `configs/demo` và `.runtime/demo.env`.
Tại thời điểm chốt: BM25=true, vector=true, graph=true, rerank=true,
top_k=5, candidate_k=20, max_iterations=3. Đây là cấu hình gần B4, chưa phải B0
và chưa tuân theo protocol benchmark ở trên. CLI/env có thể override cấu hình.

Demo vẫn có sufficiency gate và citation verification. `max_iterations=1`
không tắt gate; `candidate_k=20` không có nghĩa trace lưu 20 hit vì aggregator
và reranker đang cắt theo `top_k=5`.

## 7. Format file evaluation dataset

| Trường | Nội dung |
|---|---|
| `question_id` | ID duy nhất, ví dụ `GT001`, `GD001` |
| `question` | Câu hỏi tự nhiên bằng tiếng Việt |
| `topic` | Tên chủ đề không rỗng, thuộc phạm vi corpus đã chuẩn bị |
| `question_type` | `lookup`, `multi_clause`, `multi_document`, `comparison`, `unanswerable` |
| `answerable` | `true` nếu corpus có đủ căn cứ; ngược lại là `false` |
| `reference_answer` | Đáp án chuẩn, đầy đủ điều kiện và ngoại lệ cần thiết |
| `reference_claims` | Các ý riêng biệt mà câu trả lời cần bao phủ |
| `evidence` | Những đoạn nguồn hỗ trợ đáp án |

```json
{
  "question_id": "GT001",
  "question": "<Câu hỏi>",
  "topic": "Giao thông, vận tải",
  "question_type": "multi_clause",
  "answerable": true,
  "reference_answer": "<Đáp án chuẩn hoàn chỉnh>",
  "reference_claims": [
    "<Ý cần trả lời thứ nhất>",
    "<Ý cần trả lời thứ hai>"
  ],
  "evidence": [
    {
      "document_number": "<Số hiệu văn bản>",
      "document_title": "<Tên văn bản>",
      "article": "<Điều>",
      "clause": null,
      "point": null,
      "quote": "<Trích nguyên văn đoạn hỗ trợ đáp án>",
      "source_url": null
    }
  ]
}
```

Mỗi object lưu trên một dòng JSONL. Dùng giá trị JSON `null` khi trường tùy
chọn không áp dụng, không dùng chuỗi `"null"`. Ví dụ nhiều dòng chỉ để dễ đọc.

Phần quan trọng nhất là đáp án và bằng chứng

- reference_claims nên tách thành từng ý có thể kiểm chứng; giữ điều kiện hoặc ngoại lệ đi cùng ý tương ứng.
- quote cần trích nguyên văn, đủ ngữ cảnh; tránh bỏ phần phủ định, điều kiện áp dụng hoặc ngoại lệ.
- Dùng số hiệu văn bản và điều/khoản để định danh nguồn. Bạn không cần tìm chunk_id; bộ benchmark sẽ ánh xạ sau.
- Đáp án phải phù hợp với phiên bản văn bản trong corpus. Nếu hỏi “hiện nay”, cần ghi rõ mốc thời gian và bảo đảm corpus có đủ nguồn tương ứng.
- Nếu biết có nhiều nguồn đúng thay thế, hãy ghi thêm để tránh chấm một kết quả đúng thành sai.

```json
{
  "question_id": "OUT001",
  "question": "<Câu hỏi không thể trả lời đầy đủ từ corpus>",
  "topic": "Giáo dục, đào tạo",
  "question_type": "unanswerable",
  "answerable": false,
  "reference_answer": "<Nêu thông tin còn thiếu và lý do cần từ chối hoặc hỏi thêm>",
  "reference_claims": [],
  "evidence": []
}
```
