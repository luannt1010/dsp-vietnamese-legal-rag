"""Binary chunk qrels resolved from exact source quotations, never from system hits."""

import re

from src.benchmark.dataset import normalized
from src.benchmark.schemas import Question
from src.evaluation.metrics import average_precision, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from src.retrieval.common import as_hit


def same_location(stored, expected: str) -> bool:
    """Allow a displayed heading after an exact article/location identifier.

    An original-law article number is not guessed from a Phap Dien code.
    corpus_article can explicitly provide that mapping in the dataset.
    """
    stored, expected = normalized(str(stored or "")), normalized(expected)
    if stored == expected:
        return True
    identifier = re.match(r"^(Điều\s+[0-9]+(?:\.[A-Za-zĐđ0-9]+)*)[.]?(?:\s|$)", stored)
    return bool(identifier and identifier.group(1) == expected)


class EvidenceIndex:
    def __init__(self, chunks):
        self.by_document = {}
        for chunk in chunks:
            hit = as_hit(chunk)
            number = hit.metadata.get("document_number")
            self.by_document.setdefault(number, []).append((hit, normalized(hit.content)))

    def resolve(self, question: Question) -> list[str]:
        """Require atomic quotations to fit a leaf; fail loudly on missing labels.

        The evaluation unit is a unique chunk, with fixed chunking across B0–B4.
        Every leaf containing a labeled quote is relevant, including overlap copies.
        This is binary chunk relevance, not a graded or evidence-coverage metric.
        """
        relevant = set()
        for index, evidence in enumerate(question.evidence):
            matches = []
            for hit, text in self.by_document.get(evidence.document_number, []):
                location = {key: hit.metadata.get(key) for key in ("article", "clause", "point")}
                if any(value is not None and not same_location(location[key], value)
                       for key, value in (("article", evidence.corpus_article or evidence.article),
                                          ("clause", evidence.clause), ("point", evidence.point))):
                    continue
                if normalized(evidence.quote) in text:
                    matches.append(hit.chunk_id)
            if not matches:
                raise ValueError(f"{question.question_id}: evidence[{index}] not resolved in corpus; "
                                 "check document/location/version and use an atomic verbatim quote fitting a leaf")
            relevant.update(matches)
        return sorted(relevant)


def score_ranking(ranking, relevant_ids: list[str], ks) -> dict[str, float]:
    if not relevant_ids:
        return {}
    ids = [hit.chunk_id for hit in ranking]
    functions = {"recall": recall_at_k, "precision": precision_at_k,
                 "mrr": reciprocal_rank, "map": average_precision, "ndcg": ndcg_at_k}
    return {f"{name}@{k}": function(ids, relevant_ids, k)
            for k in ks for name, function in functions.items()}
