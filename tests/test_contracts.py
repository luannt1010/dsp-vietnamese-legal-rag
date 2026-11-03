"""Contract checks that run with unittest or pytest, without external services."""

import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from typing import get_type_hints

from pydantic import ValidationError

from core import interfaces, schemas
from core.exceptions import InsufficientEvidenceError
from core.schemas import (
    AnswerGenerationRequest,
    ContextBuilderRequest,
    GraphRetrievalRequest,
    GraphRetrievalResult,
    LegalAnswer,
    LegalChunk,
    LegalContext,
    LegalDocument,
    LegalMetadata,
    MetadataFilterRequest,
    MetadataFilterResult,
    PipelineResult,
    QueryAnalysisResult,
    QueryRequest,
    RetrievalEvaluationRequest,
    RetrievalEvaluationResult,
    RetrievalRequest,
    RetrievalResult,
    RetrievalRound,
    RetrievalRouteRequest,
    RetrievalStrategy,
    RetrievedChunk,
)
from examples.contract_demo import MockAnswerGenerator, MockRetriever, build_mock_context


class SchemaContractTests(unittest.TestCase):
    def setUp(self):
        self.context = build_mock_context()
        self.hit = self.context.chunks[0]
        self.result = RetrievalResult(
            query=self.context.query, results=[self.hit], total_candidates=1,
        )

    def test_serialization_across_all_module_boundaries(self):
        """Wire payloads reconstruct typed nested models, including citations."""
        metadata = LegalMetadata(
            document_id="mock-document", title="Mock", document_number="MOCK-001",
            document_type="mock",
        )
        chunk = LegalChunk(
            chunk_id=self.hit.chunk_id, document_id=metadata.document_id,
            content=self.hit.content, metadata=metadata, embedding=[0.1, -0.2],
        )
        answer = MockAnswerGenerator().generate(
            AnswerGenerationRequest(context=self.context, query=self.context.query),
        )
        models = [
            QueryRequest(query=self.context.query),
            QueryAnalysisResult(
                original_query=self.context.query, rewritten_query="Query mới",
                intent="legal_explanation", metadata={"legal_domain": ["labor"]},
            ),
            MetadataFilterRequest(metadata={"document_type": ["law", "decree"]}),
            MetadataFilterResult(filters={"document_type": ["law"]}),
            metadata,
            LegalDocument(document_id=metadata.document_id, content=chunk.content, metadata=metadata),
            chunk,
            RetrievalRequest(query=self.context.query),
            self.hit,
            self.result,
            RetrievalRouteRequest(query=self.context.query, intent="legal_explanation"),
            RetrievalStrategy(reason="Baseline hybrid"),
            GraphRetrievalRequest(query=self.context.query),
            GraphRetrievalResult(
                results=[self.hit], related_document_ids=[self.hit.document_id],
                relations=[{
                    "source_document_id": "mock-source", "target_document_id": "mock-target",
                    "relation_type": "mock", "evidence_chunk_ids": [self.hit.chunk_id],
                }],
            ),
            RetrievalEvaluationRequest(
                original_query=self.context.query, current_query=self.context.query,
                retrieval_result=self.result,
            ),
            RetrievalEvaluationResult(
                is_relevant=True, is_sufficient=True, confidence=0.9,
                next_action="continue", reason="Có đủ căn cứ mẫu",
            ),
            ContextBuilderRequest(retrieval_result=self.result, original_query=self.context.query),
            self.context,
            AnswerGenerationRequest(context=self.context, query=self.context.query),
            answer.citations[0],
            answer,
            RetrievalRound(
                iteration=0, query=self.context.query,
                strategy=RetrievalStrategy(reason="Baseline hybrid"), retrieval_result=self.result,
            ),
            PipelineResult(answer=answer, status="completed"),
        ]
        public_models = {
            getattr(schemas, name) for name in schemas.__all__
            if name not in {"NextAction", "PipelineStatus"}
        }
        self.assertEqual({type(model) for model in models}, public_models)
        for model in models:
            with self.subTest(model=type(model).__name__):
                self.assertEqual(type(model).model_validate_json(model.model_dump_json()), model)
                self.assertTrue(type(model).model_json_schema())
        restored = LegalAnswer.model_validate_json(answer.model_dump_json())
        citation = restored.citations[0]
        self.assertEqual(citation.document_id, self.hit.document_id)
        self.assertIn(citation.quoted_text, self.hit.content)

    def test_mutable_defaults_are_isolated(self):
        first = RetrievalResult(query="a")
        second = RetrievalResult(query="b")
        first.results.append(self.hit)
        first.relations.append({"relation_type": "mock"})
        self.assertEqual(second.results, [])
        self.assertEqual(second.relations, [])
        metadata_a = MetadataFilterRequest()
        metadata_b = MetadataFilterRequest()
        metadata_a.metadata["document_type"] = ["law"]
        self.assertEqual(metadata_b.metadata, {})

    def test_typo_and_non_json_metadata_are_rejected(self):
        with self.assertRaises(ValidationError):
            RetrievalRequest(query="a", topk=10)
        with self.assertRaises(ValidationError):
            QueryAnalysisResult(
                original_query="a", rewritten_query="b", intent="test",
                metadata={"provider_object": object()},
            )

    def test_blank_required_text_is_rejected(self):
        for payload in ("", "   ", "\n\t"):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                QueryRequest(query=payload)
        self.assertEqual(QueryRequest(query="  Câu hỏi  ").query, "Câu hỏi")

    def test_retrieval_limits(self):
        for changes in (
            {"top_k": 0}, {"top_k": -1}, {"top_k": True}, {"top_k": 1.5},
            {"candidate_k": 0}, {"top_k": 21, "candidate_k": 20},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                RetrievalRequest(query="a", **changes)
        for depth in (0, -1, True):
            with self.subTest(depth=depth), self.assertRaises(ValidationError):
                GraphRetrievalRequest(query="a", max_depth=depth)

    def test_scores_are_not_confidence(self):
        for score in (-10.0, 42.0):
            payload = self.hit.model_dump()
            payload["score"] = score
            self.assertEqual(RetrievedChunk.model_validate(payload).score, score)
        for score in (float("nan"), float("inf"), float("-inf")):
            payload = self.hit.model_dump()
            payload["score"] = score
            with self.subTest(score=score), self.assertRaises(ValidationError):
                RetrievedChunk.model_validate(payload)
        for confidence in (-0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(confidence=confidence), self.assertRaises(ValidationError):
                LegalAnswer(answer="a", confidence=confidence)

    def test_chunk_document_identity_and_vectors(self):
        metadata = LegalMetadata(
            document_id="document-a", title="Mock", document_number="MOCK-001",
            document_type="mock",
        )
        for model, extra in ((LegalDocument, {}), (LegalChunk, {"chunk_id": "chunk-a"})):
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model(document_id="document-b", content="a", metadata=metadata, **extra)
        for embedding in ([], [float("nan")], [float("inf")]):
            with self.subTest(embedding=embedding), self.assertRaises(ValidationError):
                LegalChunk(
                    chunk_id="chunk-a", document_id="document-a", content="a",
                    metadata=metadata, embedding=embedding,
                )

    def test_empty_retrieval_is_valid_but_mock_generation_refuses_empty_context(self):
        empty = RetrievalResult(query="a")
        self.assertEqual(empty.results, [])
        self.assertEqual(empty.total_candidates, 0)
        self.assertEqual(GraphRetrievalResult().results, [])
        with self.assertRaises(InsufficientEvidenceError):
            MockAnswerGenerator().generate(AnswerGenerationRequest(
                query="a", context=LegalContext(query="a", context_text=""),
            ))

    def test_refinement_and_stop_actions(self):
        base = dict(is_relevant=True, is_sufficient=False, confidence=0.5, reason="Thiếu căn cứ")
        for extra in (
            {"next_action": "refine_query", "refined_query": "Query mới"},
            {"next_action": "change_strategy", "strategy_override": {"use_graph": True}},
            {"next_action": "stop"},
        ):
            with self.subTest(extra=extra):
                self.assertFalse(RetrievalEvaluationResult(**base, **extra).is_sufficient)
        for extra in (
            {"next_action": "continue"},
            {"next_action": "unknown"},
            {"next_action": "refine_query"},
            {"next_action": "refine_query", "refined_query": "  "},
            {"next_action": "change_strategy"},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                RetrievalEvaluationResult(**base, **extra)
        with self.assertRaises(ValidationError):
            RetrievalEvaluationResult(
                is_relevant=False, is_sufficient=True, confidence=0.5,
                next_action="continue", reason="Inconsistent evidence",
            )

    def test_iteration_budget_and_strategy_merge(self):
        base = dict(original_query="a", current_query="b", retrieval_result=self.result)
        self.assertEqual(
            RetrievalEvaluationRequest(**base, iteration=2, max_iterations=3).iteration, 2,
        )
        for extra in ({"iteration": -1}, {"iteration": 3}, {"max_iterations": 0}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                RetrievalEvaluationRequest(**base, **extra)
        strategy = RetrievalStrategy(reason="Baseline")
        merged = RetrievalStrategy.model_validate({**strategy.model_dump(), "use_graph": True})
        self.assertTrue(merged.use_graph)
        for override in (
            {"use_bm25": False, "use_vector": False, "use_graph": False},
            {"top_k": 21}, {"unknown_flag": True},
        ):
            with self.subTest(override=override), self.assertRaises(ValidationError):
                RetrievalStrategy.model_validate({**strategy.model_dump(), **override})


class AbstractInterfaceTests(unittest.TestCase):
    def test_interfaces_cannot_be_instantiated_without_implementation(self):
        for name in interfaces.__all__:
            contract = getattr(interfaces, name)
            with self.subTest(name=name):
                self.assertTrue(inspect.isabstract(contract))
                with self.assertRaises(TypeError):
                    contract()

    def test_section_four_method_signatures(self):
        contracts = (
            (interfaces.BaseQueryAnalyzer, "analyze", QueryRequest, QueryAnalysisResult),
            (interfaces.BaseMetadataFilter, "build_filters", MetadataFilterRequest, MetadataFilterResult),
            (interfaces.BaseRetriever, "search", RetrievalRequest, list[RetrievedChunk]),
            (interfaces.BaseRetrievalRouter, "route", RetrievalRouteRequest, RetrievalStrategy),
            (interfaces.BaseGraphRetriever, "search", GraphRetrievalRequest, GraphRetrievalResult),
            (interfaces.BaseEvaluator, "evaluate", RetrievalEvaluationRequest, RetrievalEvaluationResult),
            (interfaces.BaseLegalContextBuilder, "build", ContextBuilderRequest, LegalContext),
            (interfaces.BaseAnswerGenerator, "generate", AnswerGenerationRequest, LegalAnswer),
        )
        for contract, method_name, input_type, output_type in contracts:
            with self.subTest(contract=contract.__name__):
                method = getattr(contract, method_name)
                self.assertEqual(list(inspect.signature(method).parameters), ["self", "request"])
                self.assertEqual(get_type_hints(method), {"request": input_type, "return": output_type})
        method = interfaces.BaseCitationVerifier.verify
        self.assertEqual(list(inspect.signature(method).parameters), ["self", "answer", "context"])
        self.assertEqual(get_type_hints(method), {
            "answer": LegalAnswer, "context": LegalContext, "return": LegalAnswer,
        })

    def test_mocks_satisfy_public_contracts(self):
        self.assertIsInstance(MockRetriever(), interfaces.BaseRetriever)
        self.assertIsInstance(MockAnswerGenerator(), interfaces.BaseAnswerGenerator)
        self.assertFalse(inspect.isabstract(MockRetriever))
        self.assertFalse(inspect.isabstract(MockAnswerGenerator))

    def test_demo_outputs_vietnamese_json_on_windows_legacy_encoding(self):
        result = subprocess.run(
            [sys.executable, "-m", "examples.contract_demo"],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        payload = json.loads(result.stdout)
        answer = LegalAnswer.model_validate(payload)
        self.assertIn("giả lập", answer.answer)
        self.assertEqual(answer.citations[0].document_number, "MOCK-001")


if __name__ == "__main__":
    unittest.main()
