# tests/unit/test_answer_generator_edge_cases.py
"""Edge‑case tests for `AnswerGenerator.generate`.
These tests verify that the generator correctly raises the expected
exceptions when the input context is missing or when the LLM returns an
empty/whitespace response.
"""

import pytest
from unittest.mock import MagicMock

from src.generation.answer_generator import AnswerGenerator
from core.schemas.answer import AnswerGenerationRequest
from core.schemas.context import LegalContext
from core.schemas.retrieval import RetrievedChunk
from core.exceptions import InsufficientEvidenceError, LLMError


class DummyLLM:
    """Simple LLM mock that returns a preset string."""

    def __init__(self, response: str):
        self._resp = response

    def generate(self, prompt: str) -> str:
        return self._resp


def make_minimal_context() -> LegalContext:
    """Build a minimal but valid `LegalContext` for testing.
    Includes a non‑empty evidence chunk to satisfy the evidence gate.
    """
    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="doc1",
        content="evidence text",
        score=1.0,
        retrieval_method="test",
        metadata={}
    )
    return LegalContext(
        query="dummy query",
        context_text="some context",
        chunks=[chunk],
        cited_document_ids=[],
    )


def test_generate_empty_legal_context_raises():
    """When `request.context` is None, `InsufficientEvidenceError` is raised."""
    # Bypass pydantic validation using model_construct.
    request = AnswerGenerationRequest.model_construct(context=None, query="any query")
    gen = AnswerGenerator(DummyLLM("{}"))
    with pytest.raises(InsufficientEvidenceError):
        gen.generate(request)


def test_generate_empty_llm_response_raises():
    """Empty or whitespace‑only LLM output should raise `LLMError`."""
    # Use a valid context.
    request = AnswerGenerationRequest(context=make_minimal_context(), query="any query")
    # Empty string response.
    gen_empty = AnswerGenerator(DummyLLM(""))
    with pytest.raises(LLMError):
        gen_empty.generate(request)
    # Whitespace response.
    gen_ws = AnswerGenerator(DummyLLM("   \n\t"))
    with pytest.raises(LLMError):
        gen_ws.generate(request)
