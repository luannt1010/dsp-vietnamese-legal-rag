import json
from pathlib import Path

from pydantic import Field, ValidationError

from core.exceptions import ConfigurationError, InsufficientEvidenceError, LLMError
from core.interfaces.base_llm import BaseLLM
from core.interfaces.base_answer_generator import BaseAnswerGenerator
from core.schemas.answer import AnswerGenerationRequest, LegalAnswer, LegalCitation
from core.schemas.base import ContractModel, NonEmptyString, PositiveInt
from src.prompting import parse_json_object


class AnswerDraft(ContractModel):
    """Internal LLM output; source numbers refer to the retained [Nguồn N] blocks."""

    answer: NonEmptyString
    sources: list[PositiveInt] = Field(min_length=1)


class AnswerGenerator(BaseAnswerGenerator):
    """Concrete implementation of the answer generation contract.

    It uses a provided :class:`BaseLLM` instance to generate a legal answer
    based on a :class:`AnswerGenerationRequest`. The prompt is assembled from
    static system/user template files located under ``prompts/answer_generation``.
    """

    def __init__(self, llm: BaseLLM, prompts_dir: Path | None = None, *, prompt_version: str = "v1"):
        self.llm = llm
        if not prompt_version or prompt_version in {".", ".."} or Path(prompt_version).name != prompt_version:
            raise ConfigurationError("invalid answer prompt version")
        # Resolve prompts directory relative to the project root if not supplied
        self.prompts_dir = prompts_dir or Path(__file__).resolve().parents[2] / "prompts" / "answer_generation"
        if prompts_dir is None and prompt_version != "v1":
            self.prompts_dir = self.prompts_dir / prompt_version
        self.system_prompt_path = self.prompts_dir / "system.txt"
        self.user_prompt_path = self.prompts_dir / "user.txt"
        self._system_prompt = self._load_prompt(self.system_prompt_path)
        self._user_template = self._load_prompt(self.user_prompt_path)
        try:
            self._user_template.format(question="", legal_context="")
        except (KeyError, IndexError, ValueError) as exc:
            raise ConfigurationError("invalid placeholders in answer user prompt") from exc

    def _load_prompt(self, path: Path) -> str:
        try:
            prompt = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ConfigurationError(f"Cannot read answer prompt: {path}") from exc
        if not prompt.strip():
            raise ConfigurationError(f"Answer prompt is empty: {path}")
        return prompt

    def _render_user_prompt(self, request: AnswerGenerationRequest) -> str:
        # Render sources once. JSON string escaping makes original line breaks
        # explicit for verbatim quotes without duplicating a source catalog.
        context_json = json.dumps(request.context.context_text, ensure_ascii=False)
        rendered = self._user_template.format(legal_context=context_json, question=request.query)
        return rendered + "\n\nAnswerDraft JSON schema:\n" + json.dumps(AnswerDraft.model_json_schema(), ensure_ascii=False)

    def generate(self, request: AnswerGenerationRequest) -> LegalAnswer:
        """Generate text/source references once; derive citations from retained sources."""
        if not request.context:
            raise InsufficientEvidenceError("No legal context provided for answer generation.")
        if not request.context.context_text or not str(request.context.context_text).strip():
            raise InsufficientEvidenceError("Context text is empty or whitespace.")
        if not request.context.chunks:
            raise InsufficientEvidenceError("No evidence chunks provided.")
        if not any(chunk.content and str(chunk.content).strip() for chunk in request.context.chunks):
            raise InsufficientEvidenceError("All evidence chunks are empty or whitespace.")
        user_prompt = self._render_user_prompt(request)
        full_prompt = f"{self._system_prompt}\n\n{user_prompt}"

        raw_output = self.llm.generate(full_prompt)

        if raw_output is None or not str(raw_output).strip():
            raise LLMError("Empty response received from LLM.")

        answer_dict = parse_json_object(raw_output, module_name="Answer generator")

        try:
            draft = AnswerDraft.model_validate(answer_dict)
        except ValidationError as exc:
            raise LLMError("Invalid AnswerDraft structure") from exc
        if len(set(draft.sources)) != len(draft.sources):
            raise LLMError("Answer draft contains duplicate source references")
        citations = []
        for number in draft.sources:
            if number > len(request.context.chunks):
                raise LLMError("Answer draft references a source outside the retained context")
            source = request.context.chunks[number - 1]
            if not source.metadata.get("document_number"):
                raise InsufficientEvidenceError("citation source has no document number")
            # The model selects evidence; it never reconstructs or repairs
            # source metadata/quotations. Keep the complete cited source so
            # conditions, exceptions and original whitespace remain intact.
            citations.append(LegalCitation(
                document_id=source.document_id, document_number=source.metadata["document_number"],
                quoted_text=source.content,
                **{key: source.metadata.get(key) for key in ("article", "clause", "point", "source_url")},
            ))
        return LegalAnswer(
            answer=draft.answer, citations=citations, confidence=0,
            disclaimer="Thông tin theo nguồn được cung cấp, không phải tư vấn pháp lý cho vụ việc cụ thể.",
        )
