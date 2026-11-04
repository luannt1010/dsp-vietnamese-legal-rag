"""One HTTP/retry implementation for Ollama generation and embedding calls."""

import time

import requests

from core.deadline import remaining_timeout, request_deadline
from core.exceptions import LLMError, RAGError
from src.observability.telemetry import backend_usage, span


class OllamaClient:
    def __init__(self, base_url: str, *, timeout_s: float, max_retries: int = 2, backoff_s: float = 1):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_s = backoff_s

    def post(self, path: str, payload: dict, *, error_type: type[RAGError] = LLMError) -> dict:
        # This nested scope also respects an outer pipeline deadline. Timeout is
        # local to each request, so a shared client has no mutable per-call state.
        with request_deadline(self.timeout_s):
            for attempt in range(self.max_retries + 1):
                try:
                    with span("ollama.request", kind="backend_request", model=payload.get("model"),
                              endpoint=path, attempt=attempt + 1) as event:
                        response = requests.post(
                            self.base_url + path, json=payload, timeout=remaining_timeout(self.timeout_s),
                        )
                        response.raise_for_status()
                        result = response.json()
                        remaining_timeout()
                        if not isinstance(result, dict):
                            raise error_type("Ollama returned a non-object JSON response")
                        event.update(backend_usage(result))
                        return result
                except (requests.ConnectionError, requests.Timeout) as exc:
                    failure = exc
                except requests.HTTPError as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    if status not in {429, 500, 502, 503, 504}:
                        raise error_type(f"Ollama HTTP request failed (status {status})") from exc
                    failure = exc
                except (requests.RequestException, ValueError) as exc:
                    # Invalid JSON and permanent HTTP errors do not get retries.
                    raise error_type("Ollama HTTP/JSON request failed") from exc
                if attempt == self.max_retries:
                    raise error_type("Ollama transient request retries exhausted") from failure
                delay = min(self.backoff_s * (2 ** attempt), remaining_timeout(self.timeout_s))
                time.sleep(delay)
        raise error_type("Ollama request did not complete")
