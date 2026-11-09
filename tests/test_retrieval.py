"""Retrieval behavior and integration contracts; no model downloads or services."""

import sys
import types
import unicodedata
import unittest
from unittest.mock import Mock, patch

from core.config import load_settings
from core.config.settings import RetrievalSettings
from core.exceptions import EmbeddingError, RetrievalError
from core.interfaces import BaseEmbedding, BaseGraphRetriever, BaseRetriever
from core.schemas import (
    GraphRetrievalResult, LegalChunk, LegalContext, LegalMetadata, QueryAnalysisResult,
    RetrievalRequest, RetrievalResult, RetrievalRouteRequest, RetrievalStrategy, RetrievedChunk,
)
from src.infrastructure.vector_store import InMemoryVectorStore
from src.retrieval.aggregation import ResultAggregator
from src.retrieval.common import as_hit, matches_filters, validate_filters
from src.retrieval.dense import VectorRetriever
from src.retrieval.hybrid.hybrid import HybridRetriever
from src.retrieval.hybrid.rrf import reciprocal_rank_fusion
from src.retrieval.reranking import CrossEncoderReRanker
from src.retrieval.router import RetrievalRouter
from src.retrieval.service import RetrievalService
from src.retrieval.sparse import BM25Lib, BM25Retriever


def chunk(identifier="a", *, content=None, domain="labor", vector=None):
    return LegalChunk(
        chunk_id=identifier, document_id=f"doc-{identifier}",
        content=content or f"Nội dung giả lập {identifier}", article="1", clause="2",
        metadata=LegalMetadata(
            document_id=f"doc-{identifier}", title="Văn bản giả lập",
            document_number=f"MOCK-{identifier}", document_type="law", legal_domain=[domain],
        ),
        embedding=[1.0, 0.0, 0.0] if vector is None else vector,
    )


def hit(identifier, score=1.0, **kwargs):
    source = as_hit(chunk(identifier, **kwargs))
    source.score = score
    return source


class FixtureEmbedding(BaseEmbedding):
    def __init__(self, vector=None):
        self.vector = [1.0, 0.0, 0.0] if vector is None else vector

    @property
    def dimension(self):
        return 3

    def embed_query(self, text):
        return self.vector

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]


class FixtureRetriever(BaseRetriever):
    def __init__(self, hits):
        self.hits, self.requests = hits, []

    def search(self, request):
        self.requests.append(request)
        return [item for item in self.hits if matches_filters(item.metadata, request.filters)][:request.top_k]


class FixtureGraph(BaseGraphRetriever):
    def __init__(self, hits, relations=None):
        self.result = GraphRetrievalResult(results=hits, relations=relations or [])
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return self.result


class MetadataFilteringTests(unittest.TestCase):
    def test_flat_and_list_semantics(self):
        metadata = {"document_type": "law", "legal_domain": ["labor", "civil"], "expiry_date": None}
        for filters, expected in (
            ({}, True), ({"legal_domain": "labor"}, True),
            ({"legal_domain": ["tax", "civil"], "document_type": ["law", "decree"]}, True),
            ({"legal_domain": "tax"}, False), ({"legal_domain": []}, False),
            ({"issued_date": None}, False), ({"expiry_date": None}, True),
            ({"legal_domain": "labor", "document_type": "decree"}, False),
        ):
            with self.subTest(filters=filters):
                validate_filters(filters)
                self.assertEqual(matches_filters(metadata, filters), expected)

    def test_unsupported_fields_and_nested_operators(self):
        for filters in ({"typo": "a"}, {"effective_date": {"gte": "2020-01-01"}},
                        {"legal_domain": [["labor"]]}, {"$or": []}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                validate_filters(filters)

    def test_source_conversion_and_snapshot_isolation(self):
        source = chunk()
        converted = as_hit(source)
        self.assertEqual(converted.metadata["article"], "1")
        self.assertEqual(converted.metadata["clause"], "2")
        self.assertIn("parent_id", converted.metadata)
        converted.metadata["legal_domain"].append("tax")
        self.assertEqual(source.metadata.legal_domain, ["labor"])


class BM25Tests(unittest.TestCase):
    def setUp(self):
        self.chunks = [chunk("a", content="lao động tiền lương"),
                       chunk("b", content="thuế thu nhập", domain="tax"),
                       chunk("c", content="lao động hợp đồng")]
        self.retriever = BM25Retriever(self.chunks)

    def test_ranking_source_and_top_k_contract(self):
        request = RetrievalRequest(query="tiền lương", top_k=1, candidate_k=3)
        results = self.retriever.search(request)
        self.assertEqual([item.chunk_id for item in results], ["a"])
        self.assertEqual(results[0].retrieval_method, "bm25")
        self.assertEqual(results[0].metadata["document_number"], "MOCK-a")
        self.assertEqual(results[0].metadata["article"], "1")
        self.assertEqual(self.retriever.search(RetrievalRequest(query="không_có")), [])

    def test_filters_and_no_matches(self):
        for filters, ids in (({"legal_domain": ["labor"]}, ["a", "c"]),
                             ({"legal_domain": []}, []), ({"legal_domain": "tax"}, [])):
            results = self.retriever.search(RetrievalRequest(query="lao động", filters=filters))
            self.assertEqual([item.chunk_id for item in results], ids)

    def test_zero_or_negative_okapi_scores_still_match(self):
        single = BM25Retriever([chunk(content="lao động")])
        results = single.search(RetrievalRequest(query="lao động"))
        self.assertEqual(len(results), 1)
        self.assertLess(results[0].score, 0)

    def test_normalization_and_configured_tokenizer(self):
        results = self.retriever.search(RetrievalRequest(query=unicodedata.normalize("NFD", "TIỀN")))
        self.assertEqual(results[0].chunk_id, "a")
        words = BM25Retriever([chunk(content="(LƯƠNG),")], tokenizer="word")
        self.assertEqual(len(words.search(RetrievalRequest(query="lương"))), 1)
        sensitive = BM25Retriever([chunk(content="LƯƠNG")], lowercase=False)
        self.assertEqual(sensitive.search(RetrievalRequest(query="lương")), [])

    def test_empty_index_and_empty_tokens(self):
        for retriever in (BM25Retriever([]), BM25Retriever([chunk(content="!!!")], tokenizer="word")):
            self.assertEqual(retriever.search(RetrievalRequest(query="lao động")), [])
            with self.assertRaises(ValueError):
                retriever.search(RetrievalRequest(query="a", filters={"unknown": "x"}))

    def test_backwards_name_and_retrieval_result_input(self):
        retriever = BM25Lib(RetrievalResult(query="index", results=[hit("a")]))
        self.assertIsInstance(retriever, BaseRetriever)
        self.assertEqual(len(retriever.search(RetrievalRequest(query="giả lập"))), 1)

    def test_invalid_settings_duplicate_ids_and_dependency_error(self):
        for kwargs in ({"k1": 0}, {"k1": float("nan")}, {"b": 2}, {"tokenizer": "unknown"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BM25Retriever([], **kwargs)
        with self.assertRaises(ValueError):
            BM25Retriever([chunk(), chunk()])
        with patch.object(self.retriever.bm25, "get_scores", side_effect=RuntimeError("broken")):
            with self.assertRaises(RetrievalError) as raised:
                self.retriever.search(RetrievalRequest(query="lao động"))
            self.assertIsInstance(raised.exception.__cause__, RuntimeError)

    def test_output_mutation_does_not_modify_index(self):
        first = self.retriever.search(RetrievalRequest(query="lương"))[0]
        first.metadata["legal_domain"].append("tax")
        self.assertEqual(self.retriever.search(RetrievalRequest(query="lương"))[0].metadata["legal_domain"], ["labor"])


class VectorTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [chunk("a", vector=[1, 0, 0]), chunk("b", vector=[0, 1, 0], domain="tax"),
                       chunk("c", vector=[0.5, 0.5, 0])]
        self.store = InMemoryVectorStore(self.chunks, dimension=3)
        self.retriever = VectorRetriever(FixtureEmbedding(), self.store)

    def test_cosine_ordering_and_top_k(self):
        results = self.retriever.search(RetrievalRequest(query="q", top_k=2))
        self.assertEqual([item.chunk_id for item in results], ["a", "c"])
        self.assertAlmostEqual(results[0].score, 1)
        self.assertAlmostEqual(results[1].score, 2 ** -0.5)
        self.assertEqual(results[0].retrieval_method, "vector")

    def test_filters_applied_before_cutoff(self):
        results = self.retriever.search(RetrievalRequest(query="q", top_k=1, filters={"legal_domain": "tax"}))
        self.assertEqual([item.chunk_id for item in results], ["b"])
        self.assertEqual(self.retriever.search(RetrievalRequest(query="q", filters={"legal_domain": []})), [])

    def test_inner_product_and_l2_scores(self):
        for metric in ("inner_product", "l2"):
            store = InMemoryVectorStore(self.chunks, dimension=3, distance_metric=metric)
            results = store.search([1, 0, 0], filters={}, top_k=3)
            self.assertEqual([item.chunk_id for item in results], ["a", "c", "b"])
            if metric == "l2":
                self.assertEqual(results[0].score, 0)
                self.assertLess(results[1].score, 0)

    def test_invalid_embeddings_and_zero_norm(self):
        for vector in ([], [1], [float("inf"), 0, 0], [float("nan"), 0, 0],
                       [True, 0, 0], ["1", 0, 0], [0, 0, 0], None):
            with self.subTest(vector=vector), self.assertRaises(EmbeddingError):
                self.store.search(vector, filters={}, top_k=1)
        for vector in ([1], [float("nan"), 0, 0], [0, 0, 0]):
            with self.subTest(vector=vector), self.assertRaises(EmbeddingError):
                VectorRetriever(FixtureEmbedding(vector), self.store).search(RetrievalRequest(query="q"))
        source = chunk()
        source.embedding = None
        with self.assertRaises(EmbeddingError):
            InMemoryVectorStore([source], dimension=3)

    def test_dimension_settings_and_empty_store(self):
        with self.assertRaises(ValueError):
            VectorRetriever(FixtureEmbedding(), InMemoryVectorStore([], dimension=2))
        with self.assertRaises(ValueError):
            InMemoryVectorStore([], dimension=3, distance_metric="unknown")
        empty = VectorRetriever(FixtureEmbedding(), InMemoryVectorStore([], dimension=3))
        self.assertEqual(empty.search(RetrievalRequest(query="q")), [])
        with self.assertRaises(ValueError):
            empty.search(RetrievalRequest(query="q", filters={"unknown": "x"}))

    def test_provider_and_store_errors_do_not_become_no_hits(self):
        with patch.object(self.retriever.embedding, "embed_query", side_effect=RuntimeError("provider")):
            with self.assertRaises(EmbeddingError) as raised:
                self.retriever.search(RetrievalRequest(query="q"))
            self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        with patch.object(self.store, "search", side_effect=RuntimeError("database")):
            with self.assertRaises(RetrievalError) as raised:
                self.retriever.search(RetrievalRequest(query="q"))
            self.assertIsInstance(raised.exception.__cause__, RuntimeError)

    def test_filter_violating_backend_is_rejected(self):
        with patch.object(self.store, "search", return_value=[hit("b", domain="tax")]):
            with self.assertRaises(RetrievalError):
                self.retriever.search(RetrievalRequest(query="q", filters={"legal_domain": "labor"}))


class FusionAndHybridTests(unittest.TestCase):
    def test_rrf_uses_ranks_and_one_vote_per_branch(self):
        results = reciprocal_rank_fusion([
            [hit("a", 10000), hit("a", 9999), hit("b", -1000)],
            [hit("b", -99), hit("c", -100)],
        ])
        self.assertEqual([item.chunk_id for item in results], ["b", "a", "c"])
        self.assertAlmostEqual(results[0].score, 1 / 62 + 1 / 61)
        self.assertAlmostEqual(results[1].score, 1 / 61)
        self.assertEqual(results[0].retrieval_method, "rrf")

    def test_rrf_empty_ties_and_conflicting_sources(self):
        self.assertEqual(reciprocal_rank_fusion([[], []]), [])
        self.assertEqual([item.chunk_id for item in reciprocal_rank_fusion([[hit("a")], [hit("b")]])], ["a", "b"])
        with self.assertRaises(RetrievalError):
            reciprocal_rank_fusion([[hit("a")], [hit("a", content="conflicting")]])
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion([], rank_constant=0)

    def test_total_candidates_before_candidate_and_final_cuts(self):
        request = RetrievalRequest(query="q", top_k=1, candidate_k=2)
        result = ResultAggregator().aggregate(request, [[hit("a"), hit("b")], [hit("b"), hit("c")]])
        self.assertEqual(result.total_candidates, 3)
        self.assertEqual([item.chunk_id for item in result.results], ["b"])

    def test_hybrid_collects_candidate_k_per_branch_then_reranks(self):
        first = FixtureRetriever([hit("a"), hit("b")])
        second = FixtureRetriever([hit("b"), hit("c")])
        model = Mock()
        # RRF order b, a, c. The cross-encoder promotes c to the final result.
        model.predict.return_value = [0.1, 0.2, 0.9]
        hybrid = HybridRetriever(first, second, reranker=CrossEncoderReRanker(model=model))
        results = hybrid.search(RetrievalRequest(query="q", top_k=1, candidate_k=3))
        self.assertEqual(first.requests[0].top_k, 3)
        self.assertEqual(second.requests[0].top_k, 3)
        self.assertEqual(results[0].chunk_id, "c")
        self.assertEqual(results[0].retrieval_method, "cross_encoder")

    def test_empty_branch_and_branch_failure(self):
        hybrid = HybridRetriever(FixtureRetriever([]), FixtureRetriever([hit("a")]))
        self.assertEqual(len(hybrid.search(RetrievalRequest(query="q"))), 1)
        hybrid = HybridRetriever(FixtureRetriever([]))
        self.assertEqual(hybrid.search(RetrievalRequest(query="q")), [])
        with patch.object(hybrid.retrievers[0], "search", side_effect=RuntimeError("down")):
            with self.assertRaises(RetrievalError):
                hybrid.search(RetrievalRequest(query="q"))
        with self.assertRaises(ValueError):
            HybridRetriever()

    def test_reranker_cannot_inject_unretrieved_evidence(self):
        reranker = Mock()
        reranker.rerank.return_value = LegalContext(query="q", context_text="", chunks=[hit("foreign")])
        with self.assertRaises(RetrievalError):
            ResultAggregator(reranker=reranker).aggregate(
                RetrievalRequest(query="q"), [[hit("a")]], use_rerank=True,
            )


class CrossEncoderTests(unittest.TestCase):
    def setUp(self):
        self.analysis = QueryAnalysisResult(original_query="original", rewritten_query="rewritten", intent="test")
        self.context = LegalContext(query="original", context_text="old", chunks=[hit("a"), hit("b")])

    def test_reorders_without_mutating_input_and_rebuilds_context(self):
        before = self.context.model_dump()
        model = Mock()
        model.predict.return_value = [[0.1], [2.0]]
        result = CrossEncoderReRanker(model=model, batch_size=8).rerank(self.analysis, self.context, top_k=1)
        self.assertEqual(self.context.model_dump(), before)
        self.assertEqual([item.chunk_id for item in result.chunks], ["b"])
        self.assertEqual(result.context_text, result.chunks[0].content)
        self.assertEqual(result.cited_document_ids, ["doc-b"])
        self.assertEqual(model.predict.call_args.args[0][0][0], "rewritten")
        self.assertEqual(model.predict.call_args.kwargs["batch_size"], 8)

    def test_lazy_loading_once_and_empty_context_skips_model(self):
        factory = Mock()
        factory.return_value.predict.return_value = [0.1, 0.2]
        module = types.ModuleType("sentence_transformers")
        module.CrossEncoder = factory
        reranker = CrossEncoderReRanker("selected-model", revision="selected-revision")
        empty = LegalContext(query="q", context_text="")
        with patch.dict(sys.modules, {"sentence_transformers": module}):
            self.assertEqual(reranker.rerank(self.analysis, empty).chunks, [])
            factory.assert_not_called()
            reranker.rerank(self.analysis, self.context)
            reranker.rerank(self.analysis, self.context)
        factory.assert_called_once_with("selected-model", device=None, max_length=512, revision="selected-revision")

    def test_invalid_prediction_shapes_and_scores(self):
        for scores in ([0.1], [[0.1, 0.9], [0.9, 0.1]], [float("nan"), 1],
                       [float("inf"), 1], [True, 1], ["0.1", 1]):
            model = Mock()
            model.predict.return_value = scores
            with self.subTest(scores=scores), self.assertRaises(RetrievalError):
                CrossEncoderReRanker(model=model).rerank(self.analysis, self.context)

    def test_prediction_failure_and_configuration(self):
        model = Mock()
        model.predict.side_effect = RuntimeError("device failure")
        with self.assertRaises(RetrievalError) as raised:
            CrossEncoderReRanker(model=model).rerank(self.analysis, self.context)
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        with self.assertRaises(ValueError):
            CrossEncoderReRanker()
        with self.assertRaises(ValueError):
            CrossEncoderReRanker(model=model, batch_size=0)


class RouterAndServiceTests(unittest.TestCase):
    def test_router_respects_defaults_and_explicit_intent_policies(self):
        # Keep the policy fixture independent of the live profile's graph switch.
        settings = load_settings(environ={}).retrieval.model_copy(update={"use_graph": False})
        router = RetrievalRouter(settings, intent_overrides={"relationships": {"use_graph": True}})
        baseline = router.route(RetrievalRouteRequest(query="q", intent="unknown", entities=["a"]))
        self.assertFalse(baseline.use_graph)
        relation = router.route(RetrievalRouteRequest(query="q", intent="relationships"))
        self.assertTrue(relation.use_graph)
        self.assertIn("relationships", relation.reason)
        with self.assertRaises(ValueError):
            RetrievalRouter(settings, intent_overrides={"large": {"candidate_k": 101}})

    def test_service_merges_branches_filters_graph_and_passes_seeds(self):
        graph = FixtureGraph([hit("c"), hit("d", domain="tax")], relations=[
            {"source_document_id": "doc-a", "target_document_id": "doc-c", "relation_type": "related",
             "evidence_chunk_ids": ["c"]},
            {"source_document_id": "doc-a", "target_document_id": "doc-d", "relation_type": "related",
             "evidence_chunk_ids": ["d"]},
        ])
        service = RetrievalService(
            bm25_retriever=FixtureRetriever([hit("a"), hit("b")]),
            vector_retriever=FixtureRetriever([hit("b")]), graph_retriever=graph,
        )
        strategy = RetrievalStrategy(use_graph=True, use_rerank=False, top_k=1, candidate_k=2, reason="test")
        result = service.retrieve("q", {"legal_domain": "labor"}, strategy, entities=["entity"])
        self.assertEqual(result.total_candidates, 3)
        self.assertEqual([item.chunk_id for item in result.results], ["b"])
        self.assertEqual(result.relations, [])  # Evidence/endpoints left the final top-k.
        self.assertEqual(graph.requests[0].seed_document_ids, ["doc-a", "doc-b"])
        self.assertEqual(graph.requests[0].entities, ["entity"])
        self.assertEqual(graph.requests[0].max_depth, 2)
        all_hits = service.retrieve("q", {"legal_domain": "labor"}, strategy.model_copy(update={"top_k": 3, "candidate_k": 3}))
        self.assertEqual(len(all_hits.relations), 1)
        self.assertEqual(all_hits.relations[0]["target_document_id"], "doc-c")

    def test_graph_only_empty_results_and_failure(self):
        settings = RetrievalSettings(use_bm25=False, use_vector=False, use_graph=True, use_rerank=False)
        graph = FixtureGraph([])
        service = RetrievalService(graph_retriever=graph, settings=settings)
        self.assertEqual(service.retrieve("q").total_candidates, 0)
        self.assertEqual(graph.requests[0].seed_document_ids, [])
        with patch.object(graph, "search", side_effect=RuntimeError("offline")):
            with self.assertRaises(RetrievalError):
                service.retrieve("q")

    def test_missing_adapters_and_strategy_bounds_fail_before_calls(self):
        retriever = FixtureRetriever([hit("a")])
        service = RetrievalService(bm25_retriever=retriever)
        with self.assertRaises(ValueError):
            service.retrieve("q")
        self.assertEqual(retriever.requests, [])
        with self.assertRaises(ValueError):
            service.retrieve("q", strategy=RetrievalStrategy(top_k=21, candidate_k=30, reason="too large"))

    def test_real_sparse_dense_hybrid_integration(self):
        chunks = [chunk("a", content="lao động lương", vector=[1, 0, 0]),
                  chunk("b", content="thuế thu nhập", vector=[0, 1, 0], domain="tax")]
        settings = RetrievalSettings(use_rerank=False, top_k=1, candidate_k=2)
        service = RetrievalService(
            bm25_retriever=BM25Retriever(chunks),
            vector_retriever=VectorRetriever(FixtureEmbedding(), InMemoryVectorStore(chunks, dimension=3)),
            settings=settings,
        )
        result = service.retrieve("lao động", {"legal_domain": ["labor"]})
        self.assertEqual(result.total_candidates, 1)
        self.assertEqual(result.results[0].chunk_id, "a")
        self.assertEqual(RetrievalResult.model_validate_json(result.model_dump_json()), result)


if __name__ == "__main__":
    unittest.main()
