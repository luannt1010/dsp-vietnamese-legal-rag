# tests/unit/test_factory.py
"""Tests for the LLM factory function.
We verify that the factory returns an OllamaBaseLLM when the provider is set to
"ollama" and that it raises ConfigurationError for unsupported providers.
"""
import importlib
import pytest
from unittest.mock import patch

from core.exceptions import ConfigurationError

# Helper Settings classes
class DummyOllamaSettings:
    provider = "ollama"
    base_url = "http://localhost"
    answer_generator = type("Role", (), {"model": "qwen2.5:7b"})()
    timeout_s = 1.0
    max_retries = 0
    retry_backoff_s = 0.0

class DummyBadSettings:
    provider = "unknown"

class DummySettings:
    llm = DummyOllamaSettings()

def test_get_llm_instance_ollama(monkeypatch):
    # Patch Settings so the factory sees the dummy configuration
    # Patch the loader to return dummy settings
    monkeypatch.setattr("src.llm.factory.load_settings", lambda: DummySettings())
    from src.llm.factory import get_llm_instance
    llm = get_llm_instance()
    # Import the class to compare types
    OllamaCls = importlib.import_module("src.llm.ollama_llm").OllamaBaseLLM
    assert isinstance(llm, OllamaCls)

def test_get_llm_instance_unknown_provider(monkeypatch):
    # Patch the loader to return a settings object with an unknown provider
    monkeypatch.setattr("src.llm.factory.load_settings", lambda: type("S", (), {"llm": DummyBadSettings()}))
    from src.llm.factory import get_llm_instance
    with pytest.raises(ConfigurationError, match="Unsupported LLM provider"):
        get_llm_instance()
