"""Metadata filtering implementation for specification 4.2."""

from core.filtering import validate_filters
from core.interfaces import BaseMetadataFilter
from core.schemas import MetadataFilterRequest, MetadataFilterResult


class MetadataFilter(BaseMetadataFilter):
    """Validate explicit metadata conditions without widening their scope.

    Field names and values already use the ingestion/retrieval vocabulary.
    No implicit aliases, case conversion, taxonomy guesses or date operators
    are applied. Scalar equality and flat lists pass through unchanged.

    The filter is stateless: a shared instance can serve concurrent requests.
    It does not call retrievers, models or databases, or cache query metadata.
    """

    def build_filters(self, request: MetadataFilterRequest) -> MetadataFilterResult:
        """Return independent conditions and their field names in input order.

        Unknown fields, unsupported operators and non-finite values raise
        ValueError. Revalidate nested mutable data at this module boundary;
        malformed schema input raises pydantic.ValidationError.
        """
        validated = MetadataFilterRequest.model_validate(request.model_dump())
        validate_filters(validated.metadata)
        return MetadataFilterResult(
            filters=validated.metadata,
            applied_filters=list(validated.metadata),
        )
