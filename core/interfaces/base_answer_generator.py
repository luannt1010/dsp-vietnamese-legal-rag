"""Answer generation contract (specification 4.9)."""

from abc import ABC, abstractmethod

from core.schemas.answer import AnswerGenerationRequest, LegalAnswer


class BaseAnswerGenerator(ABC):
    @abstractmethod
    def generate(self, request: AnswerGenerationRequest) -> LegalAnswer:
        """Answer using only supplied context and source-backed citations.

        Do not perform retrieval. Raise InsufficientEvidenceError for empty
        evidence and LLMError for provider/structured-output failures.
        Citation verification is a separate pipeline step.
        """
        raise NotImplementedError
