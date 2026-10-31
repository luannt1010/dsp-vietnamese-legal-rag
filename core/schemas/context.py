"""Context construction contracts (specification 4.8)."""

from pydantic import Field

from core.schemas.base import ContractModel, NonEmptyString
from core.schemas.retrieval import RetrievalResult, RetrievedChunk


class ContextBuilderRequest(ContractModel):
    """Evaluated retrieval output and the user's original question."""

    retrieval_result: RetrievalResult
    original_query: NonEmptyString


class LegalContext(ContractModel):
    """Context text and the exact source chunks retained within its budget."""

    query: NonEmptyString
    context_text: str
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    cited_document_ids: list[str] = Field(default_factory=list)
