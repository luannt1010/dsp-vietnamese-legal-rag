"""Retries live in the shared transport and consume the parent request budget."""

from unittest.mock import Mock, patch

import pytest
from requests.exceptions import ConnectionError

from core.config.settings import Settings
from core.deadline import request_deadline
from core.exceptions import LLMError, LLMContextWindowError, LLMOutputTruncatedError
from src.llm.ollama_llm import OllamaBaseLLM


def make_llm():
    return OllamaBaseLLM(Settings.model_validate({
        "llm": {
            "provider": "ollama", "base_url": "http://localhost:11434",
            "answer_generator": {"model": "test-model"},
            "timeout_s": 30, "max_retries": 1, "retry_backoff_s": 0.001,
        },
    }))


def test_retry_exhausted_raises():
    with patch("src.infrastructure.ollama_client.requests.post", side_effect=ConnectionError("offline")) as post:
        with pytest.raises(LLMError):
            make_llm().generate("prompt")
    assert post.call_count == 2


def test_missing_response_no_retry():
    response = Mock()
    response.json.return_value = {"other": "missing response"}
    with patch("src.infrastructure.ollama_client.requests.post", return_value=response) as post:
        with pytest.raises(LLMError, match="missing 'message.content'"):
            make_llm().generate("prompt")
    assert post.call_count == 1


def test_successful_retry():
    response = Mock()
    response.json.return_value = {"message": {"content": "ok"}}
    with patch("src.infrastructure.ollama_client.requests.post", side_effect=[ConnectionError("offline"), response]) as post:
        assert make_llm().generate("prompt") == "ok"
    assert post.call_count == 2


def test_parent_deadline_bounds_http_timeout():
    clock = [0.0]
    response = Mock()
    response.json.return_value = {"message": {"content": "ok"}}
    with patch("core.deadline.monotonic", side_effect=lambda: clock[0]):
        with request_deadline(5):
            clock[0] = 4.0
            with patch("src.infrastructure.ollama_client.requests.post", return_value=response) as post:
                assert make_llm().generate("prompt") == "ok"
            assert post.call_args.kwargs["timeout"] == 1.0


def test_context_budget_rejects_before_network_call():
    llm = make_llm()
    llm.role = llm.role.model_copy(update={"context_window_tokens": 4096})
    llm.token_counter = lambda text: 4000
    with patch("src.infrastructure.ollama_client.requests.post") as post:
        with pytest.raises(LLMContextWindowError, match="exceed"):
            llm.generate("prompt")
    post.assert_not_called()


@pytest.mark.parametrize("content", ['{"answer":"partial', ""])
def test_truncated_chat_output_is_rejected(content):
    response = Mock()
    response.json.return_value = {"message": {"content": content}, "done_reason": "length"}
    with patch("src.infrastructure.ollama_client.requests.post", return_value=response):
        with pytest.raises(LLMOutputTruncatedError, match="truncated"):
            make_llm().generate("prompt")


def test_prompt_and_output_fit_at_exact_window_boundary():
    llm = make_llm()
    llm.role = llm.role.model_copy(update={"context_window_tokens": 8192, "max_output_tokens": 2048})
    llm.token_counter = lambda _: 6016  # 6016 + 128 overhead + 2048 output = 8192.
    response = Mock()
    response.json.return_value = {"message": {"content": "ok"}}
    with patch("src.infrastructure.ollama_client.requests.post", return_value=response) as post:
        assert llm.generate("prompt") == "ok"
        assert post.call_args.kwargs["json"]["options"]["num_predict"] == 2048
        llm.token_counter = lambda _: 6017
        with pytest.raises(LLMContextWindowError):
            llm.generate("prompt")
        post.assert_called_once()


@pytest.mark.parametrize("payload", [
    {"message": None}, {"message": []}, {"message": {"content": None}},
    {"message": {"content": 123}}, {"message": {"content": []}}, None,
])
def test_malformed_response_is_llm_error(payload):
    response = Mock()
    response.json.return_value = payload
    with patch("src.infrastructure.ollama_client.requests.post", return_value=response):
        with pytest.raises(LLMError):
            make_llm().generate("prompt")
