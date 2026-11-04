"""Strict contracts for user labels and persisted benchmark records."""

from typing import Literal

from pydantic import Field, StrictBool, model_validator

from core.schemas.base import ContractModel, NonEmptyString, NonNegativeInt
from core.schemas.orchestration import PipelineResult


class Evidence(ContractModel):
    document_number: NonEmptyString
    document_title: NonEmptyString
    article: NonEmptyString
    clause: NonEmptyString | None = None
    point: NonEmptyString | None = None
    quote: NonEmptyString
    source_url: NonEmptyString | None = None
    source_version: NonEmptyString | None = None
    corpus_article: NonEmptyString | None = None


class Question(ContractModel):
    question_id: NonEmptyString = Field(pattern=r"^[A-Za-z0-9_-]+$")
    question: NonEmptyString
    topic: NonEmptyString
    question_type: Literal["lookup", "multi_clause", "multi_document", "comparison", "unanswerable"]
    answerable: StrictBool
    reference_answer: NonEmptyString
    reference_claims: list[NonEmptyString]
    evidence: list[Evidence]
    split: Literal["development", "test"] = "test"

    @model_validator(mode="after")
    def validate_labels(self):
        if self.answerable:
            if not self.reference_claims or not self.evidence or self.question_type == "unanswerable":
                raise ValueError("answerable questions require claims, evidence, and an answerable type")
        elif self.reference_claims or self.evidence or self.question_type != "unanswerable":
            raise ValueError("unanswerable questions require empty claims/evidence and type unanswerable")
        if len(set(self.reference_claims)) != len(self.reference_claims):
            raise ValueError("reference claims must be unique")
        return self


class Sample(ContractModel):
    schema_version: Literal[1] = 1
    experiment: NonEmptyString
    question_id: NonEmptyString
    repeat: NonNegativeInt
    latency_scope: Literal["full_pipeline", "analysis_replay"]
    result: PipelineResult
    telemetry: list[dict] = Field(default_factory=list)
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    context_tokens: int | None = Field(default=None, ge=0)
    relevant_chunk_ids: list[str] = Field(default_factory=list)


class Score(ContractModel):
    experiment: NonEmptyString
    question_id: NonEmptyString
    repeat: NonNegativeInt
    status: str
    topic: str
    question_type: str
    answerable: bool
    sample_fingerprint: str
    scoring_fingerprint: str
    metrics: dict[str, float | None] = Field(default_factory=dict)
    judgments: dict = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
