from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from core.exceptions import CitationVerificationError
from core.schemas import QueryRequest
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
    assert "_Change" not in schema["$defs"]
    assert "_Change" in evaluation_response_schema(settings.retrieval)["$defs"]


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
