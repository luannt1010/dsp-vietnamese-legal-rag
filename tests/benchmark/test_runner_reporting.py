from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.benchmark.artifacts import ArtifactStore
from src.benchmark.config import BenchmarkConfig, Experiment
from src.benchmark.reporting.aggregate import adjust_holm, paired_comparison
from src.benchmark.reporting.export import build_report
from src.benchmark.runner import run_benchmark
from src.benchmark.scoring.service import score_run


def test_run_resume_score_report_without_live_services(tmp_path, settings, question, chunks, pipeline_factory):
    config = BenchmarkConfig(repeats=2, warmup_queries=0, bootstrap_samples=100,
        experiments=[Experiment(id="B0", use_graph=False, use_rerank=False),
                     Experiment(id="B1", use_graph=False, use_rerank=True)])
    opened = []
    @contextmanager
    def runtime(selected, **kwargs):
        opened.append(selected)
        yield SimpleNamespace(pipeline=pipeline_factory(selected),
                              corpus=SimpleNamespace(corpus_id="fixture", manifest={"corpus_id": "fixture"}, chunks=chunks),
                              token_counter=len)
    output = tmp_path / "run"
    store = run_benchmark(config, settings, [question], output, runtime_factory=runtime, identities={"fixture": "digest"}, progress=lambda _: None)
    assert len(list(store.samples())) == 4
    assert all(len(s.result.rounds[0].retrieval_result.results) == 20 for s in store.samples())
    run_benchmark(config, settings, [question], output, runtime_factory=runtime, identities={"fixture": "digest"}, progress=lambda _: None)
    assert len(opened) == 4  # Resume did not rerun inference.
    score_run(output, progress=lambda _: None)
    report = build_report(output)
    assert report["summary"]["B0"]["metrics"]["recall@5"]["mean"] == 1
    assert report["summary"]["B1"]["metrics"]["recall@5"]["mean"] == 0
    assert report["summary"]["B0"]["metrics"]["recall@5"]["n_questions"] == 1
    assert report["comparisons"]["B1-B0"]["recall@5"]["delta"] == -1
    assert report["comparisons"]["B1-B0"]["recall@5"]["ci95"] is None  # One question is not a sample of two.
    assert (output / "reports/summary.csv").exists()
    assert list(store.samples())[0].context_tokens is not None
    changed = config.model_copy(update={"seed": 5})
    with pytest.raises(ValueError, match="identity changed"):
        run_benchmark(changed, settings, [question], output, runtime_factory=runtime, identities={"fixture": "digest"})


def test_resume_rejects_changed_corpus(tmp_path):
    store = ArtifactStore(tmp_path)
    store.initialize({"test": True})
    store.register_corpus(SimpleNamespace(corpus_id="a", manifest={"corpus_id": "a"}))
    with pytest.raises(ValueError, match="corpus changed"):
        store.register_corpus(SimpleNamespace(corpus_id="b", manifest={"corpus_id": "b"}))


def test_paired_statistics_cluster_repeats_and_holm():
    def rows(values):
        return [SimpleNamespace(question_id=f"q{i}", metrics={"recall@5": value})
                for i, value in enumerate(values) for _ in range(3)]
    result = paired_comparison(rows([0, 0]), rows([1, 1]), repeats=3, iterations=100, seed=42)
    assert result["recall@5"]["n_paired_questions"] == 2
    assert result["recall@5"]["delta"] == 1
    assert result["recall@5"]["ci95"] == [1, 1]
    comparisons = {"a": {"x": {"p_value": 0.01}, "y": {"p_value": 0.04}}, "b": {"z": {"p_value": 0.03}}}
    adjust_holm(comparisons)
    assert comparisons["a"]["x"]["p_holm"] == pytest.approx(0.03)
    assert comparisons["a"]["y"]["p_holm"] == pytest.approx(0.06)


def test_missing_repeats_do_not_enter_paired_comparison():
    left = [SimpleNamespace(question_id="q", metrics={"m": 0})]
    right = [SimpleNamespace(question_id="q", metrics={"m": 1}) for _ in range(2)]
    result = paired_comparison(left, right, repeats=2, iterations=100, seed=42)
    assert result["m"]["n_paired_questions"] == 0
