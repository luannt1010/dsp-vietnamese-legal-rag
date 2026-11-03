"""Build source-backed document relations and retain unresolved external references."""

import re
from collections import defaultdict
from dataclasses import dataclass, field

from core.schemas import LegalChunk


_ARTICLE_CODE = re.compile(r"Điều\s+\d+(?:\.\d+)*\.[A-ZĐ]+\.\d+(?:\.\d+)*", re.IGNORECASE)
_RELATION_FIELDS = {"amended_by": "AMENDS", "replaced_by": "REPLACES", "repealed_by": "REPEALS", "related_documents": "RELATED_TO"}
_RELATION_TYPES = frozenset(_RELATION_FIELDS.values())


@dataclass
class GraphSnapshot:
    chunks: list[LegalChunk]
    parents: list[LegalChunk] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    unresolved: list[dict] = field(default_factory=list)


class GraphBuilder:
    def build(self, chunks: list[LegalChunk], parents: list[LegalChunk], raw_relations: list[dict]) -> GraphSnapshot:
        result = GraphSnapshot(chunks=chunks, parents=parents)
        all_chunks = {chunk.chunk_id: chunk for chunk in [*parents, *chunks]}
        if len(all_chunks) != len(chunks) + len(parents):
            raise ValueError("graph chunk and parent IDs must be unique")
        leaves = defaultdict(list)
        aliases = defaultdict(set)
        anchors = defaultdict(list)
        article_records = defaultdict(set)
        document_chunks = defaultdict(list)
        for chunk in chunks:
            document_chunks[chunk.document_id].append(chunk.chunk_id)
            current = chunk
            seen = set()
            while current.chunk_id not in seen:
                seen.add(current.chunk_id)
                leaves[current.chunk_id].append(chunk.chunk_id)
                if current.parent_id is None:
                    break
                if current.parent_id not in all_chunks:
                    raise ValueError(f"missing graph parent: {current.parent_id}")
                current = all_chunks[current.parent_id]
                if current.document_id != chunk.document_id:
                    raise ValueError("graph parent must belong to the same document")
            else:
                raise ValueError("cyclic chunk parent hierarchy")
        for chunk in [*parents, *chunks]:
            for alias in (chunk.chunk_id, chunk.document_id, chunk.metadata.document_number):
                aliases[alias].add(chunk.document_id)
                anchors[alias].extend(leaves[chunk.chunk_id])
            if chunk.article:
                match = _ARTICLE_CODE.match(chunk.article)
                if match:
                    aliases[match.group()].add(chunk.document_id)
                    anchors[match.group()].extend(leaves[chunk.chunk_id])
                    if chunk.metadata.source_record_id:
                        article_records[match.group()].add(chunk.metadata.source_record_id)
        edges = {}

        def add(source: str, target: str, kind: str, evidence: list[str], note: str = "") -> None:
            identity = (source, target, kind)
            if identity not in edges:
                edges[identity] = {
                    "source_document_id": source, "target_document_id": target,
                    "relation_type": kind, "evidence_chunk_ids": [], "evidence_text": "",
                }
                result.relations.append(edges[identity])
            edge = edges[identity]
            edge["evidence_chunk_ids"] = list(dict.fromkeys([*edge["evidence_chunk_ids"], *evidence]))
            if note and note not in edge["evidence_text"]:
                edge["evidence_text"] = "\n".join(filter(None, [edge["evidence_text"], note]))

        for raw in raw_relations:
            source_alias = raw.get("source_document_id", raw.get("source"))
            target_alias = raw.get("target_document_id", raw.get("target"))
            kind = str(raw.get("relation_type", raw.get("type", ""))).upper()
            source_ids, target_ids = aliases.get(source_alias, set()), aliases.get(target_alias, set())
            if (len(source_ids) != 1 or len(target_ids) != 1 or kind not in _RELATION_TYPES
                    or len(article_records[source_alias]) > 1 or len(article_records[target_alias]) > 1):
                result.unresolved.append({
                    "source": source_alias, "target": target_alias, "type": kind,
                    "evidence": raw.get("evidence", ""),
                    "reason": "unresolved/ambiguous corpus endpoint or unsupported relation type",
                })
                continue
            source, target = next(iter(source_ids)), next(iter(target_ids))
            evidence = []
            identifiers = raw.get("evidence_chunk_ids")
            if identifiers is None:
                # Legacy article references anchor to their own descendants,
                # never to an unrelated first chunk of the document.
                identifiers = [source_alias, target_alias] if raw.get("evidence") else []
                resolved = [anchors.get(identifier, []) for identifier in identifiers]
            else:
                resolved = [leaves.get(identifier, []) for identifier in identifiers]
            if not resolved or any(not matches for matches in resolved):
                result.unresolved.append({**raw, "reason": "missing or unknown source evidence"})
                continue
            for matches in resolved:
                evidence.extend(matches)
            if any(all_chunks[identifier].document_id not in {source, target} for identifier in evidence):
                result.unresolved.append({**raw, "reason": "evidence belongs to another document"})
                continue
            add(source, target, kind, evidence, str(raw.get("evidence", "")))

        for chunk in chunks:
            for metadata_field, kind in _RELATION_FIELDS.items():
                for other in getattr(chunk.metadata, metadata_field):
                    if other in document_chunks:
                        # amended_by/replaced_by/repealed_by point to the later
                        # document; the typed relation points later -> earlier.
                        src, dst = (chunk.document_id, other) if kind == "RELATED_TO" else (other, chunk.document_id)
                        add(src, dst, kind, [chunk.chunk_id, document_chunks[other][0]])
        return result
