# Hợp đồng dữ liệu và interface dùng chung

Tài liệu này cụ thể hóa mục 4 của [kế hoạch kỹ thuật](vietnamese_law_rag_technical_spec.md).
Schema nằm trong `core/schemas/`, abstract class nằm trong `core/interfaces/`.
Mỗi thành viên import từ `core`, kế thừa ABC và triển khai logic trong module
được phân công. Không sao chép rồi sửa schema riêng trong `src/`.

## Cài đặt và kiểm tra

Yêu cầu Python >= 3.10, Pydantic >= 2.10 và < 3. Chạy từ thư mục gốc:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m examples.contract_demo
```

Nếu môi trường đã có Pydantic, có thể chạy kiểm tra không cần cài pytest:

```powershell
python -m unittest discover -s tests -v
```

## Danh sách contract

Tất cả method là **đồng bộ** (`def`). Model/database/provider được inject qua
constructor của implementation, không thêm vào chữ ký method chung. ABC chỉ
định nghĩa contract, chưa chứa thuật toán hay kết nối dịch vụ.

Cấu hình chung đọc bằng `core.config.load_settings()` và inject vào constructor.
Xem [CONFIGURATION.md](CONFIGURATION.md) để biết thông số, defaults, environment
overrides và cách truyền giá trị cấu hình vào request/strategy.

| Mục | ABC / method | Input | Output | Owner |
| --- | --- | --- | --- | --- |
| 4.1 | `BaseQueryAnalyzer.analyze` | `QueryRequest` | `QueryAnalysisResult` | Trí Anh |
| 4.2 | `BaseMetadataFilter.build_filters` | `MetadataFilterRequest` | `MetadataFilterResult` | Luân |
| 4.3 | Data pipeline, chưa có ABC trong mục 4 | Dữ liệu nguồn | `LegalDocument`, `LegalChunk`, `LegalMetadata` | Đức Anh |
| 4.4 | `BaseRetriever.search` | `RetrievalRequest` | `list[RetrievedChunk]` | Luân |
| 4.5 | `BaseRetrievalRouter.route` | `RetrievalRouteRequest` | `RetrievalStrategy` | Luân |
| 4.6 | `BaseGraphRetriever.search` | `GraphRetrievalRequest` | `GraphRetrievalResult` | Đức Anh |
| 4.7 | `BaseEvaluator.evaluate` | `RetrievalEvaluationRequest` | `RetrievalEvaluationResult` | Trí Anh |
| 4.8 | `BaseLegalContextBuilder.build` | `ContextBuilderRequest` | `LegalContext` | Luân |
| 4.9 | `BaseAnswerGenerator.generate` | `AnswerGenerationRequest` | `LegalAnswer` | Trung |
| 4.9 | `BaseCitationVerifier.verify` | `LegalAnswer`, `LegalContext` | `LegalAnswer` | Luân |

`BaseRetriever` dùng chung cho BM25, Vector và Hybrid Search. Graph có request
và output khác nên dùng `BaseGraphRetriever` riêng. Giữ tên method `search`
như mục 4; `retrieval_service.retrieve` trong pseudo-code mục 6 là tầng điều phối
cao hơn, chưa phải contract của từng retriever.

Implementation retrieval, cách inject adapter/model và ví dụ chạy local được
mô tả tại [RETRIEVAL.md](RETRIEVAL.md).

Implementation context, cách inject tokenizer của answer model và quy tắc giữ
nguồn trong ngân sách được mô tả tại [CONTEXT_BUILDER.md](CONTEXT_BUILDER.md).

Hai ABC phụ trợ trong cây thư mục mục 3 được định nghĩa ở mức tối thiểu:

| ABC | Method / property | Quy ước |
| --- | --- | --- |
| `BaseEmbedding` | `dimension: int` | Số chiều dương, cùng model ở ingestion và query |
| `BaseEmbedding` | `embed_query(text: str) -> list[float]` | Vector hữu hạn, đúng số chiều |
| `BaseEmbedding` | `embed_documents(texts: list[str]) -> list[list[float]]` | Giữ số lượng/thứ tự; input `[]` trả `[]` |
| `BaseLLM` | `generate(prompt: str) -> str` | Adapter trả text; agent/generator parse thành schema của mình |
| `BaseReRanker` | `rerank(query: QueryAnalysisResult, documents: LegalContext, top_k: int = 5) -> LegalContext` | Giữ nguồn, xếp hạng chunk, dựng lại text và document ID từ các chunk được giữ |

`BaseLLM.generate` khác `BaseAnswerGenerator.generate`: Trung dùng adapter LLM
bên trong answer generator và phải trả `LegalAnswer`, không trả text thô.
Tham số model, timeout, sampling và credentials nằm trong config/constructor.

## Quy tắc schema

- Tên field và giá trị mặc định giữ theo mục 4. Các `dict` và `list[dict]` mở
  được giới hạn thành dữ liệu JSON bằng `JsonValue`, vẫn serialize cùng cấu trúc.
- Field không khai báo bị từ chối (`extra="forbid"`), giúp phát hiện sai tên
  như `topk` thay vì `top_k`. Các giá trị mở bên trong metadata không bị giới
  hạn thành enum trước khi nhóm chốt taxonomy.
- Query, ID, nội dung nguồn, intent, reason và answer bắt buộc phải có nội dung;
  khoảng trắng đầu/cuối của các field này được loại bỏ.
- `top_k`, `candidate_k`, `max_depth`, `max_iterations` là số nguyên dương;
  `candidate_k >= top_k`. `iteration` bắt đầu từ 0 và nhỏ hơn `max_iterations`.
  `total_candidates >= 0`; không dùng bool làm số lượng.
- `confidence` nằm trong [0, 1]. Retrieval `score` và vector chỉ cần hữu hạn;
  score có thể âm hoặc lớn hơn 1 tùy thuật toán. Không so sánh trực tiếp score
  khác thang đo, không lấy score làm confidence.
- `document_id` trên `LegalDocument`/`LegalChunk` phải khớp
  `metadata.document_id`. `embedding=None` nghĩa là chưa embed; vector đã có
  phải khác rỗng. Adapter kiểm tra số chiều theo `BaseEmbedding.dimension`.
- Mỗi instance có list/dict mặc định riêng. Khi trao đổi qua API/file dùng
  `model_dump(mode="json")`, `model_dump_json()` và `model_validate_json()`.
- Pydantic kiểm tra cấu trúc dữ liệu, không chứng minh nội dung pháp lý đúng.
  ABC không tự kiểm tra output của method; implementation phải tạo/trả model
  đúng và có test. Không sửa trực tiếp list/dict lồng nhau rồi mặc định rằng
  Pydantic đã kiểm tra lại; hãy tạo/validate lại model tại ranh giới module.

## Metadata và truy nguyên nguồn

`LegalMetadata` chứa thông tin văn bản; `LegalChunk` giữ điều/khoản/điểm và
`parent_id` ở cấp chunk. ID phải ổn định qua ingestion và retrieval;
`amended_by`, `replaced_by`, `repealed_by`, `related_documents` chứa **document ID**.
Ngày giữ kiểu `str | None` theo đặc tả: dùng chuỗi ISO `YYYY-MM-DD` cho ngày
đã xác định, `None` cho ngày chưa biết; parser chịu trách nhiệm kiểm tra ngày.

Khi đổi `LegalChunk` sang `RetrievedChunk`, chuyển `LegalMetadata` thành dict
JSON và bổ sung các field vị trí hiện có ở cấp cao nhất của `metadata`:

```python
hit_metadata = chunk.metadata.model_dump(mode="json")
hit_metadata.update({
    "chapter": chunk.chapter,
    "article": chunk.article,
    "clause": chunk.clause,
    "point": chunk.point,
    "parent_id": chunk.parent_id,
})
# Nếu adapter có URL nguồn đã xác minh:
# hit_metadata["source_url"] = source_url
```

`RetrievedChunk.metadata` giữ kiểu dict như đặc tả, vì thế retriever phải bảo
toàn các field nguồn; không chỉ trả về text và score. Khi không có URL, truy
nguyên bằng document ID và chunk ID; không để LLM tạo URL.

`LegalCitation` giữ các field của mục 4.9. Verifier đối chiếu `document_id`,
`document_number`, vị trí và `quoted_text` với `LegalContext.chunks` để xác
định chunk nguồn. Không xác minh được thì báo `CitationVerificationError`.
Verifier còn phải kiểm tra nguồn hỗ trợ nhận định; chỉ có câu trích dẫn xuất
hiện trong chunk chưa đủ chứng minh toàn bộ câu trả lời đúng.

Implementation `src.generation.CitationVerifier` kiểm tra citation bằng code
trước, sau đó dùng `BaseLLM` được inject để đánh giá nhận định với các nguồn
đã khớp. Xem [CITATION_VERIFICATION.md](CITATION_VERIFICATION.md) cho quy tắc,
prompt và xử lý lỗi.

Không suy ra hiệu lực từ `status` tĩnh. Xác định phạm vi, thời điểm áp dụng và
quan hệ sửa đổi/thay thế cần logic nghiệp vụ riêng. Cách biểu diễn hiệu lực
theo từng quy định và graph ontology vẫn cần nhóm chốt theo mục 11.

## Metadata filtering và graph

Để các adapter diễn giải giống nhau, baseline của `filters` là mapping phẳng:

```json
{"legal_domain": ["labor"], "document_type": ["law", "decree"]}
```

- Kết hợp các key bằng AND.
- Giá trị scalar: so sánh bằng; giá trị list: khớp ít nhất một phần tử.
- Nếu metadata lưu list (như `legal_domain`), khớp bằng giao khác rỗng.
- Mapping rỗng nghĩa là không lọc. List rỗng không khớp kết quả nào.
- Không có field metadata tương ứng thì không khớp điều kiện.
- Không hỗ trợ field/operator phải báo `ValueError`, không bỏ qua âm thầm.
  Không truyền trực tiếp filter thành SQL/Cypher; adapter phải dùng tham số.
- Bộ lọc khoảng thời gian/operator lồng nhau cần bổ sung contract trước khi dùng.

Luồng đúng là `analysis.metadata` -> `MetadataFilterRequest` ->
`MetadataFilterResult.filters` -> router/retriever. Pseudo-code mục 6 đang
truyền `analysis.metadata` trực tiếp; khi triển khai phải chèn bước filter này.

Implementation `src.preprocessing.MetadataFilter`, ý nghĩa `applied_filters`
và ví dụ nối với retrieval nằm tại [METADATA_FILTERING.md](METADATA_FILTERING.md).
`None` là equality với null; số không hữu hạn bị từ chối. Danh sách field và
validation được dùng chung qua `core/filtering.py` để các tầng không lệch contract.

`GraphRetrievalRequest` trong mục 4.6 chưa có `filters` hay `top_k`. Tầng tích
hợp phải áp dụng bộ lọc lên kết quả graph trước khi hợp nhất, tránh graph mở
rộng vượt phạm vi truy vấn. `max_depth` là số cạnh tối đa được duyệt, không phải
số kết quả trả về.

`relations` giữ kiểu `list[dict]` như mục 4; graph ontology chưa bị cố định.
Baseline trao đổi cho quan hệ cấp văn bản là các key `source_document_id`,
`target_document_id`, `relation_type`, `evidence_chunk_ids`. Đây là quy ước
tích hợp, chưa có validator riêng. Đức Anh và Luân cần thống nhất thêm node,
edge và enum quan hệ trước khi triển khai graph schema.

## Feedback loop

| `next_action` | Ý nghĩa | Điều kiện |
| --- | --- | --- |
| `continue` | Sang context/generation | `is_sufficient=True`, `is_relevant=True` |
| `refine_query` | Orchestrator retrieval lại bằng query mới | Chưa đủ căn cứ; có `refined_query` khác rỗng |
| `change_strategy` | Orchestrator áp dụng chiến lược sửa đổi | Chưa đủ căn cứ; `strategy_override` khác rỗng |
| `stop` | Dừng và trả thông báo thiếu căn cứ | Chưa đủ căn cứ |

Đây là phần làm rõ các trạng thái của mục 4.7 để các thành viên không hiểu
`continue` là retrieval thêm một vòng. Evaluator không gọi retriever.
Orchestrator phải dừng tại `max_iterations` kể cả evaluator vẫn đề xuất retry.
Kết quả không có hit không được đánh giá là đủ căn cứ.

`src.orchestration.RAGPipeline` triển khai luồng này; `run(QueryRequest)` trả
`LegalAnswer`, `run_with_trace(QueryRequest)` trả `PipelineResult` cùng lịch sử
`RetrievalRound` riêng từng request. Xem [ORCHESTRATION.md](ORCHESTRATION.md)
cho factory, fallback và cách adapter dùng deadline chung.

`PipelineResult` bổ sung các field có default: `query` là câu hỏi gốc,
`analysis` là `QueryAnalysisResult | None`, `filters` là điều kiện thực dùng
(mặc định `{}`). Các trace cũ thiếu những field này vẫn validate được.

`strategy_override` là dict **một phần** của `RetrievalStrategy`, không phải
strategy đầy đủ. Orchestrator merge rồi validate lại để phát hiện key sai,
giới hạn sai hoặc tắt hết các phương thức:

```python
strategy = RetrievalStrategy.model_validate({
    **strategy.model_dump(),
    **evaluation.strategy_override,
})
```

Không dùng `model_copy(update=...)` cho dữ liệu chưa kiểm tra vì thao tác đó
không validate phần update. Sau aggregation, `total_candidates` là số chunk
ID duy nhất trước khi cắt top_k; `results` là kết quả cuối đã loại trùng.

## Lỗi và fallback

| Trường hợp | Contract |
| --- | --- |
| Input sai schema | `pydantic.ValidationError` |
| Primitive input rỗng, filter không hỗ trợ | `ValueError` |
| Không tìm thấy hit | `[]` hoặc graph result rỗng, không giả làm lỗi dịch vụ |
| Database/retriever lỗi | `RetrievalError` |
| Embedding provider/vector lỗi | `EmbeddingError` |
| LLM lỗi hoặc output không parse/validate được | `LLMError` |
| Context không có căn cứ dùng được | `InsufficientEvidenceError` |
| Citation/nhận định không xác minh được | `CitationVerificationError` |

Import lỗi từ `core.exceptions`. Wrap lỗi phụ thuộc bằng `raise ... from exc`
để giữ nguyên nguyên nhân. Orchestrator sở hữu retry/fallback và câu trả lời
thiếu căn cứ. Không trả danh sách rỗng để che lỗi provider. Không cho generation
tiếp tục khi evaluation chưa đủ căn cứ.

## Ví dụ cho thành viên

```python
from core.interfaces import BaseQueryAnalyzer
from core.schemas import QueryAnalysisResult, QueryRequest


class QueryAnalyzer(BaseQueryAnalyzer):
    def analyze(self, request: QueryRequest) -> QueryAnalysisResult:
        # Thay phần này bằng agent thật; chữ ký method giữ nguyên.
        return QueryAnalysisResult(
            original_query=request.query,
            rewritten_query=request.query,
            intent="legal_explanation",
        )
```

Xem `examples/contract_demo.py` để có mock retriever, context và answer generator
chạy được mà không cần database/API key. Dữ liệu trong ví dụ hoàn toàn giả lập,
chỉ dùng kiểm tra contract.

Khi đổi contract: Luân review thay đổi `core/`; cập nhật mục 4 nếu đổi
field/signature, tài liệu này, test và module phụ thuộc trong cùng PR.
Không cần đổi interface khi thay mock bằng implementation thật.

`LegalMetadata` bổ sung các field optional để giữ provenance: source_url,
source_record_id, source_dataset, source_revision, topic_id/topic_title và
subject_id/subject_title. Trên nguồn Hugging Face, đây là metadata của từng
điều, không được ghi đè bằng metadata của điều khác cùng văn bản. Xem
[TOPIC_CORPUS.md](TOPIC_CORPUS.md) về định danh và chọn corpus. Public method
signatures của các module hỏi đáp giữ nguyên.

`AnswerGenerator.generate` vẫn nhận `AnswerGenerationRequest` và trả
`LegalAnswer`. Đầu ra nội bộ của LLM là `AnswerDraft {answer, sources}` với
sources là các số nguyên dương của `[Nguồn N]`. Generator từ chối số ngoài
context, số trùng hoặc citation fields do model tự cung cấp; tạo citation
từ metadata/nội dung nguồn được giữ. Confidence chưa hiệu chuẩn bằng 0 và
disclaimer do code quản lý. Citation verifier tiếp tục kiểm tra nguồn và
claim support; không sửa trích dẫn sai hoặc nới phép so khớp nguyên văn.
