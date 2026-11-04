"""Score immutable inference artifacts; quality scoring never calls the pipeline."""

import json

from src.benchmark.artifacts import ArtifactStore, code_identity
from src.benchmark.schemas import Question, Score
from src.benchmark.scoring.answer import score_answer
from src.benchmark.scoring.context import score_context
from src.benchmark.scoring.retrieval import score_ranking
from src.data_pipeline.artifacts import fingerprint, write_json


def score_sample(sample, question, ks, scoring_fingerprint, *, judge=None, embedding=None, reverse_count=3):
    result = sample.result
    score = Score(experiment=sample.experiment, question_id=sample.question_id, repeat=sample.repeat,
                  status=result.status, topic=question.topic, question_type=question.question_type,
                  answerable=question.answerable, sample_fingerprint=fingerprint(sample.model_dump(mode="json")),
                  scoring_fingerprint=scoring_fingerprint)
    if question.answerable:
        score.metrics["answer_provided"] = float(result.status == "completed")
        for i, record in enumerate(result.rounds):
            if record.retrieval_result is not None:
                values = score_ranking(record.retrieval_result.results, sample.relevant_chunk_ids, ks)
                score.metrics.update({f"round_{i}.{key}": value for key, value in values.items()})
        if result.rounds and result.rounds[-1].retrieval_result is not None:
            score.metrics.update(score_ranking(result.rounds[-1].retrieval_result.results, sample.relevant_chunk_ids, ks))
        if result.status != "completed" and judge is not None:
            score.metrics["correct_answer_yield"] = 0.0
        elif result.status == "completed" and judge is not None and result.context is not None:
            metrics, details = score_answer(question, result.answer.answer, result.context, judge, embedding, reverse_count)
            score.metrics.update(metrics)
            score.judgments["answer"] = details["judgments"]
            score.errors.update(details["errors"])
            f1, faithful = metrics.get("factual_f1"), metrics.get("faithfulness")
            # Conservative, predeclared success criterion: complete and fully grounded.
            score.metrics["correct_answer_yield"] = (0.0 if f1 == 0 else
                float(f1 == 1 and faithful == 1) if f1 is not None and faithful is not None else None)
        elif result.status == "completed" and judge is not None:
            score.errors["answer"] = "completed artifact has no exact context; cannot score quality"
        if judge is not None and result.context is not None:
            metrics, details = score_context(question, result.context, judge)
            score.metrics.update(metrics)
            score.judgments["context"] = details["judgments"]
            score.errors.update(details["errors"])
        if (judge is not None and result.context is not None and result.draft_answer is not None
                and result.draft_answer != result.answer):
            metrics, details = score_answer(question, result.draft_answer.answer, result.context, judge, embedding, reverse_count)
            score.metrics.update({f"draft.{key}": value for key, value in metrics.items()})
            score.judgments["draft"] = details["judgments"]
            score.errors.update({f"draft.{key}": value for key, value in details["errors"].items()})
    else:
        score.metrics["correct_abstention"] = float(result.status == "insufficient_evidence")
        score.metrics["unsupported_answer"] = float(result.status == "completed")
    return score


def score_run(directory, *, judge=None, embedding=None, reverse_count=3, progress=print):
    store = ArtifactStore(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    questions = {q["question_id"]: Question.model_validate(q) for q in manifest["identity"]["questions"]}
    ks = manifest["identity"]["config"]["ks"]
    identity = {"code": code_identity(), "mode": "quality" if judge else "retrieval_only",
                "judge": judge.identity if judge else None, "reverse_count": reverse_count,
                "metric_definitions": "binary-chunk-qrels; ragas-style-claim-v1; correct=f1=faithfulness=1"}
    scoring_fingerprint = fingerprint(identity)
    # Separate scoring editions: changing judge/config must not mix rows in a report.
    write_json(directory / "scoring.json", {"fingerprint": scoring_fingerprint, "identity": identity})
    for sample in store.samples():
        path = store.score_path(sample)
        if path.exists():
            old = Score.model_validate_json(path.read_text(encoding="utf-8"))
            if (old.scoring_fingerprint == scoring_fingerprint
                    and old.sample_fingerprint == fingerprint(sample.model_dump(mode="json")) and not old.errors):
                continue
        score = score_sample(sample, questions[sample.question_id], ks, scoring_fingerprint,
                             judge=judge, embedding=embedding, reverse_count=reverse_count)
        store.save_score(sample, score)
        progress(f"{sample.experiment}/{sample.question_id}/{sample.repeat}: {len(score.metrics)} metrics, {len(score.errors)} judge errors")
    return scoring_fingerprint
