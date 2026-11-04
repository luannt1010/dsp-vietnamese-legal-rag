"""Dense query adapter; storage and embedding providers are injected."""

from typing import Protocol

from pydantic import JsonValue

from core.exceptions import EmbeddingError, RetrievalError
from core.interfaces import BaseEmbedding, BaseRetriever
from core.schemas import RetrievalRequest, RetrievedChunk
from src.retrieval.common import (
    matches_filters, positive_integer, scored_hit, unique_hits, validate_filters, validate_vector,
)
from src.observability.telemetry import span


class VectorStore(Protocol):
    """Backend boundary. Implement filtering before the backend top_k cut."""

    @property
    def dimension(self) -> int: ...

    def search(
        self, vector: list[float], *, filters: dict[str, JsonValue], top_k: int,
    ) -> list[RetrievedChunk]:
        """Return unique hits ordered by descending similarity (negative distance for L2)."""
        ...


class VectorRetriever(BaseRetriever):
    def __init__(self, embedding: BaseEmbedding, store: VectorStore):
        positive_integer(embedding.dimension, "embedding dimension")
        positive_integer(store.dimension, "store dimension")
        if embedding.dimension != store.dimension:
            raise ValueError("embedding dimension does not match the vector index")
        self.embedding, self.store = embedding, store

    def search(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        validate_filters(request.filters)
        try:
            vector = validate_vector(self.embedding.embed_query(request.query), self.store.dimension)
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError("query embedding failed") from exc
        try:
            with span("vector_search"):
                hits = unique_hits(self.store.search(
                    vector, filters=dict(request.filters), top_k=request.top_k,
                ))
            if any(not matches_filters(hit.metadata, request.filters) for hit in hits):
                raise RetrievalError("vector store returned a hit outside the requested filters")
            hits.sort(key=lambda hit: hit.score, reverse=True)
            return [scored_hit(hit, hit.score, "vector") for hit in hits[:request.top_k]]
        except (EmbeddingError, RetrievalError):
            raise
        except Exception as exc:
            raise RetrievalError("vector store search failed") from exc
