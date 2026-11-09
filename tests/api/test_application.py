"""Lifecycle ownership, settings precedence, probes, CORS and OpenAPI."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from core.config import Settings
from core.exceptions import ConfigurationError
from src.api.main import create_app
from src.api.settings import load_api_settings


def test_factory_does_not_load_runtime_before_startup(app, runtime_factory):
    assert runtime_factory.calls == []
    assert app.state.rag_service is None


def test_runtime_is_opened_once_without_ingestion_and_closed_on_shutdown(app, runtime_factory):
    with TestClient(app) as client:
        assert len(runtime_factory.calls) == 1
        assert runtime_factory.calls[0][0] == "enter"
        assert runtime_factory.calls[0][1].data_pipeline.auto_prepare is False
        assert app.state.settings.data_pipeline.auto_prepare is True  # Original settings remain unchanged.
        for _ in range(2):
            assert client.get("/api/v1/corpus").status_code == 200
            assert client.post("/api/v1/questions", json={"query": "Câu hỏi"}).status_code == 200
        service = app.state.rag_service
    assert [entry[0] for entry in runtime_factory.calls] == ["enter", "exit"]
    assert service.ready is False
    assert app.state.rag_service is None


def test_startup_failure_propagates_without_silent_mock(settings):
    @contextmanager
    def broken_factory(config):
        raise ConfigurationError("prepared index missing")
        yield  # pragma: no cover

    app = create_app(settings, runtime_factory=broken_factory)
    with pytest.raises(ConfigurationError, match="prepared index missing"), TestClient(app):
        pass
    assert app.state.rag_service is None


def test_runtime_closed_when_service_initialization_fails(app, runtime, runtime_factory):
    runtime.corpus.manifest = {}
    with pytest.raises(KeyError), TestClient(app):
        pass
    assert [entry[0] for entry in runtime_factory.calls] == ["enter", "exit"]
    assert app.state.rag_service is None


def test_liveness_independent_from_runtime_readiness(app):
    # Deliberately skip lifespan to simulate a service that is not ready.
    client = TestClient(app)
    assert client.get("/health/live").json() == {"status": "alive"}
    for path in ("/health/ready", "/api/v1/corpus"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_not_ready"
    assert client.post("/api/v1/questions", json={"query": "Câu hỏi"}).status_code == 503


def test_corpus_is_snapshot_identity_not_settings_or_paths(client, runtime):
    response = client.get("/api/v1/corpus")
    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == "fixed-snapshot"
    assert body["revision"] != "main"
    assert body["topics"] == ["Giáo dục, đào tạo"]
    assert body["document_count"] == 1
    assert body["chunk_count"] == 1
    assert body["parent_chunk_count"] == 0
    assert "unused-fixture-path" not in response.text
    assert "password" not in response.text
    # GET uses the cached summary, without rescanning corpus.
    runtime.corpus.chunks = None
    assert client.get("/api/v1/corpus").json() == body


def test_cors_allows_only_configured_origin_and_exposes_correlation(client):
    preflight = client.options("/api/v1/questions", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
    response = client.post("/api/v1/questions", json={"query": "Câu hỏi"},
                           headers={"Origin": "http://localhost:5173"})
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]
    rejected = client.options("/api/v1/questions", headers={
        "Origin": "https://unconfigured.example", "Access-Control-Request-Method": "POST",
    })
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


@pytest.mark.parametrize("method,path,status", [("get", "/unknown", 404), ("get", "/api/v1/questions", 405)])
def test_http_errors_use_the_same_envelope(client, method, path, status):
    response = getattr(client, method)(path)
    assert response.status_code == status
    assert response.json()["error"]["code"] == f"http_{status}"
    if status == 405:
        assert response.headers["allow"] == "POST"


def test_openapi_and_documentation_match_actual_response_types(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/questions"]["post"]
    for code in ("200", "502", "504"):
        assert operation["responses"][code]["content"]["application/json"]["schema"]["$ref"].endswith("QuestionResponse")
    for code in ("422", "503", "500"):
        assert operation["responses"][code]["content"]["application/json"]["schema"]["$ref"].endswith("ErrorResponse")
    assert schema["components"]["schemas"]["QuestionRequest"]["properties"]["query"]["maxLength"] == 4000


def test_api_settings_reuse_yaml_env_precedence_without_environment_mutation(monkeypatch, tmp_path):
    env_file = tmp_path / "credentials.env"
    env_file.write_text(
        "RAG__DATABASE__VECTOR__PASSWORD=file-secret\nRAG__API__PORT=8123\n", encoding="utf-8-sig",
    )
    monkeypatch.setenv("RAG_ENV_FILE", str(env_file))
    monkeypatch.setenv("RAG_CONFIG_DIR", "configs")
    monkeypatch.setenv("RAG__API__PORT", "8456")
    monkeypatch.delenv("RAG__DATABASE__VECTOR__PASSWORD", raising=False)
    settings = load_api_settings()
    assert settings.api.port == 8456
    assert settings.database.vector.password.get_secret_value() == "file-secret"
    import os
    assert "RAG__DATABASE__VECTOR__PASSWORD" not in os.environ


@pytest.mark.parametrize("value", [0, -1, True, "2"])
def test_capacity_configuration_rejects_invalid_values(settings, value):
    data = settings.model_dump()
    data["api"]["max_concurrent_requests"] = value
    with pytest.raises(ValueError):
        Settings.model_validate(data)
