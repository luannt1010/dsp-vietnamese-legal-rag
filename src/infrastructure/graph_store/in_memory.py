"""Deterministic graph backend for tests and later backend comparisons."""

from core.schemas import RetrievedChunk
from src.knowledge_graph.builder import GraphSnapshot
from src.retrieval.common import as_hit


class InMemoryGraphStore:
    def __init__(self):
        self.hits: list[RetrievedChunk] = []
        self.edges: list[dict] = []

    def write(self, snapshot: GraphSnapshot) -> None:
        self.hits = [as_hit(chunk) for chunk in snapshot.chunks]
        self.edges = [dict(edge) for edge in snapshot.relations]

    def lookup(self, entities: list[str], limit: int) -> list[str]:
        result = []
        for hit in self.hits:
            names = [hit.document_id, hit.metadata.get("title", ""), hit.metadata.get("document_number", "")]
            if any(entity.casefold() in str(name).casefold() for entity in entities if entity.strip() for name in names):
                if hit.document_id not in result:
                    result.append(hit.document_id)
        return result[:limit]

    def neighbors(self, documents: list[str], limit: int) -> list[str]:
        found = set()
        for edge in self.edges:
            if edge["source_document_id"] in documents:
                found.add(edge["target_document_id"])
            if edge["target_document_id"] in documents:
                found.add(edge["source_document_id"])
        return sorted(found)[:limit]

    def chunks(self, documents: list[str], limit: int) -> list[RetrievedChunk]:
        return [hit.model_copy(deep=True) for hit in self.hits if hit.document_id in documents][:limit]

    def relations(self, documents: list[str]) -> list[dict]:
        return [dict(edge) for edge in self.edges if edge["source_document_id"] in documents and edge["target_document_id"] in documents]

    def close(self) -> None:
        pass
