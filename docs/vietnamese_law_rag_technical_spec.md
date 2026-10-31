# Vietnamese Law RAG -- Technical Specification & Team Work Plan

> **Mục tiêu:** Thống nhất kiến trúc, phân công, cấu trúc repository,
> interface và quy trình GitHub để 4 thành viên có thể phát triển độc
> lập và tích hợp thống nhất.
>
> **Vai trò:** Team Lead / Technical Lead. 
> chịu trách nhiệm kiến trúc, Retrieval System và tích hợp tổng thể.
> Trung là thành viên phụ trách LLM Answer Generation với phạm vi công
> việc gọn hơn.

------------------------------------------------------------------------

## 1. System Architecture

Pipeline chính thức của dự án:

``` text
User Question
     |
     v
Query Analyzer Agent
     |
     v
Metadata Filtering
     |
     v
Retrieval Router
     |
     v
Retrieval Layer
     |
     +---- Hybrid Search
     |       |
     |       +-- BM25
     |       +-- Vector Search
     |       +-- RRF
     |       +-- Reranking
     |
     +---- Graph Retrieval
     |
     v
Retrieved Results
     |
     v
Retrieval Evaluation Agent
     |
     +---- Not relevant / Insufficient
     |          |
     |          v
     |     Refine Query / Change Strategy
     |          |
     |          +----> Retrieval Router
     |
     +---- Relevant
                |
                v
       Legal Context Builder
                |
                v
       LLM + Citation Verification
                |
                v
           Final Answer
```

### 1.1. Vai trò các thành phần

  -----------------------------------------------------------------------
  Thành phần                          Trách nhiệm
  ----------------------------------- -----------------------------------
  Query Analyzer Agent                Phân tích intent, rewrite query,
                                      trích xuất entity và metadata

  Metadata Filtering                  Chuyển metadata thành điều kiện lọc
                                      cho retrieval

  Retrieval Router                    Chọn chiến lược BM25, Vector,
                                      Hybrid và/hoặc Graph

  Hybrid Search                       Kết hợp BM25 và Vector Search, RRF
                                      và reranking

  Graph Retrieval                     Mở rộng kết quả dựa trên quan hệ
                                      pháp lý

  Retrieved Results                   Chuẩn hóa và tổng hợp kết quả từ
                                      các retriever

  Retrieval Evaluation Agent          Đánh giá relevance, độ bao phủ và
                                      mức đủ căn cứ

  Legal Context Builder               Tổ chức kết quả thành context có
                                      cấu trúc và nguồn

  LLM Answer Generation               Sinh câu trả lời dựa trên context

  Citation Verification               Kiểm tra citation có tồn tại và hỗ
                                      trợ nội dung trả lời

  Final Answer                        Trả lời cùng căn cứ pháp lý và
                                      nguồn trích dẫn
  -----------------------------------------------------------------------

### 1.2. Nguyên tắc luồng xử lý

1.  Data Pipeline chạy trước để thu thập, parse, chuẩn hóa, chunk,
    embedding và index văn bản.
2.  Khi có câu hỏi, Query Analyzer phân tích câu hỏi.
3.  Metadata Filtering tạo điều kiện lọc; retriever thực thi điều kiện
    đó trên database.
4.  Retrieval Router chọn chiến lược truy xuất.
5.  Hybrid Search và Graph Retrieval thực hiện truy xuất theo chiến
    lược.
6.  Result Aggregator chuẩn hóa và tổng hợp kết quả.
7.  Retrieval Evaluation Agent đánh giá kết quả.
8.  Nếu chưa đủ, Orchestrator quyết định refine query hoặc thay đổi
    strategy rồi gọi Retrieval Router lại.
9.  Nếu đủ, Legal Context Builder tạo context cho LLM.
10. LLM sinh câu trả lời và Citation Verifier kiểm tra nguồn.
11. Nếu không đủ căn cứ sau số vòng tối đa, hệ thống phải từ chối kết
    luận hoặc nêu rõ phần thông tin chưa xác minh; không được tự suy
    diễn.

------------------------------------------------------------------------

## 2. Phân công thành viên

### 2.1. Nguyễn Thành Luân 

**Phạm vi:** System Architecture, Retrieval System và System
Integration.

Nhiệm vụ:

-   Thiết kế kiến trúc tổng thể và quyết định interface.
-   Quản lý `core/schemas/`, `core/interfaces/` và cấu hình chung.
-   Thiết kế Metadata Filtering contract và tích hợp.
-   Implement Retrieval Router.
-   Implement BM25 Retriever.
-   Implement Dense / Vector Retriever.
-   Implement Hybrid Search.
-   Implement Reciprocal Rank Fusion (RRF).
-   Implement Cross-Encoder Reranking.
-   Implement Retrieval Result Aggregator.
-   Implement Legal Context Builder.
-   Implement Citation Verification.
-   Implement RAG Pipeline Orchestration.
-   Tích hợp API và infrastructure.
-   Review Pull Request, xử lý conflict và chịu trách nhiệm tích hợp
    cuối.

**Deliverables chính:**

-   `core/`
-   `src/preprocessing/`
-   `src/retrieval/`
-   `src/generation/context_builder.py`
-   `src/generation/citation_verifier.py`
-   `src/orchestration/`
-   `src/api/`
-   `src/infrastructure/` (phần tích hợp chung)

### 2.2. Nguyễn Trí Anh -- AI Agent Developer

**Phạm vi:** Query Understanding và Retrieval Evaluation.

Nhiệm vụ:

-   Query Analyzer Agent.
-   Intent Classification.
-   Entity Extraction.
-   Query Rewriting.
-   Metadata Extraction từ câu hỏi.
-   Retrieval Evaluation Agent.
-   Relevance Evaluation.
-   Missing Information Detection.
-   Query Refinement.
-   Evaluation Dataset và Benchmark.

**Deliverables chính:**

-   `src/query_understanding/`
-   `src/evaluation/`
-   Unit tests cho Query Understanding và Evaluation.

### 2.3. Nguyễn Đức Anh -- Data & Knowledge Graph Engineer

**Phạm vi:** Legal Data Engineering và Knowledge Graph.

Nhiệm vụ:

-   Thu thập dữ liệu pháp luật từ nguồn được phép sử dụng.
-   Document Loader cho PDF, DOCX, HTML.
-   Legal Document Parser.
-   Legal Metadata Extraction từ văn bản.
-   Legal / Hierarchical Chunking.
-   Embedding Pipeline.
-   Vector Database Indexing.
-   Knowledge Graph Construction.
-   Graph Schema và Graph Database.
-   Graph Retrieval.
-   Trích xuất quan hệ giữa văn bản, điều khoản và văn bản sửa đổi/bổ
    sung/thay thế.

**Deliverables chính:**

-   `src/data_pipeline/`
-   `src/knowledge_graph/`
-   Phần indexing và graph-store adapter được thống nhất với Technical
    Lead.
-   Unit tests cho parser, chunker và graph.

### 2.4. Trung -- LLM Developer

**Phạm vi:** Answer Generation và Prompt Engineering.

Nhiệm vụ:

-   LLM Integration theo interface chung.
-   Prompt Engineering cho Legal Answer Generation.
-   Structured Output.
-   Answer Formatting.
-   Disclaimer Generation.
-   Kiểm thử chất lượng câu trả lời trên bộ câu hỏi mẫu.

**Deliverables chính:**

-   `src/generation/answer_generator.py`
-   `src/generation/answer_formatter.py`
-   `prompts/answer_generation/`
-   Unit tests cho Answer Generation.

**Ranh giới trách nhiệm:** Trung nhận `LegalContext` đã được chuẩn hóa
và không phụ trách Retrieval Router, Data Pipeline, Citation
Verification hoặc Orchestration.

------------------------------------------------------------------------

## 3. Repository Structure

``` text
vietnamese-law-rag/
│
├── configs/
│   ├── config.yaml
│   ├── database.yaml
│   ├── retrieval.yaml
│   ├── embedding.yaml
│   └── llm.yaml
│
├── core/
│   ├── schemas/
│   │   ├── query.py
│   │   ├── metadata.py
│   │   ├── document.py
│   │   ├── retrieval.py
│   │   ├── evaluation.py
│   │   ├── context.py
│   │   └── answer.py
│   │
│   ├── interfaces/
│   │   ├── base_retriever.py
│   │   ├── base_embedding.py
│   │   ├── base_llm.py
│   │   └── base_evaluator.py
│   │
│   ├── exceptions.py
│   └── constants.py
│
├── src/
│   ├── query_understanding/
│   │   ├── query_analyzer.py
│   │   ├── query_rewriter.py
│   │   ├── intent_classifier.py
│   │   └── entity_extractor.py
│   │
│   ├── preprocessing/
│   │   ├── metadata_filter.py
│   │   └── filter_builder.py
│   │
│   ├── retrieval/
│   │   ├── router/
│   │   │   └── retrieval_router.py
│   │   ├── dense/
│   │   │   └── vector_retriever.py
│   │   ├── sparse/
│   │   │   └── bm25_retriever.py
│   │   ├── hybrid/
│   │   │   ├── hybrid_search.py
│   │   │   └── rrf.py
│   │   ├── reranking/
│   │   │   └── cross_encoder.py
│   │   ├── aggregation/
│   │   │   └── result_aggregator.py
│   │   └── base.py
│   │
│   ├── knowledge_graph/
│   │   ├── builder/
│   │   │   ├── graph_builder.py
│   │   │   └── relation_extractor.py
│   │   ├── retriever/
│   │   │   └── graph_retriever.py
│   │   └── graph_schema.py
│   │
│   ├── data_pipeline/
│   │   ├── loaders/
│   │   │   ├── pdf_loader.py
│   │   │   ├── docx_loader.py
│   │   │   └── html_loader.py
│   │   ├── parsers/
│   │   │   ├── legal_parser.py
│   │   │   └── metadata_extractor.py
│   │   ├── chunking/
│   │   │   ├── legal_chunker.py
│   │   │   └── hierarchical_chunker.py
│   │   ├── embedding/
│   │   │   └── embedding_pipeline.py
│   │   └── indexing/
│   │       ├── vector_indexer.py
│   │       └── graph_indexer.py
│   │
│   ├── evaluation/
│   │   ├── retrieval_evaluator.py
│   │   ├── evaluation_agent.py
│   │   ├── relevance_checker.py
│   │   └── metrics.py
│   │
│   ├── generation/
│   │   ├── context_builder.py
│   │   ├── answer_generator.py
│   │   ├── answer_formatter.py
│   │   └── citation_verifier.py
│   │
│   ├── orchestration/
│   │   ├── rag_pipeline.py
│   │   └── pipeline_factory.py
│   │
│   ├── infrastructure/
│   │   ├── vector_store/
│   │   │   └── pgvector_store.py
│   │   ├── graph_store/
│   │   │   └── neo4j_store.py
│   │   └── llm/
│   │       └── llm_factory.py
│   │
│   └── api/
│       ├── routes/
│       │   ├── query.py
│       │   └── health.py
│       ├── dependencies.py
│       └── main.py
│
├── prompts/
│   ├── query_analyzer/
│   │   └── system.txt
│   ├── retrieval_evaluator/
│   │   └── system.txt
│   └── answer_generation/
│       ├── system.txt
│       └── user.txt
│
├── data/
│   ├── raw/
│   ├── processed/
│   ├── chunks/
│   └── evaluation/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── notebooks/
│   ├── embedding_experiment.ipynb
│   ├── retrieval_experiment.ipynb
│   └── evaluation_experiment.ipynb
│
├── scripts/
│   ├── ingest_documents.py
│   ├── build_vector_index.py
│   └── build_knowledge_graph.py
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── INTERFACES.md
│   ├── DATABASE_SCHEMA.md
│   ├── API_SPECIFICATION.md
│   ├── CONTRIBUTING.md
│   └── TASK_ASSIGNMENT.md
│
├── migrations/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yaml
│
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```

### 3.1. Ý nghĩa các thư mục

  Thư mục                  Mục đích
  ------------------------ -------------------------------------------
  `core/`                  Schema, interface và constants dùng chung
  `configs/`               Cấu hình model, database và retrieval
  `query_understanding/`   Phân tích câu hỏi
  `preprocessing/`         Metadata Filtering
  `retrieval/`             Các thuật toán tìm kiếm
  `knowledge_graph/`       Xây dựng và truy vấn graph
  `data_pipeline/`         Thu thập và xử lý văn bản luật
  `evaluation/`            Đánh giá retrieval
  `generation/`            Context, LLM và citation
  `orchestration/`         Điều phối toàn bộ pipeline
  `infrastructure/`        Adapter kết nối database và model
  `api/`                   Backend API
  `prompts/`               Quản lý prompt riêng biệt
  `data/`                  Dữ liệu đầu vào, đầu ra và dataset
  `tests/`                 Unit, Integration và E2E tests
  `notebooks/`             Thử nghiệm thuật toán
  `docs/`                  Đặc tả và tài liệu kỹ thuật

### 3.2. Ownership

  Thư mục                             Owner            Reviewer
  ----------------------------------- ---------------- ----------
  `core/`                             Luân             Cả nhóm
  `configs/`                          Luân             Cả nhóm
  `query_understanding/`              Trí Anh          Luân
  `preprocessing/`                    Luân             Trí Anh
  `retrieval/`                        Luân             Trí Anh
  `knowledge_graph/`                  Đức Anh          Luân
  `data_pipeline/`                    Đức Anh          Luân
  `evaluation/`                       Trí Anh          Luân
  `generation/answer_generator.py`    Trung            Luân
  `generation/answer_formatter.py`    Trung            Luân
  `generation/context_builder.py`     Luân             Trung
  `generation/citation_verifier.py`   Luân             Trung
  `orchestration/`                    Luân             Cả nhóm
  `infrastructure/`                   Luân + Đức Anh   Luân
  `api/`                              Luân             Cả nhóm
  `prompts/`                          Theo module      Luân

Ownership thể hiện trách nhiệm chính, không cấm thành viên khác đóng
góp. Những thay đổi ảnh hưởng đến interface chung phải được thống nhất
trước.

------------------------------------------------------------------------

## 4. Shared Schemas -- Quy chuẩn dữ liệu

**Quy định:** Tất cả module sử dụng Pydantic v2. Không tự ý trả về
dictionary có cấu trúc tùy ý khi interface đã quy định schema.

**Contract đã triển khai:** Dùng schema tại `core/schemas/` và kế thừa
ABC tại `core/interfaces/`. Xem [docs/INTERFACES.md](INTERFACES.md)
cho mapping đầy đủ mục 4.1--4.9, validation, quy ước filter/feedback loop,
và ví dụ chạy độc lập tại `examples/contract_demo.py`.

### 4.1. Query Schemas

File: `core/schemas/query.py`

``` python
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str
    conversation_id: str | None = None


class QueryAnalysisResult(BaseModel):
    original_query: str
    rewritten_query: str
    intent: str
    entities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
```

**Ví dụ Input:**

``` json
{
  "query": "Nghỉ việc không báo trước có bị phạt không?",
  "conversation_id": null
}
```

**Ví dụ Output:**

``` json
{
  "original_query": "Nghỉ việc không báo trước có bị phạt không?",
  "rewritten_query": "Trách nhiệm pháp lý của người lao động khi đơn phương chấm dứt hợp đồng lao động không tuân thủ thời hạn báo trước",
  "intent": "legal_explanation",
  "entities": [
    "người lao động",
    "hợp đồng lao động"
  ],
  "keywords": [
    "nghỉ việc",
    "báo trước",
    "trách nhiệm pháp lý"
  ],
  "metadata": {
    "legal_domain": ["labor"],
    "document_type": ["law", "decree"]
  }
}
```

**Function Contract:**

``` python
class QueryAnalyzer:

    def analyze(
        self,
        request: QueryRequest
    ) -> QueryAnalysisResult:
        ...
```

### 4.2. Metadata Filter Schemas

File: `core/schemas/metadata.py`

``` python
from pydantic import BaseModel, Field


class MetadataFilterRequest(BaseModel):
    metadata: dict = Field(default_factory=dict)


class MetadataFilterResult(BaseModel):
    filters: dict = Field(default_factory=dict)
    applied_filters: list[str] = Field(default_factory=list)
```

**Function Contract:**

``` python
class MetadataFilter:

    def build_filters(
        self,
        request: MetadataFilterRequest
    ) -> MetadataFilterResult:
        ...
```

Metadata Filtering chỉ tạo điều kiện lọc. Retriever chịu trách nhiệm
thực thi điều kiện đó trên database.

### 4.3. Legal Document Schemas

File: `core/schemas/document.py`

``` python
from pydantic import BaseModel, Field


class LegalMetadata(BaseModel):
    document_id: str
    title: str
    document_number: str
    document_type: str

    issuing_authority: str | None = None

    issued_date: str | None = None
    effective_date: str | None = None
    expiry_date: str | None = None

    status: str = "unknown"
    legal_domain: list[str] = Field(default_factory=list)

    amended_by: list[str] = Field(default_factory=list)
    replaced_by: list[str] = Field(default_factory=list)
    repealed_by: list[str] = Field(default_factory=list)
    related_documents: list[str] = Field(default_factory=list)


class LegalDocument(BaseModel):
    document_id: str
    content: str
    metadata: LegalMetadata


class LegalChunk(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    metadata: LegalMetadata

    chapter: str | None = None
    article: str | None = None
    clause: str | None = None
    point: str | None = None

    parent_id: str | None = None
    embedding: list[float] | None = None
```

**Lưu ý về pháp luật:** Không được xác định hiệu lực chỉ dựa trên một
trường `status` tĩnh. Cần xét thời điểm truy vấn, hiệu lực theo thời
gian, văn bản sửa đổi/bổ sung/thay thế/bãi bỏ và phạm vi hiệu lực của
từng quy định.

### 4.4. Retrieval Schemas

File: `core/schemas/retrieval.py`

``` python
from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    query: str
    filters: dict = Field(default_factory=dict)

    top_k: int = 5
    candidate_k: int = 20


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    content: str

    score: float
    retrieval_method: str

    metadata: dict = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    query: str
    results: list[RetrievedChunk] = Field(default_factory=list)
    relations: list[dict] = Field(default_factory=list)
    total_candidates: int = 0
```

**Function Contract:**

``` python
class HybridSearch:

    def search(
        self,
        request: RetrievalRequest
    ) -> list[RetrievedChunk]:
        ...
```

### 4.5. Retrieval Strategy Schema

File: `core/schemas/retrieval.py`

``` python
class RetrievalRouteRequest(BaseModel):
    query: str
    intent: str

    filters: dict = Field(default_factory=dict)
    entities: list[str] = Field(default_factory=list)


class RetrievalStrategy(BaseModel):
    use_bm25: bool = True
    use_vector: bool = True
    use_graph: bool = False
    use_rerank: bool = True

    top_k: int = 5
    candidate_k: int = 20

    reason: str
```

**Function Contract:**

``` python
class RetrievalRouter:

    def route(
        self,
        request: RetrievalRouteRequest
    ) -> RetrievalStrategy:
        ...
```

Trí Anh có thể đề xuất logic phân loại intent và đặc trưng query; Luân
chịu trách nhiệm implement và tích hợp Router với các Retriever.

### 4.6. Graph Retrieval Schemas

File: `core/schemas/retrieval.py`

``` python
class GraphRetrievalRequest(BaseModel):
    query: str

    entities: list[str] = Field(default_factory=list)
    seed_document_ids: list[str] = Field(default_factory=list)

    max_depth: int = 2


class GraphRetrievalResult(BaseModel):
    results: list[RetrievedChunk] = Field(default_factory=list)

    relations: list[dict] = Field(default_factory=list)
    related_document_ids: list[str] = Field(default_factory=list)
```

**Function Contract:**

``` python
class GraphRetriever:

    def search(
        self,
        request: GraphRetrievalRequest
    ) -> GraphRetrievalResult:
        ...
```

Đức Anh implement Graph Builder và Graph Retriever. Luân tích hợp kết
quả Graph Retrieval vào Retrieval Layer.

### 4.7. Retrieval Evaluation Schemas

File: `core/schemas/evaluation.py`

``` python
from pydantic import BaseModel, Field


class RetrievalEvaluationRequest(BaseModel):
    original_query: str
    current_query: str

    retrieval_result: RetrievalResult

    iteration: int = 0
    max_iterations: int = 3


class RetrievalEvaluationResult(BaseModel):
    is_relevant: bool
    is_sufficient: bool

    confidence: float

    missing_information: list[str] = Field(default_factory=list)

    next_action: str
    # continue, refine_query, change_strategy, stop

    refined_query: str | None = None

    strategy_override: dict = Field(default_factory=dict)
    reason: str
```

**Function Contract:**

``` python
class RetrievalEvaluator:

    def evaluate(
        self,
        request: RetrievalEvaluationRequest
    ) -> RetrievalEvaluationResult:
        ...
```

Trí Anh phụ trách logic đánh giá và refinement. Trung tâm Orchestrator
(Luân) quyết định gọi lại retrieval theo kết quả đánh giá.

### 4.8. Legal Context Schemas

File: `core/schemas/context.py`

``` python
from pydantic import BaseModel, Field


class ContextBuilderRequest(BaseModel):
    retrieval_result: RetrievalResult
    original_query: str


class LegalContext(BaseModel):
    query: str
    context_text: str

    chunks: list[RetrievedChunk] = Field(default_factory=list)
    cited_document_ids: list[str] = Field(default_factory=list)
```

**Function Contract:**

``` python
class LegalContextBuilder:

    def build(
        self,
        request: ContextBuilderRequest
    ) -> LegalContext:
        ...
```

### 4.9. Answer Schemas

File: `core/schemas/answer.py`

``` python
from pydantic import BaseModel, Field


class AnswerGenerationRequest(BaseModel):
    context: LegalContext
    query: str


class LegalCitation(BaseModel):
    document_id: str
    document_number: str

    article: str | None = None
    clause: str | None = None
    point: str | None = None

    quoted_text: str
    source_url: str | None = None


class LegalAnswer(BaseModel):
    answer: str
    citations: list[LegalCitation] = Field(default_factory=list)

    confidence: float
    disclaimer: str | None = None
```

**Function Contract:**

``` python
class AnswerGenerator:

    def generate(
        self,
        request: AnswerGenerationRequest
    ) -> LegalAnswer:
        ...
```

Citation Verification do Luân phụ trách:

``` python
class CitationVerifier:

    def verify(
        self,
        answer: LegalAnswer,
        context: LegalContext
    ) -> LegalAnswer:
        ...
```

------------------------------------------------------------------------

## 5. Module Contracts -- Input/Output Summary

  ------------------------------------------------------------------------------------------------
  Module            Input                          Output                        Owner
  ----------------- ------------------------------ ----------------------------- -----------------
  Query Analyzer    `QueryRequest`                 `QueryAnalysisResult`         Trí Anh

  Query Rewriter    Query / Analysis               Rewritten query               Trí Anh

  Metadata Filter   `MetadataFilterRequest`        `MetadataFilterResult`        Luân

  Retrieval Router  `RetrievalRouteRequest`        `RetrievalStrategy`           Luân

  BM25 Retriever    `RetrievalRequest`             `list[RetrievedChunk]`        Luân

  Vector Retriever  `RetrievalRequest`             `list[RetrievedChunk]`        Luân

  Hybrid Search     `RetrievalRequest`             `list[RetrievedChunk]`        Luân

  Reranker          Query + chunks                 Ranked chunks                 Luân

  Graph Builder     Legal documents                Graph build result            Đức Anh

  Graph Retriever   `GraphRetrievalRequest`        `GraphRetrievalResult`        Đức Anh

  Result Aggregator Hybrid + Graph results         `RetrievalResult`             Luân

  Retrieval         `RetrievalEvaluationRequest`   `RetrievalEvaluationResult`   Trí Anh
  Evaluator                                                                      

  Context Builder   `ContextBuilderRequest`        `LegalContext`                Luân

  Answer Generator  `AnswerGenerationRequest`      `LegalAnswer`                 Trung

  Citation Verifier Answer + context               Verified answer               Luân

  RAG Orchestrator  `QueryRequest`                 `LegalAnswer`                 Luân
  ------------------------------------------------------------------------------------------------

**Quy tắc:** Khi thay đổi Input/Output, owner phải cập nhật schema,
`docs/INTERFACES.md`, test liên quan và thông báo cho các module phụ
thuộc.

------------------------------------------------------------------------

## 6. RAG Orchestration -- Feedback Loop

File: `src/orchestration/rag_pipeline.py`

Orchestrator chịu trách nhiệm điều phối, không để Evaluation Agent tự
gọi Retriever.

Pseudo-code:

``` python
def run_rag(query: str):

    # 1. Analyze query
    analyzed = query_analyzer.analyze(
        QueryRequest(query=query)
    )

    current_query = analyzed.rewritten_query
    strategy_override = {}

    max_iterations = 3

    # 2. Retrieval and evaluation loop
    for iteration in range(max_iterations):

        route_request = RetrievalRouteRequest(
            query=current_query,
            intent=analyzed.intent,
            filters=analyzed.metadata,
            entities=analyzed.entities
        )

        strategy = retrieval_router.route(route_request)

        if strategy_override:
            strategy = apply_strategy_override(
                strategy,
                strategy_override
            )

        retrieval_result = retrieval_service.retrieve(
            query=current_query,
            filters=analyzed.metadata,
            strategy=strategy
        )

        evaluation = retrieval_evaluator.evaluate(
            RetrievalEvaluationRequest(
                original_query=query,
                current_query=current_query,
                retrieval_result=retrieval_result,
                iteration=iteration,
                max_iterations=max_iterations
            )
        )

        if evaluation.is_sufficient:
            break

        if iteration == max_iterations - 1:
            return build_insufficient_evidence_response(
                query,
                evaluation
            )

        if evaluation.next_action == "refine_query":
            current_query = (
                evaluation.refined_query or current_query
            )

        elif evaluation.next_action == "change_strategy":
            strategy_override = evaluation.strategy_override

        elif evaluation.next_action == "stop":
            return build_insufficient_evidence_response(
                query,
                evaluation
            )

    # 3. Build legal context
    context = context_builder.build(
        ContextBuilderRequest(
            retrieval_result=retrieval_result,
            original_query=query
        )
    )

    # 4. Generate answer
    answer = answer_generator.generate(
        AnswerGenerationRequest(
            context=context,
            query=query
        )
    )

    # 5. Verify citations
    verified_answer = citation_verifier.verify(
        answer,
        context
    )

    return verified_answer
```

**Yêu cầu bắt buộc:**

-   Giới hạn số vòng retrieval.
-   Lưu lại query, strategy, kết quả và lý do evaluation của từng vòng.
-   Không tiếp tục generation khi không đủ căn cứ.
-   Có fallback khi retriever hoặc LLM lỗi.
-   Không nhầm retrieval score với answer confidence.
-   Citation phải truy nguyên được về chunk và văn bản nguồn.

------------------------------------------------------------------------

## 7. GitHub Workflow

### 7.1. Branch Strategy

``` text
main
  |
  └── develop
        |
        ├── feature/query-analyzer
        ├── feature/hybrid-search
        ├── feature/legal-parser
        ├── feature/graph-retrieval
        ├── feature/answer-generator
        └── feature/rag-pipeline
```

Quy định:

-   `main`: phiên bản ổn định.
-   `develop`: nhánh tích hợp.
-   `feature/*`: mỗi chức năng một nhánh.
-   Không commit trực tiếp vào `main`.
-   PR vào `develop` phải có test và mô tả.
-   PR thay đổi `core/schemas/` cần Luân review.
-   PR thay đổi module phải được owner hoặc reviewer phù hợp xem xét.

### 7.2. Naming Convention

  Loại             Quy ước            Ví dụ
  ---------------- ------------------ ----------------------------------
  Feature branch   `feature/<name>`   `feature/hybrid-search`
  Bug fix          `fix/<name>`       `fix/legal-parser`
  Commit           `feat:`            `feat: implement BM25 retriever`
  Commit           `fix:`             `fix: handle empty retrieval`
  Commit           `test:`            `test: add retrieval unit tests`
  Commit           `refactor:`        `refactor: update query schema`
  Commit           `docs:`            `docs: update architecture`

### 7.3. Pull Request Template

Tạo file `.github/pull_request_template.md`:

``` markdown
## Summary
Mô tả ngắn gọn chức năng đã thực hiện.

## Related Issue
Closes #<issue-number>

## Module
- [ ] Query Understanding
- [ ] Retrieval
- [ ] Knowledge Graph
- [ ] Data Pipeline
- [ ] Evaluation
- [ ] Generation
- [ ] Orchestration
- [ ] Infrastructure / API

## Input / Output
Mô tả schema đầu vào và đầu ra.

## Implementation
Mô tả cách triển khai.

## Tests
- [ ] Unit tests
- [ ] Edge cases
- [ ] Integration tests (nếu cần)

## Interface Changes
- [ ] Không thay đổi interface
- [ ] Có thay đổi interface và đã cập nhật schema/docs

## Checklist
- [ ] Code đúng convention
- [ ] Không commit `.env` hoặc secret
- [ ] Đã cập nhật README/docs nếu cần
- [ ] Đã chạy tests
```

### 7.4. Issue Template

Mỗi GitHub Issue cần có:

``` markdown
# [FEATURE] Tên chức năng

## Assignee
Tên thành viên phụ trách.

## Description
Mục tiêu chức năng.

## Input
Schema đầu vào.

## Output
Schema đầu ra.

## Dependencies
Các module hoặc schema cần có.

## Acceptance Criteria
- [ ] Đúng function signature.
- [ ] Đúng output schema.
- [ ] Xử lý input rỗng.
- [ ] Xử lý lỗi.
- [ ] Có unit tests.
- [ ] Có hướng dẫn sử dụng.

## Notes
Các lưu ý kỹ thuật.
```

------------------------------------------------------------------------

## 8. GitHub Milestones & Task Assignment

### Milestone 1 -- Foundation & Architecture

**Luân** - \[ \] Define System Architecture. - \[ \] Define Core
Pydantic Schemas. - \[ \] Define Module Interfaces. - \[ \] Setup
Repository & Development Environment.

**Trí Anh** - \[ \] Implement Query Analyzer. - \[ \] Implement Entity
Extraction.

**Đức Anh** - \[ \] Implement Legal Document Loader. - \[ \] Implement
Legal Document Parser.

**Trung** - \[ \] Research LLM options. - \[ \] Prepare initial Answer
Generation prompt templates.

### Milestone 2 -- Core Components

**Luân** - \[ \] Implement BM25 Retriever. - \[ \] Implement Dense
Retriever. - \[ \] Implement Hybrid Search. - \[ \] Implement RRF. - \[
\] Implement Cross-Encoder Reranker.

**Trí Anh** - \[ \] Implement Metadata Extraction from Query. - \[ \]
Implement Retrieval Evaluation Agent. - \[ \] Implement Missing
Information Detection.

**Đức Anh** - \[ \] Implement Legal Chunker. - \[ \] Implement Embedding
Pipeline. - \[ \] Implement Knowledge Graph Builder.

**Trung** - \[ \] Implement Answer Generator. - \[ \] Implement
Structured Output. - \[ \] Implement Answer Formatting.

### Milestone 3 -- Advanced Retrieval & Integration

**Luân** - \[ \] Implement Metadata Filtering. - \[ \] Implement
Retrieval Router. - \[ \] Implement Result Aggregator. - \[ \] Implement
Legal Context Builder. - \[ \] Implement Citation Verification.

**Trí Anh** - \[ \] Implement Query Refinement. - \[ \] Implement
Evaluation Metrics. - \[ \] Build Retrieval Evaluation Dataset.

**Đức Anh** - \[ \] Implement Graph Retriever. - \[ \] Implement Legal
Document Relations. - \[ \] Validate Graph Data.

**Trung** - \[ \] Improve Answer Prompts. - \[ \] Test Answer Quality. -
\[ \] Handle Answer Formatting Edge Cases.

### Milestone 4 -- Complete RAG Pipeline

**Luân** - \[ \] Implement RAG Orchestration. - \[ \] Integrate API. -
\[ \] Integration Testing. - \[ \] Review all module contracts.

**Trí Anh** - \[ \] Retrieval Benchmark. - \[ \] Evaluate Query Analyzer
and Evaluation Agent.

**Đức Anh** - \[ \] Validate Legal Data. - \[ \] Validate Vector and
Graph Indexing.

**Trung** - \[ \] Answer Quality Testing. - \[ \] Prepare example
questions and expected answer format.

**Cả nhóm** - \[ \] End-to-End Testing. - \[ \] Bug Fixing. - \[ \]
Documentation. - \[ \] Demo Preparation.

------------------------------------------------------------------------

## 9. Development Phases

  -----------------------------------------------------------------------
  Phase                   Trọng tâm               Kết quả
  ----------------------- ----------------------- -----------------------
  Phase 1                 Architecture, schemas,  Interface thống nhất
                          repository, mock data   

  Phase 2                 Phát triển các module   Module chạy được riêng
                          độc lập                 

  Phase 3                 Retrieval, Graph,       Retrieval Layer hoàn
                          Evaluation              chỉnh

  Phase 4                 Context, Generation,    Answer pipeline
                          Citation                

  Phase 5                 Orchestration, API,     RAG MVP
                          integration             

  Phase 6                 Benchmark, E2E, tối ưu  Phiên bản demo hoàn
                                                  chỉnh
  -----------------------------------------------------------------------

### Quy tắc phát triển song song

Không cần chờ module upstream hoàn thành toàn bộ mới code module
downstream.

Ví dụ:

-   Đức Anh cung cấp 5--10 LegalChunk mẫu đúng schema.
-   Luân dùng mock chunks để phát triển Dense Search và BM25.
-   Trung dùng mock LegalContext để phát triển Answer Generator.
-   Trí Anh dùng mock RetrievalResult để phát triển Evaluation Agent.

Khi module thật hoàn thành, thay mock implementation bằng implementation
thực tế mà không đổi contract nếu không cần thiết.

------------------------------------------------------------------------

## 10. Definition of Done

Một module chỉ được xem là hoàn thành khi đáp ứng:

  -----------------------------------------------------------------------
  Tiêu chí                            Yêu cầu
  ----------------------------------- -----------------------------------
  Interface                           Đúng Input/Output đã thống nhất

  Implementation                      Có logic thực tế, không còn hàm
                                      chính ở dạng placeholder

  Validation                          Kiểm tra input bằng Pydantic

  Error Handling                      Xử lý input rỗng, dữ liệu sai và
                                      lỗi phụ thuộc

  Unit Test                           Có test happy path và edge cases

  Documentation                       Có docstring và hướng dẫn sử dụng

  Integration                         Có thể gọi từ module phụ thuộc

  GitHub                              Có PR và được review
  -----------------------------------------------------------------------

### Ví dụ Acceptance Criteria -- Hybrid Search

-   [ ] Dense Retriever hoạt động.
-   [ ] BM25 Retriever hoạt động.
-   [ ] RRF hợp nhất kết quả.
-   [ ] Không trả về chunk trùng lặp.
-   [ ] Reranker sắp xếp kết quả.
-   [ ] Output đúng schema.
-   [ ] Xử lý được trường hợp một retriever trả về danh sách rỗng.
-   [ ] Có unit tests.

------------------------------------------------------------------------

## 11. Technical Decisions -- Công nghệ đề xuất

  Thành phần         Đề xuất ban đầu
  ------------------ ------------------------------
  Language           Python
  Backend            FastAPI
  Validation         Pydantic v2
  Vector Database    PostgreSQL + pgvector
  Graph Database     Neo4j
  Sparse Retrieval   BM25
  Hybrid Fusion      Reciprocal Rank Fusion
  Reranker           Cross-Encoder
  Embedding          Multilingual embedding model
  LLM                Gemini hoặc OpenAI
  Testing            Pytest
  Containerization   Docker
  Version Control    GitHub

Đây là baseline để nhóm thảo luận và chốt. Không nên coi các công nghệ
trên là quyết định không thể thay đổi trước khi benchmark và kiểm tra
môi trường triển khai.

### Một số quyết định kỹ thuật bắt buộc

1.  Chọn embedding model và embedding dimension.
2.  Chốt Vector Database và cách lưu metadata.
3.  Chốt Graph Database và graph schema.
4.  Chọn Cross-Encoder Reranker.
5.  Chọn LLM và structured output strategy.
6.  Chốt cách xác định hiệu lực pháp luật theo thời điểm truy vấn.

------------------------------------------------------------------------

## 12. Các nguyên tắc kỹ thuật quan trọng

### 12.1. Schema-first Development

Định nghĩa schema trước khi triển khai module. Mọi thành viên phải sử
dụng chung schema.

### 12.2. Contract-first Development

Mỗi module phải có:

-   Function signature.
-   Input schema.
-   Output schema.
-   Dependency.
-   Error handling.
-   Acceptance criteria.

### 12.3. Integration-first Development

Tích hợp liên tục, không đợi tất cả module hoàn thành mới ghép.

### 12.4. Tách Retrieval Logic khỏi Database Adapter

Ví dụ:

-   `retrieval/dense/vector_retriever.py`: logic truy xuất vector.
-   `infrastructure/vector_store/pgvector_store.py`: giao tiếp
    PostgreSQL + pgvector.

Nếu thay database, không phải viết lại toàn bộ retrieval logic.

### 12.5. Không đánh đồng Score và Confidence

-   Retrieval score: điểm thuật toán tìm kiếm.
-   Evaluation confidence: mức độ tin cậy của đánh giá retrieval.
-   Answer confidence: mức độ tin cậy của câu trả lời, nếu hệ thống có
    cơ chế hiệu chỉnh phù hợp.

Không sử dụng trực tiếp các score có thang đo khác nhau để so sánh.

### 12.6. Legal Traceability

Mỗi câu trả lời phải truy nguyên được về:

-   Văn bản pháp luật.
-   Số hiệu văn bản.
-   Điều, khoản, điểm.
-   Nội dung nguồn.
-   URL hoặc định danh nguồn.
-   Thông tin hiệu lực tại thời điểm được hỏi, nếu có đủ dữ liệu xác
    minh.

Không để LLM tự tạo số hiệu văn bản hoặc citation.

------------------------------------------------------------------------

## 13. Checklist cho buổi Kickoff

-   [ ] Chốt kiến trúc tổng thể theo pipeline.
-   [ ] Chốt phân công 4 thành viên.
-   [ ] Chốt schema dùng chung.
-   [ ] Chốt công nghệ và database.
-   [ ] Tạo GitHub repository.
-   [ ] Thiết lập `main` và `develop`.
-   [ ] Thiết lập branch protection.
-   [ ] Tạo GitHub Milestones.
-   [ ] Tạo Issues cho từng module.
-   [ ] Tạo mock LegalChunk và RetrievalResult.
-   [ ] Chốt coding convention.
-   [ ] Chốt cách review và merge PR.

------------------------------------------------------------------------

## 14. Kết luận

Mục tiêu của cách tổ chức này là để 4 thành viên có thể phát triển độc
lập nhưng vẫn đảm bảo toàn bộ module giao tiếp được với nhau.

**Vai trò của Team Lead**

1.  Định hướng kiến trúc và công nghệ.
2.  Kiểm soát schema và interface.
3.  Phát triển Retrieval System cốt lõi.
4.  Tích hợp Feedback Loop và toàn bộ RAG Pipeline.
5.  Review code và đảm bảo chất lượng hệ thống.

**Nguyên tắc chung:** Mỗi thành viên sở hữu module của mình, chịu trách
nhiệm implementation và unit test. Team Lead chịu trách nhiệm về tính
nhất quán kiến trúc và kết quả tích hợp cuối cùng.

Tài liệu này là bản đặc tả và kế hoạch làm việc ban đầu. Các schema và
function signature cần được cập nhật đồng bộ trong quá trình triển khai
nếu nhóm có quyết định kỹ thuật mới.
