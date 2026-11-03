"""Run python -m examples.orchestration_demo; all LLM verdicts/data are fixtures."""

import json
import sys

from core.config import Settings, load_settings
from core.interfaces import BaseLLM
from core.schemas import QueryRequest, RetrievalRequest
from examples.contract_demo import MockAnswerGenerator, MockRetriever
from src.orchestration import RAGPipeline, create_pipeline
from src.retrieval.sparse import BM25Retriever


class FixtureLLM(BaseLLM):
    """Return a fixed JSON response; this is not a model or quality evaluation."""

    def __init__(self, payload: dict) -> None:
        self.response = json.dumps(payload, ensure_ascii=False)

    def generate(self, prompt: str) -> str:
        return self.response


def build_demo_pipeline() -> RAGPipeline:
    settings = load_settings()
    settings = Settings.model_validate({
        **settings.model_dump(),
        "retrieval": {
            **settings.retrieval.model_dump(),
            "use_bm25": True, "use_vector": False, "use_graph": False, "use_rerank": False,
        },
    })
    # Reuse the contract demo's synthetic source and generator. BM25, metadata
    # filtering, routing, context building and citation matching run real code.
    sources = MockRetriever().search(RetrievalRequest(query="giả lập"))
    return create_pipeline(
        settings,
        query_llm=FixtureLLM({
            "rewritten_query": "giả lập", "intent": "legal_lookup",
            "metadata": {"document_type": ["mock"]},
        }),
        evaluation_llm=FixtureLLM({
            "is_relevant": True, "is_sufficient": True, "confidence": 0.8,
            "next_action": "continue", "reason": "Fixture evaluation for wiring only",
        }),
        citation_llm=FixtureLLM({"is_supported": True, "reason": "Fixture support verdict"}),
        answer_generator=MockAnswerGenerator(),
        token_counter=len,  # Test fixture; production must use the answer model's tokenizer.
        bm25_retriever=BM25Retriever(sources),
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result = build_demo_pipeline().run_with_trace(QueryRequest(query="Câu hỏi với dữ liệu giả lập"))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
