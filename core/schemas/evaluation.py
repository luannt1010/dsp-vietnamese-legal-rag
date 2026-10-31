"""Retrieval feedback contracts (specification 4.7)."""

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from core.schemas.base import (
    Confidence,
    ContractModel,
    NonEmptyString,
    NonNegativeInt,
    PositiveInt,
)
from core.schemas.retrieval import RetrievalResult


NextAction = Literal["continue", "refine_query", "change_strategy", "stop"]


class RetrievalEvaluationRequest(ContractModel):
    """One evaluation round; iteration is zero-based."""

    original_query: NonEmptyString
    current_query: NonEmptyString
    retrieval_result: RetrievalResult
    iteration: NonNegativeInt = 0
    max_iterations: PositiveInt = 3

    @model_validator(mode="after")
    def check_iteration(self) -> "RetrievalEvaluationRequest":
        if self.iteration >= self.max_iterations:
            raise ValueError("iteration must be less than max_iterations")
        return self


class RetrievalEvaluationResult(ContractModel):
    """Advice to the orchestrator; this model never triggers retrieval itself.

    'continue' means proceed to context/generation with sufficient evidence.
    strategy_override is a partial RetrievalStrategy JSON object; validate
    the merged strategy before executing it.
    """

    is_relevant: bool
    is_sufficient: bool
    confidence: Confidence
    missing_information: list[str] = Field(default_factory=list)
    next_action: NextAction
    refined_query: NonEmptyString | None = None
    strategy_override: dict[str, JsonValue] = Field(default_factory=dict)
    reason: NonEmptyString

    @model_validator(mode="after")
    def check_feedback(self) -> "RetrievalEvaluationResult":
        if self.is_sufficient:
            if not self.is_relevant or self.next_action != "continue":
                raise ValueError("sufficient evidence must be relevant with next_action='continue'")
        elif self.next_action == "continue":
            raise ValueError("cannot continue to generation with insufficient evidence")
        if self.next_action == "refine_query" and self.refined_query is None:
            raise ValueError("refine_query requires a non-empty refined_query")
        if self.next_action == "change_strategy" and not self.strategy_override:
            raise ValueError("change_strategy requires a non-empty strategy_override")
        return self
