"""Graph retrieval contract (specification 4.6)."""

from abc import ABC, abstractmethod

from core.schemas.retrieval import GraphRetrievalRequest, GraphRetrievalResult


class BaseGraphRetriever(ABC):
    @abstractmethod
    def search(self, request: GraphRetrievalRequest) -> GraphRetrievalResult:
        """Traverse at most max_depth edges and retain evidence for each relation.

        No matches returns an empty GraphRetrievalResult. Dependency failures
        raise RetrievalError. Graph expansion must be filtered by the retrieval
        integration layer before it enters the final RetrievalResult.
        """
        raise NotImplementedError
