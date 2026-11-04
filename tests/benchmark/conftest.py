"""Synthetic source-backed fixtures, with real retrieval/context/generation wiring."""

from types import SimpleNamespace

import pytest

from core.config import load_settings
from core.schemas import GraphRetrievalResult, LegalChunk, LegalMetadata
from examples.orchestration_demo import FixtureLLM
from src.benchmark.schemas import Question
from src.generation.answer_generator import AnswerGenerator
from src.orchestration import create_pipeline
from src.retrieval.reranking import CrossEncoderReRanker
from src.retrieval.sparse import BM25Retriever


@pytest.fixture
def chunks():
    metadata = LegalMetadata(document_id="fixture", document_number="FIXTURE/01", title="Synthetic fixture",
                             document_type="mock", topic_title="Giáo dục, đào tạo")
    return [LegalChunk(chunk_id=f"c{i:02}", document_id="fixture", article="Điều 1", metadata=metadata,
                       content=f"bằng chứng chuẩn {i}; đây là dữ liệu giả lập phục vụ kiểm thử.") for i in range(25)]


@pytest.fixture
def question(chunks):
    return Question(question_id="GD001", question="bằng chứng chuẩn?", topic="Giáo dục, đào tạo",
                    question_type="lookup", answerable=True, reference_answer="kết luận giả lập",
                    reference_claims=["kết luận giả lập"], evidence=[{
                        "document_number": "FIXTURE/01", "document_title": "Synthetic fixture",
                        "article": "Điều 1", "quote": "bằng chứng chuẩn 0;"}])


@pytest.fixture
def settings():
    return load_settings("configs/demo", environ={})


@pytest.fixture
def pipeline_factory(chunks):
    class Graph:
        def search(self, request):
            return GraphRetrievalResult()

    class Model:
        def predict(self, pairs, *, batch_size):
            return list(range(len(pairs)))

    def build(settings, *, evaluation=None):
        return create_pipeline(
            settings,
            query_llm=FixtureLLM({"rewritten_query": "bằng chứng chuẩn", "intent": "lookup", "metadata": {}}),
            evaluation_llm=evaluation or FixtureLLM({"is_relevant": True, "is_sufficient": True,
                "confidence": 1, "next_action": "continue", "reason": "fixture sufficient"}),
            citation_llm=FixtureLLM({"is_supported": True, "reason": "fixture supported"}),
            answer_generator=AnswerGenerator(FixtureLLM({"answer": "kết luận giả lập", "sources": [1]})),
            token_counter=len, bm25_retriever=BM25Retriever(chunks), vector_retriever=BM25Retriever(chunks),
            graph_retriever=Graph(), reranker=CrossEncoderReRanker(model=Model()))
    return build
