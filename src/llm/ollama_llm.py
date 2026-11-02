import json
import time
from typing import Any, Dict

import requests
from requests.exceptions import RequestException
from core.config.settings import Settings

from core.exceptions import LLMError
from core.interfaces.base_llm import BaseLLM


class OllamaBaseLLM(BaseLLM):
    """Concrete LLM implementation for Ollama local models.
    Accepts optional Settings injection for easier testing.

    It posts to ``http://localhost:11434/api/generate`` (or a custom base URL from
    ``Settings.llm``) with the model name and prompt. Retries, timeouts and back‑off
    respect the values defined in ``configs/llm.yml`` under the ``llm`` section.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        # Allow injection of Settings for testing; default to a Settings instance
        if settings is None:
            settings = Settings()
        llm_cfg = settings.llm
        if llm_cfg.provider != "ollama":
            raise LLMError("OllamaBaseLLM instantiated with non‑ollama provider")

        # Ollama base URL – default as per spec
        self.base_url: str = llm_cfg.base_url or "http://localhost:11434"
        self.model: str = llm_cfg.answer_generator.model  # Expected to be set (e.g., qwen2.5:7b)
        self.timeout: float = llm_cfg.timeout_s
        self.max_retries: int = llm_cfg.max_retries
        self.backoff: float = llm_cfg.retry_backoff_s
        # Generation settings
        self.temperature: float | None = getattr(llm_cfg.answer_generator, "temperature", None)
        self.max_output_tokens: int | None = getattr(llm_cfg.answer_generator, "max_output_tokens", None)
        self._timeout: float = self.timeout

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/api/generate"
        try:
            # Use provided timeout (may be per‑attempt remaining time)
            response = requests.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            # Catch any exception (including RequestException) and wrap as LLMError
            raise LLMError(f"Ollama request failed: {exc}") from exc

    def generate(self, prompt: str) -> str:
        # Prepare payload according to Ollama API spec
        # Build options dict with only non-None values
        _options = {}
        if self.temperature is not None:
            _options["temperature"] = self.temperature
        if self.max_output_tokens is not None:
            _options["num_predict"] = self.max_output_tokens
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            **({"options": _options} if _options else {}),
        }
        # Fresh deadline for this generate call
        deadline = time.monotonic() + self.timeout
        attempt = 0
        while True:
            # Compute remaining time for this attempt
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMError("Ollama generate deadline exceeded")
            # Use remaining time as request timeout
            self._timeout = remaining
            try:
                # Perform the request
                result = self._post(payload)
            except LLMError:
                # Network or request failure – retry according to policy
                attempt += 1
                if attempt > self.max_retries:
                    raise
                backoff = min(self.backoff, deadline - time.monotonic())
                if backoff > 0:
                    time.sleep(backoff)
                continue
            except Exception as exc:
                # Unexpected exception – also retry
                attempt += 1
                if attempt > self.max_retries:
                    raise LLMError(f"Unexpected error during generate: {exc}")
                backoff = min(self.backoff, deadline - time.monotonic())
                if backoff > 0:
                    time.sleep(backoff)
                continue
            # Successful request – validate protocol fields
            if "response" not in result:
                raise LLMError("Ollama response missing 'response' field")
            return result["response"].strip()
