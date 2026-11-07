"""Public corpus identity, without filesystem paths or runtime credentials."""

from typing import Literal

from core.schemas.base import ContractModel, NonNegativeInt


class CorpusResponse(ContractModel):
    corpus_id: str
    source_type: Literal["json", "huggingface"]
    dataset: str | None = None
    revision: str | None = None
    topics: list[str]
    subjects: list[str]
    document_count: NonNegativeInt
    chunk_count: NonNegativeInt
    parent_chunk_count: NonNegativeInt
    relation_count: NonNegativeInt
    unresolved_reference_count: NonNegativeInt
