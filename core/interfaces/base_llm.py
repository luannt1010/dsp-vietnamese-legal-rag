"""Provider-neutral text LLM boundary; distinct from answer generation."""

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Return generated text; reject a blank prompt and raise LLMError on failure.

        Model, credentials, sampling and timeouts belong to the implementation's
        constructor/configuration. The calling agent parses and validates its
        structured output using the corresponding shared schema.
        """
        raise NotImplementedError
