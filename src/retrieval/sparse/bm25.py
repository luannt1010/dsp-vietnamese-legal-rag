"""In-memory BM25 index using the same normalization at index/query time."""

from collections.abc import Callable, Iterable
from math import isfinite
import re
import unicodedata

from rank_bm25 import BM25Okapi

from core.exceptions import RetrievalError
from core.interfaces import BaseRetriever
from core.schemas import LegalChunk, RetrievalRequest, RetrievalResult, RetrievedChunk
from src.retrieval.common import matches_filters, scored_hit, snapshot_documents, validate_filters


def tokenize(text: str) -> list[str]:
    """Unicode word baseline retained for callers of the original helper."""
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFC", text).lower())


class BM25Retriever(BaseRetriever):
    def __init__(
        self,
        documents: Iterable[LegalChunk | RetrievedChunk] | RetrievalResult,
        k1: float = 1.2,
        b: float = 0.75,
        *,
        tokenizer: str | Callable[[str], list[str]] = "whitespace",
        lowercase: bool = True,
    ):
        if not isfinite(k1) or k1 <= 0 or not isfinite(b) or not 0 <= b <= 1:
            raise ValueError("require finite k1 > 0 and 0 <= b <= 1")
        if isinstance(tokenizer, str):
            if tokenizer == "whitespace":
                self._tokenizer = str.split
            elif tokenizer == "word":
                self._tokenizer = lambda text: re.findall(r"[^\W_]+", text)
            else:
                raise ValueError(f"unsupported BM25 tokenizer: {tokenizer}")
        elif callable(tokenizer):
            self._tokenizer = tokenizer
        else:
            raise ValueError("tokenizer must be a supported name or callable")
        self.k1, self.b, self.lowercase = k1, b, lowercase
        self.documents = snapshot_documents(documents)
        self.indexed_documents: list[RetrievedChunk] = []
        self._terms: list[set[str]] = []
        tokenized = []
        for chunk in self.documents:
            tokens = self._tokenize(chunk.content)
            if tokens:
                self.indexed_documents.append(chunk)
                self._terms.append(set(tokens))
                tokenized.append(tokens)
        try:
            self.bm25 = BM25Okapi(tokenized, k1=k1, b=b) if tokenized else None
        except Exception as exc:
            raise RetrievalError("could not build BM25 index") from exc

    def _tokenize(self, text: str) -> list[str]:
        text = unicodedata.normalize("NFC", text)
        return self._tokenizer(text.lower() if self.lowercase else text)

    def search(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        validate_filters(request.filters)
        try:
            tokens = self._tokenize(request.query)
            if self.bm25 is None or not tokens:
                return []
            terms = set(tokens)
            # Zero/negative Okapi IDF does not imply a lack of lexical matches.
            indices = [
                index for index, hit in enumerate(self.indexed_documents)
                if terms.intersection(self._terms[index])
                and matches_filters(hit.metadata, request.filters)
            ]
            scores = self.bm25.get_scores(tokens)
            indices.sort(key=lambda index: (-float(scores[index]), index))
            return [scored_hit(self.indexed_documents[i], float(scores[i]), "bm25")
                    for i in indices[:request.top_k]]
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("BM25 search failed") from exc


# Keep the name already used by the unfinished implementation.
BM25Lib = BM25Retriever
