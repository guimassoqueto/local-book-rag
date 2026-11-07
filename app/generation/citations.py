"""Ties the numbers in a generated text to the passages they stand for."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.ingestion.chunker import Chunk

_CITATION = re.compile(r"\[(\d+(?:\s*[,;–-]\s*\d+)*)\]")
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
# gpt-oss cites as 【3】 or 【3†L1-L4】, whatever the prompt shows it.
_LENTICULAR_CITATION = re.compile(r"[【［〔]\s*(\d+(?:\s*[,;–-]\s*\d+)*)[^】］〕]*[】］〕]")
_SEPARATOR = re.compile(r"\s*[,;]\s*")
_RANGE = re.compile(r"\s*[–-]\s*")
_MAX_RANGE = 50  # beyond this, "[1-9999]" is not a citation anyone meant
_EXCERPT_CHARACTERS = 80


@dataclass(frozen=True)
class Citation:
    """A source a text relies on: enough to find it in the original book."""

    number: int
    chunk_id: str
    book_id: str
    book_title: str
    chapter_number: int
    chapter_title: str
    section_title: str | None
    page_start: int | None
    page_end: int | None
    excerpt: str

    @property
    def pages(self) -> str | None:
        if self.page_start is None:
            return None
        if self.page_start == self.page_end:
            return f"p. {self.page_start}"
        return f"pp. {self.page_start}-{self.page_end}"

    @property
    def reference(self) -> str:
        parts = [self.book_title, self.chapter_title, self.section_title, self.pages]
        return ", ".join(part for part in parts if part)


def citation_for(number: int, chunk: Chunk) -> Citation:
    return Citation(
        number=number,
        chunk_id=chunk.chunk_id,
        book_id=chunk.book_id,
        book_title=chunk.book_title,
        chapter_number=chunk.chapter_number,
        chapter_title=chunk.chapter_title,
        section_title=chunk.section_title,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        excerpt=_excerpt(chunk.text),
    )


def _excerpt(text: str) -> str:
    """The passage's opening words: in a book without pages, they are how to find it."""
    flat = " ".join(text.split())
    return flat if len(flat) <= _EXCERPT_CHARACTERS else flat[:_EXCERPT_CHARACTERS].rsplit(" ", 1)[0] + "…"


def normalize_citations(text: str) -> str:
    """Rewrite each model's way of citing as [3]: nothing downstream depends on one format."""
    return _LENTICULAR_CITATION.sub(lambda match: f"[{match.group(1)}]", text)


def cited_numbers(text: str) -> list[int]:
    """Find every number cited in a text, in order of first appearance.

    Code is left out: `t = [1, 2, 3]` is a list, and reading it as citations would attach
    sources that nothing relied on, which looks right and is false.
    """
    found: dict[int, None] = {}
    for match in _CITATION.finditer(_CODE.sub(" ", text)):
        for item in _SEPARATOR.split(match.group(1)):
            bounds = [int(value) for value in _RANGE.split(item)]
            first, last = bounds[0], bounds[-1]
            if 0 <= last - first <= _MAX_RANGE:
                found.update(dict.fromkeys(range(first, last + 1)))
            else:
                found.update(dict.fromkeys(bounds))
    return list(found)


def resolve_citations(text: str, sources: Sequence[Chunk]) -> tuple[list[Citation], list[int]]:
    """Match a text's citations against the numbered sources it was given.

    Args:
        text: the generated text.
        sources: the sources, numbered from 1 in this order.

    Returns:
        The valid citations, and the numbers that match no source, which the model made up.
    """
    valid: list[Citation] = []
    invalid: list[int] = []
    for number in cited_numbers(text):
        if 1 <= number <= len(sources):
            valid.append(citation_for(number, sources[number - 1]))
        else:
            invalid.append(number)
    return valid, invalid
