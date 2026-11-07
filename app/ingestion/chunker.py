"""Splits a book into chunks that respect its structure."""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from functools import cache

from app.config.settings import ChunkingConfig
from app.ingestion.base import Block, BlockKind
from app.ingestion.structure_extractor import BookStructure, Chapter, Section
from app.utils.tokenization import TokenCounter

_SENTENCE_END = re.compile(r"[.!?…][\"'”’»)\]]*(?=\s+[\"'“‘«(\[]*[^\W_])")
_ABBREVIATIONS = frozenset("al cap cf dr dra ed eds fig figs mr mrs ms nº p pp prof profa sr sra st vol vs".split())
_TABLE_HEADER_LINES = 2  # the header row and its separator
_SEPARATOR_TOKENS = 1  # a line break is a token of its own, unlike the space before a word
_PARAGRAPH_BREAK = "\n\n"
_LINE_BREAK = "\n"
_SPACE = " "


@dataclass(frozen=True)
class Chunk:
    """The unit of retrieval. The fields are the same whatever the source format."""

    chunk_id: str
    book_id: str
    book_title: str
    chapter_number: int
    chapter_title: str
    section_title: str | None
    page_start: int | None
    page_end: int | None
    chunk_index: int
    language: str | None
    text: str


@dataclass(frozen=True)
class _Piece:
    """Text that fits in one chunk.

    Attributes:
        text: the content.
        tokens: its length.
        kind: the kind of block it came from.
        joiner: what separates it from the piece before it in a chunk.
        page_start: first page of its block.
        page_end: last page of its block.
        section_title: the section it belongs to.
    """

    text: str
    tokens: int
    kind: BlockKind
    joiner: str
    page_start: int | None
    page_end: int | None
    section_title: str | None


class Chunker:
    def __init__(self, config: ChunkingConfig, counter: TokenCounter) -> None:
        self._config = config
        self._counter = counter
        self._count = counter.count

    def chunk(self, book_id: str, book_title: str, structure: BookStructure) -> list[Chunk]:
        """Split a book.

        Args:
            book_id: goes into every chunk and its ID.
            book_title: goes into every chunk.
            structure: the book.

        Returns:
            The chunks in reading order, chunk_index being the position in the book.
        """
        self._count = cache(self._counter.count)  # fresh per book: it would otherwise keep every sentence
        chunks: list[Chunk] = []
        for chapter in structure.chapters:
            for pieces in self._chapter_groups(chapter):
                index = len(chunks)
                pages = [page for piece in pieces for page in (piece.page_start, piece.page_end) if page is not None]
                keep_pages = self._config.preserve.page_numbers and pages
                chunks.append(
                    Chunk(
                        chunk_id=f"{book_id}_chapter_{chapter.number:02d}_chunk_{index:04d}",
                        book_id=book_id,
                        book_title=book_title,
                        chapter_number=chapter.number,
                        chapter_title=chapter.title,
                        section_title=pieces[-1].section_title,
                        page_start=min(pages) if keep_pages else None,
                        page_end=max(pages) if keep_pages else None,
                        chunk_index=index,
                        language=structure.language,
                        text=pieces[0].text + "".join(piece.joiner + piece.text for piece in pieces[1:]),
                    )
                )
        return chunks

    def _chapter_groups(self, chapter: Chapter) -> Iterator[list[_Piece]]:
        if self._config.strategy == "fixed":
            yield from self._fixed_windows(chapter)
        elif self._config.preserve.sections:
            for section in chapter.sections:
                yield from self._fill(self._section_pieces(section))
        else:
            yield from self._fill(piece for section in chapter.sections for piece in self._section_pieces(section))

    def _section_pieces(self, section: Section) -> Iterator[_Piece]:
        for block in section.blocks:
            yield from self._block_pieces(block, section.title)

    def _block_pieces(self, block: Block, section_title: str | None) -> Iterator[_Piece]:
        """Keep a block whole when it fits. Otherwise divide it at the gentlest boundary that works."""

        def piece(text: str, joiner: str) -> _Piece:
            return _Piece(text, self._count(text), block.kind, joiner, block.page_start, block.page_end, section_title)

        fits = self._count(block.text) <= self._config.target_size
        if fits and (self._config.preserve.paragraphs or block.kind is not BlockKind.PARAGRAPH):
            yield piece(block.text, _PARAGRAPH_BREAK)
            return

        joiner = _SPACE if block.kind is BlockKind.PARAGRAPH else _LINE_BREAK
        for position, text in enumerate(self._divide(block)):
            yield piece(text, _PARAGRAPH_BREAK if position == 0 else joiner)

    def _divide(self, block: Block) -> Iterator[str]:
        if block.kind is BlockKind.TABLE:
            yield from self._divide_table(block.text)
            return
        units = split_sentences(block.text) if block.kind is BlockKind.PARAGRAPH else block.text.splitlines()
        for unit in units:
            yield from self._limit_size(unit)

    def _divide_table(self, text: str) -> Iterator[str]:
        """Split a table between rows, repeating its header: rows mean nothing without it."""
        lines = text.splitlines()
        header, rows = lines[:_TABLE_HEADER_LINES], lines[_TABLE_HEADER_LINES:]
        budget = self._config.target_size - self._count(_LINE_BREAK.join(header))
        if budget <= 0 or any(self._count(row) >= budget for row in rows):
            for line in lines:  # a row that cannot fit under the header anyway
                yield from self._limit_size(line)
            return

        current: list[str] = []
        tokens = 0
        for row in rows:
            row_tokens = self._count(row) + _SEPARATOR_TOKENS
            if current and tokens + row_tokens > budget:
                yield _LINE_BREAK.join([*header, *current])
                current, tokens = [], 0
            current.append(row)
            tokens += row_tokens
        if current:
            yield _LINE_BREAK.join([*header, *current])

    def _limit_size(self, text: str) -> Iterator[str]:
        """Last resort for a sentence longer than a chunk: split between words, then inside them."""
        if self._count(text) <= self._config.target_size:
            yield text
            return
        words: list[str] = []
        for word in text.split():
            if self._count(word) > self._config.target_size:
                if words:
                    yield _SPACE.join(words)
                    words = []
                yield from self._split_word(word)
            elif words and self._count(_SPACE.join([*words, word])) > self._config.target_size:
                yield _SPACE.join(words)
                words = [word]
            else:
                words.append(word)
        if words:
            yield _SPACE.join(words)

    def _split_word(self, word: str) -> Iterator[str]:
        size = max(1, len(word) * self._config.target_size // (self._count(word) + 1))
        for start in range(0, len(word), size):
            yield word[start : start + size]

    def _fixed_windows(self, chapter: Chapter) -> Iterator[list[_Piece]]:
        """The baseline that structural chunking is measured against: windows over the chapter's words."""
        words = [
            _Piece(word, self._count(word), block.kind, _SPACE, block.page_start, block.page_end, section.title)
            for section in chapter.sections
            for block in section.blocks
            for raw in block.text.split()
            for word in self._limit_size(raw)
        ]
        window: list[_Piece] = []
        tokens = 0
        for word in words:
            if window and tokens + word.tokens > self._config.target_size:
                yield window
                while tokens > self._config.overlap:
                    tokens -= window.pop(0).tokens
            window.append(word)
            tokens += word.tokens
        if window:
            yield window

    def _fill(self, pieces: Iterable[_Piece]) -> Iterator[list[_Piece]]:
        """Pack pieces into chunks up to the target size, carrying the overlap between them."""
        current: list[_Piece] = []
        tokens = 0
        carried = 0  # how many pieces at the start of `current` came from the previous chunk
        for piece in pieces:
            size = _cost(piece)
            overflows = tokens + size > self._config.target_size
            # Headings stay with what follows them, even at the cost of a slightly larger chunk.
            if overflows and any(item.kind is not BlockKind.HEADING for item in current[carried:]):
                yield current
                current = self._overlap_from(current)
                tokens = sum(_cost(item) for item in current)
                carried = len(current)
            while carried and tokens + size > self._config.target_size:
                tokens -= _cost(current.pop(0))  # the overlap gives way to new text
                carried -= 1
            current.append(piece)
            tokens += size
        if any(item.kind is not BlockKind.HEADING for item in current[carried:]):
            yield current

    def _overlap_from(self, pieces: list[_Piece]) -> list[_Piece]:
        """The closing sentences of a chunk, up to the overlap size."""
        budget = self._config.overlap
        overlap: list[_Piece] = []
        for piece in reversed(pieces):
            if piece.kind in (BlockKind.HEADING, BlockKind.TABLE, BlockKind.CODE):
                break
            for sentence in reversed(split_sentences(piece.text)):
                tokens = self._count(sentence)
                if tokens > budget:
                    return overlap
                budget -= tokens
                overlap.insert(0, replace(piece, text=sentence, tokens=tokens, joiner=_SPACE))
        return overlap


def _cost(piece: _Piece) -> int:
    return piece.tokens + (0 if piece.joiner == _SPACE else _SEPARATOR_TOKENS)


def split_sentences(text: str) -> list[str]:
    """Split at sentence-ending punctuation, unless it ends an abbreviation or an initial."""
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        if _ends_with_abbreviation(text[start:end]) or _next_letter_is_lowercase(text, end):
            continue
        sentences.append(text[start:end].strip())
        start = end
    if tail := text[start:].strip():
        sentences.append(tail)
    return sentences


def _ends_with_abbreviation(sentence: str) -> bool:
    last_word = sentence.rsplit(maxsplit=1)[-1].strip("\"'“‘«([").rstrip(".").casefold()
    return len(last_word) == 1 and last_word.isalpha() or last_word in _ABBREVIATIONS or "." in last_word


def _next_letter_is_lowercase(text: str, position: int) -> bool:
    following = text[position:].lstrip(" \t\n\"'“‘«([")
    return following[:1].islower()
