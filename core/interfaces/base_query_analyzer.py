"""Query understanding contract (specification 4.1)."""

from abc import ABC, abstractmethod

from core.schemas.query import QueryAnalysisResult, QueryRequest


class BaseQueryAnalyzer(ABC):
    @abstractmethod
    def analyze(self, request: QueryRequest) -> QueryAnalysisResult:
        """Preserve original_query and return a rewrite, intent and metadata."""
        raise NotImplementedError
