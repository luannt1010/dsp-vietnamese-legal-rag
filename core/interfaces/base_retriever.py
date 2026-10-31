"""Shared BM25, dense and hybrid contract (specification 4.4)."""

from abc import ABC, abstractmethod

from core.schemas.retrieval import RetrievalRequest, RetrievedChunk


class BaseRetriever(ABC):
    @abstractmethod
    def search(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        """Return up to top_k unique hits in descending method-specific score.

        Enforce every filter, retain source metadata and use stable chunk IDs.
        No matches returns []; dependency failures raise RetrievalError.
        Scores from different methods must be fused/reranked before comparison.
        """
        raise NotImplementedError
