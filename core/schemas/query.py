"""Input and output of the query understanding module (specification 4.1)."""

from pydantic import Field, JsonValue

from core.schemas.base import ContractModel, NonEmptyString


class QueryRequest(ContractModel):
    """User question received by the API or orchestrator."""

    query: NonEmptyString
    conversation_id: str | None = None


class QueryAnalysisResult(ContractModel):
    """Normalized query and extracted metadata, before filter translation."""

    original_query: NonEmptyString
    rewritten_query: NonEmptyString
    intent: NonEmptyString
    entities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
