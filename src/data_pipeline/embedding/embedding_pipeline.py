"""Attach ordered embeddings without mutating ingestion chunks."""

from collections.abc import Callable

from core.exceptions import EmbeddingError
from core.interfaces import BaseEmbedding
from core.schemas import LegalChunk
from src.retrieval.common import validate_vector
from src.data_pipeline.embedding.cache import EmbeddingCache


class EmbeddingPipeline:
    def __init__(self, embedding: BaseEmbedding, *, batch_size: int = 8, cache: EmbeddingCache | None = None):
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.embedding = embedding
        self.batch_size = batch_size
        self.cache = cache

    def run(
        self, chunks: list[LegalChunk], *, progress: Callable[[int, int], None] | None = None,
    ) -> list[LegalChunk]:
        result = []
        for offset in range(0, len(chunks), self.batch_size):
            batch = chunks[offset:offset + self.batch_size]
            texts = [chunk.content for chunk in batch]
            if self.cache is None:
                vectors = self.embedding.embed_documents(texts)
            else:
                by_text = {text: self.cache.get(text) for text in dict.fromkeys(texts)}
                missing = [text for text, vector in by_text.items() if vector is None]
                if missing:
                    generated = self.embedding.embed_documents(missing)
                    if len(generated) != len(missing):
                        raise EmbeddingError("embedding provider returned an incomplete batch")
                    self.cache.put_many(missing, generated)
                    by_text.update(zip(missing, generated))
                vectors = [by_text[text] for text in texts]
            if len(vectors) != len(batch):
                raise EmbeddingError("embedding provider returned an incomplete batch")
            for chunk, vector in zip(batch, vectors):
                result.append(LegalChunk.model_validate({
                    **chunk.model_dump(), "embedding": validate_vector(vector, self.embedding.dimension),
                }))
            if progress:
                progress(len(result), len(chunks))
        return result
