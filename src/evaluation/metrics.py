"""Small, deterministic ranking metrics for retrieval benchmarks."""

import math
from collections.abc import Collection, Sequence


def _validate_inputs(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int,
) -> tuple[list[str], set[str]]:
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")
    if any(not isinstance(item, str) or not item for item in retrieved_ids):
        raise ValueError("retrieved_ids must contain non-empty strings")
    if any(not isinstance(item, str) or not item for item in relevant_ids):
        raise ValueError("relevant_ids must contain non-empty strings")
    relevant = set(relevant_ids)
    if not relevant:
        raise ValueError("relevant_ids must not be empty")
    # A duplicate chunk should not count more than once in a ranked result.
    unique_ids = list(dict.fromkeys(retrieved_ids))
    return unique_ids[:k], relevant


def recall_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int,
) -> float:
    """Return the fraction of labeled relevant items found in the first k hits."""
    ranked, relevant = _validate_inputs(retrieved_ids, relevant_ids, k)
    return len(set(ranked) & relevant) / len(relevant)


def reciprocal_rank(
    retrieved_ids: Sequence[str],
    relevant_ids: Collection[str],
    k: int | None = None,
) -> float:
    """Return reciprocal rank of the first relevant hit, optionally cutoff at k."""
    if k is None:
        if any(not isinstance(item, str) or not item for item in retrieved_ids):
            raise ValueError("retrieved_ids must contain non-empty strings")
        if any(not isinstance(item, str) or not item for item in relevant_ids):
            raise ValueError("relevant_ids must contain non-empty strings")
        relevant = set(relevant_ids)
        if not relevant:
            raise ValueError("relevant_ids must not be empty")
        ranked = list(dict.fromkeys(retrieved_ids))
    else:
        ranked, relevant = _validate_inputs(retrieved_ids, relevant_ids, k)
    for rank, chunk_id in enumerate(ranked, start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0


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
