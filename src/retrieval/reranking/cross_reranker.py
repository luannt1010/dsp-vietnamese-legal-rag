"""Lazy, injectable cross-encoder implementing the existing reranker contract."""

from math import isfinite
from typing import Protocol

from core.exceptions import RetrievalError
from core.interfaces.base_reranker import BaseReRanker
from core.schemas import LegalContext, QueryAnalysisResult
from src.retrieval.common import positive_integer, scored_hit, unique_hits


class CrossEncoderModel(Protocol):
    def predict(self, pairs: list[tuple[str, str]], *, batch_size: int): ...


class CrossEncoderReRanker(BaseReRanker):
    def __init__(
        self,
        model_name: str | None = None,
        max_length: int = 512,
        batch_size: int = 16,
        device: str = "auto",
        *,
        revision: str | None = None,
        model: CrossEncoderModel | None = None,
    ):
        positive_integer(max_length, "max_length")
        positive_integer(batch_size, "batch_size")
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu or cuda")
        if model is None and (model_name is None or not model_name.strip()):
            raise ValueError("select a cross-encoder model_name or inject a model")
        self.max_length, self.batch_size = max_length, batch_size
        self.model_name, self.device, self.revision = model_name, device, revision
        self.model = model

    @property
    def reranker(self) -> CrossEncoderModel:
        if self.model is None:
            try:
                from sentence_transformers import CrossEncoder

                self.model = CrossEncoder(
                    self.model_name, device=None if self.device == "auto" else self.device,
                    max_length=self.max_length, revision=self.revision,
                )
            except Exception as exc:
                raise RetrievalError("could not load cross-encoder; install the reranking extra and check model config") from exc
        return self.model

    def _compute_score(self, query: str, contents: list[str]) -> list[float]:
        try:
            raw = self.reranker.predict(
                [(query, content) for content in contents], batch_size=self.batch_size,
            )
            if hasattr(raw, "tolist"):
                raw = raw.tolist()
            if len(raw) != len(contents):
                raise ValueError("cross-encoder returned the wrong number of scores")
            scores = []
            for value in raw:
                # Accept N and N x 1, reject multi-class predictions.
                if isinstance(value, (list, tuple)):
                    if len(value) != 1:
                        raise ValueError("cross-encoder must return one score per pair")
                    value = value[0]
                if isinstance(value, (bool, str)):
                    raise ValueError("cross-encoder returned a nonnumeric score")
                score = float(value)
                if not isfinite(score):
                    raise ValueError("cross-encoder returned a nonfinite score")
                scores.append(score)
            return scores
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("cross-encoder prediction failed") from exc

    def rerank(
        self, query: QueryAnalysisResult, documents: LegalContext, top_k: int = 5,
    ) -> LegalContext:
        positive_integer(top_k, "top_k")
        chunks = unique_hits(documents.chunks)
        if chunks:
            scores = self._compute_score(query.rewritten_query, [chunk.content for chunk in chunks])
            chunks = [scored_hit(chunk, score, "cross_encoder") for chunk, score in zip(chunks, scores)]
            chunks.sort(key=lambda chunk: chunk.score, reverse=True)
        chunks = chunks[:top_k]
        return LegalContext(
            query=documents.query, context_text="\n\n".join(chunk.content for chunk in chunks),
            chunks=chunks,
            cited_document_ids=list(dict.fromkeys(chunk.document_id for chunk in chunks)),
        )
