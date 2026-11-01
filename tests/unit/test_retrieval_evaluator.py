import unittest

from core.exceptions import LLMError
from core.interfaces import BaseLLM
from core.schemas import (
    RetrievalEvaluationRequest,
    RetrievalResult,
    RetrievedChunk,
)
from src.evaluation import RetrievalEvaluator


class FakeLLM(BaseLLM):
    def __init__(self, response: str) -> None:
        self.response = response
        self.called = False

    def generate(self, prompt: str) -> str:
        self.called = True
        return self.response


def make_request(results: list[RetrievedChunk]) -> RetrievalEvaluationRequest:
    return RetrievalEvaluationRequest(
        original_query="Người lao động được nghỉ phép thế nào?",
        current_query="Quy định nghỉ phép năm của người lao động",
        retrieval_result=RetrievalResult(
            query="Quy định nghỉ phép năm của người lao động",
            results=results,
            total_candidates=len(results),
        ),
    )


class RetrievalEvaluatorTests(unittest.TestCase):
    def test_empty_retrieval_is_insufficient_without_calling_llm(self) -> None:
        llm = FakeLLM("{}")

        result = RetrievalEvaluator(llm).evaluate(make_request([]))

        self.assertFalse(result.is_relevant)
        self.assertFalse(result.is_sufficient)
        self.assertEqual(result.next_action, "stop")
        self.assertFalse(llm.called)

    def test_valid_sufficient_evaluation_is_returned(self) -> None:
        hit = RetrievedChunk(
            chunk_id="chunk-1",
            document_id="law-1",
            content="Người lao động được nghỉ hằng năm...",
            score=0.9,
            retrieval_method="vector",
        )
        llm = FakeLLM(
            '{"is_relevant":true,"is_sufficient":true,"confidence":0.86,'
            '"missing_information":[],"next_action":"continue",'
            '"refined_query":null,"strategy_override":{},'
            '"reason":"Evidence addresses the annual leave question."}'
        )

        result = RetrievalEvaluator(llm).evaluate(make_request([hit]))

        self.assertTrue(result.is_sufficient)
        self.assertEqual(result.next_action, "continue")

    def test_invalid_feedback_contract_raises_llm_error(self) -> None:
        hit = RetrievedChunk(
            chunk_id="chunk-1",
            document_id="law-1",
            content="Text",
            score=0.2,
            retrieval_method="bm25",
        )
        llm = FakeLLM(
            '{"is_relevant":false,"is_sufficient":false,"confidence":0.4,'
            '"next_action":"continue","reason":"Not sufficient."}'
        )
        with self.assertRaises(LLMError):
            RetrievalEvaluator(llm).evaluate(make_request([hit]))

    def test_refine_action_requires_non_empty_query(self) -> None:
        hit = RetrievedChunk(
            chunk_id="chunk-1",
            document_id="law-1",
            content="Text",
            score=0.2,
            retrieval_method="bm25",
        )
        llm = FakeLLM(
            '{"is_relevant":false,"is_sufficient":false,"confidence":0.4,'
            '"missing_information":["effective date"],'
            '"next_action":"refine_query","reason":"Need a narrower query."}'
        )
        with self.assertRaises(LLMError):
            RetrievalEvaluator(llm).evaluate(make_request([hit]))


if __name__ == "__main__":
    unittest.main()
