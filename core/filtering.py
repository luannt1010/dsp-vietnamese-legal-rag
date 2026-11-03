"""Portable metadata filter validation shared by preprocessing and retrieval.

This module defines the supported condition shape, not database execution or
legal applicability. Adapters implement the matching semantics in INTERFACES.md.
"""

import json
from collections.abc import Iterable, Iterator, Mapping
from math import isfinite

from pydantic import JsonValue

from core.schemas.document import LegalMetadata
from core.schemas.retrieval import RetrievedChunk


LOCATION_FIELDS = ("chapter", "article", "clause", "point", "parent_id")
FILTER_FIELDS = frozenset(LegalMetadata.model_fields) | frozenset(LOCATION_FIELDS) | {"source_url"}


def validate_filters(filters: Mapping[str, JsonValue]) -> None:
    """Reject unknown fields and conditions outside flat scalar/list equality.

    Keep None, empty strings and empty lists: they are explicit conditions,
    not missing values. Reject non-finite numbers because they cannot be
    represented consistently in JSON or compared across database adapters.
    """
    for key, value in filters.items():
        if key not in FILTER_FIELDS:
            raise ValueError(f"unsupported metadata filter: {key}")
        values = value if isinstance(value, list) else (value,)
        for item in values:
            if item is not None and not isinstance(item, (str, int, float, bool)):
                raise ValueError(f"filter {key} only supports scalar equality or a list of scalars")
            if isinstance(item, float) and not isfinite(item):
                raise ValueError(f"filter {key} requires finite numbers")


def supported_relations(
    relations: Iterable[dict[str, JsonValue]], chunks: list[RetrievedChunk],
) -> Iterator[dict[str, JsonValue]]:
    """Keep only edges whose endpoints and complete evidence survive selection."""
    documents = {chunk.document_id for chunk in chunks}
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    seen = set()
    for relation in relations:
        source, target = relation.get("source_document_id"), relation.get("target_document_id")
        kind, evidence = relation.get("relation_type"), relation.get("evidence_chunk_ids")
        if not (
            isinstance(source, str) and source in documents
            and isinstance(target, str) and target in documents
            and isinstance(kind, str) and kind.strip()
            and isinstance(evidence, list) and evidence
            and all(isinstance(identifier, str) and identifier in chunk_ids for identifier in evidence)
        ):
            continue
        supported = {
            "source_document_id": source, "target_document_id": target,
            "relation_type": kind, "evidence_chunk_ids": sorted(set(evidence)),
        }
        identity = json.dumps(supported, sort_keys=True, ensure_ascii=False)
        if identity not in seen:
            seen.add(identity)
            yield supported
