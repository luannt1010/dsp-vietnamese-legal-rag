"""Per-request orchestration results; existing module contracts stay unchanged."""

from typing import Literal

from pydantic import Field, JsonValue

from core.schemas.answer import LegalAnswer
from core.schemas.base import ContractModel, NonEmptyString, NonNegativeInt
from core.schemas.evaluation import RetrievalEvaluationResult
from core.schemas.retrieval import RetrievalResult, RetrievalStrategy
from core.schemas.query import QueryAnalysisResult


PipelineStatus = Literal["completed", "insufficient_evidence", "failed", "timed_out"]


class RetrievalRound(ContractModel):
    """One attempted retrieval round; later fields stay None if a step fails."""

    iteration: NonNegativeInt
    query: NonEmptyString
    strategy: RetrievalStrategy
    retrieval_result: RetrievalResult | None = None
    evaluation: RetrievalEvaluationResult | None = None


class PipelineResult(ContractModel):
    """Answer and explicit request-local history, without global mutable state."""

    answer: LegalAnswer
    status: PipelineStatus
    rounds: list[RetrievalRound] = Field(default_factory=list)
    failure_stage: str | None = None
    error_type: str | None = None
    analysis: QueryAnalysisResult | None = None
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    query: NonEmptyString | None = None
