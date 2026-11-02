"""BM25 + vector candidates -> RRF -> optional cross-encoder -> top_k."""

from core.exceptions import EmbeddingError, RetrievalError
from core.interfaces import BaseRetriever
from core.interfaces.base_reranker import BaseReRanker
from core.schemas import RetrievalRequest, RetrievedChunk
from src.retrieval.aggregation.result_aggregator import ResultAggregator
from src.retrieval.common import unique_hits, validate_filters


def collect_candidates(retriever: BaseRetriever, request: RetrievalRequest) -> list[RetrievedChunk]:
    """Each branch follows BaseRetriever's top_k contract at candidate depth."""
    branch_request = RetrievalRequest(
        query=request.query, filters=request.filters,
        top_k=request.candidate_k, candidate_k=request.candidate_k,
    )
    try:
        return unique_hits(retriever.search(branch_request))[:request.candidate_k]
    except (EmbeddingError, RetrievalError, ValueError):
        raise
    except Exception as exc:
        raise RetrievalError("retrieval branch failed") from exc


class HybridRetriever(BaseRetriever):
    def __init__(
        self,
        bm25_retriever: BaseRetriever | None = None,
        vector_retriever: BaseRetriever | None = None,
        *,
        reranker: BaseReRanker | None = None,
        rank_constant: int = 60,
    ):
        if bm25_retriever is None and vector_retriever is None:
            raise ValueError("hybrid search requires at least one retriever")
        self.retrievers = [retriever for retriever in (bm25_retriever, vector_retriever)
                           if retriever is not None]
        self.aggregator = ResultAggregator(rank_constant=rank_constant, reranker=reranker)
        self.use_rerank = reranker is not None

    def search(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        validate_filters(request.filters)
        rankings = [collect_candidates(retriever, request) for retriever in self.retrievers]
        return self.aggregator.aggregate(
            request, rankings, use_rerank=self.use_rerank,
        ).results
