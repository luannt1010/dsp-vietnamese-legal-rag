# Benchmark B0–B4

Thành viên chạy lần đầu: xem [quickstart từ bản clone mới](BENCHMARK_QUICKSTART.md).
Repo có `data/evaluation/smoke.jsonl` và `configs/benchmark/smoke.yml` để kiểm
tra 15 mẫu, không cần dữ liệu trong `.runtime` của máy khác.

Benchmark nằm trong `src/benchmark`, độc lập với evaluator online trong
`src/evaluation/retrieval_evaluator.py`. Runner dùng lại `open_runtime` và
`RAGPipeline`; scorer chỉ đọc artifact, không chạy lại pipeline.

## 1. Dataset 50 câu

Tạo `data/benchmark/questions.jsonl`, UTF-8, mỗi dòng một object. Có thể bắt đầu
với 40 câu có căn cứ và 10 câu không đủ căn cứ. Đây là pilot, không tự bảo đảm
đủ độ mạnh thống kê để phân biệt các phương pháp gần nhau.

Một câu có đáp án:

```json
{
  "question_id": "GD001",
  "question": "<Câu hỏi>",
  "topic": "Giáo dục, đào tạo",
  "question_type": "lookup",
  "answerable": true,
  "reference_answer": "<Đáp án đầy đủ>",
  "reference_claims": ["<Ý chuẩn thứ nhất>", "<Ý chuẩn thứ hai>"],
  "evidence": [{
    "document_number": "<Số hiệu>",
    "document_title": "<Tên văn bản>",
    "article": "<Điều>",
    "clause": null,
    "point": null,
    "quote": "<Trích nguyên văn một đoạn hỗ trợ đáp án>",
    "source_url": null
  }],
  "split": "test"
}
```

Object được trình bày nhiều dòng cho dễ đọc; JSONL phải gộp mỗi object thành
một dòng. `split` là tùy chọn, mặc định `test`; giá trị khác là `development`.
Loại câu hỏi: `lookup`, `multi_clause`, `multi_document`, `comparison`,
`unanswerable`. Topic là tên chủ đề không rỗng trong nguồn dữ liệu; cấu hình
corpus dùng để benchmark phải chọn đúng các chủ đề tương ứng. Benchmark không
giới hạn ở ba topic demo.

Với câu không đủ căn cứ: `answerable=false`, `question_type=unanswerable`,
`reference_claims=[]`, `evidence=[]`; `reference_answer` nêu lý do cần từ chối
hoặc yêu cầu thông tin bổ sung. Đánh giá riêng việc abstain đúng và trả lời khi
thiếu căn cứ; không áp retrieval metrics yêu cầu nguồn đúng khác rỗng.

Xuất JSON Schema và kiểm tra format, không cần Ollama/database:

```powershell
python -m scripts.benchmark schema --output data/benchmark/question.schema.json
python -m scripts.benchmark validate --dataset data/benchmark/questions.jsonl
```

Kiểm tra thêm nhãn với corpus đã chuẩn bị:

```powershell
python -m scripts.benchmark validate --dataset data/benchmark/questions.jsonl --corpus data/runtime/<corpus_id>/corpus.json
```

Evidence được ánh xạ bằng số hiệu, vị trí và trích dẫn nguyên văn, chỉ chuẩn hóa
Unicode NFC và khoảng trắng; không dùng embedding/LLM để tự đoán nhãn. Nhãn là
binary **chunk qrels**, cố định chunking giữa B0–B4. Tất cả leaf chứa quote đều
được gán relevant, kể cả các leaf overlap; mỗi chunk chỉ đếm một lần. Vì vậy
Recall@k là độ bao phủ tập chunk đã gán nhãn, không phải phần trăm các ý đáp án.
Pooling các nguồn đúng thay thế và kiểm tra thủ công vẫn là trách nhiệm gán nhãn.

Quote nên là đoạn nguyên tử, nằm đầy đủ trong một leaf. Nếu quote quá dài hoặc
không khớp corpus, validation dừng và nêu question/evidence cần sửa; không tự
gán điểm 0. Với điều có tiêu đề, có thể dùng mã điều đầy đủ hoặc heading chính xác.

Lưu ý corpus Pháp điển có thể ghi `Điều 13.1.LQ.1. Phạm vi điều chỉnh` thay vì
số điều của luật gốc. Trong trường hợp đó, giữ `article` gốc và bổ sung trường
tùy chọn `corpus_article`, ví dụ `Điều 13.1.LQ.1`. Không suy đoán mã Pháp điển
từ số điều gốc. `source_version` tùy chọn lưu phiên bản pháp lý do người gán
nhãn xác nhận; nó không tự được kiểm chứng bằng ngày hiệu lực hoặc dataset SHA.

## 2. Chạy inference

Chuẩn bị model và indexes bằng quy trình demo trước. Benchmark đặt
`auto_prepare=false`, không tự tải lại nguồn hoặc xây index trong lượt đo.

```powershell
python -m scripts.benchmark run --dataset data/benchmark/questions.jsonl --output .runtime/benchmarks/pilot-50
```

Config mặc định: `configs/benchmark/hybrid.yml`, base runtime: `configs/demo`,
credentials: `.runtime/demo.env`. Có thể truyền `--config`, `--config-dir`,
`--env-file`, `--split development|test|all`. Không tune bằng test set.

- B0: Hybrid; B1: +reranker; B2: +graph; B3: +graph+reranker; B4: B3+feedback.
- B0–B3 tối đa một vòng; B4 tối đa ba vòng, chỉ refine query, khóa strategy.
- Mỗi nhánh BM25/vector lấy 20; giữ ranking tối đa 20 sau fusion/rerank;
  evaluator và Context Builder chỉ nhận top 5 và relations được hỗ trợ.
- Sufficiency gate và citation verification dùng chung. `max_iterations=1`
  không bỏ gate. Nếu một adapter trả change_strategy dù policy khóa, lượt đó
  dừng insufficient_evidence; schema Ollama cũng loại action này.
- Mặc định lặp 3 lần, xáo thứ tự cấu hình theo seed ở từng repeat, warmup một
  câu mỗi phiên runtime, concurrency=1. Record model load trong request vẫn
  được tính; warmup không bảo đảm mọi model luôn ở RAM/VRAM.
- `sessions/` lưu setup và warmup riêng để đối chiếu model load/cold-start với
  lượt đo sau warmup. Nhãn `post_warmup`/`no_warmup` mô tả quy trình, không tự
  khẳng định model đã nóng hay lạnh; đọc cùng load_duration thực tế của backend.
- `replay_analysis=false` chạy đủ pipeline để đo latency. Có thể bật true cho
  kiểm soát chất lượng; latency khi đó gắn nhãn `analysis_replay`, không gọi là
  full end-to-end. Mẫu đầu tiên tạo analysis cache có thể vẫn chạy analysis.
- Ghi thông tin máy/quantization thực tế vào `hardware_notes` trước khi chạy.

Chạy lại cùng lệnh sẽ bỏ qua mẫu đã lưu. Dataset, model digest, cấu hình hoặc
code đổi thì runner từ chối resume; dùng thư mục output mới. Runtime kiểm tra
corpus ID/signature xuyên suốt các cấu hình. Lỗi setup dừng ngay; lỗi runtime
đã được pipeline xử lý được lưu theo status. `--debug` trước tên command hiển
thị traceback khi cần debug.

## 3. Chấm artifact

Retrieval-only hoàn toàn offline:

```powershell
python -m scripts.benchmark score --output .runtime/benchmarks/pilot-50 --retrieval-only
```

Chấm đủ ba tầng:

```powershell
python -m scripts.benchmark score --output .runtime/benchmarks/pilot-50 --judge-config configs/benchmark/judging.yml
```

Judge mặc định Qwen3.5:2b, khác generator Qwen3.5:4b. Đây là model nhỏ, cùng họ
với generator và trùng model evaluator online; các lần gọi/prompt độc lập nhưng
có thể cùng thiên lệch. Đối chiếu nhãn người và chọn judge mạnh hơn nếu cần kết
luận chất lượng. Config khóa model/tokenizer/window và tự chặn self-judging
trừ khi bật `allow_same_model`. Không tự tải model Ollama còn thiếu.

Lượt chạy thật đã phát hiện lỗi ngữ nghĩa của judge: có claim tự thêm, verdict
lệch claim và phán xét vượt premise. `0 judge errors` chỉ là không có lỗi kỹ
thuật/schema. Cần hiệu chuẩn theo người chấm trước khi dùng Context/Answer
metrics để so sánh chất lượng; xem quickstart và dataset notes.

Judge cache theo nội dung, task, prompt/schema, cấu hình và model digest. Lưu
claims, verdicts và lý do để audit. Chấm lại không chạy pipeline; judge error
không trở thành điểm 0/1. Task lỗi được thử lại ở lần `score` tiếp theo, dùng
lại các phán xét hợp lệ đã cache. Thay judge tạo scoring fingerprint mới; không
trộn scores khác fingerprint trong report.

Định nghĩa metrics (tái sử dụng `src/evaluation/metrics.py`):

| Metric | Định nghĩa thực thi |
|---|---|
| Recall/Precision/MRR/MAP/nDCG@k | Binary chunk relevance, k=5,10,20; AP@k chia tổng số relevant chunks; nDCG binary |
| Context Precision | Mean precision tại các vị trí chunk được judge cho là hữu ích, chia số chunk hữu ích; không có chunk hữu ích → 0 |
| Context Recall | Tỷ lệ reference claims được toàn bộ context_text hỗ trợ |
| Faithfulness | Tỷ lệ claims trích từ answer được context_text hỗ trợ |
| Factual Precision | Tỷ lệ answer claims được reference answer hỗ trợ |
| Factual Recall | Tỷ lệ reference claims được answer hỗ trợ |
| Factual F1 | Harmonic mean của factual precision/recall |
| Answer Relevancy | Mean cosine(query, reverse question), 3 câu hỏi sinh chỉ từ answer; noncommittal → 0 |

Context precision chấm các đoạn nguồn theo thứ tự thực tế; context recall và
faithfulness thấy cả metadata/quan hệ nằm trong context_text. Không có factual
claims thì faithfulness/precision=N/A, factual recall/F1=0 với câu answerable.
Không có stage artifact thì metric stage đó=N/A, không dựng artifact giả.

`correct_answer_yield` là tiêu chí nghiêm ngặt đã khóa: answer hoàn tất,
Factual F1=1 và Faithfulness=1. Lỗi/timeout/từ chối trên câu answerable → 0;
judge error không xác định được tiêu chí → N/A. `answer_provided` cho biết tỷ
lệ trả lời câu answerable. Không dùng yield ở chế độ retrieval-only để so sánh
chất lượng (các answer hoàn tất chưa được chấm). Answer trước verification bị
từ chối được chấm riêng với prefix `draft.`, không thay thế điểm answer cuối.

Các định nghĩa dựa trên tài liệu Ragas, không tuyên bố dùng implementation hay
điểm số tương đương package Ragas vì prompt/judge khác nhau:
[Context Precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/),
[Context Recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/),
[Faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/),
[Factual Correctness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/factual_correctness/),
[Answer Relevancy](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/).

## 4. Báo cáo và inference latency

```powershell
python -m scripts.benchmark report --output .runtime/benchmarks/pilot-50
```

`reports/summary.json` chứa đầy đủ quality means/denominators, latency mean/p50/p95
theo status và latency scope, breakdown theo topic/type, delta và CI95 paired
bootstrap theo câu hỏi. Lấy mean qua các repeat của cùng câu trước khi tổng hợp.
Paired test chỉ dùng câu có đủ repeat hợp lệ ở cả hai phương pháp; n<2 không có
CI/p-value. p-value dùng paired sign-flip Monte Carlo, hiệu chỉnh Holm trên họ
metric tests xuất trong report; CI95 vẫn là pointwise, không phải simultaneous.
Dataset pilot không đồng nghĩa mọi khác biệt nhỏ đều có ý nghĩa.

`summary.csv` và `latency.csv` thuận tiện mở Excel; `report.md` tóm tắt trạng thái.
Report không tự tuyên bố một phương pháp tốt nhất và hiển thị mẫu thiếu/lỗi.
Quality metrics có N/A phải đọc cùng n_questions/n_observations và coverage;
không so sánh means một cách tách rời tỷ lệ lỗi/từ chối.

Telemetry request-local lưu trong từng sample:

- End-to-end wall-clock, stage spans, từng vòng, từng model-call gồm retries.
- HTTP attempts riêng, không cộng chồng vào tổng model-call latency.
- Ollama load/prompt/decode duration chuyển ns → ms, input/output token và
  decode tokens/giây khi có. Giá trị thiếu là N/A, không suy từ wall-clock.
- Embedding/reranker/analysis/evaluation/generation/verification riêng biệt.
- Tách completed, insufficient_evidence, failed, timed_out; timeout không phải
  latency hoàn tất. Không báo TTFT vì adapter hiện không streaming.
- Indexing, setup, warmup và offline judge ngoài phạm vi query latency. Tổng
  model-call là tổng chi phí lời gọi, không mặc định bằng end-to-end.

## 5. Cấu trúc artifact và kiểm thử

```text
<run>/
  manifest.json        # identity, sanitized settings, model/corpus fingerprints
  qrels.json           # labels resolved before retrieval
  sessions/            # setup + warmup timings/events, outside query latency
  analysis/            # optional replay cache
  samples/B0/...json   # result + exact context/draft + request telemetry
  judge-cache/...json  # independent offline judgments
  scoring.json         # active scoring edition
  scores/B0/...json    # per-question metrics/errors/judgments
  reports/             # summary.json, summary.csv, report.md
```

Không ghi credentials vào manifest. Atomic JSON publication dùng lại utility
data preparation. Có thể đọc/diff artifact của đúng question/experiment/repeat
để debug; không cần đọc log tổng hợp dài.

```powershell
python -m pytest tests/benchmark -q
```

Tests dùng dữ liệu tổng hợp và adapter giả lập, chạy retrieval/context/generation
wiring thật, không cần Ollama hoặc databases. Đây là kiểm thử triển khai, không
phải số liệu benchmark pháp lý. Cần dataset 50 câu có nhãn để chạy thí nghiệm thật.
