import importlib
from core.config.settings import Settings  # Re-export for external usage
from core.config.loader import load_settings
from core.exceptions import ConfigurationError

# Mapping provider name -> module path and class name
_PROVIDER_MAP = {
    "ollama": ("src.llm.ollama_llm", "OllamaBaseLLM"),
    # Future providers can be added here, e.g., "openai": ("src.llm.openai_llm", "OpenAIBaseLLM")
}


def get_llm_instance(settings: Settings | None = None, *, role="answer_generator", token_counter=None, response_schema=None):
    """Factory that returns an instantiated BaseLLM implementation based on settings.

    Raises:
        ConfigurationError: If provider is unknown or required configuration is missing.
    """
    # Load full configuration using the project's loader rather than constructing Settings directly
    settings = settings or load_settings()
    provider = getattr(settings.llm, "provider", None)
    if not provider:
        raise ConfigurationError("LLM provider not configured in Settings.llm.provider")
    if provider not in _PROVIDER_MAP:
        raise ConfigurationError(f"Unsupported LLM provider: {provider}")
    module_path, class_name = _PROVIDER_MAP[provider]
    module = importlib.import_module(module_path)
    llm_class = getattr(module, class_name)
    return llm_class(settings, role=role, token_counter=token_counter, response_schema=response_schema)
