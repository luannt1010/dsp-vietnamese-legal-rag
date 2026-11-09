"""Prepare reuses healthy stores and repairs only an incomplete backend."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core.config import load_settings
import src.runtime as runtime


@pytest.fixture
def prepared_stores(monkeypatch):
    corpus = SimpleNamespace(
        corpus_id="fixture", chunks=[object(), object()], parents=[object()],
        graph=SimpleNamespace(relations=[{}], unresolved=[]), manifest={"corpus_id": "fixture"},
    )

    class Vector:
        def __init__(self):
            self.count = Mock(return_value=2)
            self.has_index = Mock(return_value=True)
            self.upsert = Mock(side_effect=self.complete)

        def complete(self, chunks):
            self.count.return_value = len(chunks)
            self.has_index.return_value = True

    class Graph:
        def __init__(self):
            self.counts = Mock(return_value={"documents": 1, "chunks": 2, "parents": 1, "relations": 1})
            self.is_ready = Mock(return_value=True)
            self.write = Mock(side_effect=self.complete)

        def complete(self, snapshot):
            self.counts.return_value = {"documents": 1, "chunks": 2, "parents": 1, "relations": 1}
            self.is_ready.return_value = True

    vector, graph = Vector(), Graph()
    @contextmanager
    def stores(*args):
        yield vector, graph

    monkeypatch.setattr(runtime, "PgVectorStore", Vector)
    monkeypatch.setattr(runtime, "Neo4jStore", Graph)
    monkeypatch.setattr(runtime, "open_stores", stores)
    monkeypatch.setattr(runtime, "prepare_corpus", Mock(return_value=corpus))
    return load_settings("configs", environ={}), corpus, vector, graph


@pytest.mark.parametrize("state,vector_writes,graph_writes", [
    ("ready", 0, 0),
    ("missing_rows", 1, 0),
    ("missing_ann_index", 1, 0),
    ("graph_interrupted", 0, 1),
    ("graph_wrong_counts", 0, 1),
    ("both_missing", 1, 1),
])
def test_prepare_writes_only_incomplete_backend(prepared_stores, state, vector_writes, graph_writes):
    settings, corpus, vector, graph = prepared_stores
    if state in {"missing_rows", "both_missing"}:
        vector.count.return_value = 0
    if state == "missing_ann_index":
        vector.has_index.return_value = False
    if state in {"graph_interrupted", "both_missing"}:
        graph.is_ready.return_value = False
    if state == "graph_wrong_counts":
        graph.counts.return_value = {"documents": 1, "chunks": 1, "parents": 1, "relations": 1}
    messages = []
    result = runtime.prepare_indexes(settings, progress=messages.append)
    assert result["corpus_id"] == corpus.corpus_id
    assert vector.upsert.call_count == vector_writes
    assert graph.write.call_count == graph_writes
    if not vector_writes:
        assert "Vector index already ready; skipping indexing" in messages
    if not graph_writes:
        assert "Graph index already ready; skipping indexing" in messages


def test_force_reindex_preserves_explicit_rewrite_option(prepared_stores):
    settings, corpus, vector, graph = prepared_stores
    runtime.prepare_indexes(settings, force_reindex=True, progress=lambda _: None)
    vector.upsert.assert_called_once_with(corpus.chunks)
    graph.write.assert_called_once_with(corpus.graph)


def test_rerun_after_interrupted_graph_does_not_rewrite_ready_vector(prepared_stores):
    settings, corpus, vector, graph = prepared_stores
    graph.is_ready.return_value = False
    graph.write.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        runtime.prepare_indexes(settings, progress=lambda _: None)
    graph.write.side_effect = graph.complete
    runtime.prepare_indexes(settings, progress=lambda _: None)
    vector.upsert.assert_not_called()
    assert graph.write.call_count == 2


def test_demo_reports_interrupt_without_traceback(monkeypatch, capsys):
    from scripts import demo
    monkeypatch.setattr("sys.argv", ["demo", "prepare"])
    monkeypatch.setattr(demo, "load_demo_settings", lambda _: load_settings("configs", environ={}))
    monkeypatch.setattr(demo, "prepare_indexes", Mock(side_effect=KeyboardInterrupt))
    assert demo.main() == 130
    error = capsys.readouterr().err
    assert "Interrupted by user" in error
    assert "Traceback" not in error
