"""Retrieval routing contract (specification 4.5)."""

from abc import ABC, abstractmethod

from core.schemas.retrieval import RetrievalRouteRequest, RetrievalStrategy


class BaseRetrievalRouter(ABC):
    @abstractmethod
    def route(self, request: RetrievalRouteRequest) -> RetrievalStrategy:
        """Choose retrieval methods and limits, with an explicit reason."""
        raise NotImplementedError
