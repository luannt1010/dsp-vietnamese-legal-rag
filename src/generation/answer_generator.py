import json
from pathlib import Path

from core.interfaces.base_llm import BaseLLM
from core.interfaces.base_answer_generator import BaseAnswerGenerator
from core.schemas.answer import AnswerGenerationRequest, LegalAnswer, LegalCitation

class AnswerGenerator(BaseAnswerGenerator):
    """Concrete implementation of the answer generation contract.

    It uses a provided :class:`BaseLLM` instance to generate a legal answer
    based on a :class:`AnswerGenerationRequest`. The prompt is assembled from
    static system/user template files located under ``prompts/answer_generation``.
    """

    def __init__(self, llm: BaseLLM, prompts_dir: Path | None = None):
        self.llm = llm
        # Resolve prompts directory relative to the project root if not supplied
        self.prompts_dir = prompts_dir or Path(__file__).resolve().parents[2] / "prompts" / "answer_generation"
        self.system_prompt_path = self.prompts_dir / "system.txt"
        self.user_prompt_path = self.prompts_dir / "user.txt"

    def _load_prompt(self, path: Path) -> str:
        if not path.is_file():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8")

    def _render_user_prompt(self, request: AnswerGenerationRequest) -> str:
        # The user prompt template can contain ``{legal_context}`` and ``{question}`` placeholders.
        template = self._load_prompt(self.user_prompt_path)
        # Convert the LegalContext (Pydantic model) to a nicely formatted JSON string.
        context_json = json.dumps(request.context.model_dump(mode="json"), ensure_ascii=False, indent=2)
        return template.format(legal_context=context_json, question=request.query)

    def generate(self, request: AnswerGenerationRequest) -> LegalAnswer:
        """Generate a legal answer from the supplied request.

        Steps:
        1. Validate that a non‑empty ``LegalContext`` is provided.
        2. Load system and user prompts and compose the full prompt.
        3. Call the injected LLM.
        4. Guard against empty or whitespace‑only responses.
        5. Parse the JSON output.
        6. Validate the parsed dict against the ``LegalAnswer`` Pydantic model.
        """
        # 1️⃣ Ensure a legal context is present
        if not request.context or not request.context.model_dump():
            from core.exceptions import InsufficientEvidenceError
            raise InsufficientEvidenceError("No legal context provided for answer generation.")

        # 2️⃣ Load prompts
        system_prompt = self._load_prompt(self.system_prompt_path)
        user_prompt = self._render_user_prompt(request)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # 3️⃣ Generate raw output via the LLM abstraction
        raw_output = self.llm.generate(full_prompt)

        # 4️⃣ Guard against empty / whitespace‑only responses
        if raw_output is None or not str(raw_output).strip():
            from core.exceptions import LLMError
            raise LLMError("Empty response received from LLM.")

        # 5️⃣ Parse JSON output
        try:
            answer_dict = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            from core.exceptions import LLMError
            raise LLMError(f"Failed to decode LLM JSON output: {exc}") from exc

        # 6️⃣ Validate against LegalAnswer schema
        try:
            return LegalAnswer(**answer_dict)
        except Exception as exc:
            from core.exceptions import LLMError
            raise LLMError(f"Invalid LegalAnswer structure: {exc}") from exc
