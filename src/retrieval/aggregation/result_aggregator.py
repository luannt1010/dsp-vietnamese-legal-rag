"""Fuse candidates, preserve provenance, rerank, and apply the final cutoff."""

from collections.abc import Sequence

from pydantic import JsonValue

from core.exceptions import RetrievalError
from core.interfaces.base_reranker import BaseReRanker
from core.schemas import (
    LegalContext, QueryAnalysisResult, RetrievalRequest, RetrievalResult, RetrievedChunk,
)
from src.retrieval.common import matches_filters, positive_integer, unique_hits, validate_filters
from src.retrieval.hybrid.rrf import reciprocal_rank_fusion


class ResultAggregator:
    def __init__(self, *, rank_constant: int = 60, reranker: BaseReRanker | None = None):
        positive_integer(rank_constant, "rank_constant")
        self.rank_constant, self.reranker = rank_constant, reranker

    def aggregate(
        self,
        request: RetrievalRequest,
        rankings: Sequence[Sequence[RetrievedChunk]],
        *,
        use_rerank: bool = False,
        relations: list[dict[str, JsonValue]] | None = None,
    ) -> RetrievalResult:
        validate_filters(request.filters)
        if use_rerank and self.reranker is None:
            raise ValueError("reranking is enabled but no reranker was injected")
        filtered = [[hit for hit in branch if matches_filters(hit.metadata, request.filters)]
                    for branch in rankings]
        fused = reciprocal_rank_fusion(filtered, rank_constant=self.rank_constant)
        total = len(fused)
        candidates = fused[:request.candidate_k]
        if use_rerank and candidates:
            candidates = self._rerank(request, candidates)
        return RetrievalResult(
            query=request.query, results=candidates[:request.top_k],
            total_candidates=total, relations=relations or [],
        )

    def _rerank(self, request: RetrievalRequest, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        # Adapt to the existing BaseReRanker signature without changing core schemas.
        context = LegalContext(
            query=request.query, context_text="\n\n".join(hit.content for hit in hits),
            chunks=[hit.model_copy(deep=True) for hit in hits],
            cited_document_ids=list(dict.fromkeys(hit.document_id for hit in hits)),
        )
        analysis = QueryAnalysisResult(
            original_query=request.query, rewritten_query=request.query, intent="retrieval",
        )
        try:
            reranked = self.reranker.rerank(analysis, context, top_k=request.top_k)
            reranked = LegalContext.model_validate(reranked.model_dump())
            results = unique_hits(reranked.chunks)
            if not results or len(results) != len(reranked.chunks):
                raise ValueError("reranker must return nonempty, unique candidates")
            sources = {hit.chunk_id: hit for hit in hits}
            for hit in results:
                source = sources.get(hit.chunk_id)
                if source is None or (
                    hit.document_id != source.document_id or hit.content != source.content
                    or hit.metadata != source.metadata
                ):
                    raise ValueError("reranker changed the candidate source")
            return sorted(results, key=lambda hit: hit.score, reverse=True)
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("candidate reranking failed") from exc
