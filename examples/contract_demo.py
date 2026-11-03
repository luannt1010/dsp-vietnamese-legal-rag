"""Run with python -m examples.contract_demo; all source data is synthetic."""

import sys

from core.exceptions import InsufficientEvidenceError
from core.interfaces import BaseAnswerGenerator, BaseRetriever
from core.schemas import (
    AnswerGenerationRequest,
    LegalAnswer,
    LegalChunk,
    LegalCitation,
    LegalContext,
    LegalMetadata,
    RetrievalRequest,
    RetrievedChunk,
)


class MockRetriever(BaseRetriever):
    """One-hit fixture; filters intentionally unsupported in this mock."""

    def search(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        if request.filters:
            raise ValueError("this fixture only supports unfiltered requests")
        chunk = LegalChunk(
            chunk_id="mock-document:article-1",
            document_id="mock-document",
            content="Nội dung giả lập để kiểm tra giao tiếp giữa các module.",
            article="1",
            metadata=LegalMetadata(
                document_id="mock-document",
                title="Văn bản giả lập, không phải văn bản pháp luật",
                document_number="MOCK-001",
                document_type="mock",
            ),
        )
        metadata = chunk.metadata.model_dump(mode="json")
        metadata["article"] = chunk.article
        return [RetrievedChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            content=chunk.content,
            score=1.0,
            retrieval_method="mock",
            metadata=metadata,
        )]


class MockAnswerGenerator(BaseAnswerGenerator):
    """Use the same interface that the real answer generator will implement."""

    def generate(self, request: AnswerGenerationRequest) -> LegalAnswer:
        if not request.context.chunks or not request.context.context_text.strip():
            raise InsufficientEvidenceError("no source evidence in context")
        chunk = request.context.chunks[0]
        return LegalAnswer(
            answer="Đây là câu trả lời giả lập cho việc kiểm tra contract.",
            citations=[LegalCitation(
                document_id=chunk.document_id,
                document_number=chunk.metadata["document_number"],
                article=chunk.metadata.get("article"),
                quoted_text=chunk.content,
            )],
            confidence=0.0,
            disclaimer="Dữ liệu giả lập, không sử dụng làm tư vấn pháp luật.",
        )


def build_mock_context(query: str = "Câu hỏi thử nghiệm") -> LegalContext:
    """A context fixture for generation development, not a real context builder."""

    chunks = MockRetriever().search(RetrievalRequest(query=query))
    return LegalContext(
        query=query,
        context_text="\n\n".join(chunk.content for chunk in chunks),
        chunks=chunks,
        cited_document_ids=list(dict.fromkeys(chunk.document_id for chunk in chunks)),
    )


def main() -> None:
    # Windows terminals/pipes may default to an encoding without Vietnamese.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    context = build_mock_context()
    generator: BaseAnswerGenerator = MockAnswerGenerator()
    answer = generator.generate(AnswerGenerationRequest(context=context, query=context.query))
    print(answer.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
