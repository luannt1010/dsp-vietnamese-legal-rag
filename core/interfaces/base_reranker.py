from abc import abstractmethod, ABC
from core.schemas.context import LegalContext
from core.schemas.query import  QueryAnalysisResult

class BaseReRanker(ABC):

    @abstractmethod
    def rerank(self, query: QueryAnalysisResult, documents: LegalContext, top_k: int = 5) -> LegalContext:
        """Return a new context with up to top_k unique chunks ordered by score.

        Preserve source IDs, text and metadata. Rebuild context_text and
        cited_document_ids from the retained chunks. Failures raise RetrievalError.
        """
        raise NotImplementedError
