"""Read a pinned Phap Dien Parquet snapshot in bounded batches.

The catalog is derived from documents, not ontology_topics: the latter does
not contain every topic present in the source corpus. No viewer API is needed.
"""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download

from core.config.settings import DataSourceSettings
from core.exceptions import ConfigurationError
from src.data_pipeline import DataPipelineError
from src.data_pipeline.artifacts import fingerprint, write_json


_CATALOG_COLUMNS = ["topic_id", "topic_title_vi", "subject_id", "subject_title_vi"]


def _name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


class PhapDienDataset:
    def __init__(self, settings: DataSourceSettings, cache_dir: Path):
        self.settings = settings
        self.cache_dir = cache_dir
        self.directory = cache_dir / fingerprint({
            "dataset": settings.dataset, "config": settings.config,
            "split": settings.split, "revision": settings.revision,
        })[:20]
        self.revision: str | None = None
        self.files: list[Path] = []

    def open(self, *, download: bool, refresh: bool = False, progress=print) -> "PhapDienDataset":
        manifest_path = self.directory / "snapshot.json"
        if manifest_path.is_file() and not refresh:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files = [Path(path) for path in manifest["files"]]
            if files and all(path.is_file() for path in files):
                self.revision, self.files = manifest["revision"], files
                return self
        if not download:
            raise ConfigurationError("dataset snapshot is not cached; run prepare or enable auto_prepare")
        try:
            info = HfApi().dataset_info(self.settings.dataset, revision=self.settings.revision)
            names = sorted(item.rfilename for item in info.siblings if re.fullmatch(r"documents(?:-\d+-of-\d+)?\.parquet", item.rfilename))
            if not names:
                raise DataPipelineError("dataset has no supported documents Parquet files")
            progress(f"Downloading {len(names)} documents shards at revision {info.sha}; existing HF cache is reused")
            files = []
            for name in names:
                progress(f"Source shard: {name}")
                files.append(Path(hf_hub_download(
                    self.settings.dataset, name, repo_type="dataset", revision=info.sha,
                    cache_dir=self.cache_dir / "hub",
                )))
            required = {*_CATALOG_COLUMNS, "record_id", "article_id", "content_text", "article_title"}
            for path in files:
                missing = required - set(pq.ParquetFile(path).schema_arrow.names)
                if missing:
                    raise DataPipelineError(f"{path.name}: missing source columns {sorted(missing)}")
            self.revision, self.files = info.sha, files
            write_json(manifest_path, {"revision": info.sha, "files": [str(path) for path in files]})
            return self
        except DataPipelineError:
            raise
        except Exception as exc:
            raise DataPipelineError("could not open the Hugging Face dataset snapshot") from exc

    def catalog(self) -> dict:
        path = self.directory / f"catalog-{self.revision}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        topics, subjects, topic_counts, subject_counts = {}, {}, Counter(), Counter()
        for file in self.files:
            for batch in pq.ParquetFile(file).iter_batches(batch_size=self.settings.read_batch_size, columns=_CATALOG_COLUMNS):
                for row in batch.to_pylist():
                    topic, subject = row["topic_id"], row["subject_id"]
                    if not topic or not subject:
                        raise DataPipelineError("source row is missing topic_id or subject_id")
                    topic_counts[topic] += 1
                    subject_counts[subject] += 1
                    topics[topic] = {"id": topic, "title": row["topic_title_vi"]}
                    entry = {"id": subject, "title": row["subject_title_vi"], "topic_id": topic}
                    if subject in subjects and subjects[subject] != entry:
                        raise DataPipelineError(f"conflicting subject catalog entry: {subject}")
                    subjects[subject] = entry
        result = {
            "topics": [dict(topics[key], articles=topic_counts[key]) for key in sorted(topics)],
            "subjects": [dict(subjects[key], articles=subject_counts[key]) for key in sorted(subjects)],
        }
        write_json(path, result)
        return result

    def resolve(self, kind: str, selectors: tuple[str, ...]) -> list[str]:
        entries = self.catalog()[kind]
        resolved = set()
        for selector in selectors:
            matches = [
                entry for entry in entries
                if selector == entry["id"] or _name(selector) == _name(entry["title"] or "")
            ]
            if len(matches) != 1:
                raise ConfigurationError(f"{kind}: unknown or ambiguous name {selector!r}; use list-{kind} and select an ID")
            resolved.add(matches[0]["id"])
        return sorted(resolved)

    def iter_rows(self, topic_ids: list[str], subject_ids: list[str]):
        """Union selection; filter Arrow batches before creating Python rows."""
        for file in self.files:
            parquet = pq.ParquetFile(file)
            topics = pa.array(topic_ids, type=parquet.schema_arrow.field("topic_id").type)
            subjects = pa.array(subject_ids, type=parquet.schema_arrow.field("subject_id").type)
            for batch in parquet.iter_batches(batch_size=self.settings.read_batch_size):
                mask = pc.or_(
                    pc.is_in(batch.column("topic_id"), value_set=topics),
                    pc.is_in(batch.column("subject_id"), value_set=subjects),
                )
                yield from batch.filter(pc.fill_null(mask, False)).to_pylist()
