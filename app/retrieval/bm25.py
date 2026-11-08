"""BM25 lexical retrieval.

The index is built in memory over exactly the chunks a search may return. That takes about
60 ms for a 1,300-chunk book, so there is no second index on disk to keep in step with the
vector store, and term rarity reflects the part of the book being searched.
"""

import re
import unicodedata
from functools import lru_cache
from typing import Protocol

import bm25s
import Stemmer

from app.config.settings import BM25Config
from app.ingestion.chunker import Chunk
from app.retrieval.base import BookScope, Passage, RetrievalFilters

_TOKEN = re.compile(r"\w+")
_STEMMERS = {
    "de": "german",
    "en": "english",
    "es": "spanish",
    "fr": "french",
    "it": "italian",
    "pt": "portuguese",
}
_CACHED_BOOKS = 16
_CACHED_INDEXES = 32


class ChunkSource(Protocol):
    def load_chunks(self, book_id: str, revision: int) -> list[Chunk]: ...


class Tokenizer:
    """Lowercases and stems in the book's language, then strips accents.

    Stemming goes first because Snowball's Portuguese and Spanish rules read the accents.
    """

    def __init__(self, language: str | None, stemming: bool) -> None:
        name = _STEMMERS.get(language or "") if stemming else None
        self._stemmer = Stemmer.Stemmer(name) if name else None

    def tokenize(self, text: str) -> list[str]:
        tokens = _TOKEN.findall(text.casefold())
        if self._stemmer is not None:
            tokens = self._stemmer.stemWords(tokens)
        return [_strip_accents(token) for token in tokens]


def _strip_accents(token: str) -> str:
    decomposed = unicodedata.normalize("NFD", token)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


class BM25Retriever:
    def __init__(self, config: BM25Config, chunks: ChunkSource) -> None:
        self._config = config
        self._chunks = chunks
        self._tokenized_book = lru_cache(maxsize=_CACHED_BOOKS)(self._tokenize_book)
        self._index = lru_cache(maxsize=_CACHED_INDEXES)(self._build_index)

    def retrieve(self, query: str, scope: BookScope) -> list[Passage]:
        chunks, index = self._index(scope.book_id, scope.revision, scope.language, scope.filters)
        tokens = Tokenizer(scope.language, self._config.stemming).tokenize(query)
        if not chunks or not tokens:
            return []

        top_k = min(self._config.top_k, len(chunks))  # bm25s refuses a k beyond the corpus
        positions, scores = index.retrieve([tokens], k=top_k, show_progress=False)
        return [
            Passage(chunks[position], bm25_score=float(score))
            for position, score in zip(positions[0], scores[0], strict=True)
            if score > 0  # bm25s fills k with documents that share no term with the query
        ]

    def _build_index(
        self, book_id: str, revision: int, language: str | None, filters: RetrievalFilters
    ) -> tuple[list[Chunk], bm25s.BM25 | None]:
        allowed = [item for item in self._tokenized_book(book_id, revision, language) if filters.allows(item[0])]
        if not allowed:
            return [], None
        index = bm25s.BM25(k1=self._config.k1, b=self._config.b)
        index.index([tokens for _, tokens in allowed], show_progress=False)
        return [chunk for chunk, _ in allowed], index

    def _tokenize_book(self, book_id: str, revision: int, language: str | None) -> list[tuple[Chunk, list[str]]]:
        tokenizer = Tokenizer(language, self._config.stemming)
        return [(chunk, tokenizer.tokenize(chunk.text)) for chunk in self._chunks.load_chunks(book_id, revision)]
