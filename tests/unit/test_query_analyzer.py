import unittest

from core.exceptions import LLMError
from core.interfaces import BaseLLM
from core.schemas import QueryRequest
from src.query_understanding import QueryAnalyzer


class FakeLLM(BaseLLM):
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return self.response


class QueryAnalyzerTests(unittest.TestCase):
    def test_analyze_returns_schema_and_preserves_original_query(self) -> None:
        llm = FakeLLM(
            '{"original_query":"model altered this",'
            '"rewritten_query":"Điều kiện nghỉ phép năm",'
            '"intent":"legal_lookup","entities":["nghỉ phép"],'
            '"keywords":["nghỉ phép năm"],'
            '"metadata":{"legal_domain":["labor"]}}'
        )
        query = "Điều kiện nghỉ phép?"

        result = QueryAnalyzer(llm).analyze(QueryRequest(query=query))

        self.assertEqual(result.original_query, query)
        self.assertEqual(result.rewritten_query, "Điều kiện nghỉ phép năm")
        self.assertEqual(result.metadata, {"legal_domain": ["labor"]})
        self.assertIn(query, llm.prompt)

    def test_invalid_json_raises_llm_error(self) -> None:
        with self.assertRaises(LLMError):
            QueryAnalyzer(FakeLLM("not json")).analyze(
                QueryRequest(query="Câu hỏi pháp luật?")
            )

    def test_invalid_schema_raises_llm_error(self) -> None:
        llm = FakeLLM('{"rewritten_query":"","intent":"legal_lookup"}')
        with self.assertRaises(LLMError):
            QueryAnalyzer(llm).analyze(QueryRequest(query="Câu hỏi pháp luật?"))

    def test_non_object_response_raises_llm_error(self) -> None:
        with self.assertRaises(LLMError):
            QueryAnalyzer(FakeLLM("[]")).analyze(
                QueryRequest(query="Câu hỏi pháp luật?")
            )


if __name__ == "__main__":
    unittest.main()
