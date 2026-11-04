"""Atomic records and strict resume identity; reuse preparation's JSON writer."""

import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from src.data_pipeline.artifacts import fingerprint, write_json
from src.benchmark.schemas import Sample, Score


ROOT = Path(__file__).resolve().parents[2]


def code_identity() -> str:
    digest = hashlib.sha256()
    for folder in ("src", "core", "scripts", "prompts", "configs"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".txt", ".yml", ".yaml"}:
                digest.update(path.relative_to(ROOT).as_posix().encode())
                digest.update(path.read_bytes())
    for filename in ("pyproject.toml", "requirements.txt"):
        digest.update((ROOT / filename).read_bytes())
    return digest.hexdigest()


def sanitized_settings(settings) -> dict:
    def redact(value):
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items() if key not in {"password", "api_key"}}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value
    return redact(settings.model_dump(mode="json"))


def environment() -> dict:
    packages = {}
    for name in ("numpy", "pydantic", "onnxruntime", "neo4j", "psycopg", "requests"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {"python": platform.python_version(), "platform": platform.platform(),
            "processor": platform.processor(), "packages": packages}


class ArtifactStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def initialize(self, identity: dict) -> dict:
        path = self.directory / "manifest.json"
        expected = fingerprint(identity)
        if path.exists():
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("fingerprint") != expected or fingerprint(manifest["identity"]) != expected:
                raise ValueError("run identity changed; use a new output directory instead of mixing runs")
        else:
            manifest = {"schema_version": 1, "fingerprint": expected, "identity": identity,
                        "environment": environment(), "corpora": {}}
            write_json(path, manifest)
        return manifest

    def register_corpus(self, corpus) -> None:
        path = self.directory / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        corpora = manifest["corpora"]
        if corpora and corpus.corpus_id not in corpora:
            raise ValueError("corpus changed during the experiment; use a new run directory")
        if corpus.corpus_id in corpora and corpora[corpus.corpus_id] != corpus.manifest:
            raise ValueError("corpus manifest changed during the experiment")
        corpora[corpus.corpus_id] = corpus.manifest
        write_json(path, manifest)

    def sample_path(self, experiment: str, question_id: str, repeat: int) -> Path:
        # All three keys originate from validated schemas, never arbitrary filenames.
        return self.directory / "samples" / experiment / f"{question_id}.{repeat}.json"

    def save_sample(self, sample: Sample) -> None:
        write_json(self.sample_path(sample.experiment, sample.question_id, sample.repeat), sample.model_dump(mode="json"))

    def samples(self):
        for path in sorted((self.directory / "samples").glob("*/*.json")):
            yield Sample.model_validate_json(path.read_text(encoding="utf-8"))

    def score_path(self, sample: Sample) -> Path:
        return self.directory / "scores" / sample.experiment / f"{sample.question_id}.{sample.repeat}.json"

    def save_score(self, sample: Sample, score: Score) -> None:
        write_json(self.score_path(sample), score.model_dump(mode="json"))
