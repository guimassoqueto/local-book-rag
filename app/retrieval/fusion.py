"""Merging ranked lists from different retrievers."""

from collections.abc import Callable, Sequence
from dataclasses import replace

from app.config.settings import FusionConfig
from app.retrieval.base import Passage

Fusion = Callable[[Sequence[Passage], Sequence[Passage]], list[Passage]]


def create_fusion(config: FusionConfig) -> Fusion:
    match config.method:
        case "rrf":
            return lambda dense, bm25: reciprocal_rank_fusion(dense, bm25, config.rrf_k)
        case "weighted":
            return lambda dense, bm25: weighted_fusion(dense, bm25, config.dense_weight)


def reciprocal_rank_fusion(dense: Sequence[Passage], bm25: Sequence[Passage], k: int) -> list[Passage]:
    """Score each passage by its ranks, which need no comparable scores between the lists.

    Args:
        dense: dense results, the best first.
        bm25: BM25 results, the best first.
        k: damping constant: the larger, the less the top positions dominate.

    Returns:
        Every passage from either list, with fusion_score set, the best first.
    """
    scores: dict[str, float] = {}
    for ranking in (dense, bm25):
        for rank, passage in enumerate(ranking, start=1):
            chunk_id = passage.chunk.chunk_id
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + rank)
    return _combine(dense, bm25, scores)


def weighted_fusion(dense: Sequence[Passage], bm25: Sequence[Passage], dense_weight: float) -> list[Passage]:
    """Score each passage by a weighted sum of its scores, normalized within each list.

    Args:
        dense: dense results.
        bm25: BM25 results.
        dense_weight: the share of dense retrieval in the sum, from 0 to 1.

    Returns:
        Every passage from either list, with fusion_score set, the best first.
    """
    dense_scores = _normalized({p.chunk.chunk_id: p.dense_score or 0.0 for p in dense})
    bm25_scores = _normalized({p.chunk.chunk_id: p.bm25_score or 0.0 for p in bm25})
    scores = {
        chunk_id: dense_weight * dense_scores.get(chunk_id, 0.0) + (1 - dense_weight) * bm25_scores.get(chunk_id, 0.0)
        for chunk_id in dense_scores | bm25_scores
    }
    return _combine(dense, bm25, scores)


def _normalized(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    low, high = min(scores.values()), max(scores.values())
    span = high - low
    return {key: (value - low) / span if span else 1.0 for key, value in scores.items()}


def _combine(dense: Sequence[Passage], bm25: Sequence[Passage], scores: dict[str, float]) -> list[Passage]:
    """Merge both lists' records of each passage, keeping the score each retriever gave it."""
    merged: dict[str, Passage] = {}
    for passage in (*dense, *bm25):
        chunk_id = passage.chunk.chunk_id
        known = merged.get(chunk_id)
        merged[chunk_id] = replace(
            passage,
            dense_score=passage.dense_score if known is None or passage.dense_score is not None else known.dense_score,
            bm25_score=passage.bm25_score if known is None or passage.bm25_score is not None else known.bm25_score,
            fusion_score=scores[chunk_id],
        )
    return sorted(merged.values(), key=lambda passage: passage.fusion_score or 0.0, reverse=True)
