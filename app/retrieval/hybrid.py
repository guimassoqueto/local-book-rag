"""Hybrid retrieval: dense and lexical search, merged."""

from app.retrieval.base import BookScope, Passage, Retriever
from app.retrieval.fusion import Fusion


class HybridRetriever:
    def __init__(self, dense: Retriever, bm25: Retriever, fusion: Fusion) -> None:
        self._dense = dense
        self._bm25 = bm25
        self._fusion = fusion

    def retrieve(self, query: str, scope: BookScope) -> list[Passage]:
        return self._fusion(self._dense.retrieve(query, scope), self._bm25.retrieve(query, scope))
