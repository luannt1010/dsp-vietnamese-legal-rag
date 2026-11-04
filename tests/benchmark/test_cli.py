from contextlib import contextmanager
from types import SimpleNamespace

from scripts.benchmark import main
from src.benchmark.config import BenchmarkConfig, Experiment
from src.benchmark.runner import run_benchmark


def test_cli_schema_validate_offline_score_and_report(tmp_path, settings, question, chunks, pipeline_factory):
    dataset = tmp_path / "questions.jsonl"
    dataset.write_text(question.model_dump_json() + "\n", encoding="utf-8")
    assert main(["schema", "--output", str(tmp_path / "schema.json")]) == 0
    assert main(["validate", "--dataset", str(dataset)]) == 0
    output = tmp_path / "run"
    config = BenchmarkConfig(repeats=1, warmup_queries=0, experiments=[
        Experiment(id="B0", use_graph=False, use_rerank=False)])
    @contextmanager
    def factory(selected, **kwargs):
        yield SimpleNamespace(pipeline=pipeline_factory(selected), token_counter=len,
            corpus=SimpleNamespace(corpus_id="fixture", manifest={"corpus_id": "fixture"}, chunks=chunks))
    run_benchmark(config, settings, [question], output, runtime_factory=factory, identities={"fixture": "digest"}, progress=lambda _: None)
    assert main(["score", "--output", str(output), "--retrieval-only"]) == 0
    assert main(["report", "--output", str(output)]) == 0
    assert (output / "reports/latency.csv").is_file()
    dataset.write_text("{}\n", encoding="utf-8")
    assert main(["validate", "--dataset", str(dataset)]) == 2
