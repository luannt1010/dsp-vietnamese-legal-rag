"""Regressions from live multi-topic failures: filters, evidence budgets and retries."""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from core.config.settings import EmbeddingSettings
from core.deadline import request_deadline
from core.exceptions import ConfigurationError, EmbeddingError, LLMError
from core.schemas import QueryRequest, RetrievalEvaluationRequest, RetrievalResult, RetrievedChunk
from src.evaluation import RetrievalEvaluator
from src.infrastructure.embedding import OllamaEmbedding
from src.infrastructure.ollama_client import OllamaClient
from src.query_understanding import QueryAnalyzer
from src.query_understanding.query_analyzer import query_response_schema


def analysis_llm():
    return Mock(generate=Mock(return_value=json.dumps({
        "rewritten_query": "Nghĩa vụ của người sản xuất", "intent": "legal_lookup",
        "metadata": {"legal_domain": "Chuyen_giao_cong_nghe", "document_type": []},
    })))


def test_agent_cannot_invent_a_hard_filter_or_empty_list_for_the_query():
    vocabulary = {
        "document_type": ["Luật", "Nghị định"],
        "legal_domain": ["Chat_luong_san_pham_hang_hoa", "Chuyen_giao_cong_nghe"],
    }
    analyzer = QueryAnalyzer(analysis_llm(), metadata_vocabulary=vocabulary)
    result = analyzer.analyze(QueryRequest(query="Người sản xuất có nghĩa vụ gì về chất lượng sản phẩm, hàng hóa?"))
    assert result.metadata == {"legal_domain": ["Chat_luong_san_pham_hang_hoa"]}
    unknown = analyzer.analyze(QueryRequest(query="Người bán phải làm gì khi hàng lỗi?"))
    assert unknown.metadata == {}
    assert "metadata" not in query_response_schema()["properties"]
    assert "original_query" not in query_response_schema()["properties"]


def test_corpus_vocabulary_is_snapshotted_and_original_query_controls_filter():
    vocabulary = {"document_type": ["Luật"], "legal_domain": ["Giao_thong_duong_thuy_noi_dia"]}
    analyzer = QueryAnalyzer(analysis_llm(), metadata_vocabulary=vocabulary)
    vocabulary["document_type"].clear()
    result = analyzer.analyze(QueryRequest(query="Theo Luật Giao thông đường thủy nội địa, điều kiện là gì?"))
    assert result.metadata == {"document_type": ["Luật"], "legal_domain": ["Giao_thong_duong_thuy_noi_dia"]}


def test_generic_phap_luat_does_not_exclude_decrees_or_circulars():
    analyzer = QueryAnalyzer(analysis_llm(), metadata_vocabulary={"document_type": ["Luật", "Nghị định"]})
    assert analyzer.analyze(QueryRequest(query="Pháp luật quy định điều kiện này thế nào?")).metadata == {}


def test_unsupported_embedding_provider_fails_before_http():
    with pytest.raises(ConfigurationError, match="unsupported embedding provider"):
        OllamaEmbedding(EmbeddingSettings(provider="openai", model="fixture", dimension=2))


def test_answer_prompts_are_validated_before_serving_queries(tmp_path):
    from src.generation.answer_generator import AnswerGenerator
    with pytest.raises(ConfigurationError, match="Cannot read"):
        AnswerGenerator(Mock(), prompts_dir=tmp_path)
    (tmp_path / "system.txt").write_text("System", encoding="utf-8")
    (tmp_path / "user.txt").write_text("{wrong_placeholder}", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="placeholders"):
        AnswerGenerator(Mock(), prompts_dir=tmp_path)
    with pytest.raises(ConfigurationError, match="version"):
        AnswerGenerator(Mock(), prompt_version="../outside")


def test_vector_construction_settings_change_index_but_query_settings_do_not(monkeypatch, tmp_path):
    import src.runtime as runtime
    from core.config import load_settings
    from core.schemas import LegalChunk, LegalMetadata
    from src.data_pipeline.preparation import PreparedCorpus
    from src.knowledge_graph import GraphBuilder
    settings = load_settings("configs/demo", environ={})
    settings = settings.model_copy(update={"database": settings.database.model_copy(update={
        "graph": settings.database.graph.model_copy(update={"backend": "in_memory"}),
    })})
    chunk = LegalChunk(chunk_id="c", document_id="d", content="fixture", embedding=[1, 0],
                       metadata=LegalMetadata(document_id="d", title="fixture", document_number="MOCK", document_type="law"))
    corpus = PreparedCorpus("fixture", [chunk], [], GraphBuilder().build([chunk], [], []), {}, tmp_path)
    constructor = Mock()
    monkeypatch.setattr(runtime, "PgVectorStore", constructor)
    names = []
    for update in ({}, {"ef_search": 10}, {"hnsw_m": 24}):
        database = settings.database.model_copy(update={"vector": settings.database.vector.model_copy(update=update)})
        with runtime.open_stores(settings.model_copy(update={"database": database}), corpus):
            names.append(constructor.call_args.kwargs["table_name"])
    assert names[0] == names[1] and names[0] != names[2]


def test_feedback_schema_exposes_actual_strategy_caps_and_disallows_empty_changes():
    from core.config.settings import RetrievalSettings
    from src.evaluation.response_schema import evaluation_response_schema, _Change, _Continue
    settings = RetrievalSettings(max_top_k=7, max_candidate_k=30)
    schema = evaluation_response_schema(settings)
    change = schema["$defs"]["_Change"]["properties"]["strategy_override"]
    assert change["minProperties"] == 1 and change["required"] == []
    assert change["properties"]["top_k"]["maximum"] == 7
    assert change["properties"]["candidate_k"]["maximum"] == 30
    base = {"is_relevant": True, "confidence": 0.5, "reason": "fixture"}
    with pytest.raises(ValueError):
        _Change(**base, is_sufficient=False, next_action="change_strategy", strategy_override={})
    with pytest.raises(ValueError):
        _Continue(**base, is_sufficient=True, next_action="continue", strategy_override={"top_k": 7})


def test_evaluator_preserves_full_law_text_without_index_provenance_or_dangling_edges():
    text = "Đủ điều kiện thì áp dụng.\nNgoại lệ không được bỏ qua."
    hit = RetrievedChunk(
        chunk_id="source-a", document_id="law-a", content=text, score=-20, retrieval_method="cross_encoder",
        metadata={"document_number": "MOCK-01", "article": "Điều 1", "status": "unknown",
                  "source_url": "https://example.test/" + "x" * 20000, "source_revision": "opaque" * 1000},
    )
    result = RetrievalResult(query="điều kiện", results=[hit], relations=[{
        "source_document_id": "law-a", "target_document_id": "outside", "relation_type": "RELATED_TO",
        "evidence_chunk_ids": ["outside" + "x" * 20000],
    }])
    before = result.model_dump()
    llm = Mock(generate=Mock(return_value='{"is_relevant":true,"is_sufficient":true,"confidence":0.9,"next_action":"continue","reason":"fixture"}'))
    RetrievalEvaluator(llm).evaluate(RetrievalEvaluationRequest(original_query="điều kiện?", current_query="điều kiện?", retrieval_result=result))
    prompt = llm.generate.call_args.args[0]
    payload = json.loads(prompt.split("untrusted data:\n", 1)[1])
    evidence = payload["retrieval_result"]
    assert evidence["results"][0]["content"] == text
    assert evidence["relations"] == []
    assert "source_url" not in prompt and "source_revision" not in prompt and "-20" not in prompt
    assert len(prompt) < 5000
    assert result.model_dump() == before


@pytest.mark.parametrize("device, options", [("cpu", {"num_gpu": 0}), ("auto", None), ("cuda", {"num_gpu": -1})])
def test_embedding_device_is_passed_to_ollama_without_switching_model(device, options):
    embedding = OllamaEmbedding(EmbeddingSettings(provider="ollama", model="fixture", dimension=2, device=device))
    embedding._client = Mock()
    embedding._client.post.return_value = {"embeddings": [[1, 0]]}
    assert embedding.embed_query("query") == [1, 0]
    payload = embedding._client.post.call_args.args[1]
    assert payload.get("options") == options
    assert payload["model"] == "fixture" and payload["truncate"] is False


def response(status=200, data=None):
    value = Mock(status_code=status)
    if status >= 400:
        value.raise_for_status.side_effect = requests.HTTPError("provider detail", response=value)
    value.json.return_value = data if data is not None else {"embeddings": [[1, 0]]}
    return value


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_temporary_provider_errors_retry_within_the_same_budget(status):
    client = OllamaClient("http://fixture", timeout_s=30, max_retries=1, backoff_s=0)
    with patch("src.infrastructure.ollama_client.requests.post", side_effect=[response(status), response()]) as post:
        assert client.post("/api/embed", {}, error_type=EmbeddingError)["embeddings"] == [[1, 0]]
    assert post.call_count == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_provider_errors_are_not_retried(status):
    client = OllamaClient("http://fixture", timeout_s=30, max_retries=3, backoff_s=0)
    with patch("src.infrastructure.ollama_client.requests.post", return_value=response(status)) as post:
        with pytest.raises(EmbeddingError):
            client.post("/api/embed", {}, error_type=EmbeddingError)
    post.assert_called_once()


def test_bad_provider_json_is_not_retried():
    bad = response()
    bad.json.side_effect = ValueError("invalid json")
    with patch("src.infrastructure.ollama_client.requests.post", return_value=bad) as post:
        with pytest.raises(LLMError):
            OllamaClient("http://fixture", timeout_s=10, max_retries=2).post("/api/chat", {})
    post.assert_called_once()


def test_http_retry_cannot_extend_parent_deadline():
    clock = [0.0]
    def fail(*args, **kwargs):
        clock[0] = 1.9
        return response(503)
    with patch("core.deadline.monotonic", side_effect=lambda: clock[0]):
        with request_deadline(2):
            with patch("src.infrastructure.ollama_client.requests.post", side_effect=fail) as post:
                with patch("src.infrastructure.ollama_client.time.sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
                    with pytest.raises(TimeoutError):
                        OllamaClient("http://fixture", timeout_s=30, max_retries=2).post("/api/embed", {})
            post.assert_called_once()
