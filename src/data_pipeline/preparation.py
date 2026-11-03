"""Reproducible chunk/embedding artifacts, separate from database backends."""

import hashlib
import json
from contextlib import closing
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.config import Settings
from core.exceptions import ConfigurationError
from core.schemas import LegalChunk, LegalDocument
from src.data_pipeline.chunking import FixedTokenChunker, HierarchicalChunker, LegalChunker
from src.data_pipeline.embedding import EmbeddingPipeline
from src.data_pipeline.embedding.cache import EmbeddingCache
from src.data_pipeline.artifacts import fingerprint, write_json
from src.data_pipeline.sources import load_source
from src.infrastructure.embedding import OllamaEmbedding
from src.infrastructure.ollama_client import OllamaClient
from src.infrastructure.tokenization import ModelTokenizer
from src.knowledge_graph import GraphBuilder, GraphSnapshot


MODEL_CACHE = Path(__file__).resolve().parents[2] / ".runtime" / "models"


@dataclass
class PreparedCorpus:
    corpus_id: str
    chunks: list[LegalChunk]
    parents: list[LegalChunk]
    graph: GraphSnapshot
    manifest: dict
    directory: Path


def corpus_identity(settings: Settings, source_signature: dict) -> tuple[str, dict]:
    if settings.embedding.provider not in (None, "ollama"):
        raise ConfigurationError("demo preparation currently supports embedding.provider=ollama")
    config = settings.data_pipeline
    info = OllamaClient(settings.embedding.base_url, timeout_s=30, max_retries=0).post(
        "/api/show", {"model": settings.embedding.model},
    )
    if "embedding" not in info.get("capabilities", []):
        raise ConfigurationError("selected Ollama model does not expose embedding capability")
    # Ollama's generated modelfile includes the content-addressed FROM blob.
    # Hash it instead of caching a mutable model tag as if it were a revision.
    signature = {
        "format_version": 4,
        "source": source_signature,
        "chunking": config.chunking.model_dump(mode="json"),
        "embedding": {
            "provider": settings.embedding.provider, "model": settings.embedding.model,
            "dimension": settings.embedding.dimension, "normalize": settings.embedding.normalize,
            "tokenizer_model": settings.embedding.tokenizer_model,
            "tokenizer_revision": settings.embedding.tokenizer_revision,
            "model_digest": hashlib.sha256(info.get("modelfile", "").encode()).hexdigest(),
        },
    }
    return fingerprint(signature)[:16], signature


def prepare_corpus(
    settings: Settings, *, build: bool = False, refresh: bool = False, progress: Callable[[str], None] = print,
) -> PreparedCorpus:
    source = load_source(settings.data_pipeline, build=build, refresh=refresh, progress=progress)
    corpus_id, signature = corpus_identity(settings, source.signature)
    directory = settings.data_pipeline.index_dir / corpus_id
    artifact = directory / "corpus.json"
    cached = artifact.is_file()
    if cached:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        if payload["manifest"]["signature"] != signature:
            raise ConfigurationError("cached index signature differs; prepare a new corpus")
        chunks = [LegalChunk.model_validate(item) for item in payload["chunks"]]
        parents = [LegalChunk.model_validate(item) for item in payload["parents"]]
        progress(f"Reusing prepared corpus {corpus_id}: {len(chunks)} embedded chunks")
    else:
        if not build:
            raise ConfigurationError("corpus is not prepared; run: python -m scripts.demo prepare")
        config = settings.data_pipeline.chunking
        tokenizer = ModelTokenizer(config.tokenizer_model, revision=config.tokenizer_revision, cache_dir=MODEL_CACHE)
        chunker = {"fixed": FixedTokenChunker, "legal": LegalChunker, "hierarchical": HierarchicalChunker}[config.strategy](tokenizer, config)
        chunks, parents = [], []
        if config.strategy == "fixed":
            # The fixed baseline is allowed to cross article boundaries within
            # a document, while legal/hierarchical strategies preserve them.
            grouped = {}
            for original in source.chunks:
                grouped.setdefault(original.document_id, []).append(original)
            for document_id, articles in grouped.items():
                metadata = articles[0].metadata.model_copy(deep=True)
                if len(articles) > 1:
                    metadata.source_record_id = None
                    for field in ("source_url", "topic_id", "topic_title", "subject_id", "subject_title"):
                        values = {getattr(article.metadata, field) for article in articles}
                        setattr(metadata, field, next(iter(values)) if len(values) == 1 else None)
                    metadata.legal_domain = sorted({domain for article in articles for domain in article.metadata.legal_domain})
                result = chunker.chunk(LegalDocument(
                    document_id=document_id, metadata=metadata,
                    content="\n\n".join(article.content for article in articles),
                ))
                chunks.extend(result.chunks)
                parents.extend(result.parents)
            # Original article identities still resolve source graph references.
            parents.extend(source.chunks)
        else:
            for original in source.chunks:
                result = chunker.split_chunk(original)
                chunks.extend(result.chunks)
                parents.extend(result.parents)
        progress(f"Chunking {config.strategy}: {len(source.chunks)} sources -> {len(chunks)} leaves, {len(parents)} parents")
        with closing(EmbeddingCache(
            settings.data_pipeline.index_dir / "embeddings.sqlite3",
            namespace=fingerprint(signature["embedding"]), dimension=settings.embedding.dimension,
        )) as cache:
            chunks = EmbeddingPipeline(
                OllamaEmbedding(settings.embedding), batch_size=settings.data_pipeline.indexing_batch_size, cache=cache,
            ).run(chunks, progress=lambda done, total: progress(f"Embeddings ready {done}/{total}"))
            progress(f"Embedding cache: {cache.hits} reused texts, {cache.misses} new texts")
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "manifest": {"corpus_id": corpus_id, "signature": signature, "chunks": len(chunks), "parents": len(parents)},
            "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
            "parents": [chunk.model_dump(mode="json") for chunk in parents],
        }
    graph = GraphBuilder().build(chunks, parents, source.relations)
    if not cached:
        # Publish only after hierarchy and source evidence have been validated.
        write_json(artifact, payload)
    return PreparedCorpus(corpus_id, chunks, parents, graph, payload["manifest"], directory)
