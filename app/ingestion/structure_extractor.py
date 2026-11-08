"""Finds chapters and sections in a flat list of blocks.

Every format reports heading depth, but depth alone doesn't say what a chapter is: a book
can have one H1 for its title, or parts above its chapters.
"""

import re
from dataclasses import dataclass

from app.ingestion.base import ORDINAL, Block, BlockKind, ExtractedDocument

FRONT_MATTER_TITLE = "Front matter"
_WHOLE_BOOK_TITLE = "Full text"
_PART = re.compile(rf"^(part|parte|book|livro|volume|vol\.)\s+{ORDINAL}", re.IGNORECASE)
_CHAPTER = re.compile(rf"^(chapter|chap\.|cap[ií]tulo|cap\.)\s+{ORDINAL}", re.IGNORECASE)
_MIN_NUMBERED_CHAPTERS = 2
_NUMBERED_MAJORITY = 2  # how many times more numbered headings than depth found, to trust them instead


@dataclass(frozen=True)
class Section:
    """Consecutive blocks under one heading. The title is None before a chapter's first subheading."""

    title: str | None
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Chapter:
    """Attributes:
    number: position in the book, from 1. Unique, which a printed number is not, and
        0 for what comes before the first chapter. The title keeps any printed number.
    title: the heading as printed.
    sections: the chapter's content, in order.
    """

    number: int
    title: str
    sections: tuple[Section, ...]


@dataclass(frozen=True)
class BookStructure:
    title: str | None
    author: str | None
    language: str | None
    chapters: tuple[Chapter, ...]


def build_structure(document: ExtractedDocument) -> BookStructure:
    """Group a document's blocks into chapters and sections."""
    groups = _split_chapters(document.blocks)
    chapters: list[Chapter] = []
    number = 0
    for title, blocks in groups:
        sections = _sections(blocks)
        if not sections:
            continue  # a part divider or an empty front page: a heading without any text
        if title is not None:
            number += 1
        chapters.append(Chapter(number if title else 0, title or FRONT_MATTER_TITLE, sections))

    if len(chapters) == 1 and chapters[0].number == 0:  # no headings at all
        only = chapters[0]
        chapters = [Chapter(1, document.title or _WHOLE_BOOK_TITLE, only.sections)]

    return BookStructure(document.title, document.author, document.language, tuple(chapters))


def _split_chapters(blocks: tuple[Block, ...]) -> list[tuple[str | None, list[Block]]]:
    """Cut the blocks at chapter headings. The first group, titled None, is what precedes them."""
    starts = _chapter_starts(blocks)
    groups: list[tuple[str | None, list[Block]]] = [(None, [])]
    for index, block in enumerate(blocks):
        if index in starts:
            groups.append((block.text, []))
        groups[-1][1].append(block)
    return groups


def _chapter_starts(blocks: tuple[Block, ...]) -> set[int]:
    headings = [(index, block) for index, block in enumerate(blocks) if block.kind is BlockKind.HEADING]
    if not headings:
        return set()

    by_depth = _starts_by_depth(headings)
    # A heading that says it is a chapter outranks its depth, when depth clearly got it wrong:
    # a table of contents with one entry leaves every "Chapter N" of a novel as a subsection.
    # Otherwise it is only the label printed above a title that depth already found.
    numbered = [block.level or 1 for _, block in headings if _CHAPTER.match(block.text)]
    if len(numbered) >= _MIN_NUMBERED_CHAPTERS and len(numbered) >= len(by_depth) * _NUMBERED_MAJORITY:
        return {index for index, block in headings if (block.level or 1) <= min(numbered)}
    return by_depth


def _starts_by_depth(headings: list[tuple[int, Block]]) -> set[int]:
    base = _chapter_level([block.level or 1 for _, block in headings])
    starts: set[int] = set()
    level_inside_part: int | None = None
    for position, (index, block) in enumerate(headings):
        if block.level == base:
            starts.add(index)
            following = headings[position + 1][1].level if position + 1 < len(headings) else None
            is_part = _PART.match(block.text) and following is not None and following > base
            level_inside_part = following if is_part else None
        elif block.level == level_inside_part:
            starts.add(index)
    return starts


def _chapter_level(levels: list[int]) -> int:
    top = min(levels)
    deeper = [level for level in levels if level > top]
    if levels.count(top) == 1 and deeper:
        return min(deeper)  # a single outermost heading is the book's title
    return top


def _sections(blocks: list[Block]) -> tuple[Section, ...]:
    """Cut a chapter at its subheadings, dropping sections without any text."""
    if not blocks:
        return ()
    sections: list[tuple[str | None, list[Block]]] = [(None, [])]
    chapter_heading = blocks[0] if blocks[0].kind is BlockKind.HEADING else None
    for block in blocks:
        if block.kind is BlockKind.HEADING and block is not chapter_heading:
            sections.append((block.text, []))
        sections[-1][1].append(block)
    return tuple(
        Section(title, tuple(content))
        for title, content in sections
        if any(block.kind is not BlockKind.HEADING for block in content)
    )
