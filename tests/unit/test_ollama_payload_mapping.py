
from src.llm.ollama_llm import OllamaBaseLLM
from core.config.settings import Settings


def make_settings():
    settings = Settings()

    role_settings = settings.llm.answer_generator.model_copy(
        update={
            "model": "test-model",
            "temperature": 0.7,
            "max_output_tokens": 123,
        }
    )

    llm_settings = settings.llm.model_copy(
        update={
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "answer_generator": role_settings,
            "timeout_s": 5.0,
            "max_retries": 0,
            "retry_backoff_s": 0.001,
        }
    )

    return settings.model_copy(update={"llm": llm_settings})


captured_payload = {}


def mock_post(self, payload):
    global captured_payload
    captured_payload = payload
    return {
        "response": '{"answer": "ok", "citations": [], "confidence": 0.5}'
    }


def test_payload_includes_options(monkeypatch):
    monkeypatch.setattr(OllamaBaseLLM, "_post", mock_post)

    llm = OllamaBaseLLM(settings=make_settings())
    result = llm.generate("test prompt")

    assert captured_payload["model"] == "test-model"
    assert captured_payload["prompt"] == "test prompt"

    options = captured_payload.get("options")

    assert options is not None
    assert options["temperature"] == 0.7
    assert options["num_predict"] == 123

    assert result == '{"answer": "ok", "citations": [], "confidence": 0.5}'
