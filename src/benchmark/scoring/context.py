"""Reference-based context precision and claim-attribution context recall."""

from core.schemas.base import ContractModel
from src.benchmark.scoring.judge import Verdict
from src.evaluation.metrics import context_precision, faithfulness


class ContextVerdicts(ContractModel):
    verdicts: list[Verdict]


def score_context(question, context, judge) -> tuple[dict, dict]:
    judgments = {}
    metrics = {}
    errors = {}
    # Score independently so one failed judge task does not erase another metric.
    try:
        result = judge.ask("context_precision",
            "Đánh giá từng đoạn context có chứa thông tin hữu ích để trả lời question theo reference hay không. "
            "Chỉ cùng chủ đề không đủ. Trả verdicts theo đúng thứ tự và số lượng contexts, "
            "mỗi reason ngắn gọn tối đa hai câu.",
            {"question": question.question, "reference": question.reference_answer,
             "contexts": [chunk.content for chunk in context.chunks]}, ContextVerdicts,
            expected_count=len(context.chunks))
        if len(result.verdicts) != len(context.chunks):
            raise ValueError("context precision verdict count differs from context count")
        judgments["precision"] = result.model_dump(mode="json")
        relevant = {str(i) for i, verdict in enumerate(result.verdicts) if verdict.supported}
        metrics["context_precision"] = context_precision(
            [str(i) for i in range(len(context.chunks))], relevant) if relevant else 0.0
    except Exception as exc:
        errors["context_precision"] = f"{type(exc).__name__}: {exc}"
    try:
        result = judge.entail(question.reference_claims, context.context_text, task="context_recall")
        judgments["recall"] = result.model_dump(mode="json")
        metrics["context_recall"] = faithfulness([v.supported for v in result.verdicts])
    except Exception as exc:
        errors["context_recall"] = f"{type(exc).__name__}: {exc}"
    return metrics, {"judgments": judgments, "errors": errors}
