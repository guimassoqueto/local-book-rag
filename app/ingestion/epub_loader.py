"""EPUB extraction, in spine order, with chapters taken from the book's own table of contents."""

import warnings
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote

import ebooklib
from ebooklib import epub

from app.errors import EmptyDocumentError, InvalidDocumentError
from app.ingestion.base import Block, BlockKind, DocumentFormat, ExtractedDocument, comparable_text
from app.ingestion.html_blocks import html_to_blocks

_NEAR_HEADING_WINDOW = 4  # blocks after a TOC target in which its printed heading may appear


@dataclass(frozen=True)
class _TocEntry:
    file: str
    fragment: str | None
    title: str
    depth: int


class EpubLoader:
    def load(self, path: Path) -> ExtractedDocument:
        book = _read(path)
        entries = _flatten_toc(book.toc)
        by_file: dict[str, list[_TocEntry]] = defaultdict(list)
        for entry in entries:
            by_file[entry.file].append(entry)

        blocks: list[Block] = []
        current_depth = 0
        for item_id, linear in book.spine:
            item = book.get_item_with_id(item_id)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT or linear == "no":
                continue
            file_entries = by_file.get(unquote(item.get_name()), [])
            anchors = frozenset(entry.fragment for entry in file_entries if entry.fragment)
            content, positions = html_to_blocks(item.get_content(), anchors)
            if entries:
                content, current_depth = _apply_toc(content, positions, file_entries, current_depth)
            blocks.extend(content)

        if not blocks:
            raise EmptyDocumentError(f"{path.name} holds no text.")
        return ExtractedDocument(
            format=DocumentFormat.EPUB,
            blocks=tuple(blocks),
            title=_first_metadata(book, "title"),
            author=_first_metadata(book, "creator"),
            language=_first_metadata(book, "language"),
        )


def _read(path: Path) -> epub.EpubBook:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # EbookLib warns about its own option defaults
            return epub.read_epub(str(path), options={"ignore_ncx": False})
    except Exception as exc:  # EbookLib lets zip, XML and key errors out as they are
        raise InvalidDocumentError(f"{path.name} is a corrupted EPUB: {exc}") from exc


def _first_metadata(book: epub.EpubBook, name: str) -> str | None:
    values = book.get_metadata("DC", name)
    return values[0][0].strip() or None if values else None


def _flatten_toc(toc: object, depth: int = 0) -> list[_TocEntry]:
    entries: list[_TocEntry] = []
    for node in toc if isinstance(toc, list | tuple) else [toc]:
        if isinstance(node, tuple | list) and len(node) == 2 and not isinstance(node[0], list | tuple):
            parent, children = node
            entries.extend(_entry(parent, depth))
            entries.extend(_flatten_toc(children, depth + 1))
        elif isinstance(node, list | tuple):
            entries.extend(_flatten_toc(node, depth))
        else:
            entries.extend(_entry(node, depth))
    return entries


def _entry(node: object, depth: int) -> list[_TocEntry]:
    href = getattr(node, "href", None) or getattr(node, "file_name", None)
    title = getattr(node, "title", None)
    if not href or not title:
        return []
    file, _, fragment = href.partition("#")
    return [_TocEntry(unquote(file), fragment or None, " ".join(title.split()), depth)]


def _apply_toc(
    blocks: list[Block],
    positions: dict[str, int],
    entries: list[_TocEntry],
    depth_before_file: int,
) -> tuple[list[Block], int]:
    """Make the table of contents decide the heading levels of one spine document.

    The printed headings of EPUBs are unreliable (a chapter's title can be an h3, or an
    image), so an entry promotes the heading it points at, or adds one when there is none.
    Headings the table of contents does not know about become sections of the entry
    above them.

    Args:
        blocks: the document's blocks, with the levels of its own HTML.
        positions: where each entry's fragment is.
        entries: the entries that point into this document.
        depth_before_file: the depth of the last entry seen in earlier documents.

    Returns:
        The blocks with their final levels, and the depth of the last entry applied.
    """
    promoted: dict[int, _TocEntry] = {}
    added: dict[int, list[_TocEntry]] = defaultdict(list)
    for entry in entries:
        position = positions.get(entry.fragment, 0) if entry.fragment else 0
        heading = _heading_near(blocks, position, entry.title, promoted)
        if heading is None:
            added[position].append(entry)
        else:
            promoted[heading] = entry

    def toc_heading(entry: _TocEntry) -> Block:
        return Block(BlockKind.HEADING, entry.title, level=entry.depth + 1)

    result: list[Block] = []
    depth = depth_before_file
    for index, block in enumerate(blocks):
        for entry in added.pop(index, ()):
            depth = entry.depth
            result.append(toc_heading(entry))
        if index in promoted:
            depth = promoted[index].depth
            result.append(toc_heading(promoted[index]))
        elif block.kind is BlockKind.HEADING:
            result.append(replace(block, level=depth + 2))
        else:
            result.append(block)

    for entries_past_the_end in added.values():
        for entry in entries_past_the_end:
            depth = entry.depth
            result.append(toc_heading(entry))
    return result, depth


def _heading_near(blocks: list[Block], position: int, title: str, taken: dict[int, _TocEntry]) -> int | None:
    """Find the heading an entry points at, each heading answering to one entry only.

    A chapter and its first section can share a word ("Tuples" and "Tuples are immutable"),
    so exact matches go first.
    """
    wanted = comparable_text(title)
    window = range(position, min(position + _NEAR_HEADING_WINDOW, len(blocks)))
    candidates = [i for i in window if blocks[i].kind is BlockKind.HEADING and i not in taken]
    texts = {i: comparable_text(blocks[i].text) for i in candidates}
    exact = [i for i in candidates if texts[i] == wanted]
    partial = [i for i in candidates if texts[i] and (texts[i] in wanted or wanted in texts[i])]
    return next(iter(exact + partial), None)
