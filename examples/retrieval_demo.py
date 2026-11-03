"""Run real retrieval algorithms on synthetic chunks with fixture model adapters."""

import sys

from core.config import load_settings
from core.interfaces import BaseEmbedding
from core.schemas import LegalChunk, LegalMetadata, RetrievalRouteRequest
from src.infrastructure.vector_store import InMemoryVectorStore
from src.retrieval.dense import VectorRetriever
from src.retrieval.reranking import CrossEncoderReRanker
from src.retrieval.router import RetrievalRouter
from src.retrieval.service import RetrievalService
from src.retrieval.sparse import BM25Retriever


class DemoEmbedding(BaseEmbedding):
    """Deterministic keyword fixture; not a production semantic embedding model."""

    @property
    def dimension(self) -> int:
        return 3

    def embed_query(self, text: str) -> list[float]:
        words = set(text.lower().split())
        return [float(len(words & {"lao", "động", "lương"})),
                float(len(words & {"thuế", "thu", "nhập"})), 0.1]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]


class DemoCrossEncoder:
    """Fixture prediction only, used to exercise the real reranking adapter."""

    def predict(self, pairs: list[tuple[str, str]], *, batch_size: int) -> list[float]:
        return [float(len(set(query.lower().split()) & set(content.lower().split())))
                for query, content in pairs]


def build_demo_service() -> RetrievalService:
    settings = load_settings(environ={})
    embedding = DemoEmbedding()
    chunks = []
    for identifier, domain, text in (
        ("demo-labor-1", "labor", "Ví dụ giả lập về lao động và tiền lương."),
        ("demo-labor-2", "labor", "Ví dụ giả lập về hợp đồng lao động."),
        ("demo-tax-1", "tax", "Ví dụ giả lập về thuế thu nhập."),
    ):
        chunks.append(LegalChunk(
            chunk_id=f"{identifier}:article-1", document_id=identifier, content=text, article="1",
            metadata=LegalMetadata(
                document_id=identifier, title="Văn bản giả lập", document_number=identifier,
                document_type="mock", legal_domain=[domain],
            ),
            embedding=embedding.embed_query(text),
        ))
    return RetrievalService(
        bm25_retriever=BM25Retriever(chunks, **settings.retrieval.bm25.model_dump()),
        vector_retriever=VectorRetriever(embedding, InMemoryVectorStore(
            chunks, dimension=embedding.dimension,
            distance_metric=settings.database.vector.distance_metric,
        )),
        reranker=CrossEncoderReRanker(
            model=DemoCrossEncoder(), batch_size=settings.retrieval.reranker.batch_size,
            max_length=settings.retrieval.reranker.max_input_tokens,
        ),
        settings=settings.retrieval,
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    query = "lao động tiền lương"
    filters = {"legal_domain": ["labor"]}
    settings = load_settings(environ={})
    strategy = RetrievalRouter(settings.retrieval).route(RetrievalRouteRequest(
        query=query, intent="demo", filters=filters,
    ))
    result = build_demo_service().retrieve(query, filters, strategy)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
