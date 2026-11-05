"""Context packing, traceability and integration; no model downloads/services."""

import json
import unittest
import warnings
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from core.config import load_settings
from core.config.settings import ContextSettings
from core.exceptions import InsufficientEvidenceError
from core.interfaces import BaseLegalContextBuilder
from core.schemas import ContextBuilderRequest, LegalChunk, RetrievedChunk, RetrievalRequest, RetrievalResult
from src.generation import LegalContextBuilder
from src.retrieval.sparse import BM25Retriever


def hit(identifier="a", *, document_id="doc-a", content="Nội dung nguồn giả lập.", **metadata):
    return RetrievedChunk(
        chunk_id=identifier, document_id=document_id, content=content,
        score=1.0, retrieval_method="fixture",
        metadata={"document_id": document_id, "document_number": "MOCK-01", **metadata},
    )


def request(*chunks, relations=None, query="Câu hỏi gốc?"):
    return ContextBuilderRequest(
        original_query=query,
        retrieval_result=RetrievalResult(
            query="câu hỏi viết lại", results=list(chunks), relations=relations or [],
            total_candidates=len(chunks),
        ),
    )


def builder(budget=100_000, *, token_counter=len):
    # Character count is a deterministic test fixture, not a production tokenizer.
    return LegalContextBuilder(
        token_counter=token_counter,
        settings=ContextSettings(max_context_tokens=budget, prompt_reserve_tokens=1024),
    )


def relation(**overrides):
    return {
        "source_document_id": "doc-a", "target_document_id": "doc-b",
        "relation_type": "amends", "evidence_chunk_ids": ["a", "b"], **overrides,
    }


class ContextBuilderTests(unittest.TestCase):
    def test_parent_expansion_never_evicts_another_retained_answer_source(self):
        early = hit("early", content="Đoạn truy xuất ngắn.", parent_id="large-parent")
        answer = hit("answer", document_id="answer-doc", content="Căn cứ trả lời phải được giữ.")
        parent = hit("large-parent", content="Đoạn truy xuất ngắn. " + "Thông tin phụ. " * 100)
        budget = len(builder().build(request(parent)).context_text)
        component = LegalContextBuilder(token_counter=len, settings=ContextSettings(max_context_tokens=budget),
                                        parent_lookup={parent.chunk_id: parent}.get)
        context = component.build(request(early, answer))
        self.assertEqual([source.chunk_id for source in context.chunks], ["early", "answer"])
        self.assertLessEqual(len(context.context_text), budget)

    def test_comparison_reserves_a_source_from_each_requested_document(self):
        first = hit("first", content="A" * 100, document_number="23/2004/QH11")
        extra = hit("extra", content="B" * 100, document_number="23/2004/QH11")
        second = hit("second", document_id="doc-b", content="C" * 100, document_number="110/2014/NĐ-CP")
        budget = len(builder().build(request(first, second)).context_text)
        context = builder(budget).build(request(first, extra, second, query="So sánh 23/2004/QH11 và 110/2014/NĐ-CP?"))
        self.assertEqual([source.chunk_id for source in context.chunks], ["first", "second"])

    def test_complete_article_merges_clause_hits_and_preserves_other_conditions(self):
        article = hit("article", content="Điều 1\n1. Điều kiện A.\n2. Điều kiện B.\n3. Ngoại lệ C.")
        first = hit("clause-a", content="1. Điều kiện A.", parent_id="article")
        second = hit("clause-b", content="2. Điều kiện B.", parent_id="article")
        leaves = [hit("leaf-a", content=first.content, parent_id="clause-a"),
                  hit("leaf-b", content=second.content, parent_id="clause-b")]
        parents = {chunk.chunk_id: chunk for chunk in (article, first, second)}
        component = LegalContextBuilder(token_counter=len, parent_lookup=parents.get)
        source_request = request(*leaves)
        before = source_request.model_dump()
        context = component.build(source_request)
        self.assertEqual([chunk.chunk_id for chunk in context.chunks], ["article"])
        self.assertIn("Ngoại lệ C.", context.context_text)
        self.assertEqual(source_request.model_dump(), before)

    def test_oversized_article_keeps_the_complete_clause_that_fits(self):
        article = hit("article", content="Quy định " * 300)
        clause = hit("clause", content="1. Điều kiện và ngoại lệ.", parent_id="article")
        leaf = hit("leaf", content="Điều kiện", parent_id="clause")
        parents = {chunk.chunk_id: chunk for chunk in (article, clause)}
        component = LegalContextBuilder(
            token_counter=len, settings=ContextSettings(max_context_tokens=500), parent_lookup=parents.get,
        )
        context = component.build(request(leaf))
        self.assertEqual([chunk.chunk_id for chunk in context.chunks], ["clause"])
        self.assertIn("ngoại lệ", context.context_text)

    def test_cyclic_parent_lookup_fails_without_looping(self):
        a = hit("a", parent_id="b")
        b = hit("b", parent_id="a")
        component = LegalContextBuilder(token_counter=len, parent_lookup={"a": a, "b": b}.get)
        with self.assertRaisesRegex(ValueError, "cycle"):
            component.build(request(hit("leaf", parent_id="a")))

    def test_contract_original_query_order_and_unique_documents(self):
        first = hit("a", article="Điều 1", clause="2", point="a", source_url="https://example.org/a")
        second = hit("b", content="Nguồn thứ hai", article="Điều 2")
        third = hit("c", document_id="doc-c")
        first.score, second.score = -10.0, 100.0
        component = builder()
        self.assertIsInstance(component, BaseLegalContextBuilder)
        context = component.build(request(first, second, third))
        self.assertEqual(context.query, "Câu hỏi gốc?")
        self.assertEqual(context.chunks, [first, second, third])
        self.assertEqual(context.cited_document_ids, ["doc-a", "doc-c"])
        self.assertLess(context.context_text.index(first.content), context.context_text.index(second.content))
        source = json.loads(context.context_text.splitlines()[1].removeprefix("Metadata: "))
        for key in ("document_number", "article", "clause", "point", "source_url"):
            self.assertEqual(source[key], first.metadata[key])
        self.assertEqual(source["chunk_id"], "a")
        self.assertNotIn('"score"', context.context_text)

    def test_content_stays_verbatim_and_unknown_metadata_is_preserved(self):
        content = "Điều 1. Quy định\n  1. Giữ nguyên dấu, xuống dòng.\n\n  2. Không sửa nội dung."
        source = hit(content=content, title='Tiêu đề\n"Nguồn 2"', custom={"nested": ["x"]})
        context = builder().build(request(source))
        self.assertTrue(context.context_text.endswith(content))
        self.assertEqual(context.chunks[0].content, content)
        header = json.loads(context.context_text.splitlines()[1].removeprefix("Metadata: "))
        self.assertEqual(header["title"], source.metadata["title"])
        self.assertEqual(context.chunks[0].metadata["custom"], {"nested": ["x"]})

    def test_missing_metadata_uses_ids_without_inventing_citation_or_status(self):
        source = hit()
        source.metadata = {}
        context = builder().build(request(source))
        header = json.loads(context.context_text.splitlines()[1].removeprefix("Metadata: "))
        self.assertEqual(header, {"document_id": "doc-a", "chunk_id": "a"})

    def test_reported_effectivity_is_visible_without_inference(self):
        source = hit(
            status="unknown", effective_date="2020-01-01", expiry_date=None,
            amended_by=["doc-new"], replaced_by=["doc-replacement"],
        )
        context = builder().build(request(source))
        header = json.loads(context.context_text.splitlines()[1].removeprefix("Metadata: "))
        self.assertEqual(header["status"], "unknown")
        self.assertEqual(header["effective_date"], "2020-01-01")
        self.assertEqual(header["amended_by"], ["doc-new"])
        self.assertNotIn("expiry_date", header)

    def test_empty_evidence_and_no_whole_chunk_fits_raise(self):
        for data in (request(), request(hit(content="x" * 1000))):
            with self.subTest(data=data), self.assertRaises(InsufficientEvidenceError):
                builder(1).build(data)

    def test_exact_boundary_includes_source_labels_and_metadata(self):
        data = request(hit())
        expected = builder().build(data)
        limit = len(expected.context_text)
        self.assertEqual(builder(limit).build(data), expected)
        with self.assertRaises(InsufficientEvidenceError):
            builder(limit - 1).build(data)

    def test_separators_count_and_output_contains_only_retained_sources(self):
        first, second = hit(), hit("b", document_id="doc-b", content="Source B")
        single = builder().build(request(first))
        combined = builder().build(request(first, second))
        context = builder(len(combined.context_text) - 1).build(request(first, second))
        self.assertEqual(context, single)
        self.assertEqual(context.cited_document_ids, ["doc-a"])
        self.assertNotIn("doc-b", context.context_text)

    def test_oversized_chunks_are_skipped_and_never_truncated(self):
        small = hit("small", document_id="small-doc", content="Nguồn nhỏ")
        huge = hit("huge", document_id="huge-doc", content="rất dài " * 1000)
        expected = builder().build(request(small))
        context = builder(len(expected.context_text)).build(request(huge, small))
        self.assertEqual(context, expected)
        self.assertEqual(context.chunks[0].content, small.content)
        self.assertNotIn("huge-doc", context.context_text)

    def test_counter_sees_concatenated_text_not_additive_estimates(self):
        first, second = hit(content="SOURCE_A"), hit("b", content="SOURCE_B")
        calls = []

        def counter(text):
            calls.append(text)
            return 101 if "SOURCE_A" in text and "SOURCE_B" in text else 1

        context = builder(100, token_counter=counter).build(request(first, second))
        self.assertEqual([source.chunk_id for source in context.chunks], ["a"])
        self.assertIn("SOURCE_A", calls[-1])
        self.assertIn("SOURCE_B", calls[-1])

    def test_prompt_reserve_is_separate_from_context_budget(self):
        data = request(hit())
        expected = builder().build(data)
        component = LegalContextBuilder(
            token_counter=len,
            settings=ContextSettings(max_context_tokens=len(expected.context_text), prompt_reserve_tokens=9999),
        )
        self.assertEqual(component.build(data), expected)

    def test_identical_sources_deduplicate_ignoring_score_and_method(self):
        source = hit()
        duplicate = source.model_copy(deep=True)
        duplicate.score, duplicate.retrieval_method = 1000.0, "other"
        context = builder().build(request(source, duplicate))
        self.assertEqual(len(context.chunks), 1)
        self.assertEqual(context.context_text.count("[Nguồn "), 1)
        self.assertEqual(context.chunks[0].score, source.score)

    def test_conflicting_identity_content_or_metadata_is_rejected(self):
        for changes in (
            {"document_id": "different"}, {"content": "Nội dung khác"},
            {"metadata": {"document_number": "DIFFERENT"}},
        ):
            duplicate = hit().model_copy(update=changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                builder().build(request(hit(), duplicate))

    def test_document_identity_mismatch_is_rejected(self):
        source = hit()
        source.metadata["document_id"] = "wrong-document"
        with self.assertRaises(ValueError):
            builder().build(request(source))

    def test_nested_mutation_is_revalidated(self):
        data = request(hit())
        data.retrieval_result.results[0].metadata["unsupported_value"] = object()
        with warnings.catch_warnings():
            # Pydantic versions differ in warnings emitted before revalidation.
            warnings.simplefilter("ignore", UserWarning)
            with self.assertRaises(ValidationError):
                builder().build(data)

    def test_input_output_and_separate_builds_do_not_share_metadata(self):
        data = request(hit(custom={"nested": ["original"]}))
        before = data.model_dump()
        component = builder()
        first = component.build(data)
        second = component.build(data)
        first.chunks[0].metadata["custom"]["nested"].append("changed")
        first.cited_document_ids.append("changed")
        self.assertEqual(data.model_dump(), before)
        self.assertEqual(second.chunks[0].metadata["custom"]["nested"], ["original"])
        self.assertEqual(second.cited_document_ids, ["doc-a"])

    def test_counter_failures_propagate_and_invalid_counts_are_rejected(self):
        for count in (True, 1.5, "10", -1, 0, None):
            with self.subTest(count=count), self.assertRaises(ValueError):
                builder(token_counter=lambda text: count).build(request(hit()))
        failure = RuntimeError("tokenizer unavailable")

        def broken_counter(text):
            raise failure

        with self.assertRaises(RuntimeError) as caught:
            builder(token_counter=broken_counter).build(request(hit()))
        self.assertIs(caught.exception, failure)
        with self.assertRaises(TypeError):
            LegalContextBuilder(token_counter=None)

    def test_shared_builder_has_no_cross_request_state(self):
        component = builder()
        inputs = [request(hit(str(i), document_id=f"doc-{i}"), query=f"Câu hỏi {i}") for i in range(20)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            outputs = list(pool.map(component.build, inputs))
        for index, context in enumerate(outputs):
            self.assertEqual(context.query, f"Câu hỏi {index}")
            self.assertEqual(context.cited_document_ids, [f"doc-{index}"])

    def test_mock_corpus_bm25_and_loaded_settings_integration(self):
        with open("data/chunks/mock_chunks.json", encoding="utf-8") as stream:
            chunks = [LegalChunk.model_validate(item) for item in json.load(stream)]
        hits = BM25Retriever(chunks).search(RetrievalRequest(query="lao động", top_k=3))
        self.assertTrue(hits)
        component = LegalContextBuilder(token_counter=len, settings=load_settings().context)
        context = component.build(request(*hits))
        self.assertLessEqual(len(context.context_text), load_settings().context.max_context_tokens)
        self.assertTrue(context.chunks)
        for chunk in context.chunks:
            self.assertIn(chunk.content, context.context_text)
            self.assertIn(chunk.chunk_id, context.context_text)


class ContextRelationsTests(unittest.TestCase):
    def setUp(self):
        self.sources = [hit(), hit("b", document_id="doc-b", content="Nguồn B")]

    def test_supported_relations_are_rendered_once_with_baseline_fields(self):
        edge = relation(extra="not part of baseline")
        reordered = relation(evidence_chunk_ids=["b", "a", "b"])
        context = builder().build(request(*self.sources, relations=[edge, reordered]))
        self.assertEqual(context.context_text.count("[Quan hệ văn bản]"), 1)
        rendered = json.loads(context.context_text.split("[Quan hệ văn bản]\n")[1])
        self.assertEqual(rendered, relation())
        self.assertNotIn("extra", rendered)

    def test_malformed_or_unretained_relations_are_omitted(self):
        invalid = [
            {}, relation(source_document_id="missing"), relation(target_document_id=["doc-b"]),
            relation(evidence_chunk_ids=[]), relation(evidence_chunk_ids=["a", "missing"]),
            relation(evidence_chunk_ids=[{}]), relation(relation_type=" "),
            relation(relation_type=None), relation(evidence_chunk_ids="a"),
        ]
        context = builder().build(request(*self.sources, relations=invalid))
        self.assertNotIn("[Quan hệ văn bản]", context.context_text)

    def test_relation_is_dropped_when_its_endpoint_is_cut_by_budget(self):
        single = builder().build(request(self.sources[0]))
        context = builder(len(single.context_text)).build(request(*self.sources, relations=[relation()]))
        self.assertEqual(context, single)

    def test_relations_cannot_displace_chunks_or_exceed_budget(self):
        data = request(*self.sources)
        sources_only = builder().build(data)
        with_edge = builder().build(request(*self.sources, relations=[relation()]))
        budget = len(with_edge.context_text)
        self.assertEqual(builder(budget).build(request(*self.sources, relations=[relation()])), with_edge)
        self.assertEqual(
            builder(budget - 1).build(request(*self.sources, relations=[relation()])), sources_only,
        )


if __name__ == "__main__":
    unittest.main()
