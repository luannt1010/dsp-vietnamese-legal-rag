"""Select the existing configuration profile without changing process environment."""

import os
from pathlib import Path

from dotenv import dotenv_values

from core.config import Settings, load_settings


ROOT = Path(__file__).resolve().parents[2]


def load_api_settings() -> Settings:
    """Use demo defaults; explicit process variables override local credentials.

    RAG_CONFIG_DIR selects another profile. RAG_ENV_FILE selects the dotenv
    file; otherwise use the same ignored credentials file as scripts.demo.
    Configuration parsing and validation remain owned by core.config.
    """
    env_file = Path(os.environ.get("RAG_ENV_FILE", ROOT / ".runtime" / "demo.env"))
    file_values = dotenv_values(env_file, encoding="utf-8-sig") if env_file.is_file() else {}
    environ = {key: value for key, value in file_values.items() if value is not None}
    environ.update(os.environ)
    directory = environ.get("RAG_CONFIG_DIR", ROOT / "configs" / "demo")
    return load_settings(directory, environ=environ)
