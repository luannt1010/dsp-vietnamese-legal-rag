"""Regressions for explicit-number lookup and cross-document scope."""

import json
from unittest.mock import Mock

import pytest

from core.exceptions import LLMError
from core.schemas import QueryRequest, RetrievalRequest, RetrievalEvaluationRequest, RetrievalResult, RetrievedChunk
from src.evaluation import RetrievalEvaluator
from src.query_understanding import QueryAnalyzer
from src.query_understanding.document_references import extract_document_numbers, names_provision
from src.retrieval.sparse import BM25Retriever
from src.retrieval.common import prioritize_context_sources


def analyzer(*, provision_vocabulary=None, **payload):
    response = {"rewritten_query": "phạm vi điều chỉnh", "intent": "lookup", **payload}
    return QueryAnalyzer(Mock(generate=Mock(return_value=json.dumps(response))), metadata_vocabulary={
        "document_number": ["23/2004/QH11", "110/2014/NĐ-CP"],
        "document_type": ["Luật"], "legal_domain": ["Giao_thong_duong_thuy_noi_dia"],
    }, provision_vocabulary=provision_vocabulary)


def source(number, identifier="a"):
    return RetrievedChunk(chunk_id=identifier, document_id=identifier, content="Phạm vi điều chỉnh.",
                          metadata={"document_number": number}, score=1, retrieval_method="fixture")


def test_number_only_question_filters_real_retrieval_without_an_llm_guess():
    analysis = analyzer().analyze(QueryRequest(query="Theo văn bản 23/2004/QH11, phạm vi điều chỉnh là gì?"))
    assert analysis.metadata == {"document_number": ["23/2004/QH11"]}
    hits = BM25Retriever([source("23/2004/QH11"), source("43/2019/QH14", "wrong")]).search(
        RetrievalRequest(query="phạm vi điều chỉnh", filters=analysis.metadata))
    assert [hit.document_id for hit in hits] == ["a"]


def test_comparison_keeps_both_documents_without_and_ing_law_or_domain_filters():
    query = "So sánh Luật Giao thông đường thủy nội địa 23/2004/QH11 với 110 / 2014 / nd-cp."
    analysis = analyzer().analyze(QueryRequest(query=query))
    assert analysis.metadata == {"document_number": ["23/2004/QH11", "110/2014/NĐ-CP"]}
    assert analysis.entities[:2] == analysis.metadata["document_number"]


def test_unknown_reference_is_not_dropped_from_a_comparison():
    analysis = analyzer().analyze(QueryRequest(query="So sánh 23/2004/QH11 và 999/2099/QH99?"))
    assert analysis.metadata["document_number"] == ["23/2004/QH11", "999/2099/QH99"]


@pytest.mark.parametrize("query, expected", [
    ("Theo 76/2018/NĐ-CP và 76/2018/ND-CP", ["76/2018/NĐ-CP"]),
    ("Văn bản 23/2004/QH11x", ["23/2004/QH11x"]),
    ("23/2004/QH11 - scope and applicability", ["23/2004/QH11"]),
    ("Ngày 01/02/2020, tỷ lệ 1/2 là bao nhiêu?", []),
    ("Quyết định 33/CP và thông tư 01/2006/TTLT-BGD", ["33/CP", "01/2006/TTLT-BGD"]),
])
def test_only_complete_legal_references_are_extracted(query, expected):
    assert extract_document_numbers(query) == expected


def test_invalid_entities_are_still_rejected_as_model_output():
    with pytest.raises(LLMError):
        analyzer(entities=None).analyze(QueryRequest(query="Theo 23/2004/QH11?"))


def test_missing_requested_document_cannot_be_approved_by_a_permissive_llm():
    llm = Mock()
    request = RetrievalEvaluationRequest(
        original_query="So sánh 23/2004/QH11 và 110/2014/NĐ-CP?", current_query="phạm vi điều chỉnh",
        retrieval_result=RetrievalResult(query="scope", results=[source("23/2004/QH11")]),
    )
    result = RetrievalEvaluator(llm).evaluate(request)
    assert not result.is_sufficient and result.next_action == "stop"
    assert "110/2014/NĐ-CP" in result.missing_information[0]
    llm.generate.assert_not_called()


def test_document_presence_alone_does_not_authorize_an_answer():
    llm = Mock(generate=Mock(return_value=json.dumps({
        "is_relevant": False, "is_sufficient": False, "confidence": 1,
        "next_action": "stop", "missing_information": ["Wrong provision"], "reason": "Wrong provision",
    })))
    result = RetrievalEvaluator(llm).evaluate(RetrievalEvaluationRequest(
        original_query="Theo 23/2004/QH11, điều kiện là gì?", current_query="điều kiện",
        retrieval_result=RetrievalResult(query="điều kiện", results=[source("23/2004/QH11")]),
    ))
    assert not result.is_sufficient
    llm.generate.assert_called_once()


def test_explicit_provision_heading_survives_context_cut_without_rewriting_scores():
    unrelated = source("07/2017/QH14", "contract")
    unrelated.metadata["article"] = "Điều 19.2.LQ.23. Nội dung hợp đồng chuyển giao công nghệ"
    requested = source("07/2017/QH14", "rights")
    requested.metadata["article"] = "Điều 19.2.LQ.7. Quyền chuyển giao công nghệ"
    hits = [unrelated, requested]
    selected = prioritize_context_sources(hits, 'Điều khoản “Quyền chuyển giao công nghệ” của 07/2017/QH14 quy định gì?')
    assert [hit.chunk_id for hit in selected[:1]] == ["rights"]
    assert [hit.chunk_id for hit in hits] == ["contract", "rights"]
    assert all(hit.score == 1 for hit in selected)


def test_corpus_provision_lookup_scopes_the_named_article_for_each_document():
    vocab = {"23/2004/QH11": ["Điều 14.3.LQ.1. Phạm vi điều chỉnh", "Điều 14.3.LQ.2. Đối tượng áp dụng"],
             "110/2014/NĐ-CP": ["Điều 14.3.NĐ.2.1. Phạm vi điều chỉnh"]}
    component = analyzer(provision_vocabulary=vocab)
    result = component.analyze(QueryRequest(query="Phạm vi điều chỉnh của 23/2004/QH11 khác gì so với 110/2014/NĐ-CP?"))
    assert result.metadata == {"document_number": ["23/2004/QH11", "110/2014/NĐ-CP"],
                               "article": [vocab["23/2004/QH11"][0], vocab["110/2014/NĐ-CP"][0]]}
    vocab["23/2004/QH11"].clear()
    assert component.analyze(QueryRequest(query="Phạm vi điều chỉnh của 23/2004/QH11?")).metadata["article"]


def test_a_title_for_only_one_side_does_not_exclude_the_other_document():
    component = analyzer(provision_vocabulary={"23/2004/QH11": ["Điều 14.3.LQ.1. Phạm vi điều chỉnh"]})
    result = component.analyze(QueryRequest(query="Phạm vi điều chỉnh của 23/2004/QH11 và các yêu cầu của 110/2014/NĐ-CP?"))
    assert "article" not in result.metadata


def test_a_related_provision_cannot_substitute_for_a_named_quoted_provision():
    llm = Mock()
    hit = source("07/2017/QH14")
    hit.metadata["article"] = "Điều 19.2.LQ.23. Nội dung hợp đồng chuyển giao công nghệ"
    result = RetrievalEvaluator(llm).evaluate(RetrievalEvaluationRequest(
        original_query='Điều khoản “Quyền chuyển giao công nghệ” của 07/2017/QH14 quy định gì?',
        current_query="nội dung", retrieval_result=RetrievalResult(query="nội dung", results=[hit]),
    ))
    assert not result.is_sufficient and "Quyền chuyển giao công nghệ" in result.reason
    llm.generate.assert_not_called()


def test_question_particles_only_soften_context_priority_not_hard_filters():
    query = "Cơ sở phải thực hiện những hoạt động gì để bảo đảm an toàn trường học?"
    requested = "Điều 1. Hoạt động bảo đảm an toàn trường học"
    agency = "Điều 2. Trách nhiệm của Bộ quản lý"
    assert not names_provision(query, requested)
    assert names_provision(query, requested, allow_question_particles=True)
    assert not names_provision(query, agency, allow_question_particles=True)


def test_context_prefers_the_requested_school_activity_over_agency_duties():
    agency, activity = source("80/2017/NĐ-CP", "agency"), source("80/2017/NĐ-CP", "activity")
    agency.metadata["article"] = "Điều 1. Trách nhiệm của Bộ quản lý"
    activity.metadata["article"] = "Điều 2. Hoạt động bảo đảm an toàn trường học"
    query = "Cơ sở thực hiện những hoạt động gì để bảo đảm an toàn trường học theo 80/2017/NĐ-CP?"
    assert prioritize_context_sources([agency, activity], query)[0].chunk_id == "activity"
