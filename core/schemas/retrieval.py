"""Search, routing and graph retrieval contracts (specification 4.4--4.6)."""

from pydantic import Field, JsonValue, model_validator

from core.schemas.base import (
    ContractModel,
    FiniteFloat,
    NonEmptyString,
    NonNegativeInt,
    PositiveInt,
)


class RetrievalRequest(ContractModel):
    """Search request; candidates are collected before the final top_k cut."""

    query: NonEmptyString
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    top_k: PositiveInt = 5
    candidate_k: PositiveInt = 20

    @model_validator(mode="after")
    def check_candidate_count(self) -> "RetrievalRequest":
        if self.candidate_k < self.top_k:
            raise ValueError("candidate_k must be greater than or equal to top_k")
        return self


class RetrievedChunk(ContractModel):
    """Search hit; score is finite but has a method-specific scale.

    metadata contains serialized LegalMetadata and available chunk location
    fields (chapter/article/clause/point/parent_id/source_url).
    """

    chunk_id: NonEmptyString
    document_id: NonEmptyString
    content: NonEmptyString
    score: FiniteFloat
    retrieval_method: NonEmptyString
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RetrievalResult(ContractModel):
    """Aggregated hits; total_candidates counts unique hits before top_k."""

    query: NonEmptyString
    results: list[RetrievedChunk] = Field(default_factory=list)
    relations: list[dict[str, JsonValue]] = Field(default_factory=list)
    total_candidates: NonNegativeInt = 0


class RetrievalRouteRequest(ContractModel):
    """Router input; filters come from MetadataFilterResult.filters."""

    query: NonEmptyString
    intent: NonEmptyString
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    entities: list[str] = Field(default_factory=list)


class RetrievalStrategy(ContractModel):
    """Router decision, including the reason for selecting the search methods."""

    use_bm25: bool = True
    use_vector: bool = True
    use_graph: bool = False
    use_rerank: bool = True
    top_k: PositiveInt = 5
    candidate_k: PositiveInt = 20
    reason: NonEmptyString

    @model_validator(mode="after")
    def check_strategy(self) -> "RetrievalStrategy":
        if not (self.use_bm25 or self.use_vector or self.use_graph):
            raise ValueError("at least one retrieval method must be enabled")
        if self.candidate_k < self.top_k:
            raise ValueError("candidate_k must be greater than or equal to top_k")
        return self


class GraphRetrievalRequest(ContractModel):
    """Graph traversal from entities and/or seed document IDs."""

    query: NonEmptyString
    entities: list[str] = Field(default_factory=list)
    seed_document_ids: list[str] = Field(default_factory=list)
    max_depth: PositiveInt = 2


class GraphRetrievalResult(ContractModel):
    """Graph hits and source-backed relations; see docs/INTERFACES.md."""

    results: list[RetrievedChunk] = Field(default_factory=list)
    relations: list[dict[str, JsonValue]] = Field(default_factory=list)
    related_document_ids: list[str] = Field(default_factory=list)
