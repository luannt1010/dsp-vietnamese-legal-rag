"""Public schema imports; implementations should share these exact models."""

from core.schemas.answer import AnswerGenerationRequest, LegalAnswer, LegalCitation
from core.schemas.context import ContextBuilderRequest, LegalContext
from core.schemas.document import LegalChunk, LegalDocument, LegalMetadata
from core.schemas.evaluation import (
    NextAction,
    RetrievalEvaluationRequest,
    RetrievalEvaluationResult,
)
from core.schemas.metadata import MetadataFilterRequest, MetadataFilterResult
from core.schemas.query import QueryAnalysisResult, QueryRequest
from core.schemas.retrieval import (
    GraphRetrievalRequest,
    GraphRetrievalResult,
    RetrievalRequest,
    RetrievalResult,
    RetrievalRouteRequest,
    RetrievalStrategy,
    RetrievedChunk,
)

__all__ = [
    "AnswerGenerationRequest", "ContextBuilderRequest", "GraphRetrievalRequest",
    "GraphRetrievalResult", "LegalAnswer", "LegalChunk", "LegalCitation",
    "LegalContext", "LegalDocument", "LegalMetadata", "MetadataFilterRequest",
    "MetadataFilterResult", "NextAction", "QueryAnalysisResult", "QueryRequest",
    "RetrievalEvaluationRequest", "RetrievalEvaluationResult", "RetrievalRequest",
    "RetrievalResult", "RetrievalRouteRequest", "RetrievalStrategy", "RetrievedChunk",
]
