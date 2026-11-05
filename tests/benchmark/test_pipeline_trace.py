from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from core.exceptions import CitationVerificationError, RetrievalError
from core.schemas import QueryRequest, RetrievalResult, RetrievedChunk
from core.schemas.orchestration import PipelineRunOptions
from examples.orchestration_demo import FixtureLLM
from src.benchmark.config import load_config
from src.infrastructure.ollama_client import OllamaClient
from src.evaluation.response_schema import evaluation_response_schema
from src.observability.telemetry import capture, span


def test_full_ranking_is_distinct_from_context_and_gate(settings, pipeline_factory):
    config = load_config(Path("configs/benchmark/hybrid.yml"))
    selected = config.settings_for(settings, config.experiments[1])
    pipeline = pipeline_factory(selected)
    with capture() as events:
        result = pipeline.run_with_trace(QueryRequest(query="bằng chứng chuẩn?"), options=config.run_options())
    assert result.status == "completed"
    assert len(result.rounds[0].retrieval_result.results) == 20
    assert len(result.context.chunks) == 5
    assert result.context.chunks[0].chunk_id == result.rounds[0].retrieval_result.results[0].chunk_id
    assert result.draft_answer == result.answer
    assert {"analysis", "retrieval", "context", "generation", "verification"}.issubset({e["name"] for e in events})
    assert any(e["kind"] == "model_call" and e["role"] == "reranker" for e in events)


def test_failed_verification_retains_context_and_draft(settings, pipeline_factory):
    pipeline = pipeline_factory(settings)
    pipeline._citation_verifier = Mock()
    pipeline._citation_verifier.verify.side_effect = CitationVerificationError("fixture rejection")
    result = pipeline.run_with_trace(QueryRequest(query="bằng chứng chuẩn?"))
    assert result.status == "failed" and result.failure_stage == "verification"
    assert result.context is not None and result.draft_answer is not None
    assert result.answer != result.draft_answer


def test_gate_evaluates_exactly_the_retained_context(settings, pipeline_factory):
    pipeline = pipeline_factory(settings)
    original_build = pipeline._context_builder.build

    def keep_one(request):
        reduced = request.model_copy(deep=True)
        reduced.retrieval_result.results = reduced.retrieval_result.results[:1]
        return original_build(reduced)

    pipeline._context_builder.build = Mock(side_effect=keep_one)
    evaluate = pipeline._retrieval_evaluator.evaluate
    pipeline._retrieval_evaluator.evaluate = Mock(side_effect=evaluate)
    result = pipeline.run_with_trace(QueryRequest(query="bằng chứng chuẩn?"))
    evaluated = pipeline._retrieval_evaluator.evaluate.call_args.args[0].retrieval_result.results
    assert result.status == "completed"
    assert len(result.rounds[0].retrieval_result.results) > len(evaluated) == 1
    assert evaluated == result.context.chunks


def test_verifier_diagnostics_distinguish_unsupported_claims_from_provider_failure(settings, pipeline_factory):
    pipeline = pipeline_factory(settings)
    verifier = pipeline._citation_verifier
    verifier._llm = Mock(generate=Mock(return_value='{"is_supported":false,"reason":"Missing condition"}'))
    rejected = pipeline.run_with_trace(QueryRequest(query="bằng chứng chuẩn?"))
    assert rejected.status == "failed"
    assert rejected.failure_details["code"] == "unsupported_answer_claims"
    assert rejected.failure_details["reason"] == "Missing condition"
    verifier._llm.generate.side_effect = TimeoutError("secret provider payload")
    unavailable = pipeline.run_with_trace(QueryRequest(query="bằng chứng chuẩn?"))
    assert unavailable.failure_details["code"] == "claim_support_check_failed"
    assert unavailable.failure_details["cause_type"] == "TimeoutError"
    assert "secret provider payload" not in unavailable.model_dump_json()


def test_old_trace_serialization_does_not_add_empty_diagnostics(settings, pipeline_factory):
    result = pipeline_factory(settings).run_with_trace(QueryRequest(query="bằng chứng chuẩn?"))
    assert "failure_details" not in result.model_dump()


def test_context_selection_covers_both_documents_without_changing_raw_ranking(settings, pipeline_factory):
    pipeline = pipeline_factory(settings)
    hits = [RetrievedChunk(
        chunk_id=f"{document}-{i}", document_id=document, content=f"Căn cứ {document} {i}",
        score=1, retrieval_method="fixture", metadata={"document_number": number},
    ) for document, number, count in [("a", "23/2004/QH11", 6), ("b", "110/2014/NĐ-CP", 2)] for i in range(count)]
    pipeline._retrieval_service.retrieve = Mock(return_value=RetrievalResult(query="scope", results=hits))
    result = pipeline.run_with_trace(QueryRequest(query="So sánh 23/2004/QH11 và 110/2014/NĐ-CP?"),
                                    options=PipelineRunOptions(ranking_k=8, context_top_k=5))
    assert result.status == "completed"
    assert [hit.chunk_id for hit in result.rounds[0].retrieval_result.results] == [hit.chunk_id for hit in hits]
    assert [hit.chunk_id for hit in result.context.chunks] == ["a-0", "b-0", "a-1", "b-1", "a-2"]


@pytest.mark.parametrize("changes", [
    {"is_sufficient": False},
    {"missing_information": ["Missing a necessary fact"]},
])
def test_flat_provider_feedback_is_validated_without_repair(changes):
    from src.evaluation.response_schema import validate_feedback
    payload = {"is_relevant": True, "is_sufficient": True, "confidence": 1,
               "next_action": "continue", "reason": "fixture", **changes}
    with pytest.raises(ValueError):
        validate_feedback(payload)


def test_inactive_advice_is_discarded_without_changing_a_negative_decision():
    from src.evaluation.response_schema import validate_feedback
    with capture() as events:
        result = validate_feedback({"is_relevant": False, "is_sufficient": False, "confidence": 1,
                                    "next_action": "stop", "reason": "Missing amount",
                                    "refined_query": "An unused suggestion", "strategy_override": {"use_graph": True}})
    assert not result.is_sufficient and result.next_action == "stop"
    assert result.refined_query is None and result.strategy_override == {}
    assert events[0]["discarded_inactive_fields"] == ["refined_query", "strategy_override"]


def test_failed_retry_does_not_reuse_the_previous_round_context(settings, pipeline_factory):
    evaluation = FixtureLLM({"is_relevant": True, "is_sufficient": False, "confidence": 1,
                            "next_action": "refine_query", "refined_query": "narrower query", "reason": "fixture gap"})
    pipeline = pipeline_factory(settings, evaluation=evaluation)
    source = RetrievedChunk(chunk_id="a", document_id="a", content="Partial evidence", score=1, retrieval_method="fixture")
    pipeline._retrieval_service.retrieve = Mock(side_effect=[RetrievalResult(query="q", results=[source]), RetrievalError("fixture unavailable")])
    result = pipeline.run_with_trace(QueryRequest(query="bằng chứng chuẩn?"))
    assert len(result.rounds) == 2 and result.failure_stage == "retrieval"
    assert result.context is None and result.draft_answer is None


def test_feedback_cannot_enable_another_method(settings, pipeline_factory):
    evaluation = FixtureLLM({"is_relevant": False, "is_sufficient": False, "confidence": 0,
        "next_action": "change_strategy", "strategy_override": {"use_graph": False}, "reason": "fixture change"})
    pipeline = pipeline_factory(settings, evaluation=evaluation)
    result = pipeline.run_with_trace(QueryRequest(query="bằng chứng chuẩn?"),
        options=PipelineRunOptions(ranking_k=20, context_top_k=5, allow_strategy_changes=False))
    assert result.status == "insufficient_evidence" and len(result.rounds) == 1


def test_analysis_replay_skips_analyzer_but_preserves_filters(settings, pipeline_factory):
    pipeline = pipeline_factory(settings)
    request = QueryRequest(query="bằng chứng chuẩn?")
    first = pipeline.run_with_trace(request)
    pipeline._query_analyzer = Mock()
    pipeline._query_analyzer.analyze.side_effect = AssertionError("analysis must be replayed")
    replayed = pipeline.run_with_trace(request, analysis=first.analysis)
    assert replayed.status == "completed" and replayed.filters == first.filters
    pipeline._query_analyzer.analyze.assert_not_called()
    with pytest.raises(ValueError, match="another question"):
        pipeline.run_with_trace(QueryRequest(query="a different question"), analysis=first.analysis)


def test_locked_feedback_schema_excludes_strategy_changes(settings):
    schema = evaluation_response_schema(settings.retrieval, allow_strategy_changes=False)
    assert "change_strategy" not in schema["properties"]["next_action"]["enum"]
    assert "change_strategy" in evaluation_response_schema(settings.retrieval)["properties"]["next_action"]["enum"]
    assert "anyOf" not in schema
    assert schema["properties"]["strategy_override"]["maxProperties"] == 0


def test_telemetry_is_request_local_and_records_failure():
    def record(name):
        with capture() as events:
            with pytest.raises(ValueError):
                with span(name):
                    raise ValueError("fixture")
        return events
    with ThreadPoolExecutor(max_workers=2) as executor:
        a, b = executor.map(record, ["a", "b"])
    assert [e["name"] for e in a] == ["a"]
    assert [e["name"] for e in b] == ["b"]
    assert a[0]["status"] == "failed" and a[0]["duration_ms"] >= 0


def test_backend_timing_units_and_retry_attempts(monkeypatch):
    response = Mock()
    response.json.return_value = {"total_duration": 2_000_000_000, "eval_duration": 1_000_000_000, "eval_count": 20}
    post = Mock(side_effect=[requests.ConnectionError("fixture"), response])
    monkeypatch.setattr("src.infrastructure.ollama_client.requests.post", post)
    monkeypatch.setattr("src.infrastructure.ollama_client.time.sleep", lambda _: None)
    with capture() as events:
        OllamaClient("http://fixture", timeout_s=10, max_retries=1).post("/api/chat", {"model": "fixture"})
    assert [e["attempt"] for e in events] == [1, 2]
    assert events[0]["status"] == "failed"
    assert events[1]["total_duration_ms"] == 2000
    assert events[1]["decode_tokens_per_second"] == 20
    assert "prompt_eval_count" not in events[1]
