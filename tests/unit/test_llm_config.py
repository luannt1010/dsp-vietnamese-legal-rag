# tests/unit/test_llm_config.py
"""Regression test for loading LLM configuration via `load_settings()`.
Ensures that the yaml file `configs/llm.yml` is correctly parsed and the
resulting Settings object reflects the expected provider and model values.
"""

import pytest
from core.config.loader import load_settings


def test_load_llm_config():
    settings = load_settings()
    # Verify top‑level llm section exists
    assert hasattr(settings, "llm"), "Settings should have an 'llm' attribute"
    llm_cfg = settings.llm
    # Expected values from the repository's default llm.yml
    assert llm_cfg.provider == "ollama"
    # Model is defined under answer_generator section
    assert llm_cfg.answer_generator.model == "qwen2.5:7b"
    # Timeout defaults to 30 seconds as declared in the yaml
    assert llm_cfg.timeout_s == 30
    # Ensure retry configuration is present
    assert llm_cfg.max_retries == 2
    assert llm_cfg.retry_backoff_s == 1
