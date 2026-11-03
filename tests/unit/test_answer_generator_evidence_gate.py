
import pytest

from core.schemas.context import LegalContext
from core.schemas.retrieval import RetrievedChunk
from core.schemas.answer import AnswerGenerationRequest
from core.exceptions import InsufficientEvidenceError
from core.interfaces.base_llm import BaseLLM
from src.generation.answer_generator import AnswerGenerator


class DummyLLM(BaseLLM):
    def __init__(self):
        self.called = False
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.called = True
        self.last_prompt = prompt
        return '{"answer": "Test answer", "sources": [1]}'


def make_context(**kwargs):
    defaults = {
        "query": "Dummy query",
        "context_text": "Some context",
        "chunks": [],
        "cited_document_ids": [],
    }
    defaults.update(kwargs)
    return LegalContext(**defaults)


def make_chunk(content: str = "Chunk content"):
    return RetrievedChunk(
        chunk_id="c1",
        document_id="d1",
        content=content,
        score=1.0,
        retrieval_method="bm25",
        metadata={"document_number": "MOCK-01"},
    )


def make_request(context):
    return AnswerGenerationRequest(context=context, query="q")


@pytest.fixture
def dummy_llm():
    return DummyLLM()


@pytest.fixture
def answer_generator(dummy_llm):
    return AnswerGenerator(dummy_llm)


def test_empty_context_raises(answer_generator, dummy_llm):
    ctx = make_context(context_text="", chunks=[])
    request = make_request(ctx)

    with pytest.raises(InsufficientEvidenceError):
        answer_generator.generate(request)

    assert not dummy_llm.called


def test_whitespace_context_text_raises(answer_generator, dummy_llm):
    ctx = make_context(context_text="   ", chunks=[make_chunk()])
    request = make_request(ctx)

    with pytest.raises(InsufficientEvidenceError):
        answer_generator.generate(request)

    assert not dummy_llm.called


def test_no_chunks_raises(answer_generator, dummy_llm):
    ctx = make_context(chunks=[])
    request = make_request(ctx)

    with pytest.raises(InsufficientEvidenceError):
        answer_generator.generate(request)

    assert not dummy_llm.called


def test_all_chunks_empty_raises(answer_generator, dummy_llm):
    empty_chunk = RetrievedChunk.model_construct(
        chunk_id="c1",
        document_id="d1",
        content="   ",
        score=1.0,
        retrieval_method="bm25",
        metadata={},
    )

    ctx = make_context(chunks=[empty_chunk])
    request = make_request(ctx)

    with pytest.raises(InsufficientEvidenceError):
        answer_generator.generate(request)

    assert not dummy_llm.called

def test_valid_context_calls_llm(answer_generator, dummy_llm):
    ctx = make_context(chunks=[make_chunk()])
    request = make_request(ctx)

    answer = answer_generator.generate(request)

    assert dummy_llm.called
    assert answer.answer == "Test answer"
