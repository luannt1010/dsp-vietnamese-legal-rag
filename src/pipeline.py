import pathlib
from core.config.settings import Settings
from src.llm.factory import get_llm_instance
from src.generation.answer_generator import AnswerGenerator
from src.generation.answer_formatter import AnswerFormatter


def build_answer_pipeline():
    """Construct the minimal answer generation pipeline.

    Returns:
        tuple[AnswerGenerator, AnswerFormatter]: The generator (with an LLM instance) and formatter.
    """
    # Load settings – this will read the configuration (including the Ollama provider).
    settings = Settings()
    # Instantiate the appropriate LLM based on the provider.
    llm = get_llm_instance()
    # AnswerGenerator expects the LLM and optional prompts directory (defaults are fine).
    answer_generator = AnswerGenerator(llm)
    # Formatter does not need configuration.
    answer_formatter = AnswerFormatter()
    return answer_generator, answer_formatter
