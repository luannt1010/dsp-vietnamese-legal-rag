"""Citation verification contract (specification 4.9)."""

from abc import ABC, abstractmethod

from core.schemas.answer import LegalAnswer
from core.schemas.context import LegalContext


class BaseCitationVerifier(ABC):
    @abstractmethod
    def verify(self, answer: LegalAnswer, context: LegalContext) -> LegalAnswer:
        """Check source identity, quotation, location and support for claims.

        Return a verified answer or raise CitationVerificationError; do not
        silently accept invented sources or merely remove invalid citations.
        """
        raise NotImplementedError
