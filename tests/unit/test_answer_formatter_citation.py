# tests/unit/test_answer_formatter_citation.py

import pytest
from src.generation.answer_formatter import AnswerFormatter
from core.schemas.answer import LegalAnswer, LegalCitation


def make_citation(
    document_id: str = "doc1",
    document_number: str = "123",
    article: str | None = None,
    clause: str | None = None,
    point: str | None = None,
    quoted_text: str = "quoted",
    source_url: str | None = None,
) -> LegalCitation:
    return LegalCitation(
        document_id=document_id,
        document_number=document_number,
        article=article,
        clause=clause,
        point=point,
        quoted_text=quoted_text,
        source_url=source_url,
    )


def test_full_components_formatting():
    # Citation with all components present
    citation = make_citation(article="35", clause="1", point="a")
    answer = LegalAnswer(
        answer="Some answer",
        citations=[citation],
        confidence=0.99,
        disclaimer=None,
    )
    formatted = AnswerFormatter().format(answer)
    # Expect the citation line to contain the Vietnamese terms and proper separators
    # The expected string (based on desired format) includes "Điều 35, khoản 1, điểm a"
    assert "Điều 35, khoản 1, điểm a" in formatted, "Citation formatting does not separate article, clause, point correctly"


def test_missing_clause_or_point_omitted():
    # Only article provided
    citation = make_citation(article="35")
    answer = LegalAnswer(answer="Ans", citations=[citation], confidence=0.5)
    formatted = AnswerFormatter().format(answer)
    # Should contain only the article component, no stray commas or empty placeholders
    assert "Điều 35" in formatted
    # Ensure clause and point strings are not present
    assert "khâu" not in formatted.lower()
    assert "điểm" not in formatted.lower()


def test_quoted_text_preserved_and_source_url():
    citation = make_citation(
        article="35",
        clause="1",
        point="a",
        quoted_text="Exact quote",
        source_url="http://example.com",
    )
    answer = LegalAnswer(answer="Ans", citations=[citation], confidence=0.8)
    formatted = AnswerFormatter().format(answer)
    # The quoted text must appear exactly as provided
    assert "Exact quote" in formatted
    # The source URL should be included if present
    assert "http://example.com" in formatted
