"""Per-request orchestration results; existing module contracts stay unchanged."""

from typing import Literal

from pydantic import Field, JsonValue, model_serializer

from core.schemas.answer import LegalAnswer
from core.schemas.base import ContractModel, NonEmptyString, NonNegativeInt
from core.schemas.evaluation import RetrievalEvaluationResult
from core.schemas.retrieval import RetrievalResult, RetrievalStrategy
from core.schemas.query import QueryAnalysisResult
from core.schemas.context import LegalContext
from core.schemas.base import PositiveInt


PipelineStatus = Literal["completed", "insufficient_evidence", "failed", "timed_out"]


class PipelineRunOptions(ContractModel):
    """Optional execution controls; defaults preserve the demo's behavior."""

    ranking_k: PositiveInt | None = None
    context_top_k: PositiveInt | None = None
    allow_strategy_changes: bool = True


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
    failure_details: dict[str, str] = Field(default_factory=dict)
    analysis: QueryAnalysisResult | None = None
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    query: NonEmptyString | None = None
    context: LegalContext | None = None
    draft_answer: LegalAnswer | None = None

    @model_serializer(mode="wrap")
    def serialize_result(self, handler):
        data = handler(self)
        # Older benchmark samples have no details. Preserve their serialized
        # fingerprint when reading them to score or review historical runs.
        if not self.failure_details:
            data.pop("failure_details", None)
        return data
