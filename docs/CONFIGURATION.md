# Cấu hình chung cho nhóm

Điểm vào duy nhất là `from core.config import load_settings`. Load một lần
ở startup/factory, sau đó truyền section phù hợp vào constructor từng module.
Schema request/response không đọc file hoặc biến môi trường khi import.

Profile chạy demo thật: `load_settings("configs/demo")`, hoặc dùng
`python -m scripts.demo` để tự load profile và file credentials local.
Xem [DEMO.md](DEMO.md) cho setup và các tham số lựa chọn phương pháp.
Profile phát triển `configs` tiếp tục giữ các lựa chọn cần nhóm cấu hình.

Các field tích hợp mới: `embedding.provider=ollama`, `base_url`, tokenizer
model/revision; mỗi LLM role có tokenizer model/revision và overhead budget;
role thứ tư là `llm.citation_verifier`. `llm.keep_alive`/`think` được truyền
sang Ollama chat API. `retrieval.reranker.backend` chọn `onnx` hoặc
`sentence_transformers`, ONNX có `file_name`. Vector có backend, index_type
và các tham số HNSW/IVFFlat; graph có backend và namespace. Data pipeline có
source_chunks_file, relations_file, index_dir và ba chunking strategy
fixed/legal/hierarchical. Các path tương đối vẫn tính từ parent config_dir;
profile lồng `configs/demo` dùng `../data/...` để trỏ về data của repository.

`data_pipeline.source` chọn `json` hoặc `huggingface`. Nguồn Hugging Face có
dataset/config/split/revision, topics, subjects và read_batch_size; selector
nhận tên chính xác (chuẩn hóa hoa/thường, khoảng trắng, Unicode NFC) hoặc ID.
Topics và subjects kết hợp OR; không có selector thì prepare/chat báo lỗi,
list-topics/list-subjects vẫn chạy để tra catalog. `auto_prepare` quyết định
ask/chat có tự xây corpus/index thiếu hay không. `prepare --refresh-source`
mới resolve lại revision được yêu cầu; mặc định snapshot đã cache được pin.
Xem [TOPIC_CORPUS.md](TOPIC_CORPUS.md) cho ví dụ và vị trí cache.

Runtime hiện hỗ trợ embedding qua Ollama: `device: cpu` truyền `num_gpu: 0`,
`auto` dùng lựa chọn của server, `cuda` cho phép server tự chọn mức offload GPU.
Profile demo dùng CPU sau khi tái hiện lỗi CUDA runner. Device không đổi
model/dimension/normalization nên không làm mất hiệu lực cache embedding.

Analyzer dùng vocabulary corpus để chỉ tạo hard filter từ nhãn được nêu rõ
trong câu hỏi gốc. LLM không tự đoán hard filter. Evaluator nhận schema feedback
có giới hạn strategy của config; orchestrator merge và validate lại như cũ.
`retrieval.timeout_s` áp dụng cho từng lượt retrieval bên trong deadline tổng.

Prompt generator `v1` dùng `prompts/answer_generation/system.txt` và `user.txt`;
version khác dùng cặp file trong `prompts/answer_generation/<version>/`.
Prompt được đọc/kiểm tra khi khởi tạo, cần restart để nhận thay đổi. Các agent
còn lại dùng `prompts/<module>/<version>.txt`.

Đổi tham số xây index (HNSW `m`/`ef_construction`, IVFFlat `lists`) tạo tên
table mới cùng corpus; `ef_search`/`probes` chỉ thay lúc query. Auto-prepare
kiểm tra và xây riêng store còn thiếu, không ghi lại graph khi chỉ thiếu vector.

## Các file và người phụ trách

| File | Thông số chính | Owner |
| --- | --- | --- |
| `configs/config.yml` | Environment, API, logging, số vòng retrieval, deadline, ngân sách context | Luân |
| `configs/retrieval.yml` | BM25/Vector/Graph/Rerank, top_k, candidate_k, RRF, giới hạn graph | Luân; Đức Anh review graph |
| `configs/embedding.yml` | Provider, model/revision, dimension, normalization, batch, device | Đức Anh + Luân |
| `configs/llm.yml` | Provider, model riêng từng vai trò, temperature, output budget, prompt version, retry | Trung; Trí Anh review hai agent |
| `configs/database.yml` | PostgreSQL/pgvector, Neo4j, pool, connection timeout, distance metric | Đức Anh + Luân |
| `configs/data_pipeline.yml` | Thư mục dữ liệu, tokenizer, chiến lược chunk, kích thước/overlap, index batch | Đức Anh |

Giữ đuôi `.yml` thống nhất với file `config.yml` đã có trong repo. Loader đọc
đúng sáu tên trên; thiếu file, section sai, key trùng hoặc field không khai báo
sẽ báo `ConfigurationError`. Field không ghi trong section dùng default từ
Pydantic; giữ section dạng `{}` nếu muốn dùng toàn bộ default của section đó.

## Giá trị khởi đầu

Đây là baseline để benchmark, chưa phải thông số tối ưu cho dữ liệu của nhóm.

| Nhóm | Giá trị đề xuất ban đầu | Mục đích |
| --- | --- | --- |
| Retrieval | `top_k=5`, `candidate_k=20` | Giữ khớp defaults của schema |
| Giới hạn strategy | `max_top_k=20`, `max_candidate_k=100` | Chặn router/evaluator mở rộng chi phí quá mức |
| BM25 | `k1=1.2`, `b=0.75`, tokenizer `whitespace` | Baseline trước khi benchmark tokenizer tiếng Việt |
| Fusion | RRF `rank_constant=60` | Hợp nhất thứ hạng thay vì cộng điểm khác thang đo |
| Graph | Tắt mặc định; `max_depth=2`, `max_nodes=100` | Giới hạn phạm vi mở rộng khi được bật |
| Reranker | Bật trong strategy; batch 16, input tối đa 512 token | Chỉ khởi tạo thật sau khi chọn model |
| Embedding | Batch 32, normalize bật | Điều chỉnh theo model, bộ nhớ và distance metric |
| Chunking | Hierarchical, target 512 token, overlap 64 token | Ưu tiên ranh giới điều/khoản; chia tiếp khi quá dài |
| Context | Tối đa 4096 token; dự phòng prompt 1024 token | Còn chỗ cho câu hỏi, chỉ dẫn và đầu ra |
| LLM | Temperature 0; output 512 / 768 / 2048 token | Lần lượt query analyzer / evaluator / answer generator |
| Pipeline | Tối đa 3 vòng; deadline tổng 90 giây | Giới hạn feedback loop |
| Retry | Tối đa 2 lần thử lại; mỗi call LLM/embedding timeout 30 giây | Cùng chia sẻ deadline tổng |
| Database | Pool 5, connection timeout 5 giây | Baseline cho môi trường phát triển nhỏ |

Các giá trị BM25 tham khảo defaults của [Elastic BM25](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/index-modules-similarity.html).
RRF 60 tham khảo [Elastic RRF](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion).
Đây chỉ là tham chiếu tham số, không yêu cầu nhóm sử dụng Elasticsearch.

BM25 phải dùng cùng tokenizer và normalization khi index và query. Chuỗi
`whitespace` hiện là tên cấu hình baseline; implementation cần hỗ trợ tên này
hoặc báo lỗi rõ ràng. Muốn đổi tokenizer phải xây dựng lại sparse index.

`candidate_k` là số ứng viên tối đa **mỗi nhánh** BM25/Vector. Sau khi loại
trùng và RRF, giữ tối đa `candidate_k` ứng viên để rerank, rồi lấy `top_k`.
Graph được giới hạn riêng bằng depth/nodes và phải được lọc trước aggregation.
`total_candidates` đếm chunk ID duy nhất được aggregation xét trước cắt cuối.

## Những lựa chọn phải chốt trước khi dùng dịch vụ thật

Các field dưới đây cố ý để `null`:

- Embedding: `provider`, `model`, `revision` nếu có, `dimension`.
- Reranker: `model`, `revision` nếu có; đối chiếu `max_input_tokens` với model.
- LLM: `provider`; `model` và `context_window_tokens` cho cả bốn vai trò.
- Ingestion: `data_pipeline.chunking.tokenizer_model` để đếm token chính xác.

`load_settings()` vẫn chạy để phát triển mock. Gọi `settings.validate_runtime()`
trước khi tạo adapter cho pipeline hỏi đáp; gọi
`settings.validate_runtime(purpose="ingestion")` trước ingestion.
Nếu router bật thêm một nhánh so với defaults, gọi lại với
`settings.validate_runtime(strategy=selected_strategy)` trước khi chạy nhánh đó.
Method báo các lựa chọn/provider key còn thiếu; nó không kết nối database,
kiểm tra credentials có hợp lệ, tải model hay xác minh provider hỗ trợ tham số.

Adapter còn phải kiểm tra số chiều vector thực tế, tokenizer, khả năng đặt
temperature và giới hạn input/output của model đã chọn. Nếu model không hỗ
trợ tùy chọn, báo lỗi cấu hình; không âm thầm đổi sang model khác.

Không đổi embedding model, dimension, normalization hoặc distance metric trên
index đã có mà không kiểm tra tương thích và xây dựng lại vector/index khi cần.
Lưu model/revision và cấu hình chunk/tokenizer cùng phiên bản index để truy vết.

## Thứ tự ghi đè và secret

Ưu tiên: **Pydantic defaults < YAML < biến môi trường**.

```powershell
$env:RAG__RETRIEVAL__TOP_K = '8'
$env:RAG__RETRIEVAL__CANDIDATE_K = '40'
$env:RAG__LLM__API_KEY = '<your-key>'
$env:RAG__DATABASE__VECTOR__PASSWORD = '<your-password>'
python -m examples.config_demo
```

Tên biến dùng `RAG__SECTION__FIELD`, có thể lồng nhiều cấp, ví dụ
`RAG__LLM__ANSWER_GENERATOR__MAX_OUTPUT_TOKENS`. Số, bool, list dùng cú pháp
JSON: `8`, `false`, `["http://localhost:3000"]`. Text thông thường dùng nguyên
chuỗi; muốn giữ chuỗi chỉ gồm số phải dùng JSON string như `"123"`.
API key/password luôn được giữ nguyên chuỗi, không parse JSON.

API key/password chỉ nhận qua environment; loader từ chối chúng trong YAML.
Settings giữ secret dưới dạng `SecretStr`; adapter chỉ lấy giá trị thật bằng
`get_secret_value()` khi gọi provider/database. Không log giá trị thật.

`.env.example` chỉ liệt kê tên biến để tham khảo. Loader không tự đọc `.env` và
không nội suy `${...}` trong YAML. Shell, container hoặc launcher phải export
biến vào process. Không cần thêm `pydantic-settings` hoặc `python-dotenv`.

## Đường dẫn

```python
from core.config import load_settings

settings = load_settings()                 # ./configs hoặc RAG_CONFIG_DIR
settings = load_settings("D:/my-project/configs")
```

`config_dir` truyền trực tiếp ưu tiên hơn `RAG_CONFIG_DIR`. Đường dẫn dữ liệu
tương đối tính từ thư mục cha của config directory; với repo này là thư mục
gốc project. Loader chuyển chúng thành đường dẫn tuyệt đối nhưng không tạo
thư mục, tải file hoặc kết nối dịch vụ. Khi cài package nơi khác, truyền config
directory rõ ràng; các YAML thuộc repo, không được đóng gói vào wheel `core`.

## Truyền config vào contract

```python
from core.config import load_settings
from core.schemas import RetrievalRequest, RetrievalStrategy

settings = load_settings()
strategy = settings.retrieval.default_strategy()

# Khi evaluator đề xuất thay đổi, merge vào strategy hiện tại rồi validate:
strategy = RetrievalStrategy.model_validate({
    **strategy.model_dump(),
    "use_graph": True,
})
strategy = settings.retrieval.validate_strategy(strategy)

request = RetrievalRequest(
    query="Câu hỏi đã rewrite",
    filters={},  # Lấy từ MetadataFilterResult.filters trong pipeline thật.
    top_k=strategy.top_k,
    candidate_k=strategy.candidate_k,
)
```

`RetrievalRequest(query=...)` đơn thuần vẫn dùng default của schema. Để YAML có
tác dụng, factory/orchestrator phải truyền giá trị như ví dụ; không sửa default
schema toàn cục lúc chạy. Các module khác nhận section qua constructor:

- Trí Anh: `settings.llm.query_analyzer`, `settings.llm.retrieval_evaluator`;
  orchestrator truyền `settings.pipeline.max_iterations` vào evaluation request.
- Đức Anh: `settings.data_pipeline`, `settings.embedding`, `settings.database`,
  `settings.retrieval.graph`; graph adapter thực thi `max_nodes` qua constructor.
- Trung: `settings.llm.answer_generator` và `settings.context`; context builder
  và generator dùng chung ngân sách token.
- Luân: wiring, router, retrieval, context, API, logging, deadline và fallback.

Settings được đóng băng để tránh module sửa cấu hình đang chia sẻ. Khi thay đổi
config, khởi động lại ứng dụng; hiện chưa có hot reload hay cache ngầm.

## Các ràng buộc bắt buộc

Loader kiểm tra số dương, key sai, `candidate_k >= top_k`, hard limits,
`overlap_tokens < target_tokens`, timeout mỗi call không vượt deadline tổng,
và tổng **context + dự phòng prompt + output** không vượt cửa sổ answer model
khi cửa sổ đã khai báo. Runtime vẫn phải đếm token thực tế, kể cả các agent.

`max_iterations=3` là tổng ba vòng retrieval/evaluation, không phải ba lần retry.
`max_retries=2` là tối đa hai lần thử thêm sau call đầu. Orchestrator truyền
thời gian còn lại cho từng call; không được cộng dồn các timeout khiến vượt
deadline 90 giây.

Các quy tắc sau phải nằm trong code/contract, không tạo công tắc tắt bằng config:

- Không generation khi evaluation chưa đủ căn cứ.
- Phải kiểm tra citation và khả năng truy nguyên về nguồn.
- Không so sánh confidence với retrieval score như cùng thang đo.
- Không suy ra hiệu lực pháp luật từ một status tĩnh.

Ngày áp dụng pháp luật, metadata filter và conversation ID là dữ liệu từng
request. Không dùng một ngày hiệu lực cố định cho toàn hệ thống. Chưa đặt
ngưỡng `min_confidence` tùy ý để quyết định đủ căn cứ; phải benchmark và hiệu
chỉnh evaluator trước khi bổ sung gate dạng này.

Chạy `python -m unittest discover -s tests -v` để kiểm tra cả schema và config.
Khi thêm thông số: cập nhật model, YAML, tài liệu và test trong cùng PR.
