"""Answer generation and citation contracts (specification 4.9)."""

from pydantic import Field

from core.schemas.base import Confidence, ContractModel, NonEmptyString
from core.schemas.context import LegalContext


class AnswerGenerationRequest(ContractModel):
    """Generator input; query is the original question, not the rewritten query."""

    context: LegalContext
    query: NonEmptyString


class LegalCitation(ContractModel):
    """Source-backed quotation; the verifier resolves it against context chunks."""

    document_id: NonEmptyString
    document_number: NonEmptyString
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    quoted_text: NonEmptyString
    source_url: str | None = None


class LegalAnswer(ContractModel):
    """Answer confidence is independent of retrieval and evaluation scores."""

    answer: NonEmptyString
    citations: list[LegalCitation] = Field(default_factory=list)
    confidence: Confidence
    disclaimer: str | None = None
