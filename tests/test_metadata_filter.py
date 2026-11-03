"""Portable metadata conditions and real local retrieval integration."""

import json
import unittest
import warnings
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from core.config.settings import RetrievalSettings
from core.filtering import FILTER_FIELDS, validate_filters
from core.interfaces import BaseEmbedding, BaseGraphRetriever, BaseLLM, BaseMetadataFilter
from core.schemas import (
    ContextBuilderRequest, GraphRetrievalResult, LegalChunk, LegalMetadata,
    MetadataFilterRequest, MetadataFilterResult, QueryRequest, RetrievalRequest, RetrievalRouteRequest,
)
from src.generation import LegalContextBuilder
from src.infrastructure.vector_store import InMemoryVectorStore
from src.preprocessing import MetadataFilter
from src.query_understanding import QueryAnalyzer
from src.retrieval.common import as_hit, matches_filters
from src.retrieval.dense import VectorRetriever
from src.retrieval.router import RetrievalRouter
from src.retrieval.service import RetrievalService
from src.retrieval.sparse import BM25Retriever


def build(metadata):
    return MetadataFilter().build_filters(MetadataFilterRequest(metadata=metadata))


def chunk(identifier, *, domain, document_type="law", vector=None):
    return LegalChunk(
        chunk_id=identifier, document_id=f"doc-{identifier}",
        content=f"Nội dung lao động giả lập {identifier}", article="Điều 1",
        metadata=LegalMetadata(
            document_id=f"doc-{identifier}", title="Văn bản giả lập",
            document_number=f"MOCK-{identifier}", document_type=document_type,
            legal_domain=[domain],
        ),
        embedding=vector or [1.0, 0.0],
    )


class FixtureLLM(BaseLLM):
    def generate(self, prompt):
        return json.dumps({
            "rewritten_query": "quy định lao động", "intent": "legal_lookup",
            "metadata": {"legal_domain": ["labor"], "document_type": ["law", "decree"]},
        })


class FixtureEmbedding(BaseEmbedding):
    @property
    def dimension(self):
        return 2

    def embed_query(self, text):
        return [1.0, 0.0]

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]


class FixtureGraph(BaseGraphRetriever):
    def __init__(self, chunks):
        self.result = GraphRetrievalResult(results=[as_hit(source) for source in chunks])

    def search(self, request):
        return self.result


class MetadataFilterTests(unittest.TestCase):
    def test_public_contract_and_spec_example(self):
        component = MetadataFilter()
        self.assertIsInstance(component, BaseMetadataFilter)
        metadata = {"legal_domain": ["labor"], "document_type": ["law", "decree"]}
        result = component.build_filters(MetadataFilterRequest(metadata=metadata))
        self.assertIsInstance(result, MetadataFilterResult)
        self.assertEqual(result.filters, metadata)
        self.assertEqual(result.applied_filters, ["legal_domain", "document_type"])
        self.assertEqual(MetadataFilterResult.model_validate_json(result.model_dump_json()), result)

    def test_empty_metadata_does_not_invent_conditions(self):
        result = MetadataFilter().build_filters(MetadataFilterRequest())
        self.assertEqual(result.filters, {})
        self.assertEqual(result.applied_filters, [])

    def test_all_document_location_and_source_fields_are_supported(self):
        metadata = LegalMetadata(
            document_id="doc-a", title="Giả lập", document_number="MOCK-01",
            document_type="law", issued_date="2020-01-01", effective_date="2020-02-01",
        ).model_dump(mode="json")
        metadata.update({
            "chapter": "I", "article": "Điều 1", "clause": "2", "point": "a",
            "parent_id": "parent", "source_url": "https://example.org/source",
        })
        result = build(metadata)
        self.assertEqual(result.filters, metadata)
        self.assertEqual(set(result.filters), FILTER_FIELDS)

    def test_values_order_and_explicit_empty_conditions_are_preserved(self):
        metadata = {
            "document_type": ["law", "law", "decree"], "legal_domain": [],
            "expiry_date": None, "title": "", "article": "  Điều 1  ",
        }
        result = build(metadata)
        self.assertEqual(result.filters, metadata)
        self.assertEqual(result.applied_filters, list(metadata))
        self.assertFalse(matches_filters({"legal_domain": ["labor"]}, {"legal_domain": []}))
        self.assertTrue(matches_filters({"expiry_date": None}, {"expiry_date": result.filters["expiry_date"]}))
        self.assertFalse(matches_filters({}, {"expiry_date": result.filters["expiry_date"]}))

    def test_flat_json_scalars_are_not_coerced_to_strings(self):
        for value in (None, "law", "", 1, 1.5, False, [None, "law", 1, 1.5, False]):
            with self.subTest(value=value):
                result = build({"document_type": value})
                self.assertEqual(result.filters["document_type"], value)
                self.assertIs(type(result.filters["document_type"]), type(value))

    def test_unknown_fields_fail_even_when_value_is_null_or_empty(self):
        for key in ("typo", "intent", "year", "document_numbers", "as_of_date", "$or", "legal_domain "):
            for value in (None, [], "labor"):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "unsupported"):
                    build({key: value})

    def test_nested_conditions_are_rejected_without_dropping_known_fields(self):
        for value in ({"eq": "law"}, {"gte": "2020-01-01"}, [["law"]], [{"eq": "law"}], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "scalar equality"):
                build({"legal_domain": ["labor"], "document_type": value})

    def test_non_finite_numbers_are_rejected_by_filter_and_retrieval_validation(self):
        for number in (float("nan"), float("inf"), float("-inf")):
            for value in (number, [number]):
                with self.subTest(value=value):
                    for operation in (build, validate_filters):
                        with self.assertRaisesRegex(ValueError, "finite"):
                            operation({"document_type": value})

    def test_status_and_dates_remain_explicit_equality_conditions(self):
        metadata = {"status": "unknown", "effective_date": "2020-01-01", "expiry_date": None}
        result = build(metadata)
        self.assertEqual(result.filters, metadata)
        self.assertFalse(matches_filters(
            {"status": "unknown", "effective_date": "2019-01-01", "expiry_date": None}, result.filters,
        ))
        self.assertNotIn("as_of_date", result.filters)

    def test_request_output_and_separate_calls_do_not_share_lists(self):
        data = MetadataFilterRequest(metadata={"legal_domain": ["labor"]})
        component = MetadataFilter()
        first = component.build_filters(data)
        second = component.build_filters(data)
        first.filters["legal_domain"].append("tax")
        first.applied_filters.append("tax")
        self.assertEqual(data.metadata, {"legal_domain": ["labor"]})
        self.assertEqual(second.filters, {"legal_domain": ["labor"]})
        self.assertEqual(second.applied_filters, ["legal_domain"])
        data.metadata["legal_domain"].append("civil")
        self.assertEqual(second.filters, {"legal_domain": ["labor"]})

    def test_nested_mutation_is_revalidated(self):
        data = MetadataFilterRequest(metadata={"legal_domain": ["labor"]})
        data.metadata["legal_domain"].append(object())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with self.assertRaises(ValidationError):
                MetadataFilter().build_filters(data)

    def test_shared_instance_has_no_cross_request_state(self):
        component = MetadataFilter()
        inputs = [MetadataFilterRequest(metadata={"document_id": f"doc-{i}"}) for i in range(20)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            outputs = list(pool.map(component.build_filters, inputs))
        for index, result in enumerate(outputs):
            self.assertEqual(result.filters, {"document_id": f"doc-{index}"})
            self.assertEqual(result.applied_filters, ["document_id"])


class MetadataFilterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.sources = [
            chunk("tax", domain="tax"), chunk("labor", domain="labor"),
            chunk("labor-decree", domain="labor", document_type="decree"),
        ]

    def test_query_analyzer_filter_router_retrieval_and_context(self):
        analysis = QueryAnalyzer(FixtureLLM()).analyze(QueryRequest(query="Quy định về lao động?"))
        conditions = build(analysis.metadata)
        settings = RetrievalSettings(use_vector=False, use_rerank=False)
        strategy = RetrievalRouter(settings).route(RetrievalRouteRequest(
            query=analysis.rewritten_query, intent=analysis.intent, filters=conditions.filters,
        ))
        result = RetrievalService(bm25_retriever=BM25Retriever(self.sources), settings=settings).retrieve(
            analysis.rewritten_query, conditions.filters, strategy,
        )
        self.assertEqual({source.chunk_id for source in result.results}, {"labor", "labor-decree"})
        context = LegalContextBuilder(token_counter=len).build(ContextBuilderRequest(
            retrieval_result=result, original_query=analysis.original_query,
        ))
        self.assertEqual(context.query, analysis.original_query)
        self.assertNotIn("doc-tax", context.cited_document_ids)
        self.assertEqual(len(context.chunks), 2)

    def test_bm25_and_vector_apply_filter_before_top_k(self):
        filters = build({"legal_domain": ["labor"], "document_type": "decree"}).filters
        retrievers = [
            BM25Retriever(self.sources),
            VectorRetriever(FixtureEmbedding(), InMemoryVectorStore(self.sources, dimension=2)),
        ]
        for retriever in retrievers:
            with self.subTest(retriever=type(retriever).__name__):
                hits = retriever.search(RetrievalRequest(query="lao động", filters=filters, top_k=1))
                self.assertEqual([source.chunk_id for source in hits], ["labor-decree"])

    def test_empty_list_cannot_broaden_any_retrieval_branch(self):
        filters = build({"legal_domain": []}).filters
        settings = RetrievalSettings(use_vector=True, use_graph=True, use_rerank=False)
        result = RetrievalService(
            bm25_retriever=BM25Retriever(self.sources),
            vector_retriever=VectorRetriever(
                FixtureEmbedding(), InMemoryVectorStore(self.sources, dimension=2),
            ),
            graph_retriever=FixtureGraph(self.sources), settings=settings,
        ).retrieve("lao động", filters)
        self.assertEqual(result.results, [])
        self.assertEqual(result.total_candidates, 0)

    def test_service_filters_graph_hits_before_merging(self):
        filters = build({"legal_domain": ["labor"], "document_type": "law"}).filters
        result = RetrievalService(
            graph_retriever=FixtureGraph(self.sources),
            settings=RetrievalSettings(use_bm25=False, use_vector=False, use_graph=True, use_rerank=False),
        ).retrieve("lao động", filters)
        self.assertEqual([source.chunk_id for source in result.results], ["labor"])

if __name__ == "__main__":
    unittest.main()
