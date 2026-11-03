"""Topic selection, provenance and incremental preparation without network."""

import json
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from core.config import load_settings
from core.config.settings import DataPipelineSettings, DataSourceSettings, Settings
from core.exceptions import ConfigurationError, EmbeddingError
from src.data_pipeline import DataPipelineError
from src.data_pipeline.artifacts import write_json
from src.data_pipeline.embedding import EmbeddingPipeline
from src.data_pipeline.embedding.cache import EmbeddingCache
from src.data_pipeline.loaders.phapdien_dataset import PhapDienDataset
from src.data_pipeline.loaders.phapdien_loader import PhapDienLoader
from src.data_pipeline.preparation import PreparedCorpus, prepare_corpus
from src.data_pipeline.sources import load_source
from src.infrastructure.tokenization import ModelTokenizer
from src.knowledge_graph import GraphBuilder


def row(identifier="a", *, topic="labor", subject="employment", text="Nội dung nguồn."):
    return {
        "record_id": identifier, "topic_id": topic,
        "topic_title_vi": "Lao động" if topic == "labor" else "Dân sự",
        "subject_id": subject, "subject_title_vi": subject,
        "article_id": "Điều 1.1.LQ.1", "article_title": "Điều 1.1.LQ.1. Phạm vi",
        "content_text": text, "chapter_title": "Chương I",
        "source_note_text": "Luật số 01/2024/QH15 ngày 01/01/2024",
        "source_url": "https://example.test/" + identifier, "related_note_text": "",
    }


@pytest.fixture
def dataset(tmp_path):
    source = DataSourceSettings(type="huggingface", topics=("Lao động",), read_batch_size=1)
    config = DataPipelineSettings(source=source, index_dir=tmp_path)
    dataset = PhapDienDataset(source, tmp_path / "sources")
    files = [tmp_path / "documents-0.parquet", tmp_path / "documents-1.parquet"]
    pq.write_table(pa.Table.from_pylist([row(), row("b", text="Quy định khác.")]), files[0])
    pq.write_table(pa.Table.from_pylist([
        row("c", topic="civil", subject="marriage"), row("empty", text="  "),
    ]), files[1])
    write_json(dataset.directory / "snapshot.json", {"revision": "commit-a", "files": [str(path) for path in files]})
    dataset.open(download=False)
    return dataset, config


def test_catalog_and_selection_work_offline_across_shards(dataset, monkeypatch):
    source, _ = dataset
    monkeypatch.setattr("src.data_pipeline.loaders.phapdien_dataset.HfApi", Mock(side_effect=AssertionError("network")))
    assert {entry["id"] for entry in source.catalog()["topics"]} == {"labor", "civil"}
    for name in ("  LAO   ĐỘNG ", unicodedata.normalize("NFD", "Lao động"), "labor"):
        assert source.resolve("topics", (name,)) == ["labor"]
    assert [item["record_id"] for item in source.iter_rows(["labor"], ["employment", "marriage"])] == ["a", "b", "c", "empty"]


def test_unknown_or_ambiguous_name_is_not_fuzzy_matched(dataset):
    source, _ = dataset
    with pytest.raises(ConfigurationError, match="unknown or ambiguous"):
        source.resolve("topics", ("Lao dong",))
    catalog = source.catalog()
    catalog["subjects"].append({"id": "another", "title": "employment", "topic_id": "civil", "articles": 1})
    write_json(source.directory / f"catalog-{source.revision}.json", catalog)
    with pytest.raises(ConfigurationError, match="ambiguous"):
        source.resolve("subjects", ("employment",))
    assert source.resolve("subjects", ("another",)) == ["another"]


def test_source_selection_skips_dividers_and_preserves_identity_and_provenance(dataset, monkeypatch):
    _, config = dataset
    selected = load_source(config, build=True, progress=lambda _: None)
    assert len(selected.chunks) == 2
    assert len({chunk.chunk_id for chunk in selected.chunks}) == 2  # Same document/article labels.
    assert {chunk.metadata.source_record_id for chunk in selected.chunks} == {"a", "b"}
    assert all(chunk.metadata.source_revision == "commit-a" and chunk.metadata.topic_id == "labor" for chunk in selected.chunks)
    assert selected.chunks[0].metadata.source_url == "https://example.test/a"
    monkeypatch.setattr(PhapDienDataset, "iter_rows", Mock(side_effect=AssertionError("must reuse selection")))
    assert load_source(config, build=False, progress=lambda _: None).signature == selected.signature


def test_switching_selection_isolated_from_cached_topics(dataset):
    _, config = dataset
    labor = load_source(config, build=True, progress=lambda _: None)
    civil_config = config.model_copy(update={"source": config.source.model_copy(update={"topics": (), "subjects": ("marriage",)})})
    civil = load_source(civil_config, build=True, progress=lambda _: None)
    assert {chunk.metadata.source_record_id for chunk in civil.chunks} == {"c"}
    assert labor.signature != civil.signature
    assert civil.signature["topics"] == []


@pytest.mark.parametrize("build", [False, True])
def test_duplicate_record_with_conflicting_contents_is_rejected(dataset, build):
    source, config = dataset
    pq.write_table(pa.Table.from_pylist([row("a", text="Conflicting contents")]), source.files[1])
    if not build:
        with pytest.raises(ConfigurationError, match="selection is not prepared"):
            load_source(config, build=False, progress=lambda _: None)
    else:
        with pytest.raises(DataPipelineError, match="conflicting source record"):
            load_source(config, build=True, progress=lambda _: None)
        assert not list((source.directory / "selections").glob("*.json"))


def test_exact_duplicate_record_is_emitted_once(dataset):
    source, config = dataset
    pq.write_table(pa.Table.from_pylist([row()]), source.files[1])
    assert len(load_source(config, build=True, progress=lambda _: None).chunks) == 2


def test_snapshot_pins_revision_and_refresh_is_explicit(dataset, monkeypatch):
    source, _ = dataset
    info = Mock(return_value=SimpleNamespace(sha="commit-b", siblings=[SimpleNamespace(rfilename="documents.parquet")]))
    monkeypatch.setattr("src.data_pipeline.loaders.phapdien_dataset.HfApi", lambda: SimpleNamespace(dataset_info=info))
    download = Mock(return_value=str(source.files[0]))
    monkeypatch.setattr("src.data_pipeline.loaders.phapdien_dataset.hf_hub_download", download)
    source.open(download=True)
    info.assert_not_called()
    source.open(download=True, refresh=True, progress=lambda _: None)
    assert source.revision == "commit-b"
    assert download.call_args.kwargs["revision"] == "commit-b"


def test_download_failure_keeps_previous_snapshot(dataset, monkeypatch):
    source, _ = dataset
    before = (source.directory / "snapshot.json").read_bytes()
    monkeypatch.setattr("src.data_pipeline.loaders.phapdien_dataset.HfApi", Mock(side_effect=OSError("offline")))
    with pytest.raises(DataPipelineError, match="snapshot"):
        source.open(download=True, refresh=True)
    assert (source.directory / "snapshot.json").read_bytes() == before


def test_empty_selection_can_list_catalog_but_cannot_load_entire_corpus(tmp_path):
    config = DataPipelineSettings(source=DataSourceSettings(type="huggingface"), index_dir=tmp_path)
    with pytest.raises(ConfigurationError, match="at least one"):
        load_source(config, build=True)
    assert not (tmp_path / "sources").exists()
    assert DataSourceSettings().type == "json"


def test_embedding_cache_reuses_text_across_selection_and_respects_model(tmp_path):
    loader = PhapDienLoader()
    chunks = [loader.transform_row(row(identifier, text=text), dataset="fixture", revision="one")[1]
              for identifier, text in (("a", "Nguồn chung"), ("b", "Nguồn khác"), ("c", "Nguồn chung"))]
    embedder = Mock(dimension=2)
    embedder.embed_documents.side_effect = lambda texts: [[len(text), 1] for text in texts]
    cache = EmbeddingCache(tmp_path / "embedding.db", namespace="model-a", dimension=2)
    try:
        pipeline = EmbeddingPipeline(embedder, cache=cache, batch_size=2)
        first = pipeline.run(chunks[:1])
        second = pipeline.run(chunks)
        assert first[0].embedding == second[0].embedding == second[2].embedding
        assert sum(len(call.args[0]) for call in embedder.embed_documents.call_args_list) == 2
        assert all(chunk.embedding is None for chunk in chunks)
    finally:
        cache.close()
    other = EmbeddingCache(tmp_path / "embedding.db", namespace="model-b", dimension=2)
    try:
        assert other.get(chunks[0].content) is None
    finally:
        other.close()


def test_invalid_cached_vector_is_not_silently_used(tmp_path):
    cache = EmbeddingCache(tmp_path / "embedding.db", namespace="model", dimension=2)
    try:
        with pytest.raises(EmbeddingError):
            cache.put_many(["text"], [[1]])
        assert cache.get("text") is None
    finally:
        cache.close()


@pytest.fixture
def local_models(monkeypatch):
    tokenizer = ModelTokenizer.__new__(ModelTokenizer)
    tokenizer.tokenizer = Tokenizer(WordLevel({"[UNK]": 0}, unk_token="[UNK]"))
    tokenizer.tokenizer.pre_tokenizer = Whitespace()
    monkeypatch.setattr("src.data_pipeline.preparation.ModelTokenizer", lambda *args, **kwargs: tokenizer)
    monkeypatch.setattr("src.data_pipeline.preparation.OllamaClient.post", lambda *args, **kwargs: {"capabilities": ["embedding"], "modelfile": "model-a"})
    embedder = Mock(dimension=2)
    embedder.embed_documents.side_effect = lambda texts: [[len(text), 1] for text in texts]
    monkeypatch.setattr("src.data_pipeline.preparation.OllamaEmbedding", lambda _: embedder)
    return embedder


@pytest.mark.parametrize("strategy", ["legal", "hierarchical"])
def test_preparation_reuses_embeddings_when_topics_are_added(dataset, local_models, strategy):
    _, config = dataset
    embedder = local_models
    config = config.model_copy(update={"chunking": config.chunking.model_copy(update={"strategy": strategy, "tokenizer_model": "fixture"})})
    settings = Settings.model_validate({"embedding": {"model": "fixture", "dimension": 2}, "data_pipeline": config.model_dump()})
    first = prepare_corpus(settings, build=True, progress=lambda _: None)
    before = sum(len(call.args[0]) for call in embedder.embed_documents.call_args_list)
    source = config.source.model_copy(update={"subjects": ("marriage",)})
    extended = settings.model_copy(update={"data_pipeline": config.model_copy(update={"source": source})})
    second = prepare_corpus(extended, build=True, progress=lambda _: None)
    assert first.corpus_id != second.corpus_id
    assert {chunk.metadata.topic_id for chunk in first.chunks} == {"labor"}
    assert {chunk.metadata.topic_id for chunk in second.chunks} == {"labor", "civil"}
    assert sum(len(call.args[0]) for call in embedder.embed_documents.call_args_list) == before + 1
    again = prepare_corpus(extended, build=False, progress=lambda _: None)
    assert again.corpus_id == second.corpus_id
    assert sum(len(call.args[0]) for call in embedder.embed_documents.call_args_list) == before + 1


def test_fixed_document_windows_do_not_claim_the_first_articles_provenance(dataset, local_models):
    _, config = dataset
    config = config.model_copy(update={
        "source": config.source.model_copy(update={"topics": ("labor", "civil")}),
        "chunking": config.chunking.model_copy(update={"strategy": "fixed", "tokenizer_model": "fixture"}),
    })
    settings = Settings.model_validate({"embedding": {"model": "fixture", "dimension": 2}, "data_pipeline": config.model_dump()})
    corpus = prepare_corpus(settings, build=True, progress=lambda _: None)
    assert corpus.chunks
    for chunk in corpus.chunks:
        assert chunk.metadata.source_record_id is None
        assert chunk.metadata.source_url is None
        assert chunk.metadata.topic_id is None and chunk.metadata.subject_id is None
        assert set(chunk.metadata.legal_domain) == {"employment", "marriage"}


@pytest.mark.parametrize("auto_prepare, ready", [(True, False), (False, False), (True, True), (False, True)])
def test_runtime_prepares_missing_indexes_only_when_enabled(dataset, monkeypatch, auto_prepare, ready):
    import src.runtime as runtime

    _, config = dataset
    sources = load_source(config, build=True, progress=lambda _: None)
    graph = GraphBuilder().build(sources.chunks, [], [])
    prepared = PreparedCorpus("test", sources.chunks, [], graph, {}, config.index_dir)
    prepare = Mock(return_value=prepared)
    monkeypatch.setattr(runtime, "prepare_corpus", prepare)
    vector = Mock()
    vector.count.side_effect = [len(sources.chunks) if ready else 0, len(sources.chunks)]
    class VectorType:
        pass
    vector.__class__ = VectorType
    monkeypatch.setattr(runtime, "PgVectorStore", VectorType)
    @contextmanager
    def stores(*args):
        yield vector, Mock()
    monkeypatch.setattr(runtime, "open_stores", stores)
    monkeypatch.setattr(runtime, "ModelTokenizer", Mock(return_value=SimpleNamespace(count=len)))
    monkeypatch.setattr(runtime, "get_llm_instance", Mock())
    monkeypatch.setattr(runtime, "create_pipeline", Mock())
    monkeypatch.setattr(runtime, "OllamaEmbedding", Mock(return_value=Mock(dimension=1024)))
    vector.dimension = 1024
    settings = load_settings(Path(__file__).resolve().parents[1] / "configs/demo", environ={})
    settings = settings.model_copy(update={
        "data_pipeline": config.model_copy(update={"auto_prepare": auto_prepare}),
        "retrieval": settings.retrieval.model_copy(update={"use_rerank": False}),
    })
    if auto_prepare or ready:
        with runtime.open_runtime(settings, progress=lambda _: None):
            pass
        assert vector.upsert.call_count == (0 if ready else 1)
    else:
        with pytest.raises(ConfigurationError, match="indexes are incomplete"):
            with runtime.open_runtime(settings, progress=lambda _: None):
                pass
        vector.upsert.assert_not_called()
    assert prepare.call_args.kwargs["build"] is auto_prepare


def test_json_source_mode_remains_offline_and_uses_file_contents(tmp_path):
    _, chunk, _ = PhapDienLoader().transform_row(row())
    chunks, relations = tmp_path / "chunks.json", tmp_path / "relations.json"
    chunks.write_text(json.dumps([chunk.model_dump(mode="json")]), encoding="utf-8")
    relations.write_text("[]", encoding="utf-8")
    config = DataPipelineSettings(source_chunks_file=chunks, relations_file=relations)
    first = load_source(config, build=False, progress=lambda _: None)
    assert first.chunks[0].chunk_id == chunk.chunk_id
    relations.write_text('[{"source":"different"}]', encoding="utf-8")
    assert load_source(config, build=False, progress=lambda _: None).signature != first.signature


def test_display_article_code_ambiguous_even_within_one_document():
    loader = PhapDienLoader()
    a = loader.transform_row(row("a"), dataset="fixture")[1]
    b = loader.transform_row(row("b"), dataset="fixture")[1]
    other = row("c", topic="civil", subject="marriage")
    other["article_id"] = "Điều 2.1.LQ.1"
    other["article_title"] = "Điều 2.1.LQ.1. Nội dung"
    c = loader.transform_row(other, dataset="fixture")[1]
    graph = GraphBuilder().build([a, b, c], [], [{
        "source": c.chunk_id, "target": "Điều 1.1.LQ.1", "type": "RELATED_TO",
        "evidence_chunk_ids": [c.chunk_id], "evidence": "Một dẫn chiếu không đủ phân biệt bản ghi",
    }])
    assert graph.relations == [] and len(graph.unresolved) == 1


def test_failed_embedding_batch_can_resume_from_committed_cache(tmp_path):
    chunks = [PhapDienLoader().transform_row(row(str(i), text=f"Nguồn số {i}"))[1] for i in range(3)]
    embedder = Mock(dimension=2)
    embedder.embed_documents.side_effect = [[[1, 1], [2, 1]], EmbeddingError("offline")]
    cache = EmbeddingCache(tmp_path / "embedding.db", namespace="model", dimension=2)
    try:
        pipeline = EmbeddingPipeline(embedder, batch_size=2, cache=cache)
        with pytest.raises(EmbeddingError):
            pipeline.run(chunks)
        embedder.embed_documents.reset_mock()
        embedder.embed_documents.side_effect = lambda texts: [[3, 1] for _ in texts]
        result = pipeline.run(chunks)
        assert [chunk.embedding for chunk in result] == [[1, 1], [2, 1], [3, 1]]
        embedder.embed_documents.assert_called_once_with([chunks[-1].content])
    finally:
        cache.close()
