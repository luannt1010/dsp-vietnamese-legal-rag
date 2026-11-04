"""Claim support vs context/reference and reverse-question cosine relevance.

These implement documented Ragas-style definitions, not the Ragas package API.
All intermediate claims and verdicts are persisted by the caller.
"""

from math import hypot, isfinite

from src.benchmark.scoring.judge import Claims, ReverseQuestions
from src.evaluation.metrics import answer_relevancy, factual_correctness, faithfulness


def cosine(left, right) -> float:
    if (len(left) != len(right) or not left
            or any(type(v) not in (int, float) or not isfinite(v) for v in [*left, *right])
            or hypot(*left) == 0 or hypot(*right) == 0):
        raise ValueError("relevancy embeddings must have equal dimensions and nonzero norms")
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / (hypot(*left) * hypot(*right))))


def score_answer(question, response: str, context, judge, embedding, reverse_count: int = 3):
    metrics, judgments, errors = {}, {}, {}
    claims = None
    try:
        result = judge.ask("answer_claims",
            "Tách toàn bộ khẳng định thực tế trong response thành claims nguyên tử, tự đủ nghĩa theo question. "
            "Giữ điều kiện, ngoại lệ và phủ định. Không thêm ý; lời xã giao/từ chối không phải claim thực tế.",
            {"question": question.question, "response": response}, Claims)
        claims = list(dict.fromkeys(result.claims))
        judgments["claims"] = claims
    except Exception as exc:
        errors["answer_claims"] = f"{type(exc).__name__}: {exc}"
    if claims:
        try:
            result = judge.entail(claims, context.context_text, task="faithfulness")
            judgments["faithfulness"] = result.model_dump(mode="json")
            metrics["faithfulness"] = faithfulness([v.supported for v in result.verdicts])
        except Exception as exc:
            errors["faithfulness"] = f"{type(exc).__name__}: {exc}"
        try:
            precision = judge.entail(claims, question.reference_answer, task="factual_precision")
            recall = judge.entail(question.reference_claims, response, task="factual_recall")
            judgments["factual_precision"] = precision.model_dump(mode="json")
            judgments["factual_recall"] = recall.model_dump(mode="json")
            for mode in ("precision", "recall", "f1"):
                metrics[f"factual_{mode}"] = factual_correctness(
                    [v.supported for v in precision.verdicts], [v.supported for v in recall.verdicts], mode=mode)
        except Exception as exc:
            errors["factual_correctness"] = f"{type(exc).__name__}: {exc}"
    elif claims == []:
        # A content-free answer cannot cover the answerable reference. Faithfulness is undefined.
        metrics.update(faithfulness=None, factual_precision=None, factual_recall=0.0, factual_f1=0.0)
    try:
        result = judge.ask("answer_relevancy",
            f"Chỉ từ response, tạo đúng {reverse_count} câu hỏi tiếng Việt mà response có thể trả lời. "
            "noncommittal=true nếu response né tránh hoặc không đưa câu trả lời cụ thể.",
            {"response": response}, ReverseQuestions, expected_count=reverse_count)
        if len(result.questions) != reverse_count:
            raise ValueError("reverse-question count differs from configuration")
        judgments["relevancy"] = result.model_dump(mode="json")
        if result.noncommittal:
            metrics["answer_relevancy"] = 0.0
        else:
            vectors = embedding.embed_documents([question.question, *result.questions])
            metrics["answer_relevancy"] = answer_relevancy([cosine(vectors[0], v) for v in vectors[1:]])
    except Exception as exc:
        errors["answer_relevancy"] = f"{type(exc).__name__}: {exc}"
    return metrics, {"judgments": judgments, "errors": errors}
