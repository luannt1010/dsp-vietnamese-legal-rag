import json
import tempfile
import unittest
from pathlib import Path

from src.evaluation.dataset import (
    EvaluationDatasetError,
    EvaluationQuestion,
    load_evaluation_dataset,
)


def answerable_record(question_id: str = "GT001") -> dict:
    return {
        "question_id": question_id,
        "question": "Câu hỏi pháp luật tiếng Việt?",
        "topic": "Giao thông, vận tải",
        "question_type": "multi_clause",
        "answerable": True,
        "reference_answer": "Đáp án có căn cứ.",
        "reference_claims": ["Điều kiện thứ nhất."],
        "evidence": [{
            "document_number": "01/2025/QH15",
            "document_title": "Luật mẫu",
            "article": "Điều 1",
            "quote": "Nội dung điều khoản có liên quan.",
            "source_url": None,
        }],
    }


class EvaluationDatasetTests(unittest.TestCase):
    def test_validate_answerable_and_unanswerable_questions(self) -> None:
        answerable = EvaluationQuestion.model_validate(answerable_record())
        unanswerable = EvaluationQuestion.model_validate({
            "question_id": "OUT001",
            "question": "Câu hỏi ngoài phạm vi corpus?",
            "topic": "Giáo dục, đào tạo",
            "question_type": "unanswerable",
            "answerable": False,
            "reference_answer": "Corpus không có nguồn để kết luận.",
            "reference_claims": [],
            "evidence": [],
        })

        self.assertTrue(answerable.answerable)
        self.assertFalse(unanswerable.answerable)

    def test_unanswerable_question_cannot_contain_grounded_evidence(self) -> None:
        record = answerable_record()
        record.update({
            "question_type": "unanswerable",
            "answerable": False,
        })
        with self.assertRaises(ValueError):
            EvaluationQuestion.model_validate(record)

    def test_answerable_question_requires_claims_and_evidence(self) -> None:
        record = answerable_record()
        record["evidence"] = []
        with self.assertRaises(ValueError):
            EvaluationQuestion.model_validate(record)

    def test_load_jsonl_skips_blank_lines_and_checks_unique_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.jsonl"
            path.write_text(
                json.dumps(answerable_record(), ensure_ascii=False)
                + "\n\n"
                + json.dumps(answerable_record("GT002"), ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            records = load_evaluation_dataset(path)
        self.assertEqual([record.question_id for record in records], ["GT001", "GT002"])

    def test_load_jsonl_reports_invalid_line_and_duplicate_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.jsonl"
            valid = json.dumps(answerable_record(), ensure_ascii=False)
            path.write_text(valid + "\n" + valid + "\n", encoding="utf-8")
            with self.assertRaisesRegex(EvaluationDatasetError, "Duplicate question_id"):
                load_evaluation_dataset(path)

            path.write_text(valid + "\n{bad json}\n", encoding="utf-8")
            with self.assertRaisesRegex(EvaluationDatasetError, "line 2"):
                load_evaluation_dataset(path)

    def test_split_group_cannot_leak_across_development_and_test(self) -> None:
        development = answerable_record("GT001")
        development.update({"split": "development", "split_group": "family-a"})
        test = answerable_record("GT002")
        test.update({"split": "test", "split_group": "family-a"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.jsonl"
            path.write_text(
                json.dumps(development, ensure_ascii=False)
                + "\n"
                + json.dumps(test, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(EvaluationDatasetError, "crosses dataset splits"):
                load_evaluation_dataset(path)

    def test_empty_jsonl_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.jsonl"
            path.write_text("\n \n", encoding="utf-8")
            with self.assertRaises(EvaluationDatasetError):
                load_evaluation_dataset(path)


if __name__ == "__main__":
    unittest.main()
