"""Reciprocal rank fusion: compare ranks, never unrelated raw scores."""

from collections.abc import Sequence

from core.schemas import RetrievedChunk
from src.retrieval.common import positive_integer, scored_hit, unique_hits


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[RetrievedChunk]], *, rank_constant: int = 60,
) -> list[RetrievedChunk]:
    """Use 1-based ranks, one vote per ID per branch, and stable tie ordering."""
    positive_integer(rank_constant, "rank_constant")
    branches = [unique_hits(branch) for branch in rankings]
    sources = unique_hits(hit for branch in branches for hit in branch)
    scores = {hit.chunk_id: 0.0 for hit in sources}
    for branch in branches:
        for rank, hit in enumerate(branch, start=1):
            scores[hit.chunk_id] += 1.0 / (rank_constant + rank)
    fused = [scored_hit(hit, scores[hit.chunk_id], "rrf") for hit in sources]
    return sorted(fused, key=lambda hit: hit.score, reverse=True)
