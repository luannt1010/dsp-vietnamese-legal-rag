# tests/unit/test_answer_generator_call_counts.py
"""Tests to ensure AnswerGenerator calls the LLM exactly once per generate call.
These tests complement existing edge‑case tests and verify that no duplicate
LLM invocations occur, which could cause extra latency or cost.
"""

import json
from unittest.mock import MagicMock
import pytest
from core.exceptions import LLMError

from src.generation.answer_generator import AnswerGenerator
from core.schemas.answer import AnswerGenerationRequest, LegalAnswer
from core.schemas.context import LegalContext


def make_valid_request() -> AnswerGenerationRequest:
    """Create a minimal valid AnswerGenerationRequest used by the tests."""
    context = LegalContext(
        query="dummy query",
        context_text="some context",
        chunks=[],
        cited_document_ids=[],
    )
    return AnswerGenerationRequest(context=context, query="Explain law")


def test_generate_calls_llm_once_success():
    """When generation succeeds, the LLM should be called exactly once."""
    # Prepare a valid LegalAnswer JSON payload
    answer_payload = {
        "answer": "The law is ...",
        "citations": [],
        "confidence": 0.99,
        "disclaimer": None,
    }
    # Mock LLM with a MagicMock to track calls
    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps(answer_payload)

    generator = AnswerGenerator(mock_llm)
    request = make_valid_request()
    result: LegalAnswer = generator.generate(request)

    # Verify the result is a LegalAnswer instance
    assert isinstance(result, LegalAnswer)
    # Verify that generate was called exactly once
    assert mock_llm.generate.call_count == 1


def test_generate_calls_llm_once_empty_response():
    """Even when the LLM returns an empty response (raising LLMError), it should be called only once."""
    mock_llm = MagicMock()
    mock_llm.generate.return_value = ""  # empty response

    generator = AnswerGenerator(mock_llm)
    request = make_valid_request()
    with pytest.raises(LLMError):
        generator.generate(request)
    # The LLM should still have been invoked exactly once
    assert mock_llm.generate.call_count == 1
