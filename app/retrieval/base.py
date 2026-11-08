"""The retrieval layer's vocabulary. Nothing here knows how a passage was found."""

from dataclasses import dataclass, field
from typing import Protocol

from app.ingestion.chunker import Chunk


@dataclass(frozen=True)
class RetrievalFilters:
    """What a search may return. An empty field does not restrict anything.

    Attributes:
        book_ids: the books to search.
        chapter_numbers: chapters, as positions in the book.
        section_titles: sections, by their exact title.
        languages: ISO 639-1 codes.
        page_start: first page of a range. A chunk qualifies if it overlaps the range, so
            chunks without pages never do.
        page_end: last page of a range.
    """

    book_ids: tuple[str, ...] = ()
    chapter_numbers: tuple[int, ...] = ()
    section_titles: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    page_start: int | None = None
    page_end: int | None = None

    def allows(self, chunk: Chunk) -> bool:
        if self.chapter_numbers and chunk.chapter_number not in self.chapter_numbers:
            return False
        if self.section_titles and chunk.section_title not in self.section_titles:
            return False
        if self.languages and chunk.language not in self.languages:
            return False
        if self.page_start is not None and (chunk.page_end is None or chunk.page_end < self.page_start):
            return False
        return self.page_end is None or (chunk.page_start is not None and chunk.page_start <= self.page_end)


@dataclass(frozen=True)
class BookScope:
    """One retrieval pass: a single revision of a single book."""

    book_id: str
    revision: int
    language: str | None
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)


@dataclass(frozen=True)
class Passage:
    """A retrieved chunk, with the score of every stage it went through."""

    chunk: Chunk
    dense_score: float | None = None
    bm25_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None


class Retriever(Protocol):
    def retrieve(self, query: str, scope: BookScope) -> list[Passage]:
        """Return a book's passages for a query, the best first."""
        ...


class Reranker(Protocol):
    model: str

    def score(self, query: str, texts: list[str]) -> list[float]:
        """Score each text's relevance to the query, from 0 to 1."""
        ...
