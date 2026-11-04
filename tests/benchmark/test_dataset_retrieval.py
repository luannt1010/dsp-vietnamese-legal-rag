import json

import pytest
from pydantic import ValidationError

from src.benchmark.config import BenchmarkConfig, Experiment
from src.benchmark.dataset import load_dataset
from src.benchmark.scoring.retrieval import EvidenceIndex, score_ranking
from src.retrieval.common import as_hit


def test_labels_are_independent_of_retrieved_results(question, chunks):
    relevant = EvidenceIndex(chunks).resolve(question)
    assert relevant == ["c00"]
    scores = score_ranking([as_hit(chunks[1]), as_hit(chunks[0])], relevant, [1, 5])
    assert scores["recall@1"] == 0
    assert scores["recall@5"] == 1
    assert scores["precision@5"] == 0.2
    assert scores["mrr@5"] == scores["map@5"] == 0.5


def test_unresolved_quote_is_not_silently_scored_as_missed(question, chunks):
    question.evidence[0].quote = "not in corpus"
    with pytest.raises(ValueError, match="GD001.*not resolved"):
        EvidenceIndex(chunks).resolve(question)


def test_wrong_location_does_not_match_identical_quote(question, chunks):
    question.evidence[0].article = "Điều 2"
    with pytest.raises(ValueError, match="not resolved"):
        EvidenceIndex(chunks).resolve(question)


def test_codified_article_mapping_is_explicit(question, chunks):
    for chunk in chunks:
        chunk.article = "Điều 13.1.LQ.1. Phạm vi điều chỉnh"
    with pytest.raises(ValueError, match="not resolved"):
        EvidenceIndex(chunks).resolve(question)
    question.evidence[0].corpus_article = "Điều 13.1.LQ.1"
    assert EvidenceIndex(chunks).resolve(question) == ["c00"]


def test_loader_rejects_duplicate_text_and_reports_line(tmp_path, question):
    path = tmp_path / "questions.jsonl"
    other = question.model_copy(update={"question_id": "GD002"})
    path.write_text(question.model_dump_json() + "\n" + other.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="questions.jsonl:2: duplicate"):
        load_dataset(path)


def test_labels_and_cutoffs_fail_validation(question):
    with pytest.raises(ValidationError):
        type(question).model_validate({**question.model_dump(), "answerable": "false"})
    with pytest.raises(ValidationError):
        type(question).model_validate({**question.model_dump(), "answerable": False})
    with pytest.raises(ValidationError):
        BenchmarkConfig(experiments=[Experiment(id="B0", use_graph=False, use_rerank=False)], ranking_k=5)


def test_topic_is_not_limited_to_demo_selection(question):
    values = {**question.model_dump(), "topic": "An ninh quốc gia"}
    assert type(question).model_validate(values).topic == "An ninh quốc gia"
    with pytest.raises(ValidationError):
        type(question).model_validate({**values, "topic": "   "})
