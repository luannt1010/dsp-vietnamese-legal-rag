"""Wire existing components without selecting providers or creating mock adapters."""

from collections.abc import Callable

from core.config import Settings
from core.interfaces import BaseAnswerGenerator, BaseGraphRetriever, BaseLLM, BaseRetriever
from core.interfaces.base_reranker import BaseReRanker
from core.schemas import RetrievedChunk
from src.evaluation import RetrievalEvaluator
from src.generation import CitationVerifier, LegalContextBuilder
from src.orchestration.rag_pipeline import RAGPipeline
from src.preprocessing import MetadataFilter
from src.query_understanding import QueryAnalyzer
from src.retrieval.router import RetrievalRouter
from src.retrieval.service import RetrievalService


def create_pipeline(
    settings: Settings, *,
    query_llm: BaseLLM,
    evaluation_llm: BaseLLM,
    citation_llm: BaseLLM,
    answer_generator: BaseAnswerGenerator,
    token_counter: Callable[[str], int],
    bm25_retriever: BaseRetriever | None = None,
    vector_retriever: BaseRetriever | None = None,
    graph_retriever: BaseGraphRetriever | None = None,
    reranker: BaseReRanker | None = None,
    parent_lookup: Callable[[str], RetrievedChunk | None] | None = None,
    metadata_vocabulary: dict | None = None,
    provision_vocabulary: dict[str, list[str]] | None = None,
) -> RAGPipeline:
    """Compose selected adapters. Only enabled retrieval branches need adapters.

    Call settings.validate_runtime() before creating real provider adapters;
    fixture development can compose a pipeline without selecting real models.
    """
    return RAGPipeline(
        query_analyzer=QueryAnalyzer(
            query_llm, prompt_version=settings.llm.query_analyzer.prompt_version,
            metadata_vocabulary=metadata_vocabulary,
            provision_vocabulary=provision_vocabulary,
        ),
        metadata_filter=MetadataFilter(),
        retrieval_router=RetrievalRouter(settings.retrieval),
        retrieval_service=RetrievalService(
            bm25_retriever=bm25_retriever, vector_retriever=vector_retriever,
            graph_retriever=graph_retriever, reranker=reranker, settings=settings.retrieval,
        ),
        retrieval_evaluator=RetrievalEvaluator(
            evaluation_llm, prompt_version=settings.llm.retrieval_evaluator.prompt_version, settings=settings.retrieval,
        ),
        context_builder=LegalContextBuilder(
            token_counter=token_counter, settings=settings.context, parent_lookup=parent_lookup,
        ),
        answer_generator=answer_generator,
        citation_verifier=CitationVerifier(citation_llm, prompt_version=settings.llm.citation_verifier.prompt_version),
        settings=settings.pipeline,
    )
