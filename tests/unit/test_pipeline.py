# tests/unit/test_pipeline.py
"""Tests for the answer generation pipeline builder."""

import pytest

from src.pipeline import build_answer_pipeline

def test_build_answer_pipeline(monkeypatch):
    # Patch Settings to ensure provider is ollama
    class DummyLLMSettings:
        provider = "ollama"
        base_url = "http://dummy"
        answer_generator = type("Role", (), {"model": "qwen2.5:7b"})()
        timeout_s = 1.0
        max_retries = 0
        retry_backoff_s = 0.0
    class DummySettings:
        llm = DummyLLMSettings()
    monkeypatch.setattr("src.pipeline.Settings", lambda: DummySettings())
    # Also patch factory to use dummy settings (factory will import Settings internally)
    from src.llm.factory import Settings as FactorySettings
    monkeypatch.setattr("src.llm.factory.Settings", lambda: DummySettings())

    answer_generator, answer_formatter = build_answer_pipeline()
    # Verify types
    from src.generation.answer_generator import AnswerGenerator
    from src.generation.answer_formatter import AnswerFormatter
    assert isinstance(answer_generator, AnswerGenerator)
    assert isinstance(answer_formatter, AnswerFormatter)
