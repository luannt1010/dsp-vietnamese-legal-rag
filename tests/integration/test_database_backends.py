"""Opt-in actual pgvector/Neo4j contract checks, using isolated test namespaces."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg import sql

from core.config import load_settings
from core.config.settings import VectorDatabaseSettings
from core.schemas import LegalChunk, LegalMetadata
from src.infrastructure.graph_store import Neo4jStore
from src.infrastructure.vector_store import InMemoryVectorStore, PgVectorStore
from src.knowledge_graph import GraphBuilder, GraphRetriever
from core.schemas import GraphRetrievalRequest


pytestmark = pytest.mark.skipif(os.environ.get("RAG_RUN_DB_TESTS") != "1", reason="set RAG_RUN_DB_TESTS=1 for actual database checks")


@pytest.fixture
def settings():
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".runtime/demo.env", override=False, encoding="utf-8-sig")
    return load_settings(root / "configs/demo")


def corpus():
    return [LegalChunk(
        chunk_id=f"c-{i}", document_id=f"doc-{i}", content=f"Nội dung giả lập {i}",
        article="Điều 1", embedding=[1.0, i / 10],
        metadata=LegalMetadata(
            document_id=f"doc-{i}", title="Fixture", document_number=f"MOCK-{i}", document_type="law",
            legal_domain=["labor" if i % 2 == 0 else "tax"],
        ),
    ) for i in range(40)]


@pytest.mark.parametrize("method", ["exact", "hnsw", "ivfflat"])
@pytest.mark.parametrize("metric", ["cosine", "inner_product", "l2"])
def test_pgvector_preserves_metric_scores_and_filters_before_limit(settings, method, metric):
    config = VectorDatabaseSettings.model_validate({
        **settings.database.vector.model_dump(), "index_type": method, "distance_metric": metric,
        "ivfflat_probes": 1, "ivfflat_lists": 2,
    })
    name = "test_" + uuid4().hex[:16]
    store = PgVectorStore(config, dimension=2, table_name=name)
    try:
        chunks = corpus()
        store.upsert(chunks)
        assert store.count() == len(chunks) and store.has_index()
        if method != "exact":
            # Tiny fixtures otherwise use a sequential scan: exercise the real
            # ANN access method rather than just checking index existence.
            with store.pool.connection() as connection:
                connection.execute("SET enable_seqscan = off")
                plan = connection.execute(sql.SQL(
                    "EXPLAIN SELECT chunk_id FROM {} ORDER BY embedding {} %s::vector LIMIT 3"
                ).format(store.table, sql.SQL(store.operator)), ("[1,0.01]",)).fetchall()
                assert any(name + "_" + method in row[0] for row in plan)
        reference = InMemoryVectorStore(chunks, dimension=2, distance_metric=metric)
        for filters in ({}, {"legal_domain": ["labor"]}, {"effective_date": None}, {"legal_domain": []}, {"source_url": None}):
            actual = store.search([1, 0.01], filters=filters, top_k=3)
            expected = reference.search([1, 0.01], filters=filters, top_k=len(chunks))
            by_id = {hit.chunk_id: hit for hit in expected}
            assert len(actual) == min(3, len(expected))
            assert all(hit.chunk_id in by_id for hit in actual)
            assert [hit.score for hit in actual] == sorted((hit.score for hit in actual), reverse=True)
            assert [hit.score for hit in actual] == pytest.approx([by_id[hit.chunk_id].score for hit in actual], abs=1e-5)
            if method == "exact":
                assert [hit.chunk_id for hit in actual] == [hit.chunk_id for hit in expected[:3]]
            # ANN may return a different candidate set; exact recall is a
            # benchmark question, not an invariant of an approximate index.
    finally:
        store.close()
        assert name.startswith("test_")
        config_values = {
            "host": config.host, "port": config.port, "dbname": config.database, "user": config.username,
            "password": config.password.get_secret_value(),
        }
        with psycopg.connect(**config_values) as connection:
            connection.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier(config.schema_name, name)))


def test_neo4j_persists_hierarchy_and_source_relations(settings):
    namespace = "test_" + uuid4().hex
    store = Neo4jStore(settings.database.graph, namespace=namespace)
    chunks = corpus()[:3]
    chunks[0].metadata.related_documents = [chunks[1].document_id]
    parent = chunks[0].model_copy(deep=True, update={"chunk_id": "parent-0", "embedding": None})
    chunks[0].parent_id = parent.chunk_id
    graph = GraphBuilder().build(chunks, [parent], [])
    try:
        assert not store.is_ready()
        store.write(graph)
        assert store.is_ready()
        store._run("MATCH (c:RAGCorpus {namespace:$ns}) SET c.complete=false")
        assert not store.is_ready()  # An interrupted write is not a ready index.
        store.write(graph)  # MERGE is idempotent within this isolated corpus.
        assert store.is_ready()
        assert store.counts() == {"documents": 3, "chunks": 3, "parents": 1, "relations": 1}
        assert store._run("MATCH (c:RAGChunk {namespace:$ns})-[:PART_OF]->(p:RAGChunk {namespace:$ns}) RETURN c.chunk_id AS child, p.chunk_id AS parent") == [{"child": "c-0", "parent": "parent-0"}]
        result = GraphRetriever(store).search(GraphRetrievalRequest(
            query="nội dung", seed_document_ids=[chunks[0].document_id], max_depth=1,
        ))
        assert {hit.document_id for hit in result.results} == {chunks[0].document_id, chunks[1].document_id}
        assert result.relations[0]["evidence_chunk_ids"]
    finally:
        assert namespace.startswith("test_")
        store._run("MATCH (n {namespace:$ns}) DETACH DELETE n")
        store.close()
