"""Retrieval-only coordination; evaluation, retries and fallback belong upstream."""

from pydantic import JsonValue

from core.config.settings import RetrievalSettings
from core.filtering import supported_relations
from core.exceptions import RetrievalError
from core.interfaces import BaseGraphRetriever, BaseRetriever
from core.interfaces.base_reranker import BaseReRanker
from core.schemas import (
    GraphRetrievalRequest, GraphRetrievalResult, RetrievalRequest, RetrievalResult, RetrievalStrategy,
)
from src.retrieval.aggregation.result_aggregator import ResultAggregator
from src.retrieval.common import matches_filters, unique_hits, validate_filters
from src.retrieval.hybrid.hybrid import collect_candidates


class RetrievalService:
    def __init__(
        self, *, bm25_retriever: BaseRetriever | None = None,
        vector_retriever: BaseRetriever | None = None,
        graph_retriever: BaseGraphRetriever | None = None,
        reranker: BaseReRanker | None = None,
        settings: RetrievalSettings | None = None,
    ):
        self.settings = settings or RetrievalSettings()
        self.bm25_retriever, self.vector_retriever = bm25_retriever, vector_retriever
        self.graph_retriever = graph_retriever
        self.aggregator = ResultAggregator(
            rank_constant=self.settings.rrf.rank_constant, reranker=reranker,
        )

    def retrieve(
        self, query: str, filters: dict[str, JsonValue] | None = None,
        strategy: RetrievalStrategy | None = None, *, entities: list[str] | None = None,
    ) -> RetrievalResult:
        selected = self.settings.validate_strategy(strategy or self.settings.default_strategy())
        request = RetrievalRequest(
            query=query, filters=filters or {}, top_k=selected.top_k, candidate_k=selected.candidate_k,
        )
        validate_filters(request.filters)
        for enabled, adapter, name in (
            (selected.use_bm25, self.bm25_retriever, "BM25"),
            (selected.use_vector, self.vector_retriever, "vector"),
            (selected.use_graph, self.graph_retriever, "graph"),
            (selected.use_rerank, self.aggregator.reranker, "reranker"),
        ):
            if enabled and adapter is None:
                raise ValueError(f"{name} is enabled but no adapter was injected")
        rankings = []
        if selected.use_bm25:
            rankings.append(collect_candidates(self.bm25_retriever, request))
        if selected.use_vector:
            rankings.append(collect_candidates(self.vector_retriever, request))
        relations = []
        if selected.use_graph:
            seeds = list(dict.fromkeys(
                hit.document_id for branch in rankings for hit in branch
                if matches_filters(hit.metadata, request.filters)
            ))
            graph_request = GraphRetrievalRequest(
                query=request.query, entities=entities or [], seed_document_ids=seeds,
                max_depth=self.settings.graph.max_depth,
            )
            try:
                graph = self.graph_retriever.search(graph_request)
                graph = GraphRetrievalResult.model_validate(graph.model_dump())
            except RetrievalError:
                raise
            except Exception as exc:
                raise RetrievalError("graph retrieval failed") from exc
            graph_hits = unique_hits(
                hit for hit in graph.results if matches_filters(hit.metadata, request.filters)
            )[:self.settings.graph.max_nodes]
            rankings.append(graph_hits)
            # A relation must not reintroduce documents/evidence excluded by filters.
            allowed_hits = [hit for branch in rankings for hit in branch
                            if matches_filters(hit.metadata, request.filters)]
            relations = list(supported_relations(graph.relations, allowed_hits))
        return self.aggregator.aggregate(
            request, rankings, use_rerank=selected.use_rerank, relations=relations,
        )
