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


class LLMContextWindowError(LLMError):
    """The complete prompt and reserved output cannot fit the model window."""


class LLMOutputTruncatedError(LLMError):
    """The provider stopped at its output limit before completing the answer."""


class InsufficientEvidenceError(RAGError):
    """The available context cannot support answer generation."""


class CitationVerificationError(RAGError):
    """A citation or answer claim could not be verified against the context."""

    def __init__(self, message: str, *, code: str = "citation_verification_failed", reason: str | None = None):
        super().__init__(message)
        self.code = code
        self.reason = reason
