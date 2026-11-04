"""Experiment orchestration using the existing runtime and pipeline, not a second RAG."""

import hashlib
import json
import random
from time import perf_counter

from core.schemas import QueryAnalysisResult, QueryRequest
from src.benchmark.artifacts import ArtifactStore, code_identity, sanitized_settings
from src.benchmark.scoring.retrieval import EvidenceIndex
from src.benchmark.schemas import Sample
from src.infrastructure.ollama_client import OllamaClient
from src.data_pipeline.artifacts import write_json
from src.observability.telemetry import capture
from src.runtime import open_runtime


def model_identities(settings) -> dict:
    if settings.llm.provider != "ollama" or settings.embedding.provider != "ollama":
        raise ValueError("the live benchmark currently uses the existing Ollama runtime")
    selections = {(settings.llm.base_url or "http://localhost:11434", getattr(settings.llm, role).model)
                  for role in ("query_analyzer", "retrieval_evaluator", "answer_generator", "citation_verifier")}
    selections.add((settings.embedding.base_url, settings.embedding.model))
    identities = {}
    for url, model in sorted(selections):
        result = OllamaClient(url, timeout_s=30, max_retries=0).post("/api/show", {"model": model})
        modelfile = result.get("modelfile")
        if not isinstance(modelfile, str) or not modelfile:
            raise ValueError(f"cannot fingerprint model {model}")
        identities[f"{url}/{model}"] = hashlib.sha256(modelfile.encode()).hexdigest()
    return identities


def run_benchmark(config, settings, questions, directory, *, runtime_factory=open_runtime,
                  identities=None, progress=print) -> ArtifactStore:
    if not questions:
        raise ValueError("cannot run an empty question set")
    store = ArtifactStore(directory)
    check_models = identities is None
    identities = model_identities(settings) if identities is None else identities
    store.initialize({"config": config.model_dump(mode="json"), "settings": sanitized_settings(settings),
                      "questions": [q.model_dump(mode="json") for q in questions],
                      "code": code_identity(), "models": identities,
                      "latency_protocol": "sequential; runtime/index/warmup excluded; no offline judge"})
    options = config.run_options()
    for repeat in range(config.repeats):
        experiments = list(config.experiments)
        random.Random(config.seed + repeat).shuffle(experiments)
        for experiment in experiments:
            pending = [q for q in questions if not store.sample_path(experiment.id, q.question_id, repeat).exists()]
            if not pending:
                continue
            selected = config.settings_for(settings, experiment)
            progress(f"{experiment.id} repeat={repeat}: {len(pending)} pending")
            # Setup and preflight happen outside the timed request scope.
            setup_started = perf_counter()
            with runtime_factory(selected, allow_strategy_changes=False) as runtime:
                if check_models and model_identities(selected) != identities:
                    raise ValueError("model identity changed during the run")
                store.register_corpus(runtime.corpus)
                index = EvidenceIndex(runtime.corpus.chunks)
                labels = {q.question_id: index.resolve(q) for q in questions}
                write_qrels(store, runtime.corpus.corpus_id, labels)
                session = {"setup_ms": (perf_counter() - setup_started) * 1000,
                           "warmup_queries": [], "measurement_condition": "post_warmup" if config.warmup_queries else "no_warmup"}
                for i in range(config.warmup_queries):
                    with capture() as warmup_events:
                        warmup_started = perf_counter()
                        warmup = runtime.pipeline.run_with_trace(
                            QueryRequest(query=questions[i % len(questions)].question), options=options)
                    session["warmup_queries"].append({"duration_ms": (perf_counter() - warmup_started) * 1000,
                                                       "status": warmup.status, "telemetry": warmup_events})
                write_json(directory / "sessions" / f"{experiment.id}.{repeat}.json", session)
                for question in pending:
                    analysis = None
                    if config.replay_analysis:
                        analysis_path = directory / "analysis" / f"{question.question_id}.{repeat}.json"
                        if analysis_path.exists():
                            analysis = QueryAnalysisResult.model_validate_json(analysis_path.read_text(encoding="utf-8"))
                    with capture() as telemetry:
                        started = perf_counter()
                        result = runtime.pipeline.run_with_trace(QueryRequest(query=question.question), options=options, analysis=analysis)
                        elapsed = (perf_counter() - started) * 1000
                    if config.replay_analysis and result.analysis is not None:
                        write_json(analysis_path, result.analysis.model_dump(mode="json"))
                    sample = Sample(experiment=experiment.id, question_id=question.question_id, repeat=repeat,
                                    latency_scope="analysis_replay" if config.replay_analysis else "full_pipeline",
                                    result=result, telemetry=telemetry, latency_ms=elapsed,
                                    context_tokens=(runtime.token_counter(result.context.context_text)
                                                    if result.context is not None and runtime.token_counter else None),
                                    relevant_chunk_ids=labels[question.question_id])
                    store.save_sample(sample)
                    progress(f"  {question.question_id}: {result.status} {elapsed / 1000:.2f}s")
    return store


def write_qrels(store, corpus_id: str, labels: dict) -> None:
    path = store.directory / "qrels.json"
    value = {"corpus_id": corpus_id, "unit": "chunk_id", "relevance": "binary", "labels": labels}
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != value:
        raise ValueError("qrels changed during the run")
    write_json(path, value)
