"""Load explicit YAML sections, then apply RAG__SECTION__FIELD overrides."""

import json
import os
from pathlib import Path
from typing import Mapping

import yaml
from pydantic import ValidationError

from core.config.settings import Settings
from core.exceptions import ConfigurationError


CONFIG_FILES = {
    "config.yml": ("app", "api", "logging", "pipeline", "context"),
    "retrieval.yml": ("retrieval",),
    "embedding.yml": ("embedding",),
    "llm.yml": ("llm",),
    "database.yml": ("database",),
    "data_pipeline.yml": ("data_pipeline",),
}
SECRET_PATHS = {
    ("llm", "api_key"), ("embedding", "api_key"),
    ("database", "vector", "password"), ("database", "graph", "password"),
}


class _UniqueKeyLoader(yaml.SafeLoader):
    """Refuse ambiguous duplicate YAML keys instead of keeping the last one."""


def _unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ConfigurationError("YAML mapping keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping,
)


def _get_path(data: dict, path: tuple[str, ...]):
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _apply_environment(data: dict, environ: Mapping[str, str]) -> None:
    for name, raw in sorted(environ.items()):
        if not name.startswith("RAG__"):
            continue
        path = tuple(part.lower() for part in name[5:].split("__"))
        if len(path) < 2 or any(not part for part in path):
            raise ConfigurationError("Use environment names RAG__SECTION__FIELD")
        if path in SECRET_PATHS:
            value = raw
            if not value.strip():
                raise ConfigurationError(f"Empty secret in {name}")
        else:
            try:
                value = json.loads(raw)
            except (ValueError, TypeError):
                value = raw
        current = data
        for part in path[:-1]:
            if part not in current:
                current[part] = {}
            if not isinstance(current[part], dict):
                raise ConfigurationError(f"Conflicting environment path: {name}")
            current = current[part]
        current[path[-1]] = value


def load_settings(
    config_dir: str | Path | None = None, *, environ: Mapping[str, str] | None = None,
) -> Settings:
    """Read six files; precedence is model defaults < YAML < environment.

    Directory defaults to RAG_CONFIG_DIR or ./configs. Does not read .env,
    interpolate YAML, create directories, cache state, or connect to services.
    Relative data paths are resolved against the config directory's parent.
    """
    env = os.environ if environ is None else environ
    directory = Path(config_dir if config_dir is not None else env.get("RAG_CONFIG_DIR", "configs")).resolve()
    data = {}
    for filename, sections in CONFIG_FILES.items():
        path = directory / filename
        try:
            document = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
        except (OSError, UnicodeError, yaml.YAMLError, ConfigurationError):
            raise ConfigurationError(f"Cannot read valid YAML configuration: {path}") from None
        if not isinstance(document, dict) or set(document) != set(sections):
            raise ConfigurationError(f"{filename} must contain exactly these sections: {', '.join(sections)}")
        data.update(document)
    for path in SECRET_PATHS:
        if _get_path(data, path) is not None:
            raise ConfigurationError("Credentials must use environment variables: " + ".".join(path))
    _apply_environment(data, env)
    try:
        settings = Settings.model_validate(data)
    except ValidationError as exc:
        errors = "; ".join(
            ".".join(map(str, error["loc"])) + ": " + error["msg"]
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError("Invalid configuration: " + errors) from None
    paths = settings.data_pipeline.model_dump()
    for name in ("raw_dir", "processed_dir", "chunks_dir", "source_chunks_file", "relations_file", "index_dir"):
        if not paths[name].is_absolute():
            paths[name] = (directory.parent / paths[name]).resolve()
    return Settings.model_validate({
        **settings.model_dump(), "data_pipeline": paths,
    })
