"""Shared helpers for prompt-backed structured LLM modules."""

import json
from pathlib import Path

from core.exceptions import LLMError


_PROMPT_DIRECTORY = Path(__file__).resolve().parents[1] / "prompts"


def _reject_non_finite_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is not allowed: {value}")


def load_prompt(module_name: str, version: str) -> str:
    """Load a versioned prompt from the repository's prompts directory."""
    if not version or Path(version).name != version:
        raise ValueError("prompt version must be a non-empty filename component")
    path = _PROMPT_DIRECTORY / module_name / f"{version}.txt"
    try:
        prompt = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise LLMError(f"Cannot read prompt: {path}") from exc
    if not prompt:
        raise LLMError(f"Prompt is empty: {path}")
    return prompt


def parse_json_object(response: str, *, module_name: str) -> dict:
    """Parse a provider response that must be one JSON object."""
    try:
        value = json.loads(response, parse_constant=_reject_non_finite_constant)
    except (TypeError, ValueError) as exc:
        raise LLMError(f"{module_name} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LLMError(f"{module_name} response must be a JSON object")
    return value
