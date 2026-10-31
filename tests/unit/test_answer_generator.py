# tests/unit/test_answer_generator.py
"""Tests for AnswerGenerator.
We mock the LLM to avoid network calls and verify that generate() parses JSON into LegalAnswer.
"""
import json
from unittest.mock import MagicMock
import pytest

from src.generation.answer_generator import AnswerGenerator
from core.schemas.answer import AnswerGenerationRequest, LegalAnswer, LegalCitation
from core.schemas.context import LegalContext

# Helper dummy LLM
class DummyLLM:
    def __init__(self, response_json: str):
        self._response = response_json
    def generate(self, prompt: str) -> str:
        # simply return preset JSON string regardless of prompt
        return self._response

def make_request():
    context = LegalContext(
        query="What is the law?",
        context_text="some context",
        chunks=[],
        cited_document_ids=[],
    )
    return AnswerGenerationRequest(context=context, query="Explain law")

def test_generate_success():
    # Prepare a LegalAnswer JSON representation
    answer_data = {
        "answer": "The law is...",
        "citations": [
            {
                "document_id": "doc1",
                "document_number": "001",
                "quoted_text": "some quote",
                "source_url": None,
            }
        ],
        "confidence": 0.92,
        "disclaimer": None,
    }
    llm = DummyLLM(json.dumps(answer_data))
    gen = AnswerGenerator(llm)
    request = make_request()
    result: LegalAnswer = gen.generate(request)
    assert isinstance(result, LegalAnswer)
    assert result.answer == "The law is..."
    assert result.confidence == 0.92
    assert len(result.citations) == 1
    assert result.citations[0].document_id == "doc1"

def test_generate_invalid_json(monkeypatch):
    # LLM returns malformed JSON
    llm = DummyLLM("not a json")
    gen = AnswerGenerator(llm)
    request = make_request()
    with pytest.raises(Exception):
        gen.generate(request)
