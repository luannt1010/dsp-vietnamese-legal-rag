"""Data pipeline package for legal document loading, parsing, chunking, and indexing."""

from core.exceptions import RAGError


class DataPipelineError(RAGError):
    """Raised when document loading, parsing or chunking fails."""
