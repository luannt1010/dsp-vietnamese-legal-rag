"""Provider-neutral embedding boundary for ingestion and vector retrieval."""

from abc import ABC, abstractmethod


class BaseEmbedding(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Positive vector size; ingestion and search must use the same model."""
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Return a finite vector of length dimension; reject blank text."""
        raise NotImplementedError

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input, in order; [] returns [].

        Reject blank members. Each vector has length dimension and finite
        values. Wrap provider failures as EmbeddingError.
        """
        raise NotImplementedError
