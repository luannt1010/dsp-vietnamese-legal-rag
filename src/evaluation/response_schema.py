"""Portable provider schema and strict Python validation of feedback states."""

from typing import Literal

from pydantic import Field, JsonValue, TypeAdapter

from core.schemas import RetrievalEvaluationResult, RetrievalStrategy
from core.config.settings import RetrievalSettings
from core.schemas.base import NonEmptyString
from src.observability.telemetry import span


class _Continue(RetrievalEvaluationResult):
    is_relevant: Literal[True]
    is_sufficient: Literal[True]
    next_action: Literal["continue"]
    refined_query: Literal[None] = None
    strategy_override: dict[str, JsonValue] = Field(default_factory=dict, max_length=0)
    missing_information: list[NonEmptyString] = Field(default_factory=list, max_length=0)


class _Refine(RetrievalEvaluationResult):
    is_sufficient: Literal[False]
    next_action: Literal["refine_query"]
    refined_query: NonEmptyString
    strategy_override: dict[str, JsonValue] = Field(default_factory=dict, max_length=0)


class _Change(RetrievalEvaluationResult):
    is_sufficient: Literal[False]
    next_action: Literal["change_strategy"]
    refined_query: Literal[None] = None
    strategy_override: dict[str, JsonValue] = Field(min_length=1)


class _Stop(RetrievalEvaluationResult):
    is_sufficient: Literal[False]
    next_action: Literal["stop"]
    refined_query: Literal[None] = None
    strategy_override: dict[str, JsonValue] = Field(default_factory=dict, max_length=0)


_FEEDBACK = TypeAdapter(_Continue | _Refine | _Change | _Stop)


def validate_feedback(payload: dict) -> RetrievalEvaluationResult:
    """Validate the decision; discard advice that the selected action cannot use."""
    validated = RetrievalEvaluationResult.model_validate(payload)
    canonical = validated.model_dump()
    discarded = []
    for action, field, empty in (("refine_query", "refined_query", None),
                                 ("change_strategy", "strategy_override", {})):
        if validated.next_action != action and canonical[field] != empty:
            canonical[field] = empty
            discarded.append(field)
    if discarded:
        with span("feedback_normalization", kind="decision") as event:
            event["discarded_inactive_fields"] = discarded
    # No normalization of is_relevant/is_sufficient/next_action. Inconsistent
    # verdicts (such as false + continue) still fail rather than authorize an answer.
    checked = _FEEDBACK.validate_python(canonical)
    return RetrievalEvaluationResult.model_validate(checked.model_dump())


def evaluation_response_schema(settings: RetrievalSettings | None = None, *, allow_strategy_changes: bool = True) -> dict:
    # A union of complete feedback objects produced contradictory decisions in
    # live Ollama probes despite correct evidence. Use one flat object for the
    # provider; validate decisions and canonicalize inactive advice in Python.
    schema = RetrievalEvaluationResult.model_json_schema()
    override = RetrievalStrategy.model_json_schema()
    override["required"] = []  # An override is partial, not an entire strategy.
    if settings is not None:
        override["properties"]["top_k"]["maximum"] = settings.max_top_k
        override["properties"]["candidate_k"]["maximum"] = settings.max_candidate_k
    if not allow_strategy_changes:
        schema["properties"]["next_action"]["enum"].remove("change_strategy")
        override["maxProperties"] = 0
    schema["properties"]["strategy_override"] = override
    return schema
