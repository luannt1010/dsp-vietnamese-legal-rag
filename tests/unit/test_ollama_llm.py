# tests/unit/test_ollama_llm.py
"""Unit tests for OllamaBaseLLM implementation.
The tests mock the HTTP interactions with the Ollama server so no real server is required.
"""

import pytest
from requests.exceptions import ConnectionError
from unittest.mock import patch, MagicMock

from src.llm.ollama_llm import OllamaBaseLLM
from core.exceptions import LLMError

# Helper dummy Settings to inject configuration
class DummyLLMSettings:
    provider = "ollama"
    base_url = "http://fake-ollama"
    answer_generator = type("Role", (), {"model": "qwen2.5:7b"})()
    timeout_s = 1.0
    max_retries = 1
    retry_backoff_s = 0.0

class DummySettings:
    llm = DummyLLMSettings()

def test_successful_generate(monkeypatch):
    # Patch Settings used inside OllamaBaseLLM
    monkeypatch.setattr("src.llm.ollama_llm.Settings", lambda: DummySettings())
    # Mock HTTP response
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"message": {"content": "generated answer"}}
    with patch("src.infrastructure.ollama_client.requests.post", return_value=mock_resp) as mock_post:
        llm = OllamaBaseLLM()
        result = llm.generate("prompt")
        assert result == "generated answer"
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == "qwen2.5:7b"
        assert mock_post.call_args.args[0] == "http://fake-ollama/api/chat"
        assert payload["messages"] == [{"role": "user", "content": "prompt"}]
        assert payload["options"]["presence_penalty"] == 0
        assert payload["options"]["repeat_penalty"] == 1.0

def test_missing_response_field(monkeypatch):
    monkeypatch.setattr("src.llm.ollama_llm.Settings", lambda: DummySettings())
    bad_resp = MagicMock()
    bad_resp.raise_for_status.return_value = None
    bad_resp.json.return_value = {"not_response": "oops"}
    with patch("src.infrastructure.ollama_client.requests.post", return_value=bad_resp):
        llm = OllamaBaseLLM()
        with pytest.raises(LLMError, match="missing 'message.content'"):
            llm.generate("prompt")

def test_retry_exhausted(monkeypatch):
    # Settings with two retries
    class RetrySettings(DummySettings):
        llm = type("LLM", (), {
            "provider": "ollama",
            "base_url": "http://retry",
            "answer_generator": type("Role", (), {"model": "qwen2.5:7b"})(),
            "timeout_s": 0.1,
            "max_retries": 2,
            "retry_backoff_s": 0.0,
        })
    monkeypatch.setattr("src.llm.ollama_llm.Settings", lambda: RetrySettings())
    # First two attempts raise, third succeeds
    fail_exc = Exception("network error")
    good_resp = MagicMock()
    good_resp.raise_for_status.return_value = None
    good_resp.json.return_value = {"message": {"content": "ok"}}
    side_effects = [ConnectionError("boom"), ConnectionError("boom"), good_resp]
    with patch("src.infrastructure.ollama_client.requests.post", side_effect=side_effects) as mock_post:
        llm = OllamaBaseLLM()
        result = llm.generate("hi")
        assert result == "ok"
        assert mock_post.call_count == 3
