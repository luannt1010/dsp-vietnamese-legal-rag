"""Public abstract contracts. Concrete module classes inherit these ABCs."""

from core.interfaces.base_answer_generator import BaseAnswerGenerator
from core.interfaces.base_citation_verifier import BaseCitationVerifier
from core.interfaces.base_context_builder import BaseLegalContextBuilder
from core.interfaces.base_embedding import BaseEmbedding
from core.interfaces.base_evaluator import BaseEvaluator
from core.interfaces.base_graph_retriever import BaseGraphRetriever
from core.interfaces.base_llm import BaseLLM
from core.interfaces.base_metadata_filter import BaseMetadataFilter
from core.interfaces.base_query_analyzer import BaseQueryAnalyzer
from core.interfaces.base_retrieval_router import BaseRetrievalRouter
from core.interfaces.base_retriever import BaseRetriever
from core.interfaces.base_reranker import BaseReRanker

__all__ = [
    "BaseAnswerGenerator", "BaseCitationVerifier", "BaseEmbedding", "BaseEvaluator",
    "BaseGraphRetriever", "BaseLLM", "BaseLegalContextBuilder", "BaseMetadataFilter",
    "BaseQueryAnalyzer", "BaseRetrievalRouter", "BaseRetriever", "BaseReRanker",
]
