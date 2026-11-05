"""Feedback, generation gates, request history and shared deadline integration."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError

from core.config.settings import PipelineSettings, RetrievalSettings
from core.deadline import remaining_timeout, request_deadline
from core.exceptions import CitationVerificationError, InsufficientEvidenceError, LLMError, LLMOutputTruncatedError, RetrievalError
from core.interfaces import BaseEvaluator, BaseQueryAnalyzer
from core.schemas import (
    LegalAnswer, LegalContext, PipelineResult, QueryAnalysisResult, QueryRequest,
    RetrievalEvaluationResult, RetrievalRequest,
)
from examples.contract_demo import MockAnswerGenerator, MockRetriever
from examples.orchestration_demo import FixtureLLM, build_demo_pipeline
from src.generation import CitationVerifier, LegalContextBuilder
from src.orchestration import RAGPipeline
from src.preprocessing import MetadataFilter
from src.retrieval.router import RetrievalRouter
from src.retrieval.service import RetrievalService
from src.retrieval.sparse import BM25Retriever


def feedback(action="continue", **changes):
    return RetrievalEvaluationResult(**{
        "is_relevant": True, "is_sufficient": action == "continue", "confidence": 0.8,
        "next_action": action, "reason": f"Fixture verdict: {action}", **changes,
    })


def setup_pipeline(evaluations=None, *, settings=None):
    """Use real local modules with spies; replace only analysis/evaluation verdicts."""
    sources = MockRetriever().search(RetrievalRequest(query="giả lập"))
    retrieval_settings = RetrievalSettings(use_vector=False, use_rerank=False)
    parts = SimpleNamespace(
        analyzer=Mock(spec=BaseQueryAnalyzer),
        metadata_filter=Mock(wraps=MetadataFilter()),
        router=Mock(wraps=RetrievalRouter(retrieval_settings)),
        service=RetrievalService(bm25_retriever=BM25Retriever(sources), settings=retrieval_settings),
        evaluator=Mock(spec=BaseEvaluator),
        context=Mock(wraps=LegalContextBuilder(token_counter=len)),
        generator=Mock(wraps=MockAnswerGenerator()),
        verifier=Mock(wraps=CitationVerifier(FixtureLLM({"is_supported": True, "reason": "fixture"}))),
    )
    parts.analyzer.analyze.return_value = QueryAnalysisResult(
        original_query="Câu hỏi gốc", rewritten_query="giả lập", intent="legal_lookup",
        entities=["mock-document"], metadata={"document_type": ["mock"]},
    )
    parts.evaluator.evaluate.side_effect = evaluations if evaluations is not None else [feedback()]
    parts.service.retrieve = Mock(wraps=parts.service.retrieve)
    parts.pipeline = RAGPipeline(
        query_analyzer=parts.analyzer, metadata_filter=parts.metadata_filter,
        retrieval_router=parts.router, retrieval_service=parts.service,
        retrieval_evaluator=parts.evaluator, context_builder=parts.context,
        answer_generator=parts.generator, citation_verifier=parts.verifier, settings=settings,
    )
    return parts


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.request = QueryRequest(query="Câu hỏi gốc", conversation_id="conversation-a")

    def test_success_follows_pipeline_order_and_preserves_original_question(self):
        parts = setup_pipeline()
        calls = Mock()
        for component, method, name in (
            (parts.analyzer, "analyze", "analysis"),
            (parts.metadata_filter, "build_filters", "filter"),
            (parts.router, "route", "route"), (parts.service, "retrieve", "retrieve"),
            (parts.evaluator, "evaluate", "evaluate"), (parts.context, "build", "context"),
            (parts.generator, "generate", "generate"), (parts.verifier, "verify", "verify"),
        ):
            calls.attach_mock(getattr(component, method), name)
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.query, self.request.query)
        self.assertEqual(result.analysis.original_query, self.request.query)
        self.assertEqual(result.filters, {"document_type": ["mock"]})
        self.assertEqual([call[0] for call in calls.mock_calls], [
            "analysis", "filter", "route", "retrieve", "context", "evaluate", "generate", "verify",
        ])
        self.assertEqual(parts.analyzer.analyze.call_args.args[0], self.request)
        self.assertEqual(parts.generator.generate.call_args.args[0].query, self.request.query)
        self.assertEqual(parts.context.build.call_args.args[0].original_query, self.request.query)
        self.assertEqual(result.rounds[0].evaluation.reason, "Fixture verdict: continue")
        self.assertEqual(result.answer.confidence, 0.0)  # Not the evaluation confidence or RRF score.
        self.assertEqual(PipelineResult.model_validate_json(result.model_dump_json()), result)

    def test_refinement_returns_to_router_and_preserves_filter_scope(self):
        parts = setup_pipeline([feedback("refine_query", refined_query="nội dung"), feedback()])
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "completed")
        self.assertEqual([record.query for record in result.rounds], ["giả lập", "nội dung"])
        self.assertEqual(parts.router.route.call_count, 2)
        for index, call in enumerate(parts.evaluator.evaluate.call_args_list):
            self.assertEqual(call.args[0].original_query, self.request.query)
            self.assertEqual(call.args[0].iteration, index)
            self.assertEqual(call.args[0].max_iterations, 3)
        for call in parts.service.retrieve.call_args_list:
            self.assertEqual(call.kwargs["filters"], {"document_type": ["mock"]})
            self.assertEqual(call.kwargs["entities"], ["mock-document"])
        parts.analyzer.analyze.assert_called_once()
        parts.metadata_filter.build_filters.assert_called_once()

    def test_partial_strategy_changes_accumulate_and_pass_hard_limits(self):
        parts = setup_pipeline([
            feedback("change_strategy", strategy_override={"top_k": 2}),
            feedback("change_strategy", strategy_override={"candidate_k": 30}), feedback(),
        ])
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "completed")
        self.assertEqual([record.strategy.top_k for record in result.rounds], [5, 2, 2])
        self.assertEqual([record.strategy.candidate_k for record in result.rounds], [20, 20, 30])
        self.assertEqual(parts.router.route.call_count, 3)

    def test_strategy_changes_survive_a_later_query_refinement(self):
        parts = setup_pipeline([
            feedback("change_strategy", strategy_override={"top_k": 2}),
            feedback("refine_query", refined_query="nội dung"), feedback(),
        ])
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.rounds[2].query, "nội dung")
        self.assertEqual(result.rounds[2].strategy.top_k, 2)

    def test_iteration_limit_counts_total_retrieval_rounds(self):
        parts = setup_pipeline(
            [feedback("refine_query", refined_query="nội dung")] * 2,
            settings=PipelineSettings(max_iterations=2),
        )
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(len(result.rounds), 2)
        self.assertEqual(parts.service.retrieve.call_count, 2)
        self.assertEqual(parts.context.build.call_count, 2)
        self.assertIsNotNone(result.context)  # Retain the evidence the gate actually rejected.
        parts.generator.generate.assert_not_called()
        parts.verifier.verify.assert_not_called()
        self.assertEqual(result.answer.citations, [])
        self.assertEqual(result.answer.confidence, 0.0)

    def test_stop_exits_without_generation(self):
        parts = setup_pipeline([feedback("stop")])
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(len(result.rounds), 1)
        parts.generator.generate.assert_not_called()

    def test_empty_results_never_authorize_generation(self):
        parts = setup_pipeline()
        parts.analyzer.analyze.return_value.rewritten_query = "khôngkhớp"
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.rounds[0].retrieval_result.results, [])
        self.assertTrue(result.rounds[0].evaluation.is_sufficient)
        self.assertEqual(result.status, "insufficient_evidence")
        parts.generator.generate.assert_not_called()

    def test_empty_results_may_be_refined_when_evaluator_requests_it(self):
        parts = setup_pipeline([feedback("refine_query", refined_query="giả lập"), feedback()])
        parts.analyzer.analyze.return_value.rewritten_query = "khôngkhớp"
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.rounds[0].retrieval_result.results, [])
        self.assertTrue(result.rounds[1].retrieval_result.results)

    def test_invalid_override_fails_before_another_retrieval(self):
        for override in (
            {"top_k": 21}, {"candidate_k": 101}, {"top_k": 0},
            {"use_bm25": False}, {"topk": 2}, {"top_k": 20, "candidate_k": 10},
        ):
            with self.subTest(override=override):
                parts = setup_pipeline([feedback("change_strategy", strategy_override=override)])
                result = parts.pipeline.run_with_trace(self.request)
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.failure_stage, "routing")
                self.assertEqual(parts.service.retrieve.call_count, 1)
                parts.generator.generate.assert_not_called()

    def test_unsupported_metadata_does_not_trigger_unfiltered_retry(self):
        parts = setup_pipeline()
        parts.analyzer.analyze.return_value.metadata["as_of_date"] = "2020-01-01"
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_stage, "metadata_filtering")
        parts.service.retrieve.assert_not_called()

    def test_component_failures_return_safe_fallback_and_keep_partial_history(self):
        for component, method, stage, failure in (
            ("analyzer", "analyze", "analysis", LLMError("secret provider detail")),
            ("router", "route", "routing", ValueError("bad route")),
            ("service", "retrieve", "retrieval", RetrievalError("database failed")),
            ("evaluator", "evaluate", "evaluation", LLMError("judge failed")),
            ("context", "build", "context", InsufficientEvidenceError("budget too small")),
            ("generator", "generate", "generation", LLMError("generation failed")),
            ("generator", "generate", "generation", LLMOutputTruncatedError("truncated at 1024 tokens")),
            ("verifier", "verify", "verification", CitationVerificationError("invented citation")),
        ):
            with self.subTest(stage=stage):
                parts = setup_pipeline()
                getattr(getattr(parts, component), method).side_effect = failure
                with self.assertLogs("src.orchestration.rag_pipeline", level="WARNING") as logs:
                    result = parts.pipeline.run_with_trace(self.request)
                self.assertEqual(result.failure_stage, stage)
                self.assertEqual(result.error_type, type(failure).__name__)
                self.assertEqual(result.answer.citations, [])
                self.assertEqual(result.answer.confidence, 0.0)
                self.assertNotIn(str(failure), result.answer.answer)
                self.assertNotIn(str(failure), " ".join(logs.output))
                self.assertNotIn(self.request.query, " ".join(logs.output))
                self.assertEqual(
                    result.status, "insufficient_evidence" if stage == "context" else "failed",
                )
                if stage == "retrieval":
                    self.assertIsNone(result.rounds[0].retrieval_result)
                if stage == "evaluation":
                    self.assertIsNotNone(result.rounds[0].retrieval_result)
                    self.assertIsNone(result.rounds[0].evaluation)

    def test_empty_context_is_rejected_before_generation(self):
        parts = setup_pipeline()
        parts.context.build.return_value = LegalContext(query=self.request.query, context_text="")
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "insufficient_evidence")
        parts.generator.generate.assert_not_called()

    def test_invalid_evaluation_is_revalidated_and_cannot_bypass_generation_gate(self):
        invalid = feedback().model_copy(update={"next_action": "stop"})
        parts = setup_pipeline([invalid])
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_stage, "evaluation")
        parts.generator.generate.assert_not_called()

    def test_evaluator_cannot_mutate_source_history_or_generation_evidence(self):
        parts = setup_pipeline()

        def evaluate(request):
            request.retrieval_result.results[0].content = "Mutated evaluator input"
            return feedback()

        parts.evaluator.evaluate.side_effect = evaluate
        result = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "completed")
        self.assertNotEqual(result.rounds[0].retrieval_result.results[0].content, "Mutated evaluator input")
        self.assertNotEqual(result.answer.citations[0].quoted_text, "Mutated evaluator input")

    def test_generator_cannot_mutate_context_used_by_verifier(self):
        parts = setup_pipeline()

        def generate(request):
            result = MockAnswerGenerator().generate(request)
            request.context.chunks[0].content = "Mutated generator input"
            return result

        parts.generator.generate.side_effect = generate
        self.assertEqual(parts.pipeline.run_with_trace(self.request).status, "completed")

    def test_overrides_and_history_do_not_leak_between_requests(self):
        parts = setup_pipeline([
            feedback("change_strategy", strategy_override={"top_k": 2}), feedback(), feedback(),
        ])
        first = parts.pipeline.run_with_trace(self.request)
        second = parts.pipeline.run_with_trace(self.request)
        self.assertEqual(first.rounds[-1].strategy.top_k, 2)
        self.assertEqual(second.rounds[0].strategy.top_k, 5)
        first.rounds[0].retrieval_result.results[0].metadata["title"] = "Changed"
        self.assertNotEqual(second.rounds[0].retrieval_result.results[0].metadata["title"], "Changed")

    def test_invalid_caller_input_and_programming_errors_are_not_hidden(self):
        parts = setup_pipeline()
        with self.assertRaises(ValidationError):
            parts.pipeline.run(QueryRequest.model_construct(query=""))
        parts.analyzer.analyze.assert_not_called()
        parts.generator.generate.side_effect = AttributeError("programming error")
        with self.assertRaises(AttributeError):
            parts.pipeline.run(self.request)

    def test_factory_and_answer_only_api_run_existing_components(self):
        pipeline = build_demo_pipeline()
        result = pipeline.run_with_trace(self.request)
        self.assertEqual(result.status, "completed")
        self.assertIsInstance(pipeline.run(self.request), LegalAnswer)
        self.assertEqual(result.answer, pipeline.run(self.request))

    def test_shared_pipeline_can_run_independent_requests_concurrently(self):
        pipeline = build_demo_pipeline()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(pipeline.run_with_trace, [self.request] * 8))
        self.assertTrue(all(result.status == "completed" for result in results))
        results[0].rounds.clear()
        self.assertEqual(len(results[1].rounds), 1)
        results[0].filters["document_type"].append("tampered")
        self.assertNotIn("tampered", results[1].filters["document_type"])
        self.assertIsNone(remaining_timeout())


class DeadlineTests(unittest.TestCase):
    def test_retrieval_timeout_applies_before_the_overall_deadline(self):
        parts = setup_pipeline(settings=PipelineSettings(timeout_s=30))
        parts.service.settings = parts.service.settings.model_copy(update={"timeout_s": 2})
        clock = [0.0]
        original = parts.service.retrieve._mock_wraps
        def retrieve(**kwargs):
            self.assertLessEqual(remaining_timeout(), 2)
            result = original(**kwargs)
            clock[0] = 3.0
            return result
        parts.service.retrieve.side_effect = retrieve
        with patch("core.deadline.monotonic", side_effect=lambda: clock[0]):
            result = parts.pipeline.run_with_trace(QueryRequest(query="Câu hỏi"))
        self.assertEqual(result.status, "timed_out")
        self.assertEqual(result.failure_stage, "retrieval")
        self.assertEqual(result.query, "Câu hỏi")
        self.assertIsNotNone(result.analysis)
        parts.evaluator.evaluate.assert_not_called()
        self.assertIsNone(remaining_timeout())

    def test_expiry_prevents_starting_first_component(self):
        parts = setup_pipeline()
        with patch("core.deadline.monotonic", side_effect=[0.0, 1000.0]):
            result = parts.pipeline.run_with_trace(QueryRequest(query="Câu hỏi"))
        self.assertEqual(result.status, "timed_out")
        self.assertEqual(result.failure_stage, "analysis")
        parts.analyzer.analyze.assert_not_called()
        self.assertIsNone(remaining_timeout())

    def test_expiry_after_retrieval_discards_result_and_skips_evaluation(self):
        parts = setup_pipeline()
        clock = [0.0]
        original = parts.service.retrieve._mock_wraps

        def retrieve(**kwargs):
            result = original(**kwargs)
            clock[0] = 1000.0
            return result

        parts.service.retrieve.side_effect = retrieve
        with patch("core.deadline.monotonic", side_effect=lambda: clock[0]):
            result = parts.pipeline.run_with_trace(QueryRequest(query="Câu hỏi"))
        self.assertEqual(result.status, "timed_out")
        self.assertEqual(result.failure_stage, "retrieval")
        self.assertEqual(len(result.rounds), 1)
        parts.evaluator.evaluate.assert_not_called()
        parts.generator.generate.assert_not_called()

    def test_adapter_can_read_shrinking_budget_without_changing_abc_signatures(self):
        parts = setup_pipeline(settings=PipelineSettings(timeout_s=20))
        clock, budgets = [0.0], []
        analysis = parts.analyzer.analyze.return_value

        def analyze(request):
            budgets.append(remaining_timeout(30))
            clock[0] += 5
            return analysis

        def evaluate(request):
            budgets.append(remaining_timeout(30))
            clock[0] += 6
            return feedback()

        parts.analyzer.analyze.side_effect = analyze
        parts.evaluator.evaluate.side_effect = evaluate
        with patch("core.deadline.monotonic", side_effect=lambda: clock[0]):
            result = parts.pipeline.run_with_trace(QueryRequest(query="Câu hỏi"))
        self.assertEqual(result.status, "completed")
        self.assertEqual(budgets, [20.0, 15.0])
        self.assertEqual(remaining_timeout(30), 30)

    def test_expired_call_reports_timeout_even_if_component_wraps_provider_error(self):
        parts = setup_pipeline()
        clock = [0.0]

        def verify(answer, context):
            clock[0] = 1000.0
            raise CitationVerificationError("wrapped provider failure")

        parts.verifier.verify.side_effect = verify
        with patch("core.deadline.monotonic", side_effect=lambda: clock[0]):
            result = parts.pipeline.run_with_trace(QueryRequest(query="Câu hỏi"))
        self.assertEqual(result.status, "timed_out")
        self.assertEqual(result.failure_stage, "verification")
        self.assertEqual(result.answer.citations, [])

    def test_nested_deadline_cannot_extend_parent_and_restores_on_exception(self):
        clock = [0.0]
        with patch("core.deadline.monotonic", side_effect=lambda: clock[0]):
            with request_deadline(10):
                clock[0] = 3.0
                with request_deadline(100):
                    self.assertEqual(remaining_timeout(30), 7.0)
                self.assertEqual(remaining_timeout(5), 5)
                with self.assertRaises(RuntimeError):
                    with request_deadline(2):
                        raise RuntimeError("fixture")
                self.assertEqual(remaining_timeout(), 7.0)
        self.assertIsNone(remaining_timeout())


if __name__ == "__main__":
    unittest.main()
