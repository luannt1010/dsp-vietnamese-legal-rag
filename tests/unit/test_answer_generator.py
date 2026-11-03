# tests/unit/test_answer_generator.py
"""Tests for AnswerGenerator.
We mock the LLM to avoid network calls and verify that generate() parses JSON into LegalAnswer.
"""
import json
from unittest.mock import MagicMock
import pytest
from core.exceptions import LLMError

from src.generation.answer_generator import AnswerGenerator
from core.schemas.answer import AnswerGenerationRequest, LegalAnswer
from core.schemas.context import LegalContext
from core.schemas.retrieval import RetrievedChunk
from core.schemas import ContextBuilderRequest, RetrievalResult
from src.generation.context_builder import LegalContextBuilder

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
        chunks=[
            RetrievedChunk(
                chunk_id="c1",
                document_id="doc1",
                content="evidence text",
                score=1.0,
                retrieval_method="test",
                metadata={"document_number": "001"}
            )
        ],
        cited_document_ids=[],
    )
    return AnswerGenerationRequest(context=context, query="Explain law")

def test_generate_success():
    # The LLM supplies a draft; source metadata/quotes are assembled by code.
    answer_data = {
        "answer": "The law is...",
        "sources": [1],
    }
    llm = DummyLLM(json.dumps(answer_data))
    gen = AnswerGenerator(llm)
    request = make_request()
    result: LegalAnswer = gen.generate(request)
    assert isinstance(result, LegalAnswer)
    assert result.answer == "The law is..."
    assert result.confidence == 0
    assert len(result.citations) == 1
    assert result.citations[0].document_id == "doc1"
    assert result.citations[0].document_number == "001"
    assert result.citations[0].quoted_text == request.context.chunks[0].content

def test_generate_invalid_json(monkeypatch):
    # LLM returns malformed JSON
    llm = DummyLLM("not a json")
    gen = AnswerGenerator(llm)
    request = make_request()
    with pytest.raises(LLMError) as exc_info:
        gen.generate(request)
    # Verify original JSONDecodeError is preserved as __cause__
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_prompt_keeps_verbatim_context_without_duplicate_source_catalog():
    content = 'Điều 1. Phạm vi\nNguồn có "trích dẫn", dấu câu và xuống dòng.\nrò nư\u00adớc không được sửa.'
    url = "https://example.test/legal-source?anchor=" + "x" * 500
    source = RetrievedChunk(
        chunk_id="source-1", document_id="MOCK-1", content=content,
        score=1, retrieval_method="fixture",
        metadata={"document_number": "MOCK-01", "article": "Điều 1. Phạm vi", "source_url": url},
    )
    context = LegalContextBuilder(token_counter=len).build(ContextBuilderRequest(
        original_query="Phạm vi là gì?", retrieval_result=RetrievalResult(query="Phạm vi", results=[source]),
    ))
    before = context.model_dump()
    llm = MagicMock()
    llm.generate.return_value = json.dumps({"answer": "Theo nguồn giả lập.", "sources": [1]})
    result = AnswerGenerator(llm).generate(AnswerGenerationRequest(context=context, query=context.query))
    prompt = llm.generate.call_args.args[0]
    encoded_context = json.dumps(context.context_text, ensure_ascii=False)
    assert prompt.count(encoded_context) == 1
    assert json.loads(encoded_context) == context.context_text
    assert prompt.count(url) == 1
    assert result.citations[0].quoted_text == content
    assert result.citations[0].source_url == url
    assert result.citations[0].article == source.metadata["article"]
    assert context.model_dump() == before
    llm.generate.assert_called_once()


@pytest.mark.parametrize("sources", [[], [0], [-1], [True], ["1"], [2], [1, 1]])
def test_invalid_or_duplicate_source_references_are_rejected(sources):
    llm = DummyLLM(json.dumps({"answer": "Nội dung", "sources": sources}))
    with pytest.raises(LLMError):
        AnswerGenerator(llm).generate(make_request())


def test_model_cannot_supply_fabricated_citation_fields():
    llm = DummyLLM(json.dumps({"answer": "Nội dung", "sources": [1], "citations": [{"document_number": "FAKE"}]}))
    with pytest.raises(LLMError, match="AnswerDraft"):
        AnswerGenerator(llm).generate(make_request())


def test_missing_source_number_is_not_invented():
    from core.exceptions import InsufficientEvidenceError
    request = make_request()
    request.context.chunks[0].metadata = {}
    with pytest.raises(InsufficientEvidenceError, match="no document number"):
        AnswerGenerator(DummyLLM('{"answer":"Nội dung","sources":[1]}')).generate(request)
