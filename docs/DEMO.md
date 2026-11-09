# Chạy demo pipeline với pgvector và Neo4j

> Cấu hình hiện tại dùng `configs/` và root `.env`; xem [README](../README.md) để chạy full web application. Các ví dụ bên dưới mô tả workflow CLI trước khi di chuyển config. Khi dùng utility CLI, truyền `--config-dir configs --env-file .env`; không tạo lại thư mục config cũ.

## 1. Chuẩn bị

Chạy các lệnh từ thư mục gốc repository, dùng Python >= 3.10, Docker Desktop
và Ollama. Profile `configs/demo` đã cấu hình đầy đủ; `configs` vẫn dành cho
phát triển và tích hợp module riêng.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
ollama pull bge-m3
ollama pull qwen3.5:2b
ollama pull qwen3.5:4b
.\scripts\start_demo_databases.ps1
.\.venv\Scripts\python.exe -m scripts.demo doctor
```

Đợi database khởi động xong trước khi chạy `doctor`. Script tạo hai database
cục bộ, dùng volume riêng, không thay container của dự án khác:

| Dịch vụ | Container | Địa chỉ |
| --- | --- | --- |
| PostgreSQL + pgvector | `legalrag-pgvector` | `127.0.0.1:15432` |
| Neo4j Bolt | `legalrag-neo4j` | `bolt://127.0.0.1:17687` |
| Neo4j Browser | cùng container | `http://127.0.0.1:17474` |
| Ollama | cài trên máy | `http://127.0.0.1:11434` |

Mật khẩu ngẫu nhiên được lưu trong `.runtime/demo.env`, được CLI tự đọc.
Biến môi trường đã export được ưu tiên hơn file này. Không xóa file credentials
khi còn dùng các volume đã tạo: mật khẩu mới không tự cập nhật database cũ.
Đây là script khởi động phụ thuộc cho demo local, không phải cấu hình triển khai.

Script dùng lại port đã lưu trong `.runtime/demo.env`. Có thể chọn port khác:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_demo_databases.ps1 -PostgresPort 15432 -RecreateStoppedContainers
```

Nếu Windows chặn port cũ `55433`, kiểm tra bằng
`netsh interface ipv4 show excludedportrange protocol=tcp`, rồi chọn port có thể
bind. Script kiểm tra bind trước khi đổi container. Với container đang dừng,
switch trên giữ container cũ dưới tên `*-port-backup-*`, tạo container mới dùng
nguyên named volume và credentials, cập nhật port vào `demo.env` sau khi PostgreSQL
khởi động thành công. Không xóa volume và không tự dừng container đang chạy.
Không khởi động đồng thời container backup và container mới dùng chung data volume.
Chỉ đổi YAML hoặc `docker start` không đổi được port publishing của container cũ.

## Chọn đúng profile khi chạy CLI và API

Tên `demo` không có nghĩa là mock: profile này dùng Ollama, pgvector, Neo4j và dữ
liệu thật. `configs/` là baseline phát triển, còn các field model/embedding chưa
chọn đầy đủ; không phải profile production sẵn chạy. Đừng dùng hai profile khác
nhau cho prepare và API.

Để chọn tường minh cùng profile và credentials, chạy tại root repository:

```powershell
python -m scripts.demo --config-dir .\configs\demo --env-file .\.runtime\demo.env doctor
python -m scripts.demo --config-dir .\configs\demo --env-file .\.runtime\demo.env prepare
$env:RAG_CONFIG_DIR = (Resolve-Path .\configs\demo).Path
$env:RAG_ENV_FILE = (Resolve-Path .\.runtime\demo.env).Path
python -m src.api
```

Biến `RAG__...` đã đặt trong process ưu tiên hơn file env và YAML. Nếu từng đặt
port cũ, cập nhật `$env:RAG__DATABASE__VECTOR__PORT = '15432'` hoặc xóa override
đó trước khi khởi động lại CLI/API. CLI nhận `--config-dir` tường minh, còn API
chọn profile qua `RAG_CONFIG_DIR`.

Nếu đã có database riêng, tạo file env với các biến sau rồi truyền
`--env-file đường_dẫn`. Không ghi mật khẩu vào YAML:

```dotenv
RAG__DATABASE__VECTOR__HOST=127.0.0.1
RAG__DATABASE__VECTOR__PORT=5432
RAG__DATABASE__VECTOR__DATABASE=legal_rag
RAG__DATABASE__VECTOR__USERNAME=rag
RAG__DATABASE__VECTOR__PASSWORD=your-password
RAG__DATABASE__GRAPH__URI=bolt://127.0.0.1:7687
RAG__DATABASE__GRAPH__USERNAME=neo4j
RAG__DATABASE__GRAPH__PASSWORD=your-password
```

PostgreSQL cần cài extension pgvector >= 0.8 để dùng iterative ANN scan; tài
khoản chuẩn bị index cần quyền tạo extension/schema/table/index. Neo4j cần
quyền tạo constraint và ghi dữ liệu trong database được chọn.

## 2. Chuẩn bị index và hỏi đáp

```powershell
.\.venv\Scripts\python.exe -m scripts.demo prepare
.\.venv\Scripts\python.exe -m scripts.demo ask --question "Luật Giao thông đường thủy nội địa số 23/2004/QH11 điều chỉnh những hoạt động nào?"
.\.venv\Scripts\python.exe -m scripts.demo chat
```

`prepare` đọc nguồn theo `data_pipeline.source`, chunk, embed và tạo index
pgvector/Neo4j. Mặc định chọn chủ đề trên dataset Hugging Face có sẵn; xem
[TOPIC_CORPUS.md](TOPIC_CORPUS.md) để chọn topic/đề mục hoặc dùng lại JSON local.
Không xây dataset đánh giá mới. Model/tokenizer/reranker tải ở lần đầu;
cache model ở `.runtime/models`, cache dataset ở `data/runtime/sources`.

Artifact `data/runtime/<corpus_id>/corpus.json` lưu manifest, leaves có embedding
và parents không embed. ID phụ thuộc nội dung nguồn, relations, chunking,
tokenizer và model embedding thực tế. Với Hugging Face, signature giữ revision
thực tế và topic/subject IDs. Đổi cấu hình tạo artifact mới; embedding cùng nội
dung/model được tái sử dụng từ `data/runtime/embeddings.sqlite3`.
`prepare` có thể chạy lại.
Mỗi corpus/metric/method và tham số xây index dùng table riêng; mỗi corpus dùng
namespace graph riêng. Đổi HNSW `m`/`ef_construction` hoặc IVFFlat `lists` tạo
physical index mới; đổi `ef_search`/`probes` chỉ thay tham số truy vấn.

Với `auto_prepare: true`, `ask`/`chat` tự chuẩn bị corpus/index thiếu trước khi
nhận câu hỏi; nếu false thì yêu cầu chạy `prepare` trước. Không tự chuyển sang
mock hoặc database trong bộ nhớ khi dịch vụ lỗi. Mỗi câu hỏi là một request độc lập, chưa có memory
hội thoại. Gõ `/exit` để kết thúc.

Status `completed` nghĩa là câu trả lời đã qua verifier. `insufficient_evidence`,
`failed`, `timed_out` trả thông báo fallback, không trả câu trả lời chưa xác minh.
Lệnh `ask` có exit code 0 khi completed, 2 khi fallback, 1 khi lỗi khởi tạo/CLI.

## 3. Lựa chọn phương pháp

Các option chung đặt **trước** `prepare`, `ask` hoặc `chat`. Khi đổi chunking
hoặc kiểu index, chạy `prepare` với cùng option trước khi hỏi:

```powershell
.\.venv\Scripts\python.exe -m scripts.demo --chunking legal prepare
.\.venv\Scripts\python.exe -m scripts.demo --chunking legal chat
.\.venv\Scripts\python.exe -m scripts.demo --vector-index exact prepare
.\.venv\Scripts\python.exe -m scripts.demo --vector-index exact chat
.\.venv\Scripts\python.exe -m scripts.demo --vector-index ivfflat prepare
.\.venv\Scripts\python.exe -m scripts.demo --vector-index ivfflat chat
```

| Nhóm | Các lựa chọn | Mặc định demo và lý do |
| --- | --- | --- |
| Chunking | `fixed`, `legal`, `hierarchical` | Hierarchical: giữ điều/khoản/điểm và điều kiện; truy xuất leaves, mở rộng parent nếu đủ ngân sách |
| Vector backend | `pgvector`, `in_memory` | pgvector theo yêu cầu demo; in-memory dùng kiểm tra module |
| Vector index | `exact`, `hnsw`, `ivfflat` | HNSW cho đường mở rộng dữ liệu; exact là baseline không xấp xỉ, phù hợp corpus nhỏ |
| Metric | `cosine`, `inner_product`, `l2` trong YAML | Cosine, cùng embedding đã normalize |
| Graph backend | `neo4j`, `in_memory` | Neo4j theo yêu cầu demo |
| Reranker | `onnx`, `sentence_transformers` trong YAML | ONNX multilingual MiniLM chạy CPU, giảm bộ nhớ GPU |

Fixed chia cửa sổ token toàn văn bản, có thể cắt qua điều; legal giữ ranh giới
điều; hierarchical giữ thêm khoản/điểm. Cả ba dùng cùng tokenizer và overlap
thật, không dùng tỷ lệ ký tự/token. Parent chỉ thêm vào context khi còn nguyên
và vừa budget. Fixed không bảo đảm neo được dẫn chiếu điều vào leaf; các quan
hệ không có evidence tương ứng được giữ là unresolved thay vì gán nguồn khác.

Có `--no-rerank` để kiểm tra ảnh hưởng reranker. Đổi metric bằng
`RAG__DATABASE__VECTOR__DISTANCE_METRIC` rồi chạy `prepare`; runtime chọn table
riêng để không trộn physical index khác metric. Với backend sentence-transformers,
cài thêm `pip install -e ".[reranking]"` và chọn model/revision tương ứng.

## 4. Model và ngân sách

Default là BGE-M3 qua Ollama (1024 chiều), BM25 word tokenizer, RRF, ONNX
`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, Qwen3.5:4b cho answer generation
và Qwen3.5:2b cho analysis/evaluation/citation verification.
Model nhỏ và reranker CPU là lựa chọn chạy local trên máy 16 GB RAM/GPU 6 GB;
chưa có benchmark để khẳng định tốt nhất về chất lượng pháp luật tiếng Việt.
Các model và backend khác đổi được bằng cấu hình, không cần sửa orchestrator.

Embedding demo đặt `device: cpu`, truyền `num_gpu: 0` cho Ollama để tránh lỗi
CUDA runner đã tái hiện trên máy demo. Vẫn dùng BGE-M3 và cùng cache vector.
`device: auto` để Ollama chọn; `cuda` cho phép offload GPU tự động. HTTP tạm
thời được retry có giới hạn trong deadline, không tự đổi thiết bị/model khi lỗi.

LLM dùng chat API, structured output, temperature 0; tắt novelty/repetition
penalty để hỗ trợ chép nguyên văn. Tất cả role đều được đếm prompt bằng
tokenizer model; adapter kiểm tra prompt + overhead + output trước khi gọi.
Tokenizer HF được pin revision trong YAML. Khi đổi LLM, đổi cả tokenizer model,
revision và token budgets. Không dùng tokenizer của model khác để ước lượng.

Pipeline có deadline tổng 240 giây, tối đa 3 vòng retrieval; mỗi lượt retrieval
có timeout 60 giây, giới hạn bởi thời gian còn lại. Timeout/retry HTTP
chia sẻ deadline; kết quả về quá hạn bị loại. Context tối đa 4096 token, reserve
1024, model window 8192. Answer confidence bằng 0 vì chưa hiệu chuẩn; đây không
phải xác suất câu trả lời sai và không phải điểm retrieval/evaluation.

Generation có output budget 2048 token cho JSON draft gồm answer và sources
(số khối `[Nguồn N]`). Code dựng `LegalCitation` từ đúng nguồn được chọn,
giữ nguyên metadata và toàn bộ nội dung nguồn làm quoted_text; model không
chép lại URL, số hiệu hoặc đoạn trích. Public output vẫn là `LegalAnswer`.
Nguồn được biểu diễn một lần dưới dạng chuỗi JSON để giữ nguyên xuống dòng;
không thêm source catalog lặp lại. `LLMOutputTruncatedError` nghĩa là provider
đã cắt output ở giới hạn; JSON dở dang không được chấp nhận. Khác với
`LLMContextWindowError`, khi prompt + overhead + output không vừa cửa sổ model.
Trace giữ loại lỗi cụ thể; `--debug` cho biết số token liên quan.

Tham khảo chính thức: [BGE-M3](https://huggingface.co/BAAI/bge-m3),
[multilingual MiniLM](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1),
[Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B),
[Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B),
[Ollama chat](https://docs.ollama.com/api/chat),
[Ollama embed](https://docs.ollama.com/api/embed),
[pgvector](https://github.com/pgvector/pgvector).

## 5. Graph và giới hạn nguồn

Graph lưu Document → CONTAINS → Chunk và Chunk → PART_OF → Parent.
Quan hệ document có `relation_type`, evidence chunk IDs và evidence text;
AMENDS/REPLACES/REPEALS hướng văn bản mới → văn bản cũ. Traversal có thể đi hai
chiều để mở rộng tìm kiếm nhưng không đổi ý nghĩa của loại quan hệ.

Builder chỉ resolve endpoint không mơ hồ trong corpus. Dẫn chiếu ngoài corpus,
evidence thiếu/sai ID hoặc không neo được vào leaf được lưu riêng, không tự tạo
căn cứ pháp lý. Graph retriever BFS giới hạn depth/nodes; metadata filter vẫn
áp dụng sau graph. Chỉ đưa quan hệ vào context khi evidence của nó được giữ.

Corpus phụ thuộc topics/subjects trong YAML. Lượt rà soát ba topic Giao thông,
vận tải; Khoa học, công nghệ; Giáo dục, đào tạo có 7.425 điều thuộc 647 văn bản,
sau hierarchical là 14.708 leaves; xem [báo cáo rà soát](PIPELINE_AUDIT_REPORT.md).
JSON cũ 100 điều vẫn dùng được bằng `source.type: json`. Metadata còn thiếu ngày,
hiệu lực và có nhãn phân loại riêng. Analyzer chỉ tạo hard filter cho nhãn
corpus được nêu rõ trong câu hỏi gốc, không dùng nhãn do model suy diễn;
không ép sang taxonomy tiếng Anh. Nhãn điều Pháp điển được giữ nguyên, không
tự quy đổi thành số điều của văn bản gốc. Không dùng corpus nhỏ này để kết
luận hệ thống bao phủ mọi câu hỏi pháp luật hoặc xác nhận hiệu lực hiện hành.

## 6. Debug và kiểm thử

```powershell
.\.venv\Scripts\python.exe -m scripts.demo ask --question "Câu hỏi" --trace .runtime/my-trace.json
.\.venv\Scripts\python.exe -m scripts.demo --debug ask --question "Câu hỏi"
.\.venv\Scripts\python.exe -m pytest -q
$env:RAG_RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_database_backends.py -q
```

Trace mặc định ở `data/runtime/<corpus_id>/traces`, chứa query, strategy, kết
quả từng vòng, evaluation, analysis và filters thực dùng. Log mặc định chỉ ghi stage/type lỗi; `--debug`
có exception chi tiết và log driver, có thể chứa nội dung nguồn/query. Không
chia sẻ trace/log/credentials nếu có dữ liệu riêng tư. Hai thư mục runtime đã
được gitignore.

DB integration tests dùng table/namespace riêng có ID ngẫu nhiên và chỉ dọn
đối tượng do test tạo. Không bật biến trên thì chúng được skip; unit tests
không cần DB/model thật. Nếu Windows chặn thư mục TEMP mặc định khi pytest,
đặt TEMP và TMP vào một thư mục `.runtime/test-tmp` đã tạo trong workspace.

Chạy `python -m scripts.smoke_pipeline` để kiểm tra 10 ca thật trên ba topic
ở trên, lưu trace và `summary.json` trong `.runtime/pipeline-smoke`. Đây là
kiểm tra tích hợp có chủ đích, không phải benchmark chất lượng pháp lý.
