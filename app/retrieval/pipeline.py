"""Runs a search across books: candidates per book, optional reranking, and the final cut."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from math import ceil
from time import perf_counter

from app.retrieval.base import BookScope, Passage, Reranker, Retriever


@dataclass(frozen=True)
class RetrievalResult:
    """A search's outcome, with what the diagnostics need to explain it.

    Attributes:
        query: what was searched.
        passages: the final selection.
        candidates: every passage considered, before the final cut.
        retrieval_seconds: time spent finding candidates.
        rerank_seconds: time spent reranking them.
    """

    query: str
    passages: tuple[Passage, ...]
    candidates: tuple[Passage, ...]
    retrieval_seconds: float
    rerank_seconds: float


class RetrievalPipeline:
    def __init__(self, retriever: Retriever, reranker: Reranker | None, top_k: int) -> None:
        """Create a pipeline.

        Args:
            retriever: finds candidates.
            reranker: reorders them. None skips the stage.
            top_k: how many passages a search returns.
        """
        self._retriever = retriever
        self._reranker = reranker
        self._top_k = top_k

    def run(self, query: str, scopes: Sequence[BookScope]) -> RetrievalResult:
        """Search each book on its own, so that one book can never crowd another out."""
        started = perf_counter()
        per_book = [self._retriever.retrieve(query, scope) for scope in scopes]
        retrieved = perf_counter()

        if self._reranker is not None:
            per_book = [self._rerank(query, passages) for passages in per_book]
        reranked = perf_counter()

        return RetrievalResult(
            query=query,
            passages=tuple(_take_in_turns(per_book, self._top_k)),
            candidates=tuple(passage for passages in per_book for passage in passages),
            retrieval_seconds=retrieved - started,
            rerank_seconds=reranked - retrieved,
        )

    def _rerank(self, query: str, passages: list[Passage]) -> list[Passage]:
        scores = self._reranker.score(query, [passage.chunk.text for passage in passages])
        scored = [replace(passage, rerank_score=score) for passage, score in zip(passages, scores, strict=True)]
        return sorted(scored, key=lambda passage: passage.rerank_score or 0.0, reverse=True)


def _take_in_turns(per_book: list[list[Passage]], limit: int) -> list[Passage]:
    """Give each book the same share of the result, the remainder going to the books with more."""
    share = ceil(limit / len(per_book)) if per_book else 0
    selected: list[Passage] = []
    for rank in range(share):
        selected.extend(passages[rank] for passages in per_book if rank < len(passages))
    return selected[:limit]
