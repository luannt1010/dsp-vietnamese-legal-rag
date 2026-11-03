"""Build a bounded, source-preserving legal context (specification 4.8)."""

import json
from collections.abc import Callable, Iterable

from pydantic import JsonValue

from core.config.settings import ContextSettings
from core.filtering import supported_relations
from core.exceptions import InsufficientEvidenceError
from core.interfaces import BaseLegalContextBuilder
from core.schemas import ContextBuilderRequest, LegalContext, RetrievedChunk


# Keep citation/location and reported applicability data visible to generation.
# Other metadata remains available, unchanged, in LegalContext.chunks.
_SOURCE_METADATA_FIELDS = (
    "document_number", "title", "document_type", "issuing_authority",
    "chapter", "article", "clause", "point", "parent_id", "source_url",
    "issued_date", "effective_date", "expiry_date", "status", "legal_domain",
    "amended_by", "replaced_by", "repealed_by", "related_documents",
    "topic_id", "topic_title", "subject_id", "subject_title",
)
_SEPARATOR = "\n\n"


class LegalContextBuilder(BaseLegalContextBuilder):
    """Pack whole chunks in retrieval order, then add supported graph relations.

    token_counter must count text with the answer model's tokenizer, without
    per-call special tokens. No heuristic counter or model is loaded here.
    The generator separately accounts for the question, prompt and output;
    max_context_tokens is the budget for the complete context_text alone.

    This class keeps no per-request state. A shared instance can serve concurrent
    calls provided the injected token counter is also safe for concurrent use.
    """

    def __init__(
        self,
        *,
        token_counter: Callable[[str], int],
        settings: ContextSettings | None = None,
        parent_lookup: Callable[[str], RetrievedChunk | None] | None = None,
    ) -> None:
        if not callable(token_counter):
            raise TypeError("token_counter must be callable")
        self._token_counter = token_counter
        self._parent_lookup = parent_lookup
        self._settings = ContextSettings.model_validate(
            settings.model_dump() if settings is not None else {},
        )

    def build(self, request: ContextBuilderRequest) -> LegalContext:
        """Return exactly the retained sources, or fail if no whole chunk fits.

        Retrieval/evaluation decides relevance and sufficiency upstream. Packing
        cannot prove that the remaining evidence still answers the whole query.
        Invalid input or conflicting source identities raises ValueError (schema
        failures use its pydantic.ValidationError subclass).
        """
        # Nested lists/dicts can be mutated after Pydantic construction. Validate
        # again and take a private snapshot before making any packing decisions.
        validated = ContextBuilderRequest.model_validate(request.model_dump())
        hits = validated.retrieval_result.results
        if self._parent_lookup is not None:
            expanded = []
            for hit in hits:
                candidate = hit
                seen = {hit.chunk_id}
                parent_id = hit.metadata.get("parent_id")
                while isinstance(parent_id, str):
                    if parent_id in seen:
                        raise ValueError("cycle in context parent hierarchy")
                    seen.add(parent_id)
                    parent = self._parent_lookup(parent_id)
                    if parent is None or parent.document_id != hit.document_id:
                        break
                    if not self._fits(_render_chunk(parent, source_number=1)):
                        break
                    # Keep the largest complete ancestor that fits, so hits
                    # from several clauses share one article and its conditions.
                    candidate = parent
                    parent_id = parent.metadata.get("parent_id")
                expanded.append(candidate)
            hits = expanded
        candidates = _unique_chunks(hits)

        text = ""
        retained: list[RetrievedChunk] = []
        for chunk in candidates:
            block = _render_chunk(chunk, source_number=len(retained) + 1)
            proposed = _append_block(text, block)
            if self._fits(proposed):
                text = proposed
                retained.append(chunk)
            # Do not cut legal provisions mid-sentence. A later, smaller chunk
            # may still fit, so an oversized candidate does not stop the scan.

        if not retained:
            raise InsufficientEvidenceError(
                "no complete source chunk fits the legal context budget",
            )

        # Relations have lower priority than source evidence. Never add an edge
        # referencing a chunk/document excluded during packing or upstream top_k.
        for relation in supported_relations(validated.retrieval_result.relations, retained):
            block = "[Quan hệ văn bản]\n" + _json(relation)
            proposed = _append_block(text, block)
            if self._fits(proposed):
                text = proposed

        return LegalContext(
            query=validated.original_query,
            context_text=text,
            chunks=retained,
            cited_document_ids=list(dict.fromkeys(chunk.document_id for chunk in retained)),
        )

    def _fits(self, text: str) -> bool:
        # Count the actual concatenation, including labels, JSON and separators.
        # Token counts of separate strings are not necessarily additive.
        count = self._token_counter(text)
        if type(count) is not int or count <= 0:
            raise ValueError("token_counter must return a positive integer for nonempty text")
        return count <= self._settings.max_context_tokens


def _unique_chunks(chunks: Iterable[RetrievedChunk]) -> list[RetrievedChunk]:
    """Deduplicate by stable ID without sorting incomparable retrieval scores."""
    unique: dict[str, RetrievedChunk] = {}
    for chunk in chunks:
        metadata_id = chunk.metadata.get("document_id")
        if "document_id" in chunk.metadata and metadata_id != chunk.document_id:
            raise ValueError("chunk.document_id must match metadata.document_id")
        previous = unique.get(chunk.chunk_id)
        if previous is None:
            unique[chunk.chunk_id] = chunk
        elif (
            previous.document_id != chunk.document_id
            or previous.content != chunk.content
            or previous.metadata != chunk.metadata
        ):
            raise ValueError(f"conflicting source for chunk ID {chunk.chunk_id}")
    return list(unique.values())


def _render_chunk(chunk: RetrievedChunk, *, source_number: int) -> str:
    source: dict[str, JsonValue] = {
        "document_id": chunk.document_id,
        "chunk_id": chunk.chunk_id,
    }
    source.update({
        field: chunk.metadata[field]
        for field in _SOURCE_METADATA_FIELDS
        if field in chunk.metadata and chunk.metadata[field] is not None
    })
    # JSON escapes newlines in metadata, while content stays verbatim so a
    # verifier can locate quotations in the exact retained source chunk.
    return f"[Nguồn {source_number}]\nMetadata: {_json(source)}\nNội dung:\n{chunk.content}"


def _append_block(text: str, block: str) -> str:
    return text + _SEPARATOR + block if text else block


def _json(value: dict[str, JsonValue]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
