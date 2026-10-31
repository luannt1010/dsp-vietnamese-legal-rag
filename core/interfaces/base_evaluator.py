"""Retrieval evaluation contract (specification 4.7)."""

from abc import ABC, abstractmethod

from core.schemas.evaluation import (
    RetrievalEvaluationRequest,
    RetrievalEvaluationResult,
)


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate(self, request: RetrievalEvaluationRequest) -> RetrievalEvaluationResult:
        """Assess relevance/sufficiency and advise the orchestrator's next step.

        Never call retrieval directly. Empty evidence must be insufficient.
        At the iteration limit the orchestrator stops regardless of advice.
        """
        raise NotImplementedError
