"""Metadata filtering and source-preserving conversions shared by adapters."""

from collections.abc import Iterable, Mapping
from math import hypot, isfinite

from pydantic import JsonValue

from core.exceptions import EmbeddingError, RetrievalError
from core.filtering import FILTER_FIELDS, LOCATION_FIELDS, validate_filters
from core.schemas import LegalChunk, RetrievalResult, RetrievedChunk


def matches_filters(metadata: Mapping[str, JsonValue], filters: Mapping[str, JsonValue]) -> bool:
    """AND across fields, OR/intersection within lists; [] never matches."""
    for key, expected in filters.items():
        if key not in metadata:
            return False
        expected_values = expected if isinstance(expected, list) else [expected]
        actual = metadata[key]
        actual_values = actual if isinstance(actual, list) else [actual]
        if not any(value in actual_values for value in expected_values):
            return False
    return True


def as_hit(chunk: LegalChunk | RetrievedChunk) -> RetrievedChunk:
    """Take a validated snapshot; never share nested mutable source metadata."""
    if isinstance(chunk, RetrievedChunk):
        return RetrievedChunk.model_validate(chunk.model_dump())
    chunk = LegalChunk.model_validate(chunk.model_dump())
    metadata = chunk.metadata.model_dump(mode="json")
    metadata.update({field: getattr(chunk, field) for field in LOCATION_FIELDS})
    return RetrievedChunk(
        chunk_id=chunk.chunk_id, document_id=chunk.document_id,
        content=chunk.content, metadata=metadata, score=0.0,
        retrieval_method="indexed",
    )


def snapshot_documents(
    documents: Iterable[LegalChunk | RetrievedChunk] | RetrievalResult,
) -> list[RetrievedChunk]:
    if isinstance(documents, RetrievalResult):
        documents = documents.results
    result = [as_hit(chunk) for chunk in documents]
    ids = [chunk.chunk_id for chunk in result]
    if len(set(ids)) != len(ids):
        raise ValueError("indexed chunk IDs must be unique")
    return result


def scored_hit(hit: RetrievedChunk, score: float, method: str) -> RetrievedChunk:
    return RetrievedChunk.model_validate({
        **hit.model_dump(), "score": score, "retrieval_method": method,
    })


def unique_hits(hits: Iterable[RetrievedChunk]) -> list[RetrievedChunk]:
    """Retain ranking order and reject conflicting identities across branches."""
    unique: dict[str, RetrievedChunk] = {}
    for source in hits:
        hit = as_hit(source)
        previous = unique.get(hit.chunk_id)
        if previous is not None:
            if previous.document_id != hit.document_id or previous.content != hit.content:
                raise RetrievalError(f"conflicting source for chunk ID {hit.chunk_id}")
            if previous.metadata != hit.metadata:
                merged = dict(previous.metadata)
                for key, value in hit.metadata.items():
                    if key in merged and merged[key] != value:
                        raise RetrievalError(f"conflicting metadata for chunk ID {hit.chunk_id}")
                    merged[key] = value
                previous.metadata = merged
        else:
            unique[hit.chunk_id] = hit
    return list(unique.values())


def validate_vector(vector: Iterable[float], dimension: int) -> list[float]:
    """Embedding failures remain distinct from datastore/search failures."""
    try:
        values = list(vector)
        if len(values) != dimension or any(isinstance(value, (bool, str)) for value in values):
            raise ValueError("invalid vector dimension or element type")
        values = [float(value) for value in values]
        if not all(isfinite(value) for value in values):
            raise ValueError("vector elements must be finite")
        return values
    except (TypeError, ValueError, OverflowError) as exc:
        raise EmbeddingError("embedding must be a finite vector of the configured dimension") from exc


def positive_integer(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def normalize_vector(vector: list[float]) -> list[float]:
    """Normalize a validated vector without overflowing its norm."""
    scale = max(abs(value) for value in vector)
    if scale == 0:
        raise EmbeddingError("normalization requires a nonzero embedding")
    scaled = [value / scale for value in vector]
    norm = hypot(*scaled)
    return [value / norm for value in scaled]
