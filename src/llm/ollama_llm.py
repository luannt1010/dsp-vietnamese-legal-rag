"""Role-specific Ollama adapter using the shared deadline-aware HTTP client."""

from collections.abc import Callable

from core.config.settings import Settings
from core.exceptions import ConfigurationError, LLMError, LLMContextWindowError, LLMOutputTruncatedError
from core.interfaces import BaseLLM
from src.infrastructure.ollama_client import OllamaClient
from src.observability.telemetry import instrument


class OllamaBaseLLM(BaseLLM):
    def __init__(
        self, settings: Settings | None = None, *, role: str = "answer_generator",
        token_counter: Callable[[str], int] | None = None, response_schema: dict | None = None,
    ) -> None:
        settings = settings or Settings()
        config = settings.llm
        if config.provider != "ollama":
            raise LLMError("OllamaBaseLLM instantiated with non-ollama provider")
        if role not in {"query_analyzer", "retrieval_evaluator", "answer_generator", "citation_verifier"}:
            raise ConfigurationError(f"unsupported LLM role: {role}")
        self.role = getattr(config, role)
        self.role_name = role
        if not self.role.model:
            raise ConfigurationError(f"llm.{role}.model is required")
        self.base_url = config.base_url or "http://localhost:11434"
        self.model = self.role.model
        self.timeout = config.timeout_s
        self.max_retries = config.max_retries
        self.backoff = config.retry_backoff_s
        self.token_counter = token_counter
        self.response_schema = response_schema
        self.keep_alive = getattr(config, "keep_alive", "1m")
        self.think = getattr(config, "think", False)
        self.client = OllamaClient(
            self.base_url, timeout_s=self.timeout, max_retries=self.max_retries, backoff_s=self.backoff,
        )

    def _post(self, payload: dict) -> dict:
        return self.client.post("/api/chat", payload)

    @instrument("llm.generate", kind="model_call", role_from="role_name", model_from="model")
    def generate(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("LLM prompt must not be blank")
        window = getattr(self.role, "context_window_tokens", None)
        output = getattr(self.role, "max_output_tokens", 2048)
        if self.token_counter is not None:
            count = self.token_counter(prompt)
            if type(count) is not int or count <= 0:
                raise LLMError("token_counter must return a positive integer")
            overhead = getattr(self.role, "prompt_overhead_tokens", 128)
            if window is not None and count + overhead + output > window:
                raise LLMContextWindowError(
                    f"LLM prompt ({count}) + template overhead ({overhead}) + output ({output}) "
                    f"exceed the model context window ({window})"
                )
        options = {
            "temperature": getattr(self.role, "temperature", 0), "num_predict": output,
            # A model's default novelty penalties can alter verbatim quotations.
            "presence_penalty": 0, "repeat_penalty": 1.0,
        }
        if window is not None:
            options["num_ctx"] = window
        result = self._post({
            "model": self.model, "messages": [{"role": "user", "content": prompt}], "stream": False,
            "format": self.response_schema or "json", "options": options,
            "think": self.think, "keep_alive": self.keep_alive,
        })
        if isinstance(result, dict) and result.get("done_reason") == "length":
            raise LLMOutputTruncatedError(f"Ollama output was truncated at the configured token limit ({output})")
        message = result.get("message") if isinstance(result, dict) else None
        response = message.get("content") if isinstance(message, dict) else None
        if not isinstance(response, str) or not response.strip():
            raise LLMError("Ollama response missing 'message.content' string or containing empty output")
        return response.strip()
