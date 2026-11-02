
import pytest

from src.llm.ollama_llm import OllamaBaseLLM
from core.config.settings import Settings
from core.exceptions import LLMError


def make_settings():
    settings = Settings()

    role_settings = settings.llm.answer_generator.model_copy(
        update={"model": "test-model"}
    )

    llm_settings = settings.llm.model_copy(
        update={
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "answer_generator": role_settings,
            "timeout_s": 0.2,
            "max_retries": 1,
            "retry_backoff_s": 0.001,
        }
    )

    return settings.model_copy(update={"llm": llm_settings})


call_log = []


def mock_post_success(self, payload):
    call_log.append("success")
    return {
        "response": '{"answer": "ok", "citations": [], "confidence": 0.5}'
    }


def mock_post_fail(self, payload):
    call_log.append("fail")
    raise LLMError("Network error")


def mock_post_missing(self, payload):
    call_log.append("missing")
    return {"other": "no response field"}


def test_retry_exhausted_raises(monkeypatch):
    call_log.clear()
    monkeypatch.setattr(OllamaBaseLLM, "_post", mock_post_fail)

    llm = OllamaBaseLLM(settings=make_settings())

    with pytest.raises(LLMError):
        llm.generate("prompt")

    assert call_log.count("fail") == 2


def test_missing_response_no_retry(monkeypatch):
    call_log.clear()
    monkeypatch.setattr(OllamaBaseLLM, "_post", mock_post_missing)

    llm = OllamaBaseLLM(settings=make_settings())

    with pytest.raises(LLMError) as exc:
        llm.generate("prompt")

    assert "missing 'response'" in str(exc.value)
    assert call_log == ["missing"]


def test_successful_retry(monkeypatch):
    call_log.clear()

    seq = [mock_post_fail, mock_post_success]

    def side_effect(self, payload):
        func = seq.pop(0)
        return func(self, payload)

    monkeypatch.setattr(OllamaBaseLLM, "_post", side_effect)

    llm = OllamaBaseLLM(settings=make_settings())
    result = llm.generate("prompt")

    assert call_log == ["fail", "success"]
    assert result.startswith('{"answer"')
