# Chạy benchmark từ bản clone mới

> Cấu hình hiện tại dùng `configs/` và root `.env`; xem [README](../README.md) để chạy full web application. Các ví dụ bên dưới mô tả workflow CLI trước khi di chuyển config. Khi dùng utility CLI, truyền `--config-dir configs --env-file .env`; không tạo lại thư mục config cũ.

Các lệnh dưới đây dùng Windows PowerShell và chạy từ thư mục gốc repo.
Không cần copy `.runtime`, credentials, model cache hoặc kết quả từ máy khác.
Đọc [thiết kế và metric definitions](BENCHMARK.md) khi mở rộng thí nghiệm.

## 1. Cài môi trường

Cần Python >=3.10 (khuyến nghị 3.12), Git, Docker Desktop và Ollama.
Mở Docker Desktop/Ollama trước khi kiểm tra dịch vụ.

```powershell
git clone https://github.com/luannt1010/dsp-vietnamese-legal-rag.git
cd dsp-vietnamese-legal-rag

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Nếu PowerShell chặn Activate.ps1, chạy
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` trong terminal này
rồi activate lại. Có thể dùng Conda theo [README](../README.md) thay cho venv.

## 2. Model, database và phạm vi corpus

```powershell
ollama pull bge-m3
ollama pull qwen3.5:2b
ollama pull qwen3.5:4b

powershell -ExecutionPolicy Bypass -File .\scripts\start_demo_databases.ps1
```

Nếu Ollama app chưa phục vụ kết nối, chạy `ollama serve` ở terminal khác.
Script database tạo credentials riêng trong `.runtime/demo.env`; CLI demo và
benchmark tự đọc file này. PostgreSQL mặc định dùng port 15432, Neo4j Bolt dùng 17687.
Giữ file credentials khi tái sử dụng volumes cũ; không commit file này.

Dataset đi kèm thuộc **An ninh quốc gia**. Đặt các override sau trong **cùng
terminal** dùng cho mọi lệnh prepare/run/score. Revision được khóa theo snapshot
đã đối chiếu evidence; cấu hình demo gốc vẫn giữ ba chủ đề demo.

```powershell
$env:RAG__DATA_PIPELINE__SOURCE__TOPICS = '["An ninh quốc gia"]'
$env:RAG__DATA_PIPELINE__SOURCE__SUBJECTS = '[]'
$env:RAG__DATA_PIPELINE__SOURCE__REVISION = 'a1b6860c821b7142ffe2385178af4e4bb6f86aff'

python -m scripts.demo doctor
python -m scripts.demo prepare
```

Chỉ tiếp tục khi doctor kết nối được models/PostgreSQL/pgvector/Neo4j và
prepare thành công. Lần đầu cần Internet để tải dataset, tokenizer và reranker,
tạo embedding/index; có thể mất nhiều thời gian. Các lần sau dùng lại cache.
Model Ollama có tag thay đổi được: runner lưu model digest và từ chối trộn
model khác digest trong cùng run.

`prepare` nạp lại corpus cache để kiểm tra; file lớn vẫn có thể cần thời gian
đọc/validate. Index đã đủ row count/index HNSW hoặc IVFFlat và graph có marker
complete/counts đúng sẽ được bỏ qua, không ghi lại toàn bộ. Khi cần chủ động
ghi lại database từ embedding cache, dùng `python -m scripts.demo prepare
--force-reindex` (một dòng). `--refresh-source` là tùy chọn riêng để kiểm tra
revision nguồn, không đồng nghĩa ép ghi lại index đã sẵn sàng.

## 3. Smoke benchmark 15 mẫu

Repo cung cấp:

- `data/evaluation/smoke.jsonl`: ANQG001, ANQG022, ANQG031; quote ANQG022 đã
  giới hạn ở khoản định nghĩa được hỏi. [Dataset notes](../data/evaluation/README.md).
- `configs/benchmark/smoke.yml`: B0–B4, một repeat, một warmup mỗi cấu hình.
- Base runtime: `configs/demo`. Các biến môi trường ở bước 2 chọn corpus đúng.

```powershell
python -m scripts.benchmark validate --dataset data/evaluation/smoke.jsonl

$runDir = ".runtime/benchmarks/smoke-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

python -m scripts.benchmark run --dataset data/evaluation/smoke.jsonl --config configs/benchmark/smoke.yml --output $runDir
```

Runner kiểm tra evidence với corpus thật trước khi inference. Không cần tự điền
corpus ID của máy khác. Benchmark yêu cầu index đã chuẩn bị, không tự xây index
trong phạm vi đo latency. Chạy lại cùng lệnh với cùng `$runDir` để resume; nếu
đổi code/dataset/model/config, dùng một thư mục output mới.

Các cấu hình:

| ID | Phương pháp | Số vòng retrieval tối đa |
|---|---|---:|
| B0 | BM25 + Vector / RRF | 1 |
| B1 | B0 + Reranker | 1 |
| B2 | B0 + Graph | 1 |
| B3 | B0 + Graph + Reranker | 1 |
| B4 | B3 + Feedback refine query | 3 |

Mỗi nhánh BM25/vector lấy 20; lưu ranking tối đa 20 sau fusion/rerank; evaluator
và Context Builder nhận top 5. B4 có thể dừng sau một vòng nếu đã đủ căn cứ.
Ba câu smoke kiểm tra luồng chạy, không đại diện benchmark chất lượng đầy đủ.

## 4. Chấm và xuất báo cáo

Chấm retrieval không cần gọi judge:

```powershell
python -m scripts.benchmark score --output $runDir --retrieval-only
python -m scripts.benchmark report --output $runDir
```

Chấm thêm Context/Answer bằng model judge cục bộ, tái sử dụng inference artifact:

```powershell
python -m scripts.benchmark score --output $runDir --judge-config configs/benchmark/judging.yml
python -m scripts.benchmark report --output $runDir
```

**Judge hiện cần hiệu chuẩn.** Lượt smoke đã phát hiện Qwen3.5:2b có thể thêm
claim không xuất hiện trong response, nhầm thứ tự phán xét hoặc dùng kiến thức
ngoài premise. Ràng buộc schema/số lượng/độ dài chỉ kiểm soát tính hợp lệ kỹ
thuật. `0 judge errors` không chứng minh phán xét ngữ nghĩa đúng. Chấm đủ ba
tầng dùng được để kiểm tra hệ thống; chưa dùng các điểm LLM-judged để xếp hạng
phương pháp khi chưa đối chiếu với nhãn người.

Nếu thay judge, chỉnh `configs/benchmark/judging.yml` gồm model, tokenizer,
context window và token budget; tải model đó trước. Scorer chặn self-judging
trừ khi chủ động bật `allow_same_model`. Judge cache có identity riêng và được
chấm lại mà không chạy lại inference.

Kết quả trong `$runDir/reports`:

| File | Nội dung |
|---|---|
| `report.md` | Trạng thái và đầy đủ quality means, gồm các điểm Precision |
| `summary.csv` | Metrics trung bình theo cấu hình, mở bằng Excel được |
| `latency.csv` | Mean/p50/p95 theo stage/model/backend/status |
| `summary.json` | Denominators, breakdown, paired CI/p-values |

Các thư mục `samples/`, `scores/`, `sessions/`, `judge-cache/` giữ trace, context,
draft/final answer, timing và phán xét để debug. Output cục bộ được Git ignore.

## 5. Bộ dữ liệu lớn hơn

`data/evaluation/data.json` là **JSONL dù đuôi .json**, gồm 31 câu gốc. File
chưa phải gold set đã duyệt: quote ANQG022 dài hơn một leaf và ANQG009/010/030
còn các điểm cần rà lại giữa question/reference/claims. Không chạy nguyên file
này rồi coi kết quả là benchmark chuẩn; xem [dataset notes](../data/evaluation/README.md).

Khi đã có bộ câu hỏi kiểm duyệt, chọn các topic chứa evidence, prepare corpus
tương ứng, kiểm tra schema/evidence và chạy ba repeat bằng:

```powershell
python -m scripts.benchmark validate --dataset data/benchmark/questions.jsonl

$runDir = ".runtime/benchmarks/full-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
python -m scripts.benchmark run --dataset data/benchmark/questions.jsonl --config configs/benchmark/hybrid.yml --output $runDir
```

`data/benchmark/questions.jsonl` trong ví dụ là file do nhóm chuẩn bị, không phải
file có sẵn trong repo. Thêm câu nhiều nguồn/thiếu căn cứ, chia development/test
theo nhóm nguồn và hiệu chuẩn judge trước khi kết luận hơn/kém.

Precision@k dùng mẫu số k. Với chỉ một gold chunk, P@5 tối đa theo qrels đó là
0.2 dù retrieval tìm đúng; không đổi mẫu số để làm điểm cao. Context Precision
là metric theo thứ hạng, không phải tỷ lệ mọi đoạn context hữu ích.

## 6. Lỗi thường gặp và tests

Sau bản sửa truy xuất theo số hiệu và đóng gói context, dùng **thư mục run mới**.
Ví dụ chạy lại bộ development đã chuẩn hóa trong Windows CMD/Conda:

```cmd
conda activate free_env
cd /d D:\dsp-vietnamese-legal-rag
set RAG__DATA_PIPELINE__SOURCE__TOPICS=
set RAG__DATA_PIPELINE__SOURCE__SUBJECTS=[]
set RAG__DATA_PIPELINE__SOURCE__REVISION=a1b6860c821b7142ffe2385178af4e4bb6f86aff
python -m scripts.demo doctor
python -m scripts.demo prepare
python -m scripts.benchmark run --dataset data\evaluation\new\three_topics_pilot.development.v1.jsonl --split development --config configs\benchmark\smoke.yml --output .runtime\benchmarks\three-topics-dev-next-01
python -m scripts.benchmark score --output .runtime\benchmarks\three-topics-dev-next-01
python -m scripts.benchmark report --output .runtime\benchmarks\three-topics-dev-next-01
```

Các lệnh `set` ở đây là cú pháp **CMD**: bỏ override topic từ smoke ANQG để
dùng ba topic mặc định trong `configs/demo/data_pipeline.yml`. Khi đổi từ corpus
ANQG sang ba topic này, cần chạy prepare một lần cho corpus mới. Đổi tên output
nếu `three-topics-dev-next-01` đã tồn tại từ một lần chạy khác.

Không cần prepare/index lại chỉ vì thay query filtering, context packing hoặc
evaluator. `samples/...json` giữ `result.failure_details` khi có lỗi verifier:
`citation_source_mismatch` là nguồn/quote không khớp; `unsupported_answer_claims`
là verifier từ chối nội dung; `claim_support_check_failed` là bước gọi/đọc kết quả
verifier bị lỗi, xem thêm `cause_type`. Không đánh đồng ba trường hợp này.
Telemetry `context_selection` cho biết nguồn đã giữ để đối chiếu với ranking.
Evaluator nhận context đã đóng gói; trace giữ context cả khi gate từ chối.

Schema gửi cho provider là một object phẳng; Python vẫn kiểm tra các invariant
của feedback, không tự chuyển verdict sai cấu trúc thành "continue". Gợi ý
`refined_query`/`strategy_override` không thuộc action đã chọn được loại bỏ,
giữ nguyên verdict/action và ghi `feedback_normalization` vào telemetry. Cấu hình
demo dùng evaluator `qwen3.5:4b`, tokenizer 4B và prompt `v2`; các model
embedding/generation/verification giữ nguyên. Câu hỏi nhiều văn bản chia lượt
chọn nguồn cho context từ ranking, còn metric retrieval vẫn chấm ranking gốc.
Điểm do judge chấm vẫn cần hiệu chuẩn riêng.

| Hiện tượng | Cách kiểm tra |
|---|---|
| Ollama retries exhausted | Mở Ollama/ollama serve; kiểm tra ollama list và doctor |
| Database connection error | Mở Docker Desktop, chạy script start database, chờ dịch vụ sẵn sàng rồi doctor |
| Snapshot/selection/index not prepared | Kiểm tra các override topic/revision trong cùng terminal rồi chạy prepare |
| Evidence not resolved | Dùng số hiệu/vị trí/quote nguyên văn; quote phải nằm trong leaf; kiểm tra topic và phiên bản nguồn |
| Run identity changed | Dùng output directory mới sau khi đổi code/config/dataset/model |
| Judge errors hoặc N/A | Xem scores/ và token/window/schema; rerun score, không cần rerun inference |

Thêm `--debug` **trước tên command** để thấy traceback, ví dụ
`python -m scripts.benchmark --debug run ...`.

```powershell
python -m pytest tests/benchmark -q
python -m pytest -q
```

Tests dùng fixtures, không thay thế chạy model thật. Khi dùng terminal mới,
activate môi trường và đặt lại các override topic/revision ở bước 2.
