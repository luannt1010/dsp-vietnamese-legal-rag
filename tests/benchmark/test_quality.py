import json
from types import SimpleNamespace

import pytest

from core.schemas import LegalContext
from examples.orchestration_demo import FixtureLLM
from src.benchmark.scoring.answer import cosine, score_answer
from src.benchmark.scoring.context import score_context
from src.benchmark.scoring.judge import Judge, Verdicts
from src.retrieval.common import as_hit


def test_structured_judge_cache_and_cardinality_validation(tmp_path):
    calls = []
    def factory(schema):
        calls.append(schema)
        return FixtureLLM({"verdicts": [{"supported": True, "reason": "fixture"}]})
    judge = Judge(factory, tmp_path, {"model": "fixture", "prompt_version": 1})
    assert judge.entail(["claim"], "premise").verdicts[0].supported
    assert calls[0]["properties"]["verdicts"]["minItems"] == 1
    assert calls[0]["properties"]["verdicts"]["maxItems"] == 1
    assert calls[0]["$defs"]["Verdict"]["properties"]["reason"]["maxLength"] == 320
    judge.entail(["claim"], "premise")
    assert len(calls) == 1
    with pytest.raises(ValueError, match="exactly 2"):
        judge.entail(["claim", "other claim"], "premise")
    assert len(list(tmp_path.glob("*.json"))) == 1  # Invalid judgments were not cached.


def test_three_quality_stages_use_correct_premises(question, chunks):
    class JudgeFixture:
        def __init__(self):
            self.premises = {}
        def ask(self, task, instruction, payload, schema, **kwargs):
            if task == "answer_claims":
                return schema(claims=["supported claim", "unsupported claim"])
            if task == "context_precision":
                return schema(verdicts=[{"supported": False, "reason": "noise"}, {"supported": True, "reason": "useful"}])
            if task == "answer_relevancy":
                assert "question" not in payload  # Reverse questions cannot see the original query.
                return schema(questions=["q1", "q2", "q3"], noncommittal=False)
            raise AssertionError(task)
        def entail(self, claims, premise, *, task):
            self.premises[task] = premise
            return Verdicts(verdicts=[{"supported": i == 0, "reason": "fixture"} for i in range(len(claims))])
    judge = JudgeFixture()
    context = LegalContext(query=question.question, context_text="EXACT CONTEXT", chunks=[as_hit(c) for c in chunks[:2]])
    embedding = SimpleNamespace(embed_documents=lambda texts: [[1.0, 0.0] for _ in texts])
    metrics, details = score_answer(question, "FINAL ANSWER", context, judge, embedding)
    assert metrics["faithfulness"] == 0.5
    assert metrics["factual_precision"] == 0.5
    assert metrics["factual_recall"] == 1
    assert metrics["factual_f1"] == pytest.approx(2 / 3)
    assert metrics["answer_relevancy"] == 1
    assert judge.premises["faithfulness"] == "EXACT CONTEXT"
    assert judge.premises["factual_precision"] == question.reference_answer
    assert judge.premises["factual_recall"] == "FINAL ANSWER"
    metrics, details = score_context(question, context, judge)
    assert metrics["context_precision"] == 0.5
    assert metrics["context_recall"] == 1
    assert judge.premises["context_recall"] == "EXACT CONTEXT"


def test_judge_failure_is_not_a_zero_score(question, chunks):
    class Broken:
        def ask(self, *args, **kwargs):
            raise RuntimeError("judge offline")
        entail = ask
    context = LegalContext(query=question.question, context_text="fixture", chunks=[as_hit(chunks[0])])
    metrics, details = score_context(question, context, Broken())
    assert metrics == {}
    assert set(details["errors"]) == {"context_precision", "context_recall"}


def test_cosine_rejects_invalid_vectors():
    for vector in ([0.0, 0.0], [float("nan"), 1], [1]):
        with pytest.raises(ValueError):
            cosine(vector, [1, 0])


def test_content_free_answer_is_not_perfectly_faithful(question, chunks):
    class EmptyClaimsJudge:
        def ask(self, task, instruction, payload, schema, **kwargs):
            if task == "answer_claims":
                return schema(claims=[])
            return schema(questions=["q"] * 3, noncommittal=True)
    context = LegalContext(query=question.question, context_text="fixture", chunks=[as_hit(chunks[0])])
    metrics, details = score_answer(question, "Tôi không biết.", context, EmptyClaimsJudge(), None)
    assert metrics["faithfulness"] is None
    assert metrics["factual_f1"] == metrics["answer_relevancy"] == 0
    assert not details["errors"]
