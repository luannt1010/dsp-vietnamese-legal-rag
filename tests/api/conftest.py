"""Inject fixture providers at the runtime boundary; exercise the real HTTP app."""

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from core.config import Settings, load_settings
from core.schemas import LegalAnswer, LegalChunk, LegalContext, LegalMetadata, PipelineResult
from src.api.main import create_app
from src.data_pipeline.preparation import PreparedCorpus
from src.knowledge_graph import GraphSnapshot
from src.orchestration import RAGPipeline
from src.retrieval.common import as_hit
from src.runtime import DemoRuntime


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def settings():
    original = load_settings("configs/demo", environ={})
    data = original.model_dump()
    data["api"]["cors_origins"] = ["http://localhost:5173"]
    return Settings.model_validate(data)


@pytest.fixture
def runtime():
    chunk = LegalChunk(
        chunk_id="fixture-chunk", document_id="fixture-document", content="Nội dung nguồn giả lập.",
        article="Điều 1", metadata=LegalMetadata(
            document_id="fixture-document", title="Văn bản giả lập", document_number="01/2026/TEST",
            document_type="mock", topic_title="Giáo dục, đào tạo", subject_title="Đề mục giả lập",
            source_revision="fixed-snapshot", source_url="https://example.com/source",
        ),
    )
    graph = GraphSnapshot(chunks=[chunk])
    corpus = PreparedCorpus(
        corpus_id="fixture-corpus", chunks=[chunk], parents=[], graph=graph,
        manifest={"signature": {"source": {"dataset": "fixture-dataset", "revision": "fixed-snapshot"}}},
        directory=Path("unused-fixture-path"),
    )
    pipeline = Mock(spec=RAGPipeline)
    pipeline.run_with_trace.return_value = PipelineResult(
        status="completed", answer=LegalAnswer(
            answer="Đáp án đã kiểm chứng.", confidence=0,
            citations=[{
                "document_id": chunk.document_id, "document_number": chunk.metadata.document_number,
                "article": chunk.article, "quoted_text": chunk.content,
                "source_url": chunk.metadata.source_url,
            }],
        ),
        context=LegalContext(
            query="Câu hỏi", context_text=chunk.content, chunks=[as_hit(chunk)],
            cited_document_ids=[chunk.document_id],
        ),
    )
    return DemoRuntime(pipeline=pipeline, corpus=corpus, vector_store=Mock(), graph_store=Mock())


@pytest.fixture
def runtime_factory(runtime):
    calls = []

    @contextmanager
    def factory(config):
        calls.append(("enter", config))
        try:
            yield runtime
        finally:
            calls.append(("exit", config))

    factory.calls = calls
    return factory


@pytest.fixture
def app(settings, runtime_factory):
    return create_app(settings, runtime_factory=runtime_factory)


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as session:
        yield session
