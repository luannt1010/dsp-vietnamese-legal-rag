"""Small, deterministic ranking metrics for retrieval benchmarks."""

import math
from collections.abc import Collection, Sequence
from typing import Literal


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")


def _validate_ids(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
) -> tuple[list[str], set[str]]:
    if any(not isinstance(item, str) or not item for item in retrieved_ids):
        raise ValueError("retrieved_ids must contain non-empty strings")
    if any(not isinstance(item, str) or not item for item in relevant_ids):
        raise ValueError("relevant_ids must contain non-empty strings")
    relevant = set(relevant_ids)
    if not relevant:
        raise ValueError("relevant_ids must not be empty")
    return list(dict.fromkeys(retrieved_ids)), relevant


def _validate_inputs(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int,
) -> tuple[list[str], set[str]]:
    _validate_k(k)
    unique_ids, relevant = _validate_ids(retrieved_ids, relevant_ids)
    return unique_ids[:k], relevant


def _validate_binary_judgments(judgments: Sequence[bool], *, name: str) -> None:
    if not judgments:
        raise ValueError(f"{name} must not be empty")
    if any(type(judgment) is not bool for judgment in judgments):
        raise ValueError(f"{name} must contain only bool values")


def _validate_similarity_scores(scores: Sequence[float]) -> None:
    if not scores:
        raise ValueError("similarity_scores must not be empty")
    if any(
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or not -1 <= score <= 1
        for score in scores
    ):
        raise ValueError("similarity_scores must be finite values between -1 and 1")


def recall_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int,
) -> float:
    """Return the fraction of labeled relevant items found in the first k hits."""
    ranked, relevant = _validate_inputs(retrieved_ids, relevant_ids, k)
    return len(set(ranked) & relevant) / len(relevant)


def precision_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int,
) -> float:
    """Return relevant unique retrieved IDs at k divided by k."""
    ranked, relevant = _validate_inputs(retrieved_ids, relevant_ids, k)
    return len(set(ranked) & relevant) / k


def average_precision(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int | None = None,
) -> float:
    """Return average precision for one ranking; missed relevant IDs count as misses."""
    if k is None:
        ranked, relevant = _validate_ids(retrieved_ids, relevant_ids)
    else:
        ranked, relevant = _validate_inputs(retrieved_ids, relevant_ids, k)
    relevant_seen = 0
    precision_sum = 0.0
    for rank, chunk_id in enumerate(ranked, start=1):
        if chunk_id in relevant:
            relevant_seen += 1
            precision_sum += relevant_seen / rank
    return precision_sum / len(relevant)


def mean_average_precision(
    ranked_results: Sequence[Sequence[str]],
    relevant_results: Sequence[Collection[str]],
    k: int | None = None,
) -> float:
    """Return mean average precision across paired query rankings and labels."""
    if not ranked_results or len(ranked_results) != len(relevant_results):
        raise ValueError("ranked_results and relevant_results must be non-empty and aligned")
    return sum(
        average_precision(ranking, relevant, k)
        for ranking, relevant in zip(ranked_results, relevant_results)
    ) / len(ranked_results)


def reciprocal_rank(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int | None = None,
) -> float:
    """Return reciprocal rank of the first relevant hit, optionally cutoff at k."""
    if k is None:
        ranked, relevant = _validate_ids(retrieved_ids, relevant_ids)
    else:
        ranked, relevant = _validate_inputs(retrieved_ids, relevant_ids, k)
    for rank, chunk_id in enumerate(ranked, start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(
    ranked_results: Sequence[Sequence[str]],
    relevant_results: Sequence[Collection[str]],
    k: int | None = None,
) -> float:
    """Return mean reciprocal rank across paired query rankings and labels."""
    if not ranked_results or len(ranked_results) != len(relevant_results):
        raise ValueError("ranked_results and relevant_results must be non-empty and aligned")
    return sum(
        reciprocal_rank(ranking, relevant, k)
        for ranking, relevant in zip(ranked_results, relevant_results)
    ) / len(ranked_results)


def hit_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int,
) -> float:
    """Return 1.0 when at least one relevant ID appears in the first k hits."""
    ranked, relevant = _validate_inputs(retrieved_ids, relevant_ids, k)
    return float(bool(set(ranked) & relevant))


def context_precision(
    retrieved_context_ids: Sequence[str],
    relevant_context_ids: Collection[str],
    k: int | None = None,
) -> float:
    """Return rank-aware context precision from reference context IDs.

    This is the deterministic ID-judged variant: it aggregates precision at
    ranks judged relevant and divides by relevant retrieved contexts, following
    the Context Precision definition used by Ragas. It does not call an LLM to
    judge semantic relevance.
    """
    if k is None:
        ranked, relevant = _validate_ids(retrieved_context_ids, relevant_context_ids)
    else:
        ranked, relevant = _validate_inputs(retrieved_context_ids, relevant_context_ids, k)
    relevant_ranks = [
        rank
        for rank, context_id in enumerate(ranked, start=1)
        if context_id in relevant
    ]
    if not relevant_ranks:
        return 0.0
    return sum(
        sum(context_id in relevant for context_id in ranked[:rank]) / rank
        for rank in relevant_ranks
    ) / len(relevant_ranks)


def context_recall(
    retrieved_context_ids: Sequence[str],
    reference_context_ids: Collection[str],
) -> float:
    """Return the fraction of reference context IDs that were retrieved."""
    ranked, reference = _validate_ids(retrieved_context_ids, reference_context_ids)
    return len(set(ranked) & reference) / len(reference)


def faithfulness(claim_support: Sequence[bool]) -> float:
    """Aggregate judged answer-claim support by retrieved context.

    Each bool indicates whether one answer claim is supported by the supplied
    context. Claim extraction and support judgments must be supplied externally.
    """
    _validate_binary_judgments(claim_support, name="claim_support")
    return sum(claim_support) / len(claim_support)


def answer_relevancy(similarity_scores: Sequence[float]) -> float:
    """Average cosine similarities of generated questions to the user query.

    Similarities are produced by an embedding/judging stage; this function only
    aggregates them. Cosine similarity is allowed to be negative.
    """
    _validate_similarity_scores(similarity_scores)
    return sum(similarity_scores) / len(similarity_scores)


def factual_correctness(
    response_claim_support: Sequence[bool],
    reference_claim_coverage: Sequence[bool],
    mode: Literal["precision", "recall", "f1"] = "f1",
) -> float:
    """Aggregate claim-level judgments against a reference answer.

    `response_claim_support` marks response claims supported by the reference;
    `reference_claim_coverage` marks reference claims covered by the response.
    Claim matching/entailment is an annotation or model-judge responsibility.
    """
    _validate_binary_judgments(
        response_claim_support, name="response_claim_support",
    )
    _validate_binary_judgments(
        reference_claim_coverage, name="reference_claim_coverage",
    )
    precision = sum(response_claim_support) / len(response_claim_support)
    recall = sum(reference_claim_coverage) / len(reference_claim_coverage)
    if mode == "precision":
        return precision
    if mode == "recall":
        return recall
    if mode == "f1":
        return 0.0 if precision + recall == 0 else (
            2 * precision * recall / (precision + recall)
        )
    raise ValueError("mode must be 'precision', 'recall', or 'f1'")


def ndcg_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int,
) -> float:
    """Return binary-relevance normalized discounted cumulative gain at k."""
    ranked, relevant = _validate_inputs(retrieved_ids, relevant_ids, k)
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(ranked, start=1)
        if chunk_id in relevant
    )
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal_dcg
