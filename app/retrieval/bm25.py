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

# Historical spelling: old Portuguese spellings (Sophia, elle, facto) and modern ones (Sofia, ele,
# fato) give the same key. y -> i is applied before stemming: Snowball's Portuguese stemmer doesn't
# take y for a vowel, so it strips "tipo" to "tip" and leaves "typo" whole. These patterns apply to
# the stemmed, accent-free key, where they make fewer modern words collide. Each is the narrowest
# form that still matches the old spellings of Quincas Borba, and the order is the one measured.
_AFTER_STEMMING = tuple(
    (re.compile(pattern), replacement)
    for pattern, replacement in (
        (r"ph", "f"),
        (r"th", "t"),
        (r"([bcdfgklmnpt])\1", r"\1"),  # not rr or ss, which modern spelling keeps
        (r"ct", "t"),
        (r"gn", "n"),
        (r"bd", "d"),
        (r"^sc(?=[ei])", "c"),
        (r"z$", "s"),
        (r"(?<=[aeiou])h(?=[aeiou])", ""),
        (r"oup", "up"),
    )
)

# Modern keys that the patterns would make identical to another modern key, as pacto would become
# pato: they are left as they are. devtools/measure_historical_spelling.py computes them from a
# Brazilian word list, and fails when this set differs from what it finds.
_KEPT_KEYS: frozenset[str] = frozenset(
    """
    abdica abdon afaz assaz ayres bacter baham baz bell benign benz braz cact caract collor
    compact conjectur constrict contact convict coz cruz dactilograf defecca dez dign dignam doz
    duct electr emma epictet erect esparz espect facca facco faz ficca fuz garoup gnom gnu gnus
    godoy guiz impugn lact levy luiz luz magn magnes magnet magnif mallet math mogn moz mull
    myanm naz noz pact pactu paty paz poetiz prez profetiz provect queiroz resign revez rez ruy
    sarney secca seychell sign souz terez tez thaumaturg the thom traz trez ulysses valley vaz
    veloz veredict vez victor voz yog
    """.split()
)


class ChunkSource(Protocol):
    def load_chunks(self, book_id: str, revision: int) -> list[Chunk]: ...


class Tokenizer:
    """Lowercases and stems in the book's language, then strips accents.

    Stemming goes first because Snowball's Portuguese and Spanish rules read the accents. With
    historical spelling on, a Portuguese word's key also has its old spelling folded onto the modern
    one, Sophia onto Sofia, so that a question in either spelling finds the other. Only the keys
    change: the text a search returns never does.
    """

    def __init__(self, language: str | None, stemming: bool, historical_spelling: bool = False) -> None:
        name = _STEMMERS.get(language or "") if stemming else None
        self._stemmer = Stemmer.Stemmer(name) if name else None
        self._folds = historical_spelling and language == "pt" and self._stemmer is not None

    def tokenize(self, text: str) -> list[str]:
        tokens = _TOKEN.findall(text.casefold())
        if self._folds:
            # Once per distinct word: a book repeats most of its words, and folding stems twice.
            keys = {word: historical_key(word, self._stemmer) for word in set(tokens)}
            return [keys[word] for word in tokens]
        if self._stemmer is not None:
            tokens = self._stemmer.stemWords(tokens)
        return [_strip_accents(token) for token in tokens]


def historical_key(word: str, stemmer: Stemmer.Stemmer, kept: frozenset[str] = _KEPT_KEYS) -> str:
    """The key of a casefolded Portuguese word, with an old spelling folded onto the modern one.

    A word whose plain key is in `kept` keeps that key, since folding it would make it another
    modern word. `kept` is a parameter only for devtools/measure_historical_spelling.py.
    """
    plain = _strip_accents(stemmer.stemWord(word))
    if plain in kept:
        return plain
    key = _strip_accents(stemmer.stemWord(word.replace("y", "i"))) if "y" in word else plain
    for pattern, replacement in _AFTER_STEMMING:
        key = pattern.sub(replacement, key)
    return key


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
        tokens = Tokenizer(scope.language, self._config.stemming, self._config.historical_spelling).tokenize(query)
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
        tokenizer = Tokenizer(language, self._config.stemming, self._config.historical_spelling)
        return [(chunk, tokenizer.tokenize(chunk.text)) for chunk in self._chunks.load_chunks(book_id, revision)]
