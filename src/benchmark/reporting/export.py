"""Export complete machine-readable results and compact reviewable tables."""

import csv
import json
from collections import defaultdict

from src.benchmark.artifacts import ArtifactStore
from src.benchmark.reporting.aggregate import adjust_holm, paired_comparison, summarize
from src.benchmark.schemas import Score
from src.data_pipeline.artifacts import fingerprint, write_json


def build_report(directory):
    store = ArtifactStore(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    scoring = json.loads((directory / "scoring.json").read_text(encoding="utf-8"))
    config = manifest["identity"]["config"]
    questions = {q["question_id"]: q for q in manifest["identity"]["questions"]}
    samples = list(store.samples())
    scores = []
    seen = set()
    for sample in samples:
        key = (sample.experiment, sample.question_id, sample.repeat)
        if key in seen:
            raise ValueError(f"duplicate sample: {key}")
        seen.add(key)
        path = store.score_path(sample)
        if path.exists():
            score = Score.model_validate_json(path.read_text(encoding="utf-8"))
            if score.scoring_fingerprint != scoring["fingerprint"] or score.sample_fingerprint != fingerprint(sample.model_dump(mode="json")):
                raise ValueError("stale/mixed scores; rerun score before reporting")
            scores.append(score)
    grouped_samples, grouped_scores = defaultdict(list), defaultdict(list)
    for sample in samples:
        grouped_samples[sample.experiment].append(sample)
    for score in scores:
        grouped_scores[score.experiment].append(score)
    summary = {}
    for experiment in config["experiments"]:
        name = experiment["id"]
        summary[name] = summarize(grouped_scores[name], grouped_samples[name], len(questions) * config["repeats"])
    breakdown = {}
    for field in ("topic", "question_type"):
        breakdown[field] = {}
        for value in sorted({q[field] for q in questions.values()}):
            ids = {qid for qid, q in questions.items() if q[field] == value}
            breakdown[field][value] = {e["id"]: summarize(
                [s for s in grouped_scores[e["id"]] if s.question_id in ids],
                [s for s in grouped_samples[e["id"]] if s.question_id in ids], len(ids) * config["repeats"])
                for e in config["experiments"]}
    comparisons = {}
    pairs = [("B0", e["id"]) for e in config["experiments"] if e["id"] != "B0"]
    pairs += [("B3", "B4"), ("B0", "B2"), ("B1", "B3")]
    for left, right in dict.fromkeys(pairs):
        if left in summary and right in summary:
            comparisons[f"{right}-{left}"] = paired_comparison(
                grouped_scores[left], grouped_scores[right], repeats=config["repeats"],
                iterations=config["bootstrap_samples"], seed=config["seed"])
    adjust_holm(comparisons)
    result = {"manifest_fingerprint": manifest["fingerprint"], "scoring": scoring,
              "summary": summary, "breakdown": breakdown, "comparisons": comparisons,
              "notes": ["CI95 are pointwise paired bootstrap intervals; use p_holm for the family of reported metric tests.",
                        "Quality means exclude N/A/judge errors: inspect coverage and n_questions before comparing.",
                        "Paired tests require valid scores for every repeat on both methods.",
                        "Binary chunk qrels and semantic context recall measure different units.",
                        "Incomplete runs are reported explicitly; no universal winner is inferred."]}
    output = directory / "reports"
    write_json(output / "summary.json", result)
    metric_names = sorted({m for stats in summary.values() for m in stats["metrics"]})
    with (output / "summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["experiment", "recorded", "expected", "coverage", *metric_names])
        writer.writeheader()
        for name, stats in summary.items():
            writer.writerow({"experiment": name, "recorded": stats["recorded_samples"], "expected": stats["expected_samples"],
                             "coverage": stats["answer_coverage"],
                             **{metric: stats["metrics"].get(metric, {}).get("mean") for metric in metric_names}})
    with (output / "latency.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["experiment", "scope_status_metric", "n", "mean", "p50", "p95"])
        writer.writeheader()
        for name, stats in summary.items():
            for metric, values in stats["timing"].items():
                writer.writerow({"experiment": name, "scope_status_metric": metric, **values})
    lines = ["# Hybrid RAG benchmark", "", "| Method | Samples / expected | Answer coverage | Judge-error samples |",
             "|---|---:|---:|---:|"]
    for name, stats in summary.items():
        coverage = stats["answer_coverage"]
        lines.append(f"| {name} | {stats['recorded_samples']}/{stats['expected_samples']} | "
                     f"{coverage if coverage is not None else 'N/A'} | {stats['judge_error_samples']} |")
    lines += ["", "## Quality metrics", "",
              "| Metric | " + " | ".join(summary) + " |",
              "|---|" + "---:|" * len(summary)]
    for metric in metric_names:
        if metric.startswith("round_"):
            continue  # Round-level details remain in JSON/CSV.
        values = [stats["metrics"].get(metric, {}).get("mean") for stats in summary.values()]
        lines.append(f"| {metric} | " + " | ".join(
            f"{value:.4f}" if value is not None else "N/A" for value in values) + " |")
    lines += ["", "See summary.csv for quality means and latency.csv for timings; summary.json contains denominators,",
              "topic/type breakdowns, paired intervals, and Holm-adjusted p-values.", "", *result["notes"]]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
