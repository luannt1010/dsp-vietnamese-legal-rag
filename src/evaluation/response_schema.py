"""Expose feedback-state invariants to structured-output providers as well."""

from typing import Literal

from pydantic import Field, JsonValue, TypeAdapter

from core.schemas import RetrievalEvaluationResult, RetrievalStrategy
from core.config.settings import RetrievalSettings
from core.schemas.base import NonEmptyString


class _Continue(RetrievalEvaluationResult):
    is_relevant: Literal[True]
    is_sufficient: Literal[True]
    next_action: Literal["continue"]
    refined_query: Literal[None] = None
    strategy_override: dict[str, JsonValue] = Field(default_factory=dict, max_length=0)


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


def evaluation_response_schema(settings: RetrievalSettings | None = None) -> dict:
    # Pydantic model validators are not represented by model_json_schema().
    # Literal branches prevent a provider from emitting false + "continue".
    schema = TypeAdapter(_Continue | _Refine | _Change | _Stop).json_schema()
    override = RetrievalStrategy.model_json_schema()
    override["required"] = []  # An override is partial, not an entire strategy.
    override["minProperties"] = 1
    if settings is not None:
        override["properties"]["top_k"]["maximum"] = settings.max_top_k
        override["properties"]["candidate_k"]["maximum"] = settings.max_candidate_k
    schema["$defs"]["_Change"]["properties"]["strategy_override"] = override
    # Let the model identify the evidence/gaps before selecting its verdict.
    for definition in schema["$defs"].values():
        properties = definition.get("properties", {})
        definition["properties"] = {
            key: properties[key] for key in ("reason", "missing_information", *properties)
            if key in properties
        }
    return schema
