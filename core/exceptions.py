"""Common runtime failures; schema validation uses pydantic.ValidationError."""


class ConfigurationError(ValueError):
    """Configuration could not be loaded or is not ready for real adapters."""


class RAGError(Exception):
    """Base exception for recoverable pipeline/service failures."""


class RetrievalError(RAGError):
    """A retriever or its datastore failed; different from no matching hits."""


class EmbeddingError(RAGError):
    """An embedding provider failed or returned invalid vectors."""


class LLMError(RAGError):
    """An LLM call failed or its structured output could not be validated."""


class InsufficientEvidenceError(RAGError):
    """The available context cannot support answer generation."""


class CitationVerificationError(RAGError):
    """A citation or answer claim could not be verified against the context."""
