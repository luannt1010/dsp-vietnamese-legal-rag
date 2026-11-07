"""Verify HTTP contracts, failure projection and real pipeline integration."""

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from core.schemas import LegalAnswer
from examples.orchestration_demo import build_demo_pipeline


def test_verified_answer_has_retained_sources_and_correlation_id(client, runtime):
    response = client.post("/api/v1/questions", json={"query": "  Câu hỏi  "})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["answer"]["citations"][0]["quoted_text"] == body["sources"][0]["content"]
    assert body["corpus_id"] == "fixture-corpus"
    assert body["duration_ms"] >= 0
    assert body["request_id"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"
    assert runtime.pipeline.run_with_trace.call_args.args[0].query == "Câu hỏi"
    for private_field in ("draft_answer", "analysis", "filters", "context", "failure_details"):
        assert private_field not in body


@pytest.mark.parametrize("payload", [
    {}, {"query": ""}, {"query": " \n "}, {"query": 123}, {"query": None},
    {"query": "x" * 4001}, {"query": "Câu hỏi", "top_k": 1000},
    {"query": "Câu hỏi", "conversation_id": "unsupported-memory"},
])
def test_invalid_input_does_not_call_pipeline(client, runtime, payload):
    response = client.post("/api/v1/questions", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["issues"]
    assert body["request_id"] == response.headers["x-request-id"]
    assert all(set(issue) == {"location", "code", "message"} for issue in body["error"]["issues"])
    runtime.pipeline.run_with_trace.assert_not_called()


def test_invalid_json_has_safe_validation_envelope(client, runtime):
    response = client.post("/api/v1/questions", content='{"query":', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert "input" not in response.json()["error"]["issues"][0]
    runtime.pipeline.run_with_trace.assert_not_called()


def test_public_query_length_boundary(client):
    assert client.post("/api/v1/questions", json={"query": "x" * 4000}).status_code == 200


@pytest.mark.parametrize("status,http_status", [
    ("insufficient_evidence", 200), ("failed", 502), ("timed_out", 504),
])
def test_pipeline_fallback_preserved_without_draft_or_rejected_sources(client, runtime, status, http_status):
    result = runtime.pipeline.run_with_trace.return_value
    result.draft_answer = result.answer.model_copy(deep=True)
    result.draft_answer.answer = "UNVERIFIED_DRAFT"
    result.answer = LegalAnswer(answer="Thông báo fallback của pipeline.", citations=[], confidence=0)
    result.status = status
    result.failure_stage = "verification" if status == "failed" else None
    result.error_type = "CitationVerificationError" if status == "failed" else None
    result.failure_details = {"code": "unsupported_answer_claims", "reason": "PRIVATE_MODEL_REASON"}
    response = client.post("/api/v1/questions", json={"query": "Câu hỏi"})
    assert response.status_code == http_status
    body = response.json()
    assert body["status"] == status
    assert body["answer"] == result.answer.model_dump()
    assert body["sources"] == []
    assert "UNVERIFIED_DRAFT" not in response.text
    assert "PRIVATE_MODEL_REASON" not in response.text
    if status == "failed":
        assert body["failure"] == {"stage": "verification", "code": "unsupported_answer_claims"}


def test_unexpected_exception_is_safe_and_slot_is_released(client, runtime, caplog):
    good_result = runtime.pipeline.run_with_trace.return_value
    runtime.pipeline.run_with_trace.side_effect = [AttributeError("SECRET_PROVIDER_DETAIL"), good_result]
    with caplog.at_level(logging.INFO):
        failed = client.post("/api/v1/questions", json={"query": "PRIVATE_USER_QUESTION"},
                             headers={"Origin": "http://localhost:5173"})
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "internal_error"
    assert failed.json()["request_id"] == failed.headers["x-request-id"]
    assert failed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "SECRET_PROVIDER_DETAIL" not in failed.text
    assert "SECRET_PROVIDER_DETAIL" not in caplog.text
    assert "PRIVATE_USER_QUESTION" not in caplog.text
    assert failed.headers["x-request-id"] in caplog.text
    assert client.post("/api/v1/questions", json={"query": "Câu hỏi khác"}).status_code == 200


def test_busy_request_fails_fast_while_health_remains_responsive(client, runtime):
    entered, release = Event(), Event()
    result = runtime.pipeline.run_with_trace.return_value

    def blocking_pipeline(question):
        entered.set()
        assert release.wait(10), "test worker was not released"
        return result

    runtime.pipeline.run_with_trace.side_effect = blocking_pipeline
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(client.post, "/api/v1/questions", json={"query": "Câu hỏi thứ nhất"})
        try:
            assert entered.wait(5)
            busy = client.post("/api/v1/questions", json={"query": "Câu hỏi thứ hai"})
            assert busy.status_code == 503
            assert busy.json()["error"]["code"] == "service_busy"
            assert busy.headers["retry-after"] == "1"
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 200
            assert client.get("/api/v1/corpus").status_code == 200
            assert runtime.pipeline.run_with_trace.call_count == 1
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
    assert client.post("/api/v1/questions", json={"query": "Câu hỏi sau"}).status_code == 200


def test_requests_do_not_share_response_state(client, runtime):
    first = client.post("/api/v1/questions", json={"query": "Câu hỏi A"})
    first_body = first.json()
    first_body["answer"]["answer"] = "client-side mutation"
    second = client.post("/api/v1/questions", json={"query": "Câu hỏi B"})
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    assert second.json()["answer"]["answer"] == "Đáp án đã kiểm chứng."
    assert [call.args[0].query for call in runtime.pipeline.run_with_trace.call_args_list] == ["Câu hỏi A", "Câu hỏi B"]


def test_http_to_real_orchestration_with_fixture_providers(client, runtime):
    # BM25/filter/router/context/citation matching are real; LLM/data are fixtures.
    runtime.pipeline.run_with_trace.side_effect = build_demo_pipeline().run_with_trace
    response = client.post("/api/v1/questions", json={"query": "Câu hỏi với dữ liệu giả lập"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["rounds"] == 1
    assert body["answer"]["citations"]
    assert body["sources"]
    assert body["answer"]["confidence"] == 0
