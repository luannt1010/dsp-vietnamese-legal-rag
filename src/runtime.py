"""Composition root for the actual local demo: Ollama + pgvector + Neo4j."""

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

from core.config import Settings
from core.exceptions import ConfigurationError
from core.schemas import QueryAnalysisResult, RetrievalEvaluationResult
from src.data_pipeline.preparation import MODEL_CACHE, PreparedCorpus, prepare_corpus
from src.data_pipeline.artifacts import fingerprint
from src.evaluation.response_schema import evaluation_response_schema
from src.generation.answer_generator import AnswerDraft, AnswerGenerator
from src.generation.citation_verifier import ClaimSupportResult
from src.infrastructure.embedding import OllamaEmbedding
from src.infrastructure.graph_store import InMemoryGraphStore, Neo4jStore
from src.infrastructure.tokenization import ModelTokenizer
from src.infrastructure.vector_store import InMemoryVectorStore, PgVectorStore
from src.knowledge_graph import GraphRetriever
from src.llm.factory import get_llm_instance
from src.orchestration import RAGPipeline, create_pipeline
from src.query_understanding.query_analyzer import query_response_schema
from src.retrieval.common import as_hit
from src.retrieval.dense import VectorRetriever
from src.retrieval.reranking import CrossEncoderReRanker
from src.retrieval.reranking.onnx_model import OnnxCrossEncoder
from src.retrieval.sparse import BM25Retriever


@dataclass
class DemoRuntime:
    pipeline: RAGPipeline
    corpus: PreparedCorpus
    vector_store: PgVectorStore | InMemoryVectorStore
    graph_store: Neo4jStore | InMemoryGraphStore
    token_counter: Callable[[str], int] | None = None


@contextmanager
def open_stores(settings: Settings, corpus: PreparedCorpus):
    with ExitStack() as stack:
        vector_config = settings.database.vector
        if vector_config.backend == "pgvector":
            metric = {"cosine": "cos", "inner_product": "ip", "l2": "l2"}[vector_config.distance_metric]
            name = f"{vector_config.table_name}_{corpus.corpus_id}_{metric}_{vector_config.index_type}"
            construction = {}
            if vector_config.index_type == "hnsw":
                construction = {"m": vector_config.hnsw_m, "ef_construction": vector_config.ef_construction}
            elif vector_config.index_type == "ivfflat":
                construction = {"lists": vector_config.ivfflat_lists}
            if construction:
                name += "_" + fingerprint(construction)[:6]
            vector = PgVectorStore(vector_config, dimension=settings.embedding.dimension, table_name=name)
            stack.callback(vector.close)
        else:
            vector = InMemoryVectorStore(
                corpus.chunks, dimension=settings.embedding.dimension,
                distance_metric=vector_config.distance_metric,
            )
        if settings.database.graph.backend == "neo4j":
            graph = Neo4jStore(settings.database.graph, namespace=settings.database.graph.namespace + ":" + corpus.corpus_id)
        else:
            graph = InMemoryGraphStore()
            graph.write(corpus.graph)
        stack.callback(graph.close)
        yield vector, graph


def _write_indexes(settings: Settings, corpus: PreparedCorpus, vector, graph, *, progress, write_vector=True, write_graph=True) -> None:
    if write_vector and isinstance(vector, PgVectorStore):
        progress(f"Indexing pgvector/{settings.database.vector.index_type}")
        vector.upsert(corpus.chunks)
        if vector.count() != len(corpus.chunks):
            raise ConfigurationError("pgvector row count differs from prepared corpus")
    if write_graph:
        progress("Indexing graph")
        graph.write(corpus.graph)


def prepare_indexes(settings: Settings, *, refresh: bool = False, progress=print) -> dict:
    settings.validate_runtime(purpose="ingestion")
    corpus = prepare_corpus(settings, build=True, refresh=refresh, progress=progress)
    with open_stores(settings, corpus) as (vector, graph):
        _write_indexes(settings, corpus, vector, graph, progress=progress)
        info = {
            **corpus.manifest, "vector_backend": settings.database.vector.backend,
            "vector_index": settings.database.vector.index_type,
            "graph_backend": settings.database.graph.backend,
            "resolved_relations": len(corpus.graph.relations), "unresolved_references": len(corpus.graph.unresolved),
        }
        if isinstance(graph, Neo4jStore):
            info["neo4j"] = graph.counts()
        return info


@contextmanager
def open_runtime(settings: Settings, *, progress=print, allow_strategy_changes: bool = True) -> Iterator[DemoRuntime]:
    settings.validate_runtime()
    corpus = prepare_corpus(settings, build=settings.data_pipeline.auto_prepare, progress=progress)
    with open_stores(settings, corpus) as (vector, graph):
        vector_ready = not isinstance(vector, PgVectorStore) or (vector.count() == len(corpus.chunks) and vector.has_index())
        graph_ready = True
        if isinstance(graph, Neo4jStore):
            counts = graph.counts()
            graph_ready = graph.is_ready() and (counts["chunks"] == len(corpus.chunks) and counts["parents"] == len(corpus.parents)
                              and counts["relations"] == len(corpus.graph.relations))
        if not (vector_ready and graph_ready):
            if not settings.data_pipeline.auto_prepare:
                raise ConfigurationError("database indexes are incomplete; run prepare or enable auto_prepare")
            _write_indexes(settings, corpus, vector, graph, progress=progress, write_vector=not vector_ready, write_graph=not graph_ready)
        counters = {}
        role_models = {
            "query_analyzer": QueryAnalysisResult, "retrieval_evaluator": RetrievalEvaluationResult,
            "answer_generator": AnswerDraft, "citation_verifier": ClaimSupportResult,
        }
        llms = {}
        tokenizers = {}
        for name, schema in role_models.items():
            role = getattr(settings.llm, name)
            if not role.tokenizer_model:
                raise ConfigurationError(f"llm.{name}.tokenizer_model is required for the real demo")
            key = (role.tokenizer_model, role.tokenizer_revision)
            if key not in tokenizers:
                progress(f"Loading tokenizer {role.tokenizer_model}")
                tokenizers[key] = ModelTokenizer(role.tokenizer_model, revision=role.tokenizer_revision, cache_dir=MODEL_CACHE)
            counters[name] = tokenizers[key].count
            response_schema = schema.model_json_schema()
            if name == "retrieval_evaluator":
                response_schema = evaluation_response_schema(settings.retrieval, allow_strategy_changes=allow_strategy_changes)
            elif name == "query_analyzer":
                response_schema = query_response_schema()
            llms[name] = get_llm_instance(
                settings, role=name, token_counter=counters[name],
                response_schema=response_schema,
            )
        reranker = None
        if settings.retrieval.use_rerank:
            config = settings.retrieval.reranker
            progress(f"Loading reranker {config.model} ({config.backend})")
            model = OnnxCrossEncoder(
                config.model, revision=config.revision, file_name=config.file_name,
                max_length=config.max_input_tokens, cache_dir=MODEL_CACHE,
            ) if config.backend == "onnx" else None
            reranker = CrossEncoderReRanker(
                model_name=config.model, model=model, revision=config.revision,
                max_length=config.max_input_tokens, batch_size=config.batch_size, device=config.device,
            )
        bm25 = settings.retrieval.bm25
        parents = {chunk.chunk_id: as_hit(chunk) for chunk in corpus.parents}
        vocabulary = {
            "document_type": sorted({chunk.metadata.document_type for chunk in corpus.chunks}),
            "legal_domain": sorted({domain for chunk in corpus.chunks for domain in chunk.metadata.legal_domain}),
        }
        pipeline = create_pipeline(
            settings, query_llm=llms["query_analyzer"], evaluation_llm=llms["retrieval_evaluator"],
            citation_llm=llms["citation_verifier"],
            answer_generator=AnswerGenerator(llms["answer_generator"], prompt_version=settings.llm.answer_generator.prompt_version),
            token_counter=counters["answer_generator"], parent_lookup=parents.get, metadata_vocabulary=vocabulary,
            bm25_retriever=BM25Retriever(corpus.chunks, k1=bm25.k1, b=bm25.b, tokenizer=bm25.tokenizer, lowercase=bm25.lowercase),
            vector_retriever=VectorRetriever(OllamaEmbedding(settings.embedding), vector),
            graph_retriever=GraphRetriever(graph, settings.retrieval.graph), reranker=reranker,
        )
        yield DemoRuntime(pipeline, corpus, vector, graph, counters["answer_generator"])
