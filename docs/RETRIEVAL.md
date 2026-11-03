# Triển khai retrieval

Các module trong `src/retrieval/` triển khai contract đồng bộ của
[INTERFACES.md](INTERFACES.md), dùng schema trong `core.schemas` và cấu hình
trong [CONFIGURATION.md](CONFIGURATION.md).

## Chạy local

Từ thư mục gốc, Python >= 3.10:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m examples.retrieval_demo
```

Ví dụ dùng chunk giả lập, embedding và điểm cross-encoder giả lập; BM25,
tìm kiếm vector, lọc, RRF và aggregation chạy bằng implementation thật.
Không cần API key, database hay tải model. Không dùng dữ liệu/model giả lập
này để đánh giá chất lượng tìm kiếm pháp luật.

## Các thành phần

| Module | Trách nhiệm |
| --- | --- |
| `sparse/bm25.py` | `BM25Retriever` / tên cũ `BM25Lib`: index từ `LegalChunk`, `RetrievedChunk` hoặc `RetrievalResult.results` |
| `dense/vector_retriever.py` | `VectorRetriever`: gọi `BaseEmbedding`, kiểm tra vector rồi tìm qua `VectorStore` được inject |
| `hybrid/rrf.py` | `reciprocal_rank_fusion`: hợp nhất bằng rank, mỗi chunk có tối đa một phiếu trong mỗi nhánh |
| `hybrid/hybrid.py` | `HybridRetriever`: BM25/Vector -> RRF -> rerank tùy chọn -> top_k |
| `reranking/cross_reranker.py` | `CrossEncoderReRanker`: lazy load model hoặc nhận model qua constructor |
| `aggregation/result_aggregator.py` | `ResultAggregator`: hợp nhất, đếm ứng viên duy nhất, giới hạn và rerank |
| `router/retrieval_router.py` | `RetrievalRouter`: defaults và policy theo intent được cấu hình tường minh |
| `service.py` | `RetrievalService`: điều phối các nhánh theo strategy, tích hợp graph adapter |
| `../infrastructure/vector_store/in_memory.py` | `InMemoryVectorStore`: tìm kiếm vector chính xác bằng cosine, inner product hoặc L2 |

Giữ các tên file BM25/hybrid/reranker đang có trong bản viết dở. Chữ ký
`BaseRetriever.search`, `BaseReRanker.rerank` và các schema giữ nguyên.
`BaseReRanker` được bổ sung vào export của `core.interfaces`.

## Quy tắc truy xuất

- Mỗi `BaseRetriever.search` trả tối đa `request.top_k` hit duy nhất.
  Hybrid/service gọi mỗi nhánh với `top_k=candidate_k` để thu thập ứng viên.
- RRF dùng rank bắt đầu từ 1, công thức `sum(1 / (rank_constant + rank))`.
  Không cộng trực tiếp điểm BM25 với điểm vector. Hòa điểm giữ thứ tự xuất hiện.
- Sau hợp nhất, giới hạn pool rerank ở `candidate_k`, sau đó lấy `top_k`.
  `RetrievalResult.total_candidates` đếm ID duy nhất sau lọc, trước hai lần cắt này.
- Metadata lưu toàn bộ `LegalMetadata` và `chapter/article/clause/point/parent_id`.
  Metadata bổ sung như URL nguồn được giữ khi đầu vào là `RetrievedChunk`.
- Filters là mapping phẳng, AND giữa các key; scalar so sánh bằng, list khớp
  ít nhất một giá trị. List rỗng không khớp gì. `None` là giá trị equality,
  không có nghĩa là bỏ qua điều kiện. Field bị thiếu không khớp.
- Field lọc hỗ trợ: các field `LegalMetadata`, vị trí chunk nêu trên và `source_url`.
  Field/operator khác hoặc điều kiện lồng nhau báo `ValueError`, kể cả index rỗng.
- Sparse dùng NFC, tùy chọn lowercase và tokenizer giống nhau ở index/query.
  Hỗ trợ `whitespace` theo config, `word` theo Unicode hoặc callable được inject.
  Chỉ trả chunk có ít nhất một token query; vẫn giữ điểm Okapi bằng 0/âm.
  Đổi tokenizer/normalization phải xây dựng lại index.
- Dense yêu cầu dimension khớp, vector hữu hạn. Cosine từ chối vector zero.
  Inner product giữ dot product; L2 trả khoảng cách âm để điểm cao luôn tốt hơn.
- Input index trùng ID bị từ chối. Cùng ID từ nhiều nhánh phải khớp document,
  nội dung và các metadata chung; metadata bổ sung được hợp nhất.
- Dữ liệu index và hit trả về được sao chép để không sửa metadata nguồn qua output.

## Tích hợp pipeline

```python
from core.config import load_settings
from core.schemas import MetadataFilterRequest, RetrievalRouteRequest
from src.preprocessing import MetadataFilter
from src.retrieval.router import RetrievalRouter
from src.retrieval.service import RetrievalService

settings = load_settings()
router = RetrievalRouter(settings.retrieval)
filter_result = MetadataFilter().build_filters(MetadataFilterRequest(metadata=analysis.metadata))
# bm25, vector, graph, reranker là các adapter đã tạo trong composition root.
service = RetrievalService(
    bm25_retriever=bm25,
    vector_retriever=vector,
    graph_retriever=graph,
    reranker=reranker,
    settings=settings.retrieval,
)
strategy = router.route(RetrievalRouteRequest(
    query=analysis.rewritten_query,
    intent=analysis.intent,
    filters=filter_result.filters,
    entities=analysis.entities,
))
result = service.retrieve(
    query=analysis.rewritten_query,
    filters=filter_result.filters,
    strategy=strategy,
    entities=analysis.entities,
)
```

Filter phải đi từ `BaseMetadataFilter.build_filters`, không truyền trực tiếp
`analysis.metadata`. Xem [METADATA_FILTERING.md](METADATA_FILTERING.md) cho
implementation và quy tắc validation. Router mặc định dùng cấu hình; không tự đoán taxonomy
intent hoặc bật graph chỉ vì query có entity. Khi nhóm chốt intent có thể inject
`intent_overrides={"<intent đã thống nhất>": {"use_graph": True}}`.
Router và service đều kiểm tra hard limits của strategy.

Graph retriever do module knowledge graph cung cấp qua `BaseGraphRetriever`.
Service truyền entities, seed document ID và `max_depth`; adapter chịu trách
nhiệm giới hạn traversal bằng `max_nodes` qua constructor. Service lọc graph
hits trước fusion, giới hạn số hit graph bằng `max_nodes`, và chỉ giữ quan hệ
có hai document cùng các evidence chunk ID trong tập ứng viên đã lọc.
Quan hệ dùng các key baseline trong INTERFACES.md; `relations` có thể tham chiếu
ứng viên đã bị cắt khỏi kết quả cuối. Context builder phải chọn lại nguồn/quan
hệ phù hợp với ngân sách context và các chunk thực sự được giữ.

Reranker giữ chữ ký `QueryAnalysisResult, LegalContext -> LegalContext` hiện có.
Aggregator tạo context tạm cho pool ứng viên, dùng query retrieval làm
`rewritten_query` rồi gọi reranker. Context trả về được dựng lại từ các chunk
được chọn; đây chưa phải context pháp lý cuối của `BaseLegalContextBuilder`.
Aggregator từ chối reranker đưa thêm chunk hoặc sửa nội dung/metadata nguồn.

## Model và database thật

```powershell
python -m pip install -e ".[reranking]"
```

Chọn model bằng `settings.retrieval.reranker.model`, rồi tạo:

```python
from src.retrieval.reranking import CrossEncoderReRanker

config = settings.retrieval.reranker
reranker = CrossEncoderReRanker(
    model_name=config.model,
    revision=config.revision,
    batch_size=config.batch_size,
    max_length=config.max_input_tokens,
    device=config.device,
)
```

Không tự chọn model khi config còn `null`. Model được tải ở lần chấm điểm đầu
tiên; input rỗng không tải model. Chỉ nhận một điểm hữu hạn cho mỗi cặp query/chunk,
hỗ trợ output shape `N` hoặc `N x 1`, từ chối output phân loại nhiều nhãn.
API dựa trên [Sentence Transformers CrossEncoder](https://www.sbert.net/docs/package_reference/cross_encoder/model.html).
BM25 dùng [rank_bm25 BM25Okapi](https://github.com/dorianbrown/rank_bm25).

`VectorStore` là protocol nội bộ ở `dense/vector_retriever.py`. Adapter database
cần công bố `dimension` và triển khai:

```python
def search(self, vector, *, filters, top_k) -> list[RetrievedChunk]:
    ...
```

Backend phải áp dụng filter **trước** cắt top_k, trả hit theo similarity giảm dần,
và bảo toàn nguồn. `VectorRetriever` phát hiện backend trả hit vi phạm filter.
Hiện có backend trong bộ nhớ và `PgVectorStore` trong
`src/infrastructure/vector_store`, hỗ trợ exact/HNSW/IVFFlat và ba metric.
`OllamaEmbedding` trong `src/infrastructure/embedding` dùng embed API theo batch.
Reranker có thêm backend ONNX dùng cùng `CrossEncoderReRanker`; Neo4j graph
được ghép ở `src/runtime.py`. Xem [DEMO.md](DEMO.md) để chọn phương pháp.
Không kết nối database hoặc tải model thật trong unit test. Gọi `settings.validate_runtime`
theo CONFIGURATION.md ở composition root trước khi dùng dịch vụ thật.

Lỗi embedding báo `EmbeddingError`; index/store/model/retriever lỗi báo
`RetrievalError` và giữ exception gốc qua `raise ... from exc`. Không trả `[]`
để che lỗi. Thiếu adapter đang bật báo `ValueError` trước khi truy xuất.
Retry/fallback, timeout/deadline tổng và feedback loop do orchestrator quản lý;
retrieval service đồng bộ không tự triển khai cơ chế hủy call đang chạy.
