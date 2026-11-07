"""Bound concurrent inference and expose only verified public results."""

import logging
from time import perf_counter

from anyio import CapacityLimiter, WouldBlock
from starlette.concurrency import run_in_threadpool

from core.config import Settings
from src.api.schemas.corpus import CorpusResponse
from src.api.schemas.questions import FailureInfo, QuestionRequest, QuestionResponse
from src.runtime import DemoRuntime


logger = logging.getLogger(__name__)


class ServiceUnavailableError(Exception):
    """The runtime is not accepting questions."""


class ServiceBusyError(ServiceUnavailableError):
    """All inference slots are occupied; no unbounded request queue is kept."""


class RAGService:
    """One instance per worker, sharing the runtime but no question history.

    Admission happens before entering the thread pool. AnyIO waits for a
    synchronous worker to finish before releasing its slot on cancellation;
    a client disconnect cannot make a still-running model call look idle.
    The orchestrator continues to own deadlines, retries and verification.
    """

    def __init__(self, runtime: DemoRuntime, settings: Settings) -> None:
        self._pipeline = runtime.pipeline
        self._limiter = CapacityLimiter(settings.api.max_concurrent_requests)
        self.ready = True
        self.corpus = _corpus_response(runtime, settings)

    async def ask(self, question: QuestionRequest, *, request_id: str) -> QuestionResponse:
        if not self.ready:
            raise ServiceUnavailableError
        try:
            self._limiter.acquire_nowait()
        except WouldBlock:
            raise ServiceBusyError from None

        started = perf_counter()
        try:
            result = await run_in_threadpool(self._pipeline.run_with_trace, question)
            # Keep the orchestrator's fallback unchanged. Never publish drafts,
            # rejected contexts, internal analysis or evaluator reasoning.
            sources = result.context.chunks if result.status == "completed" and result.context else []
            failure = None
            if result.failure_stage or result.error_type:
                failure = FailureInfo(
                    stage=result.failure_stage,
                    code=result.failure_details.get("code", result.error_type or "pipeline_failed"),
                )
            response = QuestionResponse(
                request_id=request_id, status=result.status, answer=result.answer,
                sources=sources, corpus_id=self.corpus.corpus_id, rounds=len(result.rounds),
                duration_ms=(perf_counter() - started) * 1000, failure=failure,
            )
            logger.info(
                "rag_question request_id=%s status=%s rounds=%s duration_ms=%.2f failure_stage=%s code=%s",
                request_id, response.status, response.rounds, response.duration_ms,
                failure.stage if failure else None, failure.code if failure else None,
            )
            return response
        finally:
            self._limiter.release()


def _corpus_response(runtime: DemoRuntime, settings: Settings) -> CorpusResponse:
    """Read the prepared snapshot once, rather than scanning it per GET request."""
    corpus = runtime.corpus
    source = corpus.manifest["signature"]["source"]
    return CorpusResponse(
        corpus_id=corpus.corpus_id, source_type=settings.data_pipeline.source.type,
        dataset=source.get("dataset"), revision=source.get("revision"),
        topics=sorted({chunk.metadata.topic_title for chunk in corpus.chunks if chunk.metadata.topic_title}),
        subjects=sorted({chunk.metadata.subject_title for chunk in corpus.chunks if chunk.metadata.subject_title}),
        document_count=len({chunk.document_id for chunk in corpus.chunks}),
        chunk_count=len(corpus.chunks), parent_chunk_count=len(corpus.parents),
        relation_count=len(corpus.graph.relations),
        unresolved_reference_count=len(corpus.graph.unresolved),
    )
