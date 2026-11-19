"""The structured document representation shared by every stage of ingestion."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class DocumentFormat(StrEnum):
    """What the library reads. Books are converted to Markdown outside it (specs/005-markdown-only)."""

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
    """

    kind: BlockKind
    text: str
    level: int | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    """A document after extraction: flat blocks in reading order, and its declared language.

    The book's title is not read from it: it is the name of the file the book arrived as.
    """

    format: DocumentFormat
    blocks: tuple[Block, ...]
    language: str | None = None


# What follows "Chapter" or "Part" in a real one: a number, a Roman numeral or a number word.
ORDINAL = (
    r"(\d+|m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{1,3}|v)|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|onze|doze)\b"
)


class DocumentLoader(Protocol):
    def load(self, path: Path) -> ExtractedDocument:
        """Extract a document.

        Args:
            path: the document.

        Raises:
            EmptyDocumentError: the file holds no text.
        """
        ...
