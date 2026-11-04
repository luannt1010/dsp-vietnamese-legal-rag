"""Cluster repeats by question; never treat repeated generations as new questions."""

from collections import defaultdict
from statistics import mean

import numpy as np


def distribution(values) -> dict:
    if not values:
        return {"n": 0, "mean": None, "p50": None, "p95": None}
    return {"n": len(values), "mean": mean(values),
            "p50": float(np.percentile(values, 50)), "p95": float(np.percentile(values, 95))}


def question_means(scores) -> dict:
    grouped = defaultdict(list)
    for score in scores:
        for metric, value in score.metrics.items():
            if value is not None:
                grouped[(metric, score.question_id)].append(value)
    return {key: mean(values) for key, values in grouped.items()}


def summarize(scores, samples, expected: int) -> dict:
    means = question_means(scores)
    metrics = defaultdict(list)
    for (metric, _), value in means.items():
        metrics[metric].append(value)
    timing = defaultdict(list)
    statuses = defaultdict(int)
    for sample in samples:
        status = sample.result.status
        statuses[status] += 1
        prefix = f"{sample.latency_scope}/{status}"
        timing[prefix + "/end_to_end_ms"].append(sample.latency_ms)
        timing[prefix + "/rounds"].append(len(sample.result.rounds))
        per_query = defaultdict(float)
        for event in sample.telemetry:
            if event["kind"] == "model_call":
                per_query["model_call_count"] += 1
                per_query["model_call_total_ms"] += event["duration_ms"]
                per_query[f"model/{event.get('role', 'unknown')}_ms"] += event["duration_ms"]
            if event["kind"] == "stage":
                per_query[f"stage/{event['name']}_ms"] += event["duration_ms"]
            if event["kind"] == "backend_request":
                per_query["backend_request_count"] += 1
                per_query["backend_failed_attempt_count"] += float(event["status"] != "completed")
                for field in ("load_duration_ms", "prompt_eval_duration_ms", "eval_duration_ms", "prompt_eval_count", "eval_count"):
                    if field in event:
                        per_query[f"backend/{field}"] += event[field]
        if per_query.get("backend/eval_duration_ms", 0) > 0:
            per_query["backend/decode_tokens_per_second"] = (
                per_query.get("backend/eval_count", 0) * 1000 / per_query["backend/eval_duration_ms"])
        for name, value in per_query.items():
            timing[prefix + "/" + name].append(value)
        if sample.context_tokens is not None:
            timing[prefix + "/context_tokens"].append(sample.context_tokens)
    return {"expected_samples": expected, "recorded_samples": len(samples),
            "missing_samples": expected - len(samples), "scored_samples": len(scores),
            "statuses": dict(statuses), "judge_error_samples": sum(bool(s.errors) for s in scores),
            "answer_coverage": (statuses["completed"] / len(samples)) if samples else None,
            "metrics": {name: {"mean": mean(values), "n_questions": len(values),
                                "n_observations": sum(s.metrics.get(name) is not None for s in scores)}
                        for name, values in sorted(metrics.items())},
            "timing": {name: distribution(values) for name, values in sorted(timing.items())}}


def paired_comparison(left, right, *, repeats: int, iterations: int, seed: int) -> dict:
    """right minus left, requiring every repeat to have a valid paired metric.

    CI: percentile paired bootstrap across question means. p: two-sided Monte
    Carlo sign-flip randomization; Holm correction is applied across report tests.
    """
    left_means, right_means = question_means(left), question_means(right)
    counts = []
    for scores in (left, right):
        counter = defaultdict(int)
        for score in scores:
            for metric, value in score.metrics.items():
                if value is not None:
                    counter[(metric, score.question_id)] += 1
        counts.append(counter)
    metrics = sorted({key[0] for key in left_means} & {key[0] for key in right_means})
    output = {}
    for metric in metrics:
        keys = sorted(key for key in left_means.keys() & right_means.keys()
                      if key[0] == metric and all(count[key] == repeats for count in counts))
        differences = np.array([right_means[key] - left_means[key] for key in keys], dtype=float)
        n = len(differences)
        record = {"n_paired_questions": n, "delta": float(differences.mean()) if n else None,
                  "ci95": None, "p_value": None}
        if n >= 2:
            rng = np.random.default_rng(seed)
            boot = differences[rng.integers(0, n, size=(iterations, n))].mean(axis=1)
            record["ci95"] = [float(v) for v in np.percentile(boot, [2.5, 97.5])]
            randomized = (differences * rng.choice([-1, 1], size=(iterations, n))).mean(axis=1)
            record["p_value"] = float((1 + np.count_nonzero(np.abs(randomized) >= abs(differences.mean()))) / (iterations + 1))
        output[metric] = record
    return output


def adjust_holm(comparisons: dict) -> None:
    tests = sorted((record["p_value"], comparison, metric)
                   for comparison, metrics in comparisons.items() for metric, record in metrics.items()
                   if record["p_value"] is not None)
    previous = 0.0
    for rank, (p_value, comparison, metric) in enumerate(tests):
        previous = max(previous, min(1.0, p_value * (len(tests) - rank)))
        comparisons[comparison][metric]["p_holm"] = previous
