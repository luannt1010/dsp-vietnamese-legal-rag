"""Filter translation contract (specification 4.2)."""

from abc import ABC, abstractmethod

from core.schemas.metadata import MetadataFilterRequest, MetadataFilterResult


class BaseMetadataFilter(ABC):
    @abstractmethod
    def build_filters(self, request: MetadataFilterRequest) -> MetadataFilterResult:
        """Build portable conditions; do not execute a database query.

        Unsupported conditions must raise ValueError, never be silently ignored.
        """
        raise NotImplementedError
