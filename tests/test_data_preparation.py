"""Token/structure invariants and source-backed graph construction without services."""

from unittest.mock import Mock

import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from core.config.settings import ChunkingSettings, EmbeddingSettings, GraphSettings, RetrievalSettings
from core.exceptions import EmbeddingError
from core.schemas import (
    ContextBuilderRequest, GraphRetrievalRequest, LegalChunk, LegalDocument, LegalMetadata,
    RetrievalResult,
)
from src.data_pipeline.chunking import FixedTokenChunker, HierarchicalChunker, LegalChunker
from src.data_pipeline.embedding import EmbeddingPipeline
from src.generation import LegalContextBuilder
from src.infrastructure.embedding import OllamaEmbedding
from src.infrastructure.graph_store import InMemoryGraphStore
from src.infrastructure.tokenization import ModelTokenizer
from src.knowledge_graph import GraphBuilder, GraphRetriever
from src.retrieval.common import as_hit
from src.retrieval.service import RetrievalService


@pytest.fixture
def tokenizer():
    result = ModelTokenizer.__new__(ModelTokenizer)
    result.tokenizer = Tokenizer(WordLevel({"[UNK]": 0}, unk_token="[UNK]"))
    result.tokenizer.pre_tokenizer = Whitespace()
    return result


def source(identifier="a", *, document="doc-a", article="Điều 1.1.LQ.1. Phạm vi", content=None, **metadata):
    return LegalChunk(
        chunk_id=identifier, document_id=document, article=article,
        content=content or article + "\nNội dung nguồn giả lập.",
        metadata=LegalMetadata(
            document_id=document, title="Văn bản giả lập", document_number="MOCK-" + document,
            document_type="law", **metadata,
        ),
    )


def test_unicode_token_windows_keep_source_spans_and_overlap(tokenizer):
    text = "một hai ba bốn năm sáu bảy tám chín mười"
    windows = tokenizer.windows(text, max_tokens=4, overlap_tokens=1)
    assert windows == ["một hai ba bốn", "bốn năm sáu bảy", "bảy tám chín mười"]
    assert all(tokenizer.count(piece) <= 4 and piece in text for piece in windows)
    with pytest.raises(ValueError):
        tokenizer.windows(text, max_tokens=4, overlap_tokens=4)


@pytest.mark.parametrize("chunker_type", [FixedTokenChunker, LegalChunker, HierarchicalChunker])
def test_chunking_is_bounded_deterministic_and_preserves_source(tokenizer, chunker_type):
    body = "1. " + " ".join(f"từ{i}" for i in range(45)) + "\n2. " + " ".join(f"khác{i}" for i in range(30))
    original = source(content="Điều 1.1.LQ.1. Phạm vi\n" + body)
    before = original.model_dump()
    chunker = chunker_type(tokenizer, ChunkingSettings(target_tokens=28, overlap_tokens=3))
    result = chunker.split_chunk(original)
    assert result.chunks
    assert all(tokenizer.count(chunk.content) <= 28 for chunk in result.chunks)
    parent_ids = {chunk.chunk_id for chunk in result.parents}
    assert all(chunk.parent_id in parent_ids for chunk in result.chunks)
    assert len({chunk.chunk_id for chunk in [*result.chunks, *result.parents]}) == len(result.chunks) + len(result.parents)
    assert [chunk.chunk_id for chunk in chunker.split_chunk(original).chunks] == [chunk.chunk_id for chunk in result.chunks]
    assert original.model_dump() == before
    for word in [f"từ{i}" for i in range(45)] + [f"khác{i}" for i in range(30)]:
        assert any(word in chunk.content for chunk in result.chunks)


def test_hierarchy_keeps_clause_conditions_with_points(tokenizer):
    original = source(content="Điều 1\n1. Khi đủ điều kiện:\na) " + "nội dung " * 25 + "\nb) " + "quy định " * 25)
    original.article = "Điều 1"
    result = HierarchicalChunker(tokenizer, ChunkingSettings(target_tokens=24, overlap_tokens=2)).split_chunk(original)
    assert {chunk.point for chunk in result.chunks} == {"a", "b"}
    assert all(chunk.clause == "1" and "Khi đủ điều kiện" in chunk.content for chunk in result.chunks)


def test_restarted_lists_do_not_create_duplicate_or_ambiguous_clause_ids(tokenizer):
    original = source(content="Điều 1\n1. " + "nguồn đầu " * 30 + "\n2. Nguồn hai.\n1. " + "nguồn trích dẫn " * 30)
    original.article = "Điều 1"
    result = HierarchicalChunker(tokenizer, ChunkingSettings(target_tokens=30, overlap_tokens=2)).split_chunk(original)
    assert all(chunk.clause is None for chunk in result.chunks)
    assert len({chunk.chunk_id for chunk in result.parents + result.chunks}) == len(result.parents + result.chunks)
    assert any("nguồn đầu" in chunk.content for chunk in result.chunks)
    assert any("nguồn trích dẫn" in chunk.content for chunk in result.chunks)


def test_legal_chunker_uses_existing_article_parser(tokenizer):
    document = LegalDocument(
        document_id="doc-a", metadata=source().metadata,
        content="Điều 1. Phạm vi\nNội dung một.\nĐiều 2. Trách nhiệm\nNội dung hai.",
    )
    result = LegalChunker(tokenizer, ChunkingSettings(target_tokens=40, overlap_tokens=2)).chunk(document)
    assert len(result.chunks) == 2
    assert result.chunks[0].article.startswith("Điều 1")
    assert result.chunks[1].article.startswith("Điều 2")


def test_embedding_batches_preserve_count_order_and_input():
    embedding = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="fixture", dimension=2, batch_size=2))
    embedding._client = Mock()
    embedding._client.post.side_effect = [
        {"embeddings": [[3, 4], [4, 3]]}, {"embeddings": [[1, 0]]},
    ]
    inputs = [source("a"), source("b"), source("c")]
    result = EmbeddingPipeline(embedding, batch_size=3).run(inputs)
    assert [chunk.chunk_id for chunk in result] == ["a", "b", "c"]
    assert result[0].embedding == [0.6, 0.8]
    assert result[2].embedding == [1, 0]
    assert all(chunk.embedding is None for chunk in inputs)
    assert embedding.embed_documents([]) == []
    assert embedding._client.post.call_count == 2
    assert embedding._client.post.call_args.kwargs["error_type"] is EmbeddingError


@pytest.mark.parametrize("raw", [[], [[1]], [[float("nan"), 1]], [[0, 0]]])
def test_invalid_embedding_protocol_is_rejected(raw):
    embedding = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="fixture", dimension=2))
    embedding._client = Mock()
    embedding._client.post.return_value = {"embeddings": raw}
    with pytest.raises(EmbeddingError):
        embedding.embed_query("query")


def test_graph_normalizes_legacy_references_without_inventing_external_nodes(tokenizer):
    a, b = source("a"), source("b", document="doc-b", article="Điều 1.2.LQ.2. Định nghĩa")
    chunker = HierarchicalChunker(tokenizer, ChunkingSettings(target_tokens=50, overlap_tokens=2))
    first, second = chunker.split_chunk(a), chunker.split_chunk(b)
    graph = GraphBuilder().build(first.chunks + second.chunks, first.parents + second.parents, [
        {"source": "Điều 1.1.LQ.1", "target": "Điều 1.2.LQ.2", "type": "RELATED_TO", "evidence": "Nguồn có dẫn chiếu"},
        {"source": "Điều 1.1.LQ.1", "target": "Điều 99.1.LQ.1", "type": "RELATED_TO", "evidence": "Ngoài corpus"},
    ])
    assert len(graph.relations) == 1 and len(graph.unresolved) == 1
    edge = graph.relations[0]
    assert edge["source_document_id"] == "doc-a" and edge["target_document_id"] == "doc-b"
    assert set(edge["evidence_chunk_ids"]).issubset({chunk.chunk_id for chunk in graph.chunks})


def test_metadata_amendment_direction_is_later_to_earlier():
    a = source("a", amended_by=["doc-b"])
    b = source("b", document="doc-b")
    edge = GraphBuilder().build([a, b], [], []).relations[0]
    assert (edge["source_document_id"], edge["relation_type"], edge["target_document_id"]) == ("doc-b", "AMENDS", "doc-a")


def test_graph_does_not_replace_unknown_or_unrelated_evidence():
    a, b, c = source("a"), source("b", document="doc-b"), source("c", document="doc-c")
    raw = {"source": "doc-a", "target": "doc-b", "type": "RELATED_TO", "evidence": "Reference"}
    for identifiers in ([], ["missing"], ["a", "missing"], ["c"]):
        graph = GraphBuilder().build([a, b, c], [], [{**raw, "evidence_chunk_ids": identifiers}])
        assert graph.relations == [] and len(graph.unresolved) == 1


def test_legacy_graph_evidence_uses_referenced_article_not_first_document_chunk():
    first = source("first", article="Điều 1.1.LQ.1. Phạm vi")
    cited = source("cited", article="Điều 1.1.LQ.2. Dẫn chiếu")
    target = source("target", document="doc-b", article="Điều 1.2.LQ.3. Quy định")
    graph = GraphBuilder().build([first, cited, target], [], [{
        "source": "Điều 1.1.LQ.2", "target": "Điều 1.2.LQ.3", "type": "RELATED_TO", "evidence": "Reference",
    }])
    assert graph.relations[0]["evidence_chunk_ids"] == ["cited", "target"]


def test_graph_bfs_depth_limit_and_post_graph_filters():
    a = source("a", legal_domain=["labor"], related_documents=["doc-b"])
    b = source("b", document="doc-b", legal_domain=["tax"], related_documents=["doc-c"])
    c = source("c", document="doc-c", legal_domain=["tax"])
    store = InMemoryGraphStore()
    store.write(GraphBuilder().build([a, b, c], [], []))
    retriever = GraphRetriever(store, GraphSettings(max_depth=2, max_nodes=10))
    one = retriever.search(GraphRetrievalRequest(query="nguồn", seed_document_ids=["doc-a"], max_depth=1))
    assert set(one.related_document_ids) == {"doc-a", "doc-b"}
    two = retriever.search(GraphRetrievalRequest(query="nguồn", seed_document_ids=["doc-a"], max_depth=2))
    assert set(two.related_document_ids) == {"doc-a", "doc-b", "doc-c"}
    limited = GraphRetriever(store, GraphSettings(max_nodes=2)).search(
        GraphRetrievalRequest(query="nguồn", seed_document_ids=["doc-a"]),
    )
    assert len(limited.results) <= 2 and len(limited.related_document_ids) <= 2
    result = RetrievalService(
        graph_retriever=retriever,
        settings=RetrievalSettings(use_bm25=False, use_vector=False, use_graph=True, use_rerank=False),
    ).retrieve("nguồn", {"legal_domain": ["labor"]}, entities=["doc-a"])
    assert [hit.document_id for hit in result.results] == ["doc-a"]
    assert result.relations == []


def test_missing_graph_parent_is_rejected():
    child = source()
    child.parent_id = "missing"
    with pytest.raises(ValueError, match="missing graph parent"):
        GraphBuilder().build([child], [], [])


def test_cross_document_graph_parent_is_rejected():
    child = source("child")
    parent = source("parent", document="doc-b")
    child.parent_id = parent.chunk_id
    with pytest.raises(ValueError, match="same document"):
        GraphBuilder().build([child], [parent], [])


def test_parent_context_expansion_keeps_complete_source_and_correct_identity():
    parent = source(content="Điều 1.1.LQ.1. Phạm vi\nĐủ điều kiện thì áp dụng. Ngoại lệ phải được xem xét.")
    child = source("leaf", content="Đủ điều kiện thì áp dụng.")
    child.parent_id = parent.chunk_id
    builder = LegalContextBuilder(token_counter=len, parent_lookup={parent.chunk_id: as_hit(parent)}.get)
    result = builder.build(ContextBuilderRequest(
        original_query="query", retrieval_result=RetrievalResult(query="query", results=[as_hit(child)]),
    ))
    assert result.chunks[0].chunk_id == parent.chunk_id
    assert "Ngoại lệ phải được xem xét" in result.context_text
    assert result.cited_document_ids == [parent.document_id]
