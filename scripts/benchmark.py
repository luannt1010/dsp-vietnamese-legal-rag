"""Validate labels, run inference, score artifacts, and report as separate commands."""

import argparse
import json
import logging
from pathlib import Path
import sys

from dotenv import load_dotenv
import yaml

from core.config import load_settings
from core.schemas import LegalChunk
from src.benchmark.artifacts import ROOT, sanitized_settings
from src.benchmark.config import load_config
from src.benchmark.dataset import load_dataset
from src.benchmark.reporting.export import build_report
from src.benchmark.runner import model_identities, run_benchmark
from src.benchmark.schemas import Question
from src.benchmark.scoring.judge import JudgeSettings, live_judge
from src.benchmark.scoring.retrieval import EvidenceIndex
from src.benchmark.scoring.service import score_run
from src.infrastructure.embedding import OllamaEmbedding


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--debug", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)
    schema = commands.add_parser("schema", help="write the accepted question JSON Schema")
    schema.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", help="validate JSONL; optionally resolve exact evidence against corpus.json")
    validate.add_argument("--dataset", type=Path, required=True)
    validate.add_argument("--corpus", type=Path)
    run = commands.add_parser("run", help="run B0–B4, with atomic resume")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--config", type=Path, default=ROOT / "configs/benchmark/hybrid.yml")
    run.add_argument("--split", choices=["development", "test", "all"], default="test")
    for command in (run, commands.add_parser("score", help="score existing samples, no pipeline inference")):
        command.add_argument("--config-dir", type=Path, default=ROOT / "configs/demo")
        command.add_argument("--env-file", type=Path, default=ROOT / ".runtime/demo.env")
        command.add_argument("--output", type=Path, required=True, help="run directory")
    score = commands.choices["score"]
    score.add_argument("--retrieval-only", action="store_true", help="no judge/model calls")
    score.add_argument("--judge-config", type=Path, default=ROOT / "configs/benchmark/judging.yml")
    report = commands.add_parser("report", help="export JSON/CSV/Markdown from scored artifacts")
    report.add_argument("--output", type=Path, required=True)
    return root


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)
    try:
        if args.command == "schema":
            from src.data_pipeline.artifacts import write_json
            write_json(args.output, Question.model_json_schema())
            print(args.output)
        elif args.command == "validate":
            questions = load_dataset(args.dataset)
            if args.corpus:
                payload = json.loads(args.corpus.read_text(encoding="utf-8"))
                index = EvidenceIndex([LegalChunk.model_validate(chunk) for chunk in payload["chunks"]])
                for question in questions:
                    index.resolve(question)
            print(json.dumps({"questions": len(questions), "answerable": sum(q.answerable for q in questions),
                              "evidence_checked": bool(args.corpus)}, ensure_ascii=False))
        elif args.command == "report":
            result = build_report(args.output)
            print(f"Report: {args.output / 'reports/report.md'}; {len(result['summary'])} experiments")
        elif args.command == "score" and args.retrieval_only:
            score_run(args.output)
        else:
            if args.env_file.is_file():
                load_dotenv(args.env_file, override=False, encoding="utf-8-sig")
            settings = load_settings(args.config_dir)
            if args.command == "run":
                config = load_config(args.config)
                questions = load_dataset(args.dataset)
                questions = [q for q in questions if args.split == "all" or q.split == args.split]
                if not questions:
                    raise ValueError("no questions in the selected split")
                run_benchmark(config, settings, questions, args.output)
            else:
                judge_config = JudgeSettings.model_validate(yaml.safe_load(args.judge_config.read_text(encoding="utf-8-sig")))
                manifest = json.loads((args.output / "manifest.json").read_text(encoding="utf-8"))
                if settings.embedding.model_dump(mode="json", exclude={"api_key"}) != manifest["identity"]["settings"]["embedding"]:
                    raise ValueError("scoring embedding differs from the run; restore its configuration")
                if judge_config.model == manifest["identity"]["settings"]["llm"]["answer_generator"]["model"] and not judge_config.allow_same_model:
                    raise ValueError("judge equals the run's generator; choose another judge")
                data = settings.model_dump()
                for role in ("query_analyzer", "retrieval_evaluator", "answer_generator", "citation_verifier"):
                    data["llm"][role]["model"] = judge_config.model
                from core.config import Settings
                identity = {"config": judge_config.model_dump(mode="json"), "models": model_identities(Settings.model_validate(data)),
                            "embedding": sanitized_settings(settings)["embedding"]}
                embedding_key = f"{settings.embedding.base_url}/{settings.embedding.model}"
                if identity["models"][embedding_key] != manifest["identity"]["models"].get(embedding_key):
                    raise ValueError("embedding model digest changed since inference")
                judge = live_judge(settings, judge_config, args.output / "judge-cache", identity)
                score_run(args.output, judge=judge, embedding=OllamaEmbedding(settings.embedding),
                          reverse_count=judge_config.reverse_questions)
        return 0
    except Exception as exc:
        if args.debug:
            logging.exception("benchmark failed")
        else:
            print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
