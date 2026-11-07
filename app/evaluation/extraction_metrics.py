"""Document extraction quality, measured against the structure a book declares for itself."""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from ebooklib import epub

from app.ingestion.base import BlockKind, comparable_text
from app.ingestion.epub_loader import flatten_toc
from app.ingestion.pipeline import ProcessedDocument

_SECTION_NUMBER = re.compile(r"^\s*\d+(\.\d+)*\.?\s+")


@dataclass(frozen=True)
class ExtractionScores:
    """Attributes:
    toc_entries: entries in the book's own table of contents.
    toc_coverage: the share of them that survived as headings. Losing one attributes a whole
        chapter's text to the chapter before it.
    chapters: chapters detected.
    chunks: chunks produced.
    pages_covered: the share of a PDF's pages that reached a chunk. None for other formats.
    """

    toc_entries: int
    toc_coverage: float | None
    chapters: int
    chunks: int
    pages_covered: float | None


def toc_titles(path: Path) -> list[str]:
    """Read a document's own table of contents."""
    if path.suffix == ".pdf":
        with pymupdf.open(path) as document:
            return [title for _, title, page in document.get_toc() if page > 0]
    if path.suffix == ".epub":
        return [entry.title for entry in flatten_toc(epub.read_epub(str(path)).toc)]
    return []


def _title_key(title: str) -> str:
    """Identify a title without its number: outlines often leave out the number a heading prints."""
    return comparable_text(_SECTION_NUMBER.sub("", title))


def extraction_scores(path: Path, processed: ProcessedDocument) -> ExtractionScores:
    titles = toc_titles(path)
    # Counted, not just found: Think Python has 20 sections called "Glossary", and losing six of
    # them must show even though the title survives elsewhere.
    wanted = Counter(_title_key(title) for title in titles)
    found = Counter(_title_key(block.text) for block in processed.normalized.blocks if block.kind is BlockKind.HEADING)
    kept = sum((wanted & found).values())
    return ExtractionScores(
        toc_entries=len(titles),
        toc_coverage=kept / len(titles) if titles else None,
        chapters=len(processed.structure.chapters),
        chunks=len(processed.chunks),
        pages_covered=_pages_covered(path, processed),
    )


def _pages_covered(path: Path, processed: ProcessedDocument) -> float | None:
    if path.suffix != ".pdf":
        return None
    with pymupdf.open(path) as document:
        total = len(document)
    covered: set[int] = set()
    for chunk in processed.chunks:
        if chunk.page_start is not None and chunk.page_end is not None:
            covered.update(range(chunk.page_start, chunk.page_end + 1))
    return len(covered) / total
