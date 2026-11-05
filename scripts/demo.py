"""CLI demo and index preparation. No API server or benchmark dataset required."""

import argparse
import json
import logging
import sys
import traceback
from pathlib import Path
from uuid import uuid4

import psycopg
from dotenv import load_dotenv
from neo4j import GraphDatabase

from core.config import Settings, load_settings
from core.schemas import QueryRequest
from src.generation.answer_formatter import AnswerFormatter
from src.infrastructure.ollama_client import OllamaClient
from src.runtime import open_runtime, prepare_indexes
from src.data_pipeline.loaders.phapdien_dataset import PhapDienDataset


ROOT = Path(__file__).resolve().parents[1]


def load_demo_settings(args) -> Settings:
    if args.env_file.is_file():
        load_dotenv(args.env_file, override=False, encoding="utf-8-sig")
    settings = load_settings(args.config_dir)
    data = settings.model_dump()
    if args.chunking:
        data["data_pipeline"]["chunking"]["strategy"] = args.chunking
    if args.vector_index:
        data["database"]["vector"]["index_type"] = args.vector_index
    if args.vector_backend:
        data["database"]["vector"]["backend"] = args.vector_backend
    if args.graph_backend:
        data["database"]["graph"]["backend"] = args.graph_backend
    if args.no_rerank:
        data["retrieval"]["use_rerank"] = False
    return Settings.model_validate(data)


def doctor(settings: Settings) -> dict:
    models = sorted({getattr(settings.llm, role).model for role in (
        "query_analyzer", "retrieval_evaluator", "answer_generator", "citation_verifier",
    )})
    client = OllamaClient(settings.llm.base_url or "http://localhost:11434", timeout_s=20, max_retries=0)
    report = {"llm_models": {model: client.post("/api/show", {"model": model}).get("capabilities") for model in models}}
    report["embedding"] = OllamaClient(settings.embedding.base_url, timeout_s=20, max_retries=0).post(
        "/api/show", {"model": settings.embedding.model},
    ).get("capabilities")
    vector = settings.database.vector
    if vector.backend == "pgvector":
        with psycopg.connect(
            host=vector.host, port=vector.port, dbname=vector.database, user=vector.username,
            password=vector.password.get_secret_value() if vector.password else None, connect_timeout=10,
        ) as connection:
            report["postgresql"] = connection.execute("SELECT version()").fetchone()[0]
            extension = connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
            report["pgvector"] = extension[0] if extension else "enabled during prepare"
    graph = settings.database.graph
    if graph.backend == "neo4j":
        auth = (graph.username, graph.password.get_secret_value()) if graph.password else None
        with GraphDatabase.driver(graph.uri, auth=auth, connection_timeout=10) as driver:
            driver.verify_connectivity()
            report["neo4j"] = "connected"
    return report


def ask(runtime, question: str, trace_path: Path | None = None) -> int:
    result = runtime.pipeline.run_with_trace(QueryRequest(query=question))
    print(AnswerFormatter().format(result.answer))
    trace_path = trace_path or runtime.corpus.directory / "traces" / (uuid4().hex + ".json")
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nStatus: {result.status}; rounds: {len(result.rounds)}; trace: {trace_path}")
    if result.failure_stage:
        print(f"Failed stage: {result.failure_stage}; error: {result.error_type}")
    return 0 if result.status == "completed" else 2


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=ROOT / "configs" / "demo")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".runtime" / "demo.env")
    parser.add_argument("--chunking", choices=["fixed", "legal", "hierarchical"])
    parser.add_argument("--vector-index", choices=["exact", "hnsw", "ivfflat"])
    parser.add_argument("--vector-backend", choices=["pgvector", "in_memory"])
    parser.add_argument("--graph-backend", choices=["neo4j", "in_memory"])
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--debug", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check actual model and database connectivity")
    prepare = commands.add_parser("prepare", help="chunk, embed and index the configured corpus")
    prepare.add_argument("--refresh-source", action="store_true", help="resolve the requested HF revision again (cached by default)")
    prepare.add_argument("--force-reindex", action="store_true", help="write database indexes even when already ready; reuse prepared embeddings")
    for kind in ("topics", "subjects"):
        listing = commands.add_parser("list-" + kind, help="list dataset names, IDs and article counts")
        listing.add_argument("--refresh-source", action="store_true")
    query = commands.add_parser("ask", help="run one actual RAG request")
    query.add_argument("--question", required=True)
    query.add_argument("--trace", type=Path)
    commands.add_parser("chat", help="interactive terminal demo (independent questions)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)
    try:
        settings = load_demo_settings(args)
        logging.getLogger().setLevel(logging.DEBUG if args.debug else settings.logging.level)
        if args.command in {"list-topics", "list-subjects"}:
            source = settings.data_pipeline.source
            dataset = PhapDienDataset(source, settings.data_pipeline.index_dir / "sources").open(
                download=True, refresh=args.refresh_source,
            )
            kind = args.command.removeprefix("list-")
            for entry in sorted(dataset.catalog()[kind], key=lambda item: (item["title"] or "", item["id"])):
                parent = f" | topic: {entry['topic_id']}" if kind == "subjects" else ""
                print(f"{entry['id']} | {entry['title']} | {entry['articles']} articles{parent}")
            return 0
        if args.command == "doctor":
            print(json.dumps(doctor(settings), ensure_ascii=False, indent=2))
            return 0
        if args.command == "prepare":
            print(json.dumps(prepare_indexes(settings, refresh=args.refresh_source, force_reindex=args.force_reindex),
                             ensure_ascii=False, indent=2))
            return 0
        with open_runtime(settings) as runtime:
            if args.command == "ask":
                return ask(runtime, args.question, args.trace)
            print("Nhập câu hỏi; gõ /exit để kết thúc. Mỗi câu hỏi là một request độc lập.")
            while True:
                try:
                    question = input("> ").strip()
                except EOFError:
                    break
                if question == "/exit":
                    break
                if question:
                    ask(runtime, question)
        return 0
    except KeyboardInterrupt:
        print("Interrupted by user. Rerun prepare if database indexing was interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
