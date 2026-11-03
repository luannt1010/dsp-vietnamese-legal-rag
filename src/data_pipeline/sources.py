"""Resolve configured input into the same source chunks/relations contracts."""

import hashlib
import json
from dataclasses import dataclass

from core.config.settings import DataPipelineSettings
from core.exceptions import ConfigurationError
from core.schemas import LegalChunk
from src.data_pipeline import DataPipelineError
from src.data_pipeline.artifacts import fingerprint, write_json
from src.data_pipeline.loaders.phapdien_dataset import PhapDienDataset
from src.data_pipeline.loaders.phapdien_loader import PhapDienLoader


@dataclass
class SourceCorpus:
    chunks: list[LegalChunk]
    relations: list[dict]
    signature: dict


def load_source(config: DataPipelineSettings, *, build: bool, refresh: bool = False, progress=print) -> SourceCorpus:
    if config.source.type == "json":
        chunks = json.loads(config.source_chunks_file.read_text(encoding="utf-8"))
        relations = json.loads(config.relations_file.read_text(encoding="utf-8"))
        signature = {
            "type": "json", "source_sha256": hashlib.sha256(config.source_chunks_file.read_bytes()).hexdigest(),
            "relations_sha256": hashlib.sha256(config.relations_file.read_bytes()).hexdigest(),
        }
    else:
        if not (config.source.topics or config.source.subjects):
            raise ConfigurationError("huggingface source requires at least one topic or subject; use list-topics/list-subjects")
        dataset = PhapDienDataset(config.source, config.index_dir / "sources").open(
            download=build, refresh=refresh, progress=progress,
        )
        topics = dataset.resolve("topics", config.source.topics)
        subjects = dataset.resolve("subjects", config.source.subjects)
        signature = {
            "type": "huggingface", "dataset": config.source.dataset,
            "config": config.source.config, "split": config.source.split,
            "revision": dataset.revision, "topics": topics, "subjects": subjects,
            "transform_version": 1,
        }
        selection = dataset.directory / "selections" / (fingerprint(signature) + ".json")
        if selection.is_file():
            payload = json.loads(selection.read_text(encoding="utf-8"))
            if payload["signature"] != signature:
                raise ConfigurationError("cached source selection has a conflicting signature")
            chunks, relations = payload["chunks"], payload["relations"]
        else:
            if not build:
                raise ConfigurationError("topic selection is not prepared; run prepare or enable auto_prepare")
            chunks, relations, seen, skipped = [], [], {}, 0
            loader = PhapDienLoader()
            progress(f"Selecting {len(topics)} topics + {len(subjects)} subjects from revision {dataset.revision}")
            for row in dataset.iter_rows(topics, subjects):
                if not (row.get("content_text") or "").strip():
                    skipped += 1  # Dataset section dividers are not evidence.
                    continue
                try:
                    _, chunk, edges = loader.transform_row(row, dataset=config.source.dataset, revision=dataset.revision)
                except (DataPipelineError, ValueError) as exc:
                    raise DataPipelineError(f"invalid source record: {row.get('record_id')}") from exc
                value = chunk.model_dump(mode="json")
                digest = fingerprint(value)
                previous = seen.get(chunk.chunk_id)
                if previous is not None:
                    if previous != digest:
                        raise DataPipelineError(f"conflicting source record: {chunk.chunk_id}")
                    continue
                seen[chunk.chunk_id] = digest
                chunks.append(value)
                relations.extend(edges)
            if not chunks:
                raise DataPipelineError("selected topics/subjects contain no nonempty source articles")
            progress(f"Selected {len(chunks)} articles; skipped {skipped} empty section dividers")
            write_json(selection, {"signature": signature, "chunks": chunks, "relations": relations, "skipped_empty": skipped})
    source = [LegalChunk.model_validate(item) for item in chunks]
    if not source or len({chunk.chunk_id for chunk in source}) != len(source):
        raise ConfigurationError("source corpus must contain nonempty, unique chunk IDs")
    progress(f"Source: {len(source)} articles, {len({chunk.document_id for chunk in source})} documents")
    return SourceCorpus(source, relations, signature)
