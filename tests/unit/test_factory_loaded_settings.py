# tests/unit/test_factory_loaded_settings.py
"""Regression test ensuring that the LLM factory uses `load_settings()`.
The factory should obtain its configuration via the loader rather than
instantiating `Settings` directly. By monkey‑patching `load_settings` we can
verify that the returned Settings object is used.
"""

import importlib
import pytest
from unittest.mock import patch

# Dummy configuration matching the expected schema
class DummyLLMSettings:
    provider = "ollama"
    base_url = "http://dummy"
    answer_generator = type("Role", (), {"model": "qwen2.5:7b"})()
    timeout_s = 1.0
    max_retries = 0
    retry_backoff_s = 0.0

class DummySettings:
    llm = DummyLLMSettings()

def test_factory_uses_load_settings(monkeypatch):
    # Patch the loader to return our dummy settings
    monkeypatch.setattr(
        "src.llm.factory.load_settings",
        lambda: DummySettings(),
    )
    # Ensure the original Settings class is NOT instantiated
    with patch("src.llm.factory.Settings") as mock_settings:
        mock_settings.side_effect = Exception("Settings should not be called")
        from src.llm.factory import get_llm_instance
        llm = get_llm_instance()
        # The concrete class should be OllamaBaseLLM
        OllamaCls = importlib.import_module("src.llm.ollama_llm").OllamaBaseLLM
        assert isinstance(llm, OllamaCls)
