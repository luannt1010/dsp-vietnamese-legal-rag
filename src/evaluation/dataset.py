"""Validation and loading for the team's labeled evaluation dataset."""

import json
from pathlib import Path
from typing import Literal

from pydantic import ValidationError, model_validator

from core.schemas.base import ContractModel, NonEmptyString


QuestionType = Literal[
    "lookup",
    "multi_clause",
    "multi_document",
    "comparison",
    "unanswerable",
]
DatasetSplit = Literal["development", "test"]


class EvaluationEvidence(ContractModel):
    """Source passage that supports a reference answer or claim."""

    document_number: NonEmptyString
    document_title: NonEmptyString
    article: NonEmptyString | None = None
    clause: NonEmptyString | None = None
    point: NonEmptyString | None = None
    quote: NonEmptyString
    source_url: str | None = None


class EvaluationQuestion(ContractModel):
    """One human-authored and source-grounded benchmark question."""

    question_id: NonEmptyString
    question: NonEmptyString
    topic: NonEmptyString
    question_type: QuestionType
    answerable: bool
    reference_answer: NonEmptyString
    reference_claims: list[NonEmptyString]
    evidence: list[EvaluationEvidence]
    split: DatasetSplit | None = None
    split_group: NonEmptyString | None = None

    @model_validator(mode="after")
    def check_answerability(self) -> "EvaluationQuestion":
        if (self.split is None) != (self.split_group is None):
            raise ValueError("split and split_group must be provided together")
        if self.question_type == "unanswerable":
            if self.answerable or self.reference_claims or self.evidence:
                raise ValueError(
                    "unanswerable questions must have answerable=false and empty claims/evidence"
                )
        elif not self.answerable:
            raise ValueError("answerable=false requires question_type='unanswerable'")
        elif not self.reference_claims or not self.evidence:
            raise ValueError(
                "answerable questions require reference_claims and source evidence"
            )
        return self


class EvaluationDatasetError(ValueError):
    """Evaluation dataset could not be decoded or violates its contract."""


def load_evaluation_dataset(path: str | Path) -> list[EvaluationQuestion]:
    """Load UTF-8 JSONL records and report errors with their line numbers."""
    dataset_path = Path(path)
    try:
        contents = dataset_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvaluationDatasetError(
            f"Cannot read evaluation dataset: {dataset_path}"
        ) from exc

    records: list[EvaluationQuestion] = []
    seen_ids: set[str] = set()
    group_splits: dict[str, DatasetSplit] = {}
    for line_number, line in enumerate(contents.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except (json.JSONDecodeError, ValueError) as exc:
            raise EvaluationDatasetError(
                f"Invalid JSON on line {line_number} of {dataset_path}"
            ) from exc
        try:
            record = EvaluationQuestion.model_validate(payload)
        except ValidationError as exc:
            raise EvaluationDatasetError(
                f"Invalid evaluation question on line {line_number} of {dataset_path}"
            ) from exc
        if record.question_id in seen_ids:
            raise EvaluationDatasetError(
                f"Duplicate question_id {record.question_id!r} on line {line_number}"
            )
        seen_ids.add(record.question_id)
        if record.split is not None and record.split_group is not None:
            previous_split = group_splits.setdefault(record.split_group, record.split)
            if previous_split != record.split:
                raise EvaluationDatasetError(
                    f"Split group {record.split_group!r} crosses dataset splits "
                    f"on line {line_number}"
                )
        records.append(record)

    if not records:
        raise EvaluationDatasetError(f"Evaluation dataset is empty: {dataset_path}")
    return records
