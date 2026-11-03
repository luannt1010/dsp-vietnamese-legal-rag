"""Exact vector search for local development and integration without a database."""

from collections.abc import Iterable
from math import fsum, hypot

from pydantic import JsonValue

from core.exceptions import EmbeddingError, RetrievalError
from core.schemas import LegalChunk, RetrievedChunk
from src.retrieval.common import (
    matches_filters, normalize_vector, positive_integer, scored_hit, snapshot_documents, validate_filters, validate_vector,
)


class InMemoryVectorStore:
    def __init__(
        self, chunks: Iterable[LegalChunk], *, dimension: int, distance_metric: str = "cosine",
    ):
        positive_integer(dimension, "dimension")
        if distance_metric not in {"cosine", "inner_product", "l2"}:
            raise ValueError(f"unsupported vector distance metric: {distance_metric}")
        self._dimension = dimension
        self.distance_metric = distance_metric
        chunks = list(chunks)
        self._hits = snapshot_documents(chunks)
        self._vectors = [self._prepare(chunk.embedding) for chunk in chunks]

    @property
    def dimension(self) -> int:
        return self._dimension

    def _prepare(self, vector: Iterable[float] | None) -> list[float]:
        values = validate_vector(vector, self.dimension)
        if self.distance_metric == "cosine":
            values = normalize_vector(values)
        return values

    def search(
        self, vector: list[float], *, filters: dict[str, JsonValue], top_k: int,
    ) -> list[RetrievedChunk]:
        validate_filters(filters)
        positive_integer(top_k, "top_k")
        query = self._prepare(vector)
        try:
            results = []
            for hit, stored in zip(self._hits, self._vectors):
                if not matches_filters(hit.metadata, filters):
                    continue
                if self.distance_metric == "l2":
                    score = -hypot(*(left - right for left, right in zip(query, stored)))
                else:
                    score = fsum(left * right for left, right in zip(query, stored))
                results.append(scored_hit(hit, score, "vector"))
            results.sort(key=lambda hit: hit.score, reverse=True)
            return results[:top_k]
        except Exception as exc:
            raise RetrievalError("in-memory vector search failed") from exc
