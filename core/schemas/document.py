"""Ingestion, metadata and chunk contracts (specification 4.3)."""

from pydantic import Field, model_validator

from core.schemas.base import ContractModel, FiniteFloat, NonEmptyString


class LegalMetadata(ContractModel):
    """Document metadata; status alone does not establish legal applicability.

    Dates use ISO YYYY-MM-DD strings when known; missing dates are None.
    Relationship lists contain document IDs, not titles or document numbers.
    """

    document_id: NonEmptyString
    title: NonEmptyString
    document_number: NonEmptyString
    document_type: NonEmptyString
    issuing_authority: str | None = None
    issued_date: str | None = None
    effective_date: str | None = None
    expiry_date: str | None = None
    status: str = "unknown"
    legal_domain: list[str] = Field(default_factory=list)
    amended_by: list[str] = Field(default_factory=list)
    replaced_by: list[str] = Field(default_factory=list)
    repealed_by: list[str] = Field(default_factory=list)
    related_documents: list[str] = Field(default_factory=list)
    # Article-level provenance survives splitting and retrieval unchanged.
    source_url: str | None = None
    source_record_id: str | None = None
    source_dataset: str | None = None
    source_revision: str | None = None
    topic_id: str | None = None
    topic_title: str | None = None
    subject_id: str | None = None
    subject_title: str | None = None


class LegalDocument(ContractModel):
    """Parsed document, before chunking."""

    document_id: NonEmptyString
    content: NonEmptyString
    metadata: LegalMetadata

    @model_validator(mode="after")
    def check_document_id(self) -> "LegalDocument":
        if self.document_id != self.metadata.document_id:
            raise ValueError("document_id must match metadata.document_id")
        return self


class LegalChunk(ContractModel):
    """Stable retrieval unit; parent_id refers to another chunk ID."""

    chunk_id: NonEmptyString
    document_id: NonEmptyString
    content: NonEmptyString
    metadata: LegalMetadata
    chapter: str | None = None
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    parent_id: str | None = None
    embedding: list[FiniteFloat] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def check_document_id(self) -> "LegalChunk":
        if self.document_id != self.metadata.document_id:
            raise ValueError("document_id must match metadata.document_id")
        return self
