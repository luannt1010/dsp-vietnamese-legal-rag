"""Legal context contract (specification 4.8)."""

from abc import ABC, abstractmethod

from core.schemas.context import ContextBuilderRequest, LegalContext


class BaseLegalContextBuilder(ABC):
    @abstractmethod
    def build(self, request: ContextBuilderRequest) -> LegalContext:
        """Build context from retained hits, preserving source attribution.

        chunks must describe the sources actually included in context_text;
        cited_document_ids must be unique IDs of those chunks' documents.
        Raise InsufficientEvidenceError when no usable evidence remains.
        """
        raise NotImplementedError
