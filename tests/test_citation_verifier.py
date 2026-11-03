"""Citation provenance and claim-check orchestration; LLM verdicts are fixtures."""

import json
import unittest
import warnings

from pydantic import ValidationError

from core.config.settings import ContextSettings
from core.exceptions import CitationVerificationError
from core.interfaces import BaseCitationVerifier, BaseLLM
from core.schemas import (
    ContextBuilderRequest, LegalAnswer, LegalCitation, LegalContext,
    RetrievalRequest, RetrievalResult, RetrievedChunk,
)
from src.generation import CitationVerifier, LegalContextBuilder
from src.retrieval.sparse import BM25Retriever


_QUOTE = "Người tham gia được nhận hỗ trợ khi đủ điều kiện."


def source(identifier="a", *, document_id="doc-a", content=None, **metadata):
    return RetrievedChunk(
        chunk_id=identifier, document_id=document_id,
        content=content or f"Điều 1. {_QUOTE}", score=1.0, retrieval_method="fixture",
        metadata={
            "document_id": document_id, "document_number": "MOCK-01", "article": "Điều 1",
            "clause": "1", "point": "a", "source_url": "https://example.org/source",
            **metadata,
        },
    )


def citation(**overrides):
    return LegalCitation(**{
        "document_id": "doc-a", "document_number": "MOCK-01", "article": "Điều 1",
        "clause": "1", "point": "a", "source_url": "https://example.org/source",
        "quoted_text": _QUOTE, **overrides,
    })


def answer(*citations, text=_QUOTE):
    return LegalAnswer(
        answer=text, citations=list(citations), confidence=0.7,
        disclaimer="Chỉ dùng dữ liệu giả lập trong kiểm thử.",
    )


def context(*sources):
    return LegalContextBuilder(token_counter=len).build(ContextBuilderRequest(
        original_query="Ai được nhận hỗ trợ?",
        retrieval_result=RetrievalResult(query="hỗ trợ", results=list(sources)),
    ))


class FixtureLLM(BaseLLM):
    def __init__(self, response='{"is_supported":true,"reason":"Fixture verdict"}', *, error=None):
        self.response = response
        self.error = error
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.response


class CitationVerifierTests(unittest.TestCase):
    def setUp(self):
        self.llm = FixtureLLM()
        self.verifier = CitationVerifier(self.llm)
        self.answer = answer(citation())
        self.context = context(source())

    def test_contract_returns_unchanged_independent_answer(self):
        self.assertIsInstance(self.verifier, BaseCitationVerifier)
        before_answer = self.answer.model_dump()
        before_context = self.context.model_dump()
        verified = self.verifier.verify(self.answer, self.context)
        self.assertEqual(verified.model_dump(), before_answer)
        self.assertEqual(self.context.model_dump(), before_context)
        self.assertEqual(len(self.llm.prompts), 1)
        verified.citations[0].quoted_text = "Changed"
        self.assertEqual(self.answer.model_dump(), before_answer)

    def test_unknown_document_or_wrong_number_is_rejected_before_llm(self):
        for changes in ({"document_id": "invented"}, {"document_number": "invented"}):
            with self.subTest(changes=changes), self.assertRaises(CitationVerificationError):
                self.verifier.verify(answer(citation(**changes)), self.context)
        self.assertEqual(self.llm.prompts, [])

    def test_each_supplied_location_and_url_must_match(self):
        for field in ("article", "clause", "point", "source_url"):
            for value in ("wrong", "", " "):
                with self.subTest(field=field, value=value), self.assertRaises(CitationVerificationError):
                    self.verifier.verify(answer(citation(**{field: value})), self.context)
        self.assertEqual(self.llm.prompts, [])

    def test_optional_location_and_url_can_be_omitted(self):
        data = answer(citation(article=None, clause=None, point=None, source_url=None))
        self.assertEqual(self.verifier.verify(data, self.context), data)

    def test_missing_source_metadata_cannot_be_invented_by_citation(self):
        for field in ("document_number", "article", "clause", "point", "source_url"):
            missing = source()
            del missing.metadata[field]
            with self.subTest(field=field), self.assertRaises(CitationVerificationError):
                self.verifier.verify(self.answer, context(missing))
        self.assertEqual(self.llm.prompts, [])

    def test_quote_must_be_exact_not_fuzzy_or_assembled_from_fragments(self):
        for quote in (_QUOTE.replace("hỗ trợ", "ho tro"), _QUOTE.replace(" ", "  "),
                      _QUOTE.replace("được", "không được"), _QUOTE.replace(".", "!")):
            with self.subTest(quote=quote), self.assertRaises(CitationVerificationError):
                self.verifier.verify(answer(citation(quoted_text=quote)), self.context)
        split_context = context(source(content="Đoạn đầu"), source("b", content="Đoạn cuối"))
        with self.assertRaises(CitationVerificationError):
            self.verifier.verify(answer(citation(quoted_text="Đoạn đầu Đoạn cuối")), split_context)
        self.assertEqual(self.llm.prompts, [])

    def test_number_location_and_quote_must_come_from_same_chunk(self):
        contexts = [
            context(source(content="Không có câu trích dẫn"), source("b", document_number="OTHER")),
            context(source(content="Không có câu trích dẫn"), source("b", article="Điều 2")),
        ]
        for data in contexts:
            with self.subTest(data=data), self.assertRaises(CitationVerificationError):
                self.verifier.verify(self.answer, data)
        self.assertEqual(self.llm.prompts, [])

    def test_one_invalid_citation_fails_whole_answer_without_repair(self):
        data = answer(citation(), citation(document_number="invented"))
        before = data.model_dump()
        with self.assertRaisesRegex(CitationVerificationError, "citation 2"):
            self.verifier.verify(data, self.context)
        self.assertEqual(data.model_dump(), before)
        self.assertEqual(self.llm.prompts, [])

    def test_absent_citations_and_empty_context_are_rejected(self):
        empty = LegalContext(query="Câu hỏi", context_text="")
        for data, evidence in ((answer(), self.context), (self.answer, empty)):
            with self.subTest(data=data), self.assertRaises(CitationVerificationError):
                self.verifier.verify(data, evidence)
        self.assertEqual(self.llm.prompts, [])

    def test_context_ids_must_describe_retained_sources(self):
        for identifiers in ([], ["invented"], ["doc-a", "doc-a"], ["doc-a", "invented"]):
            evidence = self.context.model_copy(deep=True)
            evidence.cited_document_ids = identifiers
            with self.subTest(identifiers=identifiers), self.assertRaises(CitationVerificationError):
                self.verifier.verify(self.answer, evidence)
        self.assertEqual(self.llm.prompts, [])

    def test_duplicate_or_conflicting_context_sources_are_rejected(self):
        duplicate = self.context.model_copy(deep=True)
        duplicate.chunks.append(duplicate.chunks[0].model_copy(deep=True))
        conflicting = self.context.model_copy(deep=True)
        conflicting.chunks[0].metadata["document_id"] = "different"
        for evidence in (duplicate, conflicting):
            with self.subTest(evidence=evidence), self.assertRaises(CitationVerificationError):
                self.verifier.verify(self.answer, evidence)
        self.assertEqual(self.llm.prompts, [])

    def test_hidden_source_in_chunks_cannot_support_a_citation(self):
        evidence = self.context.model_copy(deep=True)
        evidence.context_text = "Không chứa nội dung nguồn"
        with self.assertRaises(CitationVerificationError):
            self.verifier.verify(self.answer, evidence)
        self.assertEqual(self.llm.prompts, [])

    def test_real_quote_does_not_override_negative_claim_verdict(self):
        llm = FixtureLLM('{"is_supported":false,"reason":"Bỏ qua điều kiện áp dụng"}')
        data = answer(citation(), text="Mọi người đều được nhận hỗ trợ vô điều kiện.")
        with self.assertRaisesRegex(CitationVerificationError, "Bỏ qua điều kiện"):
            CitationVerifier(llm).verify(data, self.context)
        self.assertEqual(len(llm.prompts), 1)

    def test_llm_receives_full_cited_sources_without_uncited_sources_or_confidence(self):
        cited = source(content=f"{_QUOTE}\nNgoại lệ giả lập cần xét.")
        uncited = source("other", document_id="doc-other", content="Nguồn không được trích dẫn")
        evidence = context(cited, uncited)
        self.verifier.verify(self.answer, evidence)
        payload = json.loads(self.llm.prompts[0].split("untrusted data:\n", 1)[1])
        self.assertEqual(payload["query"], evidence.query)
        self.assertEqual(payload["answer"], self.answer.answer)
        self.assertEqual(payload["disclaimer"], self.answer.disclaimer)
        self.assertEqual([item["chunk_id"] for item in payload["sources"]], ["a"])
        self.assertEqual(payload["sources"][0]["content"], cited.content)
        self.assertEqual(payload["sources"][0]["metadata"], {
            key: cited.metadata[key] for key in ("document_number", "article", "clause", "point")
        })
        self.assertNotIn("citations", payload)  # Quotes were already matched; full sources appear once.
        self.assertNotIn("confidence", payload)
        self.assertNotIn("score", payload["sources"][0])

    def test_multiple_matches_and_duplicate_citations_do_not_duplicate_source_payload(self):
        evidence = context(source(), source("b"))
        self.verifier.verify(answer(citation(), citation()), evidence)
        payload = json.loads(self.llm.prompts[0].split("untrusted data:\n", 1)[1])
        self.assertEqual([item["chunk_id"] for item in payload["sources"]], ["a", "b"])
        self.assertEqual(len(self.llm.prompts), 1)

    def test_invalid_or_incomplete_llm_verdict_is_a_verification_failure(self):
        for response in (
            "not json", "[]", "{}", '{"is_supported":true}',
            '{"is_supported":"true","reason":"fixture"}',
            '{"is_supported":1,"reason":"fixture"}',
            '{"is_supported":true,"reason":" "}',
            '{"is_supported":true,"reason":"fixture","extra":true}',
        ):
            with self.subTest(response=response), self.assertRaises(CitationVerificationError) as caught:
                CitationVerifier(FixtureLLM(response)).verify(self.answer, self.context)
            self.assertIsNotNone(caught.exception.__cause__)

    def test_provider_error_is_preserved_as_cause(self):
        failure = TimeoutError("fixture provider timeout")
        with self.assertRaises(CitationVerificationError) as caught:
            CitationVerifier(FixtureLLM(error=failure)).verify(self.answer, self.context)
        self.assertIs(caught.exception.__cause__, failure)

    def test_mutated_nested_citation_is_revalidated_before_llm(self):
        self.answer.citations.append({"document_id": "missing fields"})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with self.assertRaises(ValidationError):
                self.verifier.verify(self.answer, self.context)
        self.assertEqual(self.llm.prompts, [])

    def test_context_builder_budget_excludes_a_previously_retrieved_citation(self):
        kept = source("kept", document_id="doc-kept", content="Nguồn ngắn")
        excluded = source(content="Nội dung dài " * 1000 + _QUOTE)
        evidence = LegalContextBuilder(
            token_counter=len, settings=ContextSettings(max_context_tokens=1000),
        ).build(ContextBuilderRequest(
            original_query="Câu hỏi", retrieval_result=RetrievalResult(query="query", results=[kept, excluded]),
        ))
        with self.assertRaises(CitationVerificationError):
            self.verifier.verify(self.answer, evidence)
        self.assertEqual(self.llm.prompts, [])

    def test_bm25_context_and_verifier_integration(self):
        hits = BM25Retriever([source()]).search(RetrievalRequest(query="hỗ trợ"))
        evidence = context(*hits)
        verified = self.verifier.verify(self.answer, evidence)
        self.assertEqual(verified, self.answer)
        self.assertEqual(len(self.llm.prompts), 1)


if __name__ == "__main__":
    unittest.main()
