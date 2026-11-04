"""Read JSONL without silently accepting duplicate questions or malformed labels."""

import json
from pathlib import Path
import unicodedata

from src.benchmark.schemas import Question


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def load_dataset(path: Path) -> list[Question]:
    questions = []
    ids, texts = set(), set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            question = Question.model_validate(json.loads(line))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{path.name}:{line_number}: {exc}") from exc
        text = normalized(question.question).casefold()
        if question.question_id in ids or text in texts:
            raise ValueError(f"{path.name}:{line_number}: duplicate question ID or question text")
        ids.add(question.question_id)
        texts.add(text)
        questions.append(question)
    if not questions:
        raise ValueError("dataset must contain at least one question")
    return questions
