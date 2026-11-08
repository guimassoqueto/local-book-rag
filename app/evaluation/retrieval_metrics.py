"""Retrieval quality, measured against a question's evidence.

Evidence is a list of sets: one set per quote, holding the chunks where that quote appears.
Overlap can put a quote in two chunks, so finding either one finds that piece of evidence, and
finding both counts once.
"""

from collections.abc import Sequence
from math import log2

Evidence = Sequence[set[str]]


def _covered(chunks: Sequence[str], evidence: Evidence) -> int:
    found = set(chunks)
    return sum(1 for chunk_ids in evidence if chunk_ids & found)


def recall_at_k(ranking: Sequence[str], evidence: Evidence, k: int) -> float:
    """The share of the evidence found in the first k results."""
    return _covered(ranking[:k], evidence) / len(evidence) if evidence else 0.0


def reciprocal_rank(ranking: Sequence[str], evidence: Evidence) -> float:
    """One over the position of the first result holding any evidence."""
    relevant = set().union(*evidence) if evidence else set()
    return next((1 / rank for rank, chunk_id in enumerate(ranking, start=1) if chunk_id in relevant), 0.0)


def ndcg_at_k(ranking: Sequence[str], evidence: Evidence, k: int) -> float:
    """How close the order is to the ideal one, in which new evidence comes first.

    A chunk earns credit for every quote it adds, and so does the ideal order. Otherwise two
    quotes in one chunk could never reach 1, which would penalize larger chunks for holding
    more of the evidence, in the very experiment that compares chunk sizes.
    """
    ideal = _discounted_gain(_ideal_order(evidence), evidence, k)
    return _discounted_gain(ranking, evidence, k) / ideal if ideal else 0.0


def _discounted_gain(ranking: Sequence[str], evidence: Evidence, k: int) -> float:
    remaining = list(evidence)
    gain = 0.0
    for rank, chunk_id in enumerate(ranking[:k], start=1):
        new = [chunk_ids for chunk_ids in remaining if chunk_id in chunk_ids]
        remaining = [chunk_ids for chunk_ids in remaining if chunk_id not in chunk_ids]
        gain += len(new) / log2(rank + 1)
    return gain


def _ideal_order(evidence: Evidence) -> list[str]:
    """The best possible ranking: at each position, the chunk that adds the most quotes."""
    remaining = [chunk_ids for chunk_ids in evidence if chunk_ids]
    order: list[str] = []
    while remaining:
        candidates = sorted(set().union(*remaining))
        best = max(candidates, key=lambda chunk_id: sum(chunk_id in chunk_ids for chunk_ids in remaining))
        order.append(best)
        remaining = [chunk_ids for chunk_ids in remaining if best not in chunk_ids]
    return order


def context_precision(context: Sequence[str], evidence: Evidence) -> float:
    """Average precision of the final context: whether what it holds is relevant, and comes early."""
    relevant = set().union(*evidence) if evidence else set()
    hits = 0
    total = 0.0
    for rank, chunk_id in enumerate(context, start=1):
        if chunk_id in relevant:
            hits += 1
            total += hits / rank
    return total / hits if hits else 0.0


def context_recall(context: Sequence[str], evidence: Evidence) -> float:
    """The share of the evidence that reached the model."""
    return _covered(context, evidence) / len(evidence) if evidence else 0.0
