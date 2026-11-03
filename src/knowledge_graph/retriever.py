"""Bounded breadth-first document expansion over a pluggable graph store."""

from typing import Protocol

from core.config.settings import GraphSettings
from core.exceptions import RetrievalError
from core.interfaces import BaseGraphRetriever
from core.schemas import GraphRetrievalRequest, GraphRetrievalResult, RetrievedChunk
from src.retrieval.common import scored_hit
from src.retrieval.sparse.bm25 import tokenize


class GraphStore(Protocol):
    def lookup(self, entities: list[str], limit: int) -> list[str]: ...
    def neighbors(self, documents: list[str], limit: int) -> list[str]: ...
    def chunks(self, documents: list[str], limit: int) -> list[RetrievedChunk]: ...
    def relations(self, documents: list[str]) -> list[dict]: ...


class GraphRetriever(BaseGraphRetriever):
    def __init__(self, store: GraphStore, settings: GraphSettings | None = None):
        self.store = store
        self.settings = settings or GraphSettings()

    def search(self, request: GraphRetrievalRequest) -> GraphRetrievalResult:
        try:
            seeds = request.seed_document_ids or self.store.lookup(request.entities, self.settings.max_nodes)
            depths = {identifier: 0 for identifier in seeds[:self.settings.max_nodes]}
            frontier = list(depths)
            for depth in range(1, min(request.max_depth, self.settings.max_depth) + 1):
                remaining = self.settings.max_nodes - len(depths)
                if not frontier or remaining <= 0:
                    break
                neighbors = self.store.neighbors(frontier, self.settings.max_nodes)
                frontier = [identifier for identifier in neighbors if identifier not in depths][:remaining]
                depths.update((identifier, depth) for identifier in frontier)
            candidates = self.store.chunks(list(depths), self.settings.max_nodes)
            words = set(tokenize(request.query))
            candidates.sort(key=lambda hit: (
                -len(words.intersection(tokenize(hit.content))), depths.get(hit.document_id, 0), hit.chunk_id,
            ))
            hits = [scored_hit(hit, 1.0 / (1 + depths[hit.document_id]), "graph") for hit in candidates]
            ids = {hit.chunk_id for hit in hits}
            # A later hybrid branch may supply a target document's chunks;
            # endpoint retention is checked after branch aggregation.
            relations = [edge for edge in self.store.relations(list(depths))
                         if edge.get("evidence_chunk_ids") and set(edge["evidence_chunk_ids"]).issubset(ids)]
            return GraphRetrievalResult(
                results=hits, relations=relations, related_document_ids=list(depths),
            )
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("graph traversal failed") from exc
