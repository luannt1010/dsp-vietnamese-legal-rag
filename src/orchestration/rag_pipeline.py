"""Coordinate the RAG pipeline and feedback loop from specification section 6."""

import logging
from collections.abc import Callable
from typing import TypeVar

from pydantic import JsonValue

from core.config.settings import PipelineSettings
from core.deadline import remaining_timeout, request_deadline
from core.filtering import supported_relations
from core.schemas.orchestration import PipelineRunOptions
from core.exceptions import CitationVerificationError, InsufficientEvidenceError, RAGError
from core.interfaces import (
    BaseAnswerGenerator, BaseCitationVerifier, BaseEvaluator, BaseLegalContextBuilder,
    BaseMetadataFilter, BaseQueryAnalyzer, BaseRetrievalRouter,
)
from core.schemas import (
    AnswerGenerationRequest, ContextBuilderRequest, LegalAnswer, LegalContext,
    MetadataFilterRequest, MetadataFilterResult, PipelineResult, PipelineStatus,
    QueryAnalysisResult, QueryRequest, RetrievalEvaluationRequest, RetrievalEvaluationResult,
    RetrievalResult, RetrievalRound, RetrievalRouteRequest, RetrievalStrategy,
)
from src.retrieval.service import RetrievalService
from src.retrieval.common import prioritize_context_sources
from src.observability.telemetry import set_round, span


_logger = logging.getLogger(__name__)
_T = TypeVar("_T")
_FALLBACK_MESSAGES = {
    "insufficient_evidence": "Chưa đủ căn cứ từ các nguồn đã truy xuất để trả lời câu hỏi này.",
    "failed": "Hệ thống chưa thể hoàn tất việc kiểm tra căn cứ. Vui lòng thử lại sau.",
    "timed_out": "Đã hết thời gian xử lý trước khi xác minh đầy đủ căn cứ cho câu trả lời.",
}


class RAGPipeline:
    """Inject modules once; keep query, overrides and history local to each run."""

    def __init__(
        self, *,
        query_analyzer: BaseQueryAnalyzer,
        metadata_filter: BaseMetadataFilter,
        retrieval_router: BaseRetrievalRouter,
        retrieval_service: RetrievalService,
        retrieval_evaluator: BaseEvaluator,
        context_builder: BaseLegalContextBuilder,
        answer_generator: BaseAnswerGenerator,
        citation_verifier: BaseCitationVerifier,
        settings: PipelineSettings | None = None,
    ) -> None:
        self._query_analyzer = query_analyzer
        self._metadata_filter = metadata_filter
        self._retrieval_router = retrieval_router
        self._retrieval_service = retrieval_service
        self._retrieval_evaluator = retrieval_evaluator
        self._context_builder = context_builder
        self._answer_generator = answer_generator
        self._citation_verifier = citation_verifier
        self._settings = settings or PipelineSettings()

    def run(self, request: QueryRequest) -> LegalAnswer:
        """Return the verified answer, or an explicit fallback with no citations."""
        return self.run_with_trace(request).answer

    def run_with_trace(
        self, request: QueryRequest, *, options: PipelineRunOptions | None = None,
        analysis: QueryAnalysisResult | None = None,
    ) -> PipelineResult:
        """Keep every round's query, strategy, results and evaluation reason.

        Invalid caller input raises ValidationError. Expected component/runtime
        failures produce a fallback; programming errors are not silently hidden.
        """
        request = QueryRequest.model_validate(request.model_dump())
        options = PipelineRunOptions.model_validate((options or PipelineRunOptions()).model_dump())
        if analysis is not None:
            analysis = QueryAnalysisResult.model_validate(analysis.model_dump())
            if analysis.original_query != request.query:
                raise ValueError("replayed analysis belongs to another question")
        rounds: list[RetrievalRound] = []
        context = None
        draft = None
        filters: dict[str, JsonValue] = {}
        stage = "analysis"
        with request_deadline(self._settings.timeout_s), span("pipeline"):
            try:
                if analysis is None:
                    analysis = QueryAnalysisResult.model_validate(
                        _call(self._query_analyzer.analyze, request, span_name="analysis").model_dump(),
                    )
                stage = "metadata_filtering"
                filters = MetadataFilterResult.model_validate(_call(
                    self._metadata_filter.build_filters,
                    MetadataFilterRequest(metadata=analysis.metadata),
                    span_name="metadata_filtering",
                ).model_dump()).filters
                current_query = analysis.rewritten_query
                overrides: dict[str, JsonValue] = {}

                for iteration in range(self._settings.max_iterations):
                    set_round(iteration)
                    context = None  # A failed retry must not expose a previous round's context.
                    # Return through the router on every feedback round. Partial
                    # overrides persist; a later override replaces only its keys.
                    stage = "routing"
                    routed = _call(self._retrieval_router.route, RetrievalRouteRequest(
                        query=current_query, intent=analysis.intent,
                        filters=filters, entities=analysis.entities,
                    ), span_name="routing")
                    strategy = self._retrieval_service.settings.validate_strategy(
                        RetrievalStrategy.model_validate({**routed.model_dump(), **overrides,
                            **({"top_k": options.ranking_k} if options.ranking_k is not None else {})}),
                    )
                    record = RetrievalRound(
                        iteration=iteration, query=current_query,
                        strategy=strategy.model_copy(deep=True),
                    )
                    rounds.append(record)

                    stage = "retrieval"
                    with request_deadline(self._retrieval_service.settings.timeout_s):
                        retrieved = RetrievalResult.model_validate(_call(
                            self._retrieval_service.retrieve,
                            query=current_query, filters=filters, strategy=strategy,
                            entities=analysis.entities,
                            span_name="retrieval",
                        ).model_dump())
                    record.retrieval_result = retrieved.model_copy(deep=True)

                    # Preserve the full ranking for retrieval metrics. Select the
                    # bounded candidates, then evaluate exactly the packed context.
                    if options.context_top_k is not None:
                        hits = prioritize_context_sources(retrieved.results, request.query)[:options.context_top_k]
                        retrieved = RetrievalResult(
                            query=retrieved.query, results=hits, total_candidates=retrieved.total_candidates,
                            relations=list(supported_relations(retrieved.relations, hits)),
                        )

                    stage = "context"
                    evidence = retrieved
                    if retrieved.results:
                        context = LegalContext.model_validate(_call(
                            self._context_builder.build,
                            ContextBuilderRequest(retrieval_result=retrieved, original_query=request.query),
                            span_name="context",
                        ).model_dump())
                        if not context.chunks or not context.context_text.strip():
                            raise InsufficientEvidenceError("context contains no usable evidence")
                        evidence = RetrievalResult(
                            query=retrieved.query, results=context.chunks,
                            total_candidates=retrieved.total_candidates,
                            relations=list(supported_relations(retrieved.relations, context.chunks)),
                        )

                    stage = "evaluation"
                    evaluation = RetrievalEvaluationResult.model_validate(_call(
                        self._retrieval_evaluator.evaluate,
                        RetrievalEvaluationRequest(
                            original_query=request.query, current_query=current_query,
                            retrieval_result=evidence.model_copy(deep=True),
                            iteration=iteration, max_iterations=self._settings.max_iterations,
                        ),
                        span_name="evaluation",
                    ).model_dump())
                    record.evaluation = evaluation.model_copy(deep=True)

                    # An empty retrieval can never authorize generation, even if
                    # a custom evaluator incorrectly calls it sufficient.
                    if evaluation.is_relevant and evaluation.is_sufficient:
                        if retrieved.results:
                            break
                        return _fallback("insufficient_evidence", rounds, query=request.query, analysis=analysis, filters=filters, context=context)
                    if evaluation.next_action == "stop" or iteration == self._settings.max_iterations - 1:
                        return _fallback("insufficient_evidence", rounds, query=request.query, analysis=analysis, filters=filters, context=context)
                    if evaluation.next_action == "refine_query":
                        current_query = evaluation.refined_query or current_query
                    elif evaluation.next_action == "change_strategy":
                        if not options.allow_strategy_changes:
                            return _fallback("insufficient_evidence", rounds, query=request.query, analysis=analysis, filters=filters, context=context)
                        overrides.update(evaluation.strategy_override)

                stage = "generation"
                answer = LegalAnswer.model_validate(_call(
                    self._answer_generator.generate,
                    AnswerGenerationRequest(context=context.model_copy(deep=True), query=request.query),
                    span_name="generation",
                ).model_dump())
                draft = answer.model_copy(deep=True)
                stage = "verification"
                verified = LegalAnswer.model_validate(_call(
                    self._citation_verifier.verify, answer, context, span_name="verification",
                ).model_dump())
                return PipelineResult(answer=verified, status="completed", rounds=rounds, query=request.query,
                                      analysis=analysis, filters=filters, context=context, draft_answer=draft)
            except (RAGError, ValueError, TimeoutError) as exc:
                if isinstance(exc, TimeoutError):
                    status = "timed_out"
                elif isinstance(exc, InsufficientEvidenceError):
                    status = "insufficient_evidence"
                else:
                    status = "failed"
                # Do not log query text, source content, credentials or raw
                # provider error messages. Detailed history is explicitly returned.
                details = _failure_details(exc)
                _logger.warning("rag_pipeline_failed stage=%s error_type=%s code=%s cause_type=%s",
                                stage, type(exc).__name__, details["code"], details.get("cause_type", "none"))
                _logger.debug("rag_pipeline_failure_details", exc_info=True)
                return _fallback(status, rounds, stage=stage, error_type=type(exc).__name__, query=request.query,
                                 analysis=analysis, filters=filters, context=context, draft=draft, failure_details=details)


def _call(operation: Callable[..., _T], *args, span_name: str = "operation", **kwargs) -> _T:
    """Check the shared deadline before and after a synchronous component call."""
    remaining_timeout()
    try:
        with span(span_name):
            return operation(*args, **kwargs)
    finally:
        remaining_timeout()


def _fallback(
    status: PipelineStatus, rounds: list[RetrievalRound], *,
    stage: str | None = None, error_type: str | None = None,
    analysis: QueryAnalysisResult | None = None, filters: dict[str, JsonValue] | None = None,
    query: str | None = None,
    context: LegalContext | None = None, draft: LegalAnswer | None = None,
    failure_details: dict[str, str] | None = None,
) -> PipelineResult:
    return PipelineResult(
        answer=LegalAnswer(
            answer=_FALLBACK_MESSAGES[status], citations=[], confidence=0.0,
            disclaimer="Chưa có kết luận pháp lý được xác minh cho câu hỏi này.",
        ),
        status=status, rounds=rounds, failure_stage=stage, error_type=error_type,
        query=query, analysis=analysis, filters=filters or {},
        context=context, draft_answer=draft,
        failure_details=failure_details or {},
    )


def _failure_details(exc: Exception) -> dict[str, str]:
    """Keep diagnostic codes and explicit verifier reasons, not raw provider errors."""
    details = {"code": getattr(exc, "code", type(exc).__name__)}
    if exc.__cause__ is not None:
        details["cause_type"] = type(exc.__cause__).__name__
    if isinstance(exc, CitationVerificationError):
        details["message"] = str(exc)[:1000]
        if exc.reason:
            details["reason"] = exc.reason[:1000]
    return details
