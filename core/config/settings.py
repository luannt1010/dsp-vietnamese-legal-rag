"""Validated configuration shared by module constructors and orchestration."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from core.exceptions import ConfigurationError
from core.schemas.base import NonEmptyString, NonNegativeInt, PositiveInt
from core.schemas.retrieval import RetrievalStrategy


PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class ConfigModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_default=True,
        hide_input_in_errors=True, allow_inf_nan=False,
    )

    @field_validator("*")
    @classmethod
    def reject_blank_secrets(cls, value):
        if isinstance(value, SecretStr) and not value.get_secret_value().strip():
            raise ValueError("secret must not be blank")
        return value


class AppSettings(ConfigModel):
    environment: Literal["development", "test", "production"] = "development"


class APISettings(ConfigModel):
    host: NonEmptyString = "127.0.0.1"
    port: Annotated[int, Field(strict=True, ge=1, le=65535)] = 8000
    cors_origins: tuple[str, ...] = ()


class LoggingSettings(ConfigModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["text", "json"] = "text"
    log_query_text: bool = False
    log_context_text: bool = False


class PipelineSettings(ConfigModel):
    max_iterations: PositiveInt = 3
    timeout_s: PositiveFloat = 90.0


class ContextSettings(ConfigModel):
    max_context_tokens: PositiveInt = 4096
    prompt_reserve_tokens: PositiveInt = 1024


class BM25Settings(ConfigModel):
    k1: Annotated[float, Field(gt=0)] = 1.2
    b: Annotated[float, Field(ge=0, le=1)] = 0.75
    tokenizer: NonEmptyString = "whitespace"
    lowercase: bool = True


class RRFSettings(ConfigModel):
    rank_constant: PositiveInt = 60


class RerankerSettings(ConfigModel):
    backend: Literal["sentence_transformers", "onnx"] = "sentence_transformers"
    model: NonEmptyString | None = None
    revision: NonEmptyString | None = None
    batch_size: PositiveInt = 16
    max_input_tokens: PositiveInt = 512
    device: Literal["auto", "cpu", "cuda"] = "auto"
    file_name: NonEmptyString = "onnx/model_quint8_avx2.onnx"


class GraphSettings(ConfigModel):
    max_depth: PositiveInt = 2
    max_nodes: PositiveInt = 100


class RetrievalSettings(ConfigModel):
    use_bm25: bool = True
    use_vector: bool = True
    use_graph: bool = False
    use_rerank: bool = True
    top_k: PositiveInt = 5
    candidate_k: PositiveInt = 20
    max_top_k: PositiveInt = 20
    max_candidate_k: PositiveInt = 100
    timeout_s: PositiveFloat = 10.0
    bm25: BM25Settings = Field(default_factory=BM25Settings)
    rrf: RRFSettings = Field(default_factory=RRFSettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    graph: GraphSettings = Field(default_factory=GraphSettings)

    @model_validator(mode="after")
    def check_limits(self) -> "RetrievalSettings":
        if not (self.use_bm25 or self.use_vector or self.use_graph):
            raise ValueError("at least one retrieval method must be enabled")
        if not self.top_k <= self.candidate_k <= self.max_candidate_k:
            raise ValueError("require top_k <= candidate_k <= max_candidate_k")
        if not self.top_k <= self.max_top_k <= self.max_candidate_k:
            raise ValueError("require top_k <= max_top_k <= max_candidate_k")
        return self

    def default_strategy(self) -> RetrievalStrategy:
        """Build the router's baseline; schema defaults are not runtime config."""
        return RetrievalStrategy(
            use_bm25=self.use_bm25, use_vector=self.use_vector,
            use_graph=self.use_graph, use_rerank=self.use_rerank,
            top_k=self.top_k, candidate_k=self.candidate_k,
            reason="Configured retrieval defaults",
        )

    def validate_strategy(self, strategy: RetrievalStrategy) -> RetrievalStrategy:
        """Apply hard limits after the router or evaluator changes a strategy."""
        validated = RetrievalStrategy.model_validate(strategy.model_dump())
        if validated.top_k > self.max_top_k:
            raise ValueError("strategy.top_k exceeds configured max_top_k")
        if validated.candidate_k > self.max_candidate_k:
            raise ValueError("strategy.candidate_k exceeds configured max_candidate_k")
        return validated


class EmbeddingSettings(ConfigModel):
    provider: Literal["local", "openai", "gemini", "ollama"] | None = None
    base_url: NonEmptyString = "http://localhost:11434"
    model: NonEmptyString | None = None
    revision: NonEmptyString | None = None
    dimension: PositiveInt | None = None
    normalize: bool = True
    batch_size: PositiveInt = 32
    device: Literal["auto", "cpu", "cuda"] = "auto"
    timeout_s: PositiveFloat = 30.0
    max_retries: NonNegativeInt = 2
    tokenizer_model: NonEmptyString | None = None
    tokenizer_revision: NonEmptyString | None = None
    api_key: SecretStr | None = None


class LLMRoleSettings(ConfigModel):
    model: NonEmptyString | None = None
    context_window_tokens: PositiveInt | None = None
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.0
    max_output_tokens: PositiveInt = 2048
    prompt_version: NonEmptyString = "v1"
    tokenizer_model: NonEmptyString | None = None
    tokenizer_revision: NonEmptyString | None = None
    prompt_overhead_tokens: NonNegativeInt = 128


class LLMSettings(ConfigModel):
    provider: Literal["local", "openai", "gemini", "ollama"] | None = None
    base_url: NonEmptyString | None = None
    api_key: SecretStr | None = None
    timeout_s: PositiveFloat = 30.0
    max_retries: NonNegativeInt = 2
    retry_backoff_s: PositiveFloat = 1.0
    keep_alive: NonEmptyString = "1m"
    think: bool = False
    query_analyzer: LLMRoleSettings = Field(
        default_factory=lambda: LLMRoleSettings(max_output_tokens=512),
    )
    retrieval_evaluator: LLMRoleSettings = Field(
        default_factory=lambda: LLMRoleSettings(max_output_tokens=768),
    )
    answer_generator: LLMRoleSettings = Field(default_factory=LLMRoleSettings)
    citation_verifier: LLMRoleSettings = Field(
        default_factory=lambda: LLMRoleSettings(max_output_tokens=512),
    )


class VectorDatabaseSettings(ConfigModel):
    backend: Literal["in_memory", "pgvector"] = "in_memory"
    index_type: Literal["exact", "hnsw", "ivfflat"] = "hnsw"
    host: NonEmptyString = "localhost"
    port: Annotated[int, Field(strict=True, ge=1, le=65535)] = 5432
    database: NonEmptyString = "legal_rag"
    username: NonEmptyString = "rag"
    password: SecretStr | None = None
    schema_name: NonEmptyString = "public"
    table_name: NonEmptyString = "legal_chunks"
    distance_metric: Literal["cosine", "inner_product", "l2"] = "cosine"
    pool_size: PositiveInt = 5
    connect_timeout_s: PositiveFloat = 5.0
    ef_search: PositiveInt = 100
    hnsw_m: PositiveInt = 16
    ef_construction: PositiveInt = 128
    ivfflat_lists: PositiveInt = 10
    ivfflat_probes: PositiveInt = 3


class GraphDatabaseSettings(ConfigModel):
    backend: Literal["in_memory", "neo4j"] = "in_memory"
    namespace: NonEmptyString = "legal_rag"
    uri: NonEmptyString = "bolt://localhost:7687"
    database: NonEmptyString = "neo4j"
    username: NonEmptyString = "neo4j"
    password: SecretStr | None = None
    pool_size: PositiveInt = 5
    connect_timeout_s: PositiveFloat = 5.0


class DatabaseSettings(ConfigModel):
    vector: VectorDatabaseSettings = Field(default_factory=VectorDatabaseSettings)
    graph: GraphDatabaseSettings = Field(default_factory=GraphDatabaseSettings)


class ChunkingSettings(ConfigModel):
    strategy: Literal["fixed", "legal", "hierarchical"] = "hierarchical"
    tokenizer_model: NonEmptyString | None = None
    tokenizer_revision: NonEmptyString | None = None
    target_tokens: PositiveInt = 512
    overlap_tokens: NonNegativeInt = 64

    @model_validator(mode="after")
    def check_overlap(self) -> "ChunkingSettings":
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be less than target_tokens")
        return self


class DataSourceSettings(ConfigModel):
    type: Literal["json", "huggingface"] = "json"
    dataset: NonEmptyString = "tmquan/phapdien-moj-gov-vn"
    config: Literal["documents"] = "documents"
    split: Literal["train"] = "train"
    revision: NonEmptyString = "main"
    topics: tuple[NonEmptyString, ...] = ()
    subjects: tuple[NonEmptyString, ...] = ()
    read_batch_size: PositiveInt = 512


class DataPipelineSettings(ConfigModel):
    source: DataSourceSettings = Field(default_factory=DataSourceSettings)
    auto_prepare: bool = False
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    chunks_dir: Path = Path("data/chunks")
    indexing_batch_size: PositiveInt = 100
    source_chunks_file: Path = Path("data/chunks/phapdien_chunks.json")
    relations_file: Path = Path("data/processed/phapdien_relations.json")
    index_dir: Path = Path("data/runtime")
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)


class Settings(ConfigModel):
    app: AppSettings = Field(default_factory=AppSettings)
    api: APISettings = Field(default_factory=APISettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    data_pipeline: DataPipelineSettings = Field(default_factory=DataPipelineSettings)

    @model_validator(mode="after")
    def check_budgets(self) -> "Settings":
        if self.retrieval.timeout_s > self.pipeline.timeout_s:
            raise ValueError("retrieval.timeout_s must not exceed pipeline.timeout_s")
        for config in (self.llm, self.embedding):
            if config.timeout_s > self.pipeline.timeout_s:
                raise ValueError("provider timeout_s must not exceed pipeline.timeout_s")
        role = self.llm.answer_generator
        required = (
            self.context.max_context_tokens + self.context.prompt_reserve_tokens
            + role.max_output_tokens
        )
        if role.context_window_tokens is not None and required > role.context_window_tokens:
            raise ValueError("answer model context window is smaller than configured token budgets")
        for role in (self.llm.query_analyzer, self.llm.retrieval_evaluator, role, self.llm.citation_verifier):
            if role.context_window_tokens is not None and role.max_output_tokens >= role.context_window_tokens:
                raise ValueError("max_output_tokens must be less than the model context window")
        return self

    def validate_runtime(
        self, *, purpose: Literal["query", "ingestion"] = "query",
        strategy: RetrievalStrategy | None = None,
    ) -> None:
        """Check required selections before constructing real service adapters.

        Does not contact services or verify model capabilities/credentials.
        Mock development only needs load_settings(), not this readiness check.
        """
        if purpose not in ("query", "ingestion"):
            raise ValueError("purpose must be query or ingestion")
        selected = self.retrieval.validate_strategy(strategy or self.retrieval.default_strategy())
        missing = []
        if selected.use_vector or purpose == "ingestion":
            for name in ("provider", "model", "dimension"):
                if getattr(self.embedding, name) is None:
                    missing.append(f"embedding.{name}")
            if self.embedding.provider in ("openai", "gemini") and not self.embedding.api_key:
                missing.append("embedding.api_key")
        if purpose == "ingestion":
            if not self.data_pipeline.chunking.tokenizer_model:
                missing.append("data_pipeline.chunking.tokenizer_model")
        else:
            if self.llm.provider is None:
                missing.append("llm.provider")
            if self.llm.provider in ("openai", "gemini") and not self.llm.api_key:
                missing.append("llm.api_key")
            for name in ("query_analyzer", "retrieval_evaluator", "answer_generator", "citation_verifier"):
                role = getattr(self.llm, name)
                for field in ("model", "context_window_tokens"):
                    if getattr(role, field) is None:
                        missing.append(f"llm.{name}.{field}")
            if selected.use_rerank and not self.retrieval.reranker.model:
                missing.append("retrieval.reranker.model")
        if missing:
            raise ConfigurationError("Missing runtime configuration: " + ", ".join(missing))
