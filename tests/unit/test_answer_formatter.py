# tests/unit/test_answer_formatter.py
"""Tests for AnswerFormatter.
We verify that the formatter produces a readable string with answer text,
citations, confidence and optional disclaimer.
"""
import pytest

from src.generation.answer_formatter import AnswerFormatter
from core.schemas.answer import LegalAnswer, LegalCitation

def test_format_basic():
    citation = LegalCitation(
        document_id="doc1",
        document_number="001",
        article=None,
        clause=None,
        point=None,
        quoted_text="Important quote",
        source_url=None,
    )
    answer = LegalAnswer(
        answer="Here is the answer.",
        citations=[citation],
        confidence=0.85,
        disclaimer=None,
    )
    formatter = AnswerFormatter()
    output = formatter.format(answer)
    # Basic parts should be present
    assert "Here is the answer." in output
    assert "Citations:" in output
    assert "[1] doc1 - 001: Important quote" in output
    assert "Confidence: 0.85" in output

def test_format_with_disclaimer():
    answer = LegalAnswer(
        answer="Answer text",
        citations=[],
        confidence=0.99,
        disclaimer="This is a disclaimer.",
    )
    formatter = AnswerFormatter()
    output = formatter.format(answer)
    assert "Disclaimer: This is a disclaimer." in output
