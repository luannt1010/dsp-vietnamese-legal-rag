"""Metadata filter boundary (specification 4.2)."""

from pydantic import Field, JsonValue

from core.schemas.base import ContractModel


class MetadataFilterRequest(ContractModel):
    """Metadata extracted from a query; not a database query."""

    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class MetadataFilterResult(ContractModel):
    """Portable conditions that each retriever must enforce."""

    filters: dict[str, JsonValue] = Field(default_factory=dict)
    applied_filters: list[str] = Field(default_factory=list)
