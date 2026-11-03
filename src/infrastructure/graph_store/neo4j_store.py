"""Neo4j persistence with explicit hierarchy, typed legal edges and namespace isolation."""

import hashlib
import json

from neo4j import GraphDatabase, Query

from core.config.settings import GraphDatabaseSettings
from core.deadline import remaining_timeout
from core.exceptions import RetrievalError
from core.schemas import RetrievedChunk
from src.knowledge_graph.builder import GraphSnapshot
from src.retrieval.common import as_hit


class Neo4jStore:
    def __init__(self, settings: GraphDatabaseSettings, *, namespace: str | None = None):
        self.settings = settings
        self.namespace = namespace or settings.namespace
        auth = (settings.username, settings.password.get_secret_value()) if settings.password else None
        try:
            self.driver = GraphDatabase.driver(
                settings.uri, auth=auth, connection_timeout=settings.connect_timeout_s,
                max_connection_pool_size=settings.pool_size, max_transaction_retry_time=0,
            )
            self.driver.verify_connectivity()
        except Exception as exc:
            raise RetrievalError("could not connect to Neo4j; check URI and credentials") from exc

    def _run(self, statement: str, **parameters) -> list[dict]:
        try:
            timeout = remaining_timeout(self.settings.connect_timeout_s)
            with self.driver.session(database=self.settings.database) as session:
                return session.run(Query(statement, timeout=timeout), ns=self.namespace, **parameters).data()
        except Exception as exc:
            raise RetrievalError("Neo4j query failed") from exc

    def write(self, snapshot: GraphSnapshot) -> None:
        self._run("CREATE CONSTRAINT legalrag_corpus IF NOT EXISTS FOR (c:RAGCorpus) REQUIRE c.namespace IS UNIQUE")
        self._run("MERGE (c:RAGCorpus {namespace:$ns}) SET c.complete=false")
        for label, key in (("RAGDocument", "document_id"), ("RAGChunk", "chunk_id"), ("RAGReference", "reference_id")):
            self._run(f"CREATE CONSTRAINT legalrag_{key} IF NOT EXISTS FOR (n:{label}) REQUIRE (n.namespace, n.{key}) IS UNIQUE")
        documents = {}
        retrievable = {chunk.chunk_id for chunk in snapshot.chunks}
        rows = []
        for chunk in [*snapshot.parents, *snapshot.chunks]:
            documents[chunk.document_id] = chunk.metadata.model_dump(mode="json")
            hit = as_hit(chunk)
            rows.append({
                "id": hit.chunk_id, "document_id": hit.document_id, "content": hit.content,
                "metadata": json.dumps(hit.metadata, ensure_ascii=False, allow_nan=False),
                "parent_id": chunk.parent_id, "retrievable": chunk.chunk_id in retrievable,
            })
        self._run(
            "UNWIND $rows AS row MERGE (d:RAGDocument {namespace:$ns, document_id:row.document_id}) "
            "SET d.title=row.title, d.document_number=row.document_number",
            rows=list(documents.values()),
        )
        for offset in range(0, len(rows), 100):
            self._run(
                "UNWIND $rows AS row MATCH (d:RAGDocument {namespace:$ns, document_id:row.document_id}) "
                "MERGE (c:RAGChunk {namespace:$ns, chunk_id:row.id}) "
                "SET c.document_id=row.document_id, c.content=row.content, c.metadata=row.metadata, "
                "c.parent_id=row.parent_id, c.retrievable=row.retrievable MERGE (d)-[:CONTAINS]->(c)",
                rows=rows[offset:offset + 100],
            )
        self._run(
            "MATCH (c:RAGChunk {namespace:$ns}), (p:RAGChunk {namespace:$ns}) "
            "WHERE c.parent_id=p.chunk_id MERGE (c)-[:PART_OF]->(p)",
        )
        self._run(
            "UNWIND $rows AS row MATCH (a:RAGDocument {namespace:$ns, document_id:row.source_document_id}), "
            "(b:RAGDocument {namespace:$ns, document_id:row.target_document_id}) "
            "MERGE (a)-[r:LEGAL_RELATION {relation_type:row.relation_type}]->(b) "
            "SET r.evidence_chunk_ids=row.evidence_chunk_ids, r.evidence_text=row.evidence_text",
            rows=snapshot.relations,
        )
        references = [{
            "reference_id": hashlib.sha256(json.dumps(ref, sort_keys=True).encode()).hexdigest(),
            "data": json.dumps(ref, ensure_ascii=False),
        } for ref in snapshot.unresolved]
        self._run(
            "UNWIND $rows AS row MERGE (r:RAGReference {namespace:$ns, reference_id:row.reference_id}) SET r.data=row.data",
            rows=references,
        )
        self._run("MATCH (c:RAGCorpus {namespace:$ns}) SET c.complete=true")

    def is_ready(self) -> bool:
        rows = self._run("MATCH (c:RAGCorpus {namespace:$ns}) RETURN c.complete AS complete")
        return bool(rows and rows[0]["complete"])

    def lookup(self, entities: list[str], limit: int) -> list[str]:
        if not entities:
            return []
        rows = self._run(
            "MATCH (d:RAGDocument {namespace:$ns}) WHERE any(term IN $terms WHERE "
            "toLower(d.title) CONTAINS term OR toLower(d.document_number) CONTAINS term OR toLower(d.document_id)=term) "
            "RETURN d.document_id AS id ORDER BY id LIMIT $limit",
            terms=[entity.casefold() for entity in entities if entity.strip()], limit=limit,
        )
        return [row["id"] for row in rows]

    def neighbors(self, documents: list[str], limit: int) -> list[str]:
        rows = self._run(
            "MATCH (a:RAGDocument {namespace:$ns})-[:LEGAL_RELATION]-(b:RAGDocument {namespace:$ns}) "
            "WHERE a.document_id IN $ids RETURN DISTINCT b.document_id AS id ORDER BY id LIMIT $limit",
            ids=documents, limit=limit,
        )
        return [row["id"] for row in rows]

    def chunks(self, documents: list[str], limit: int) -> list[RetrievedChunk]:
        rows = self._run(
            "MATCH (d:RAGDocument {namespace:$ns})-[:CONTAINS]->(c:RAGChunk) "
            "WHERE d.document_id IN $ids AND c.retrievable=true "
            "RETURN c.chunk_id AS id, c.document_id AS document_id, c.content AS content, c.metadata AS metadata "
            "ORDER BY document_id, id LIMIT $limit", ids=documents, limit=limit,
        )
        return [RetrievedChunk(
            chunk_id=row["id"], document_id=row["document_id"], content=row["content"],
            metadata=json.loads(row["metadata"]), score=0.0, retrieval_method="graph",
        ) for row in rows]

    def relations(self, documents: list[str]) -> list[dict]:
        return self._run(
            "MATCH (a:RAGDocument {namespace:$ns})-[r:LEGAL_RELATION]->(b:RAGDocument {namespace:$ns}) "
            "WHERE a.document_id IN $ids AND b.document_id IN $ids RETURN a.document_id AS source_document_id, "
            "b.document_id AS target_document_id, r.relation_type AS relation_type, r.evidence_chunk_ids AS evidence_chunk_ids",
            ids=documents,
        )

    def counts(self) -> dict:
        return {
            "documents": self._run("MATCH (d:RAGDocument {namespace:$ns}) RETURN count(d) AS n")[0]["n"],
            "chunks": self._run("MATCH (c:RAGChunk {namespace:$ns}) WHERE c.retrievable=true RETURN count(c) AS n")[0]["n"],
            "parents": self._run("MATCH (c:RAGChunk {namespace:$ns}) WHERE c.retrievable=false RETURN count(c) AS n")[0]["n"],
            "relations": self._run("MATCH (:RAGDocument {namespace:$ns})-[r:LEGAL_RELATION]->() RETURN count(r) AS n")[0]["n"],
        }

    def close(self) -> None:
        self.driver.close()
