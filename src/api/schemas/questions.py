"""Bounded HTTP input and a public projection of PipelineResult."""

from pydantic import Field

from core.schemas import LegalAnswer, QueryRequest, RetrievedChunk
from core.schemas.base import ContractModel, NonEmptyString, NonNegativeInt
from core.schemas.orchestration import PipelineStatus


class QuestionRequest(QueryRequest):
    """Each question is independent; conversational memory is not implemented."""

    query: NonEmptyString = Field(max_length=4000)
    conversation_id: None = None


class FailureInfo(ContractModel):
    """Safe diagnostic codes, without provider messages or model reasoning."""

    stage: str | None = None
    code: str


class QuestionResponse(ContractModel):
    request_id: str
    status: PipelineStatus
    answer: LegalAnswer
    sources: list[RetrievedChunk] = Field(default_factory=list)
    corpus_id: str
    rounds: NonNegativeInt
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    failure: FailureInfo | None = None
