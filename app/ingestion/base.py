"""The structured document representation shared by every stage of ingestion."""

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class DocumentFormat(StrEnum):
    PDF = "pdf"
    EPUB = "epub"
    MARKDOWN = "markdown"


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    CODE = "code"


@dataclass(frozen=True)
class Block:
    """One structural element, in reading order.

    Attributes:
        kind: what the element is.
        text: its content. Lists, tables and code keep their line structure.
        level: heading depth, 1 being the outermost. None for anything but a heading.
        page_start: first page, or None where the format has no pages.
        page_end: last page, or None where the format has no pages.
        margin: found at the top or bottom edge of a page, so possibly a running header
            or footer. The normalizer decides.
    """

    kind: BlockKind
    text: str
    level: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    margin: bool = False


@dataclass(frozen=True)
class ExtractedDocument:
    """A document after extraction: flat blocks in reading order, and its metadata."""

    format: DocumentFormat
    blocks: tuple[Block, ...]
    title: str | None = None
    author: str | None = None
    language: str | None = None


# What follows "Chapter" or "Part" in a real one: a number, a Roman numeral or a number word.
ORDINAL = (
    r"(\d+|m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{1,3}|v)|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|onze|doze)\b"
)


def comparable_text(text: str) -> str:
    """Reduce text to its letters and digits, to match a heading against a table of contents."""
    return re.sub(r"\W+", "", text).casefold()


class DocumentLoader(Protocol):
    def load(self, path: Path) -> ExtractedDocument:
        """Extract a document.

        Raises:
            InvalidDocumentError: the file is corrupted.
            EmptyDocumentError: the file holds no text.
            ScannedDocumentError: the file is a scanned PDF and OCR is off.
        """
        ...
