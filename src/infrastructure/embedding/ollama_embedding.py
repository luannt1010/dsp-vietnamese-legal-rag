"""Batched Ollama dense embeddings with explicit dimension and normalization."""

from core.config.settings import EmbeddingSettings
from core.exceptions import ConfigurationError, EmbeddingError
from core.interfaces import BaseEmbedding
from src.infrastructure.ollama_client import OllamaClient
from src.retrieval.common import normalize_vector, validate_vector
from src.observability.telemetry import instrument


class OllamaEmbedding(BaseEmbedding):
    def __init__(self, settings: EmbeddingSettings):
        if settings.provider not in (None, "ollama"):
            raise ConfigurationError(f"unsupported embedding provider for Ollama adapter: {settings.provider}")
        if not settings.model or not settings.dimension:
            raise ValueError("embedding model and dimension must be configured")
        self.settings = settings
        self._client = OllamaClient(
            settings.base_url, timeout_s=settings.timeout_s, max_retries=settings.max_retries,
        )

    @property
    def dimension(self) -> int:
        return self.settings.dimension

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    @instrument("embedding", kind="model_call", role="embedding")
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("embedding inputs must be nonempty strings")
        vectors = []
        for offset in range(0, len(texts), self.settings.batch_size):
            batch = texts[offset:offset + self.settings.batch_size]
            payload = {
                "model": self.settings.model, "input": batch,
                "truncate": False, "keep_alive": "1m",
            }
            if self.settings.device == "cpu":
                payload["options"] = {"num_gpu": 0}
            elif self.settings.device == "cuda":
                payload["options"] = {"num_gpu": -1}
            result = self._client.post("/api/embed", payload, error_type=EmbeddingError)
            embeddings = result.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise EmbeddingError("Ollama returned the wrong embedding batch size")
            for raw in embeddings:
                vector = validate_vector(raw, self.dimension)
                vectors.append(normalize_vector(vector) if self.settings.normalize else vector)
        return vectors
