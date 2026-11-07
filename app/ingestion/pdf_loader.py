"""PDF extraction with PyMuPDF.

Headings come from the book's table of contents when it has one. Font sizes find the
rest: on their own for a PDF without a table of contents, and for the sections below it
otherwise. Page numbers are physical (1 is the first page of the file), which is what a
PDF viewer jumps to.
"""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf

from app.config.settings import PdfConfig
from app.errors import EmptyDocumentError, InvalidDocumentError, ScannedDocumentError
from app.ingestion.base import (
    ORDINAL,
    Block,
    BlockKind,
    DocumentFormat,
    DocumentLoader,
    ExtractedDocument,
    comparable_text,
)
from app.utils.logging import get_logger, log_event

logger = get_logger("ingestion.pdf")

_TEXT_FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP  # leaves ligatures expanded
_TEXT_BLOCK = 0
_BOLD_FLAG = 16
_MARGIN_FRACTION = 0.10  # share of the page height, at each end, where running headers live
_MIN_PAGE_CHARACTERS = 16  # fewer than this on a page is not a text layer
_MAX_SCANNED_SHARE = 0.5  # above this share of image-only pages, a PDF counts as scanned
_HEADING_SIZE_RATIO = 1.15
_MAX_HEADING_CHARACTERS = 160
_MAX_CHAPTER_WORD_CHARACTERS = 80
_MAX_HEADING_LEVELS = 3
_INDENT_FONT_RATIO = 0.8  # first-line indentation, relative to the font size
_MIN_LINES_TO_SPLIT = 3
_TERMINAL_PUNCTUATION = (".", "!", "?", "…", ":", '"', "”", "»", ")")
_NON_HEADING_ENDINGS = (".", ",", ";")
_CHAPTER_WORD = re.compile(rf"^(chapter|chap\.|cap[ií]tulo|cap\.|part|parte|book|livro)\s+{ORDINAL}", re.IGNORECASE)


@dataclass(frozen=True)
class _Line:
    text: str
    x0: float
    y0: float
    size: float
    bold: bool


@dataclass
class _Item:
    text: str
    y0: float
    size: float
    bold: bool
    margin: bool
    kind: BlockKind = BlockKind.PARAGRAPH
    level: int | None = None


@dataclass
class _Page:
    number: int
    items: list[_Item]
    characters: int
    has_images: bool


class PdfLoader:
    def __init__(self, config: PdfConfig, ocr_loader: DocumentLoader | None = None) -> None:
        """Create the loader.

        Args:
            config: extraction settings.
            ocr_loader: takes over scanned PDFs. Without one, they are rejected.
        """
        self._config = config
        self._ocr_loader = ocr_loader

    def load(self, path: Path) -> ExtractedDocument:
        try:
            document = pymupdf.open(path, filetype="pdf")
        except Exception as exc:  # PyMuPDF has no common base for its open errors
            raise InvalidDocumentError(f"{path.name} is a corrupted PDF: {exc}") from exc

        with document:
            if document.needs_pass:
                raise InvalidDocumentError(f"{path.name} is password-protected.")
            pages = [self._read_page(page, index + 1) for index, page in enumerate(document)]
            if self._is_scanned(pages, path):
                if self._ocr_loader is None:
                    raise ScannedDocumentError(
                        f"{path.name} has no text layer: its pages are images. Enable OCR with "
                        "pdf.ocr.enabled in config/ingestion.yaml to read it."
                    )
                log_event(logger, "scanned pdf sent to ocr", file=path.name)
                return self._ocr_loader.load(path)

            _mark_headings(pages)
            if toc := [entry for entry in document.get_toc() if 0 < entry[2] <= len(pages)]:
                _apply_toc(pages, toc)

            metadata = document.metadata or {}
            return ExtractedDocument(
                format=DocumentFormat.PDF,
                blocks=tuple(_to_blocks(pages)),
                title=(metadata.get("title") or "").strip() or None,
                author=(metadata.get("author") or "").strip() or None,
            )

    def _read_page(self, page: pymupdf.Page, number: int) -> _Page:
        height = page.rect.height
        tables = page.find_tables().tables if self._config.extract_tables else []
        table_boxes = [pymupdf.Rect(table.bbox) for table in tables]

        items: list[_Item] = []
        for block in page.get_text("dict", flags=_TEXT_FLAGS)["blocks"]:
            if block["type"] != _TEXT_BLOCK or _inside_any(block["bbox"], table_boxes):
                continue
            lines = [line for raw in block["lines"] if (line := _read_line(raw)) is not None]
            margin = block["bbox"][3] <= height * _MARGIN_FRACTION or block["bbox"][1] >= height * (
                1 - _MARGIN_FRACTION
            )
            for paragraph in _split_paragraphs(lines):
                if text := _join_lines(line.text for line in paragraph):
                    size, bold = _dominant_style(paragraph)
                    items.append(_Item(text, paragraph[0].y0, size, bold, margin))

        for table in tables:
            position = next((i for i, item in enumerate(items) if item.y0 >= table.bbox[1]), len(items))
            items.insert(position, _Item(table.to_markdown(), table.bbox[1], 0, False, False, BlockKind.TABLE))

        return _Page(number, items, sum(len(item.text) for item in items), bool(page.get_images()))

    def _is_scanned(self, pages: list[_Page], path: Path) -> bool:
        without_text = [page for page in pages if page.characters < _MIN_PAGE_CHARACTERS]
        image_only = [page for page in without_text if page.has_images]
        if len(without_text) == len(pages) and not image_only:
            raise EmptyDocumentError(f"{path.name} holds no text.")
        if image_only:
            log_event(logger, "pages without text", file=path.name, pages=len(image_only), total=len(pages))
        return len(image_only) > len(pages) * _MAX_SCANNED_SHARE


def _inside_any(box: Any, tables: list[pymupdf.Rect]) -> bool:
    x = (box[0] + box[2]) / 2
    y = (box[1] + box[3]) / 2
    return any(table.contains(pymupdf.Point(x, y)) for table in tables)


def _read_line(raw: dict[str, Any]) -> _Line | None:
    spans = [span for span in raw["spans"] if span["text"].strip()]
    if not spans:
        return None
    longest = max(spans, key=lambda span: len(span["text"]))
    bold = bool(longest["flags"] & _BOLD_FLAG) or "bold" in longest["font"].lower()
    return _Line("".join(span["text"] for span in raw["spans"]), raw["bbox"][0], raw["bbox"][1], longest["size"], bold)


def _split_paragraphs(lines: list[_Line]) -> list[list[_Line]]:
    """Split a text block at first-line indents: books separate paragraphs with those, not gaps."""
    if len(lines) < _MIN_LINES_TO_SPLIT:
        return [lines] if lines else []

    left, count = Counter(round(line.x0) for line in lines).most_common(1)[0]
    if count * 2 < len(lines):
        return [lines]  # no common left edge: centered or free-form text

    paragraphs = [[lines[0]]]
    for previous, line in zip(lines, lines[1:], strict=False):
        indented = line.x0 - left >= line.size * _INDENT_FONT_RATIO
        if indented and previous.text.rstrip().endswith(_TERMINAL_PUNCTUATION):
            paragraphs.append([line])
        else:
            paragraphs[-1].append(line)
    return paragraphs


def _join_lines(lines: Any) -> str:
    text = ""
    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            continue
        if not text:
            text = line
        elif text[-1] in "-­" and text[-2:-1].isalpha() and line[0].islower():
            text = text[:-1] + line  # a word broken across lines
        else:
            text = f"{text} {line}"
    return text


def _dominant_style(lines: list[_Line]) -> tuple[float, bool]:
    sizes: Counter[float] = Counter()
    bold_characters = 0
    for line in lines:
        sizes[round(line.size, 1)] += len(line.text)
        bold_characters += len(line.text) if line.bold else 0
    return sizes.most_common(1)[0][0], bold_characters * 2 > sum(sizes.values())


def _body_size(pages: list[_Page]) -> float:
    sizes: Counter[float] = Counter()
    for page in pages:
        for item in page.items:
            if item.kind is BlockKind.PARAGRAPH and not item.margin:
                sizes[item.size] += len(item.text)
    return sizes.most_common(1)[0][0] if sizes else 0.0


def _looks_like_heading(item: _Item, body_size: float) -> bool:
    text = item.text
    if item.kind is not BlockKind.PARAGRAPH:
        return False
    if not 3 <= len(text) <= _MAX_HEADING_CHARACTERS or text.endswith(_NON_HEADING_ENDINGS):
        return False
    if not any(character.isalpha() for character in text):
        return False
    if item.size >= body_size * _HEADING_SIZE_RATIO:
        return True
    if item.size >= body_size and len(text) <= _MAX_CHAPTER_WORD_CHARACTERS and _CHAPTER_WORD.match(text):
        return True
    return item.bold and item.size >= body_size


def _mark_headings(pages: list[_Page]) -> None:
    """Turn heading-like text into headings, the largest font being the outermost level."""
    body_size = _body_size(pages)
    candidates = [item for page in pages for item in page.items if _looks_like_heading(item, body_size)]
    sizes = sorted({item.size for item in candidates}, reverse=True)
    levels = {size: min(rank, _MAX_HEADING_LEVELS) for rank, size in enumerate(sizes, start=1)}
    for item in candidates:
        item.kind = BlockKind.HEADING
        item.level = levels[item.size]


def _apply_toc(pages: list[_Page], toc: list[list[Any]]) -> None:
    """Promote the headings the table of contents names, and demote the others to sections below it."""
    deepest = max(level for level, _, _ in toc)
    for page in pages:
        for item in page.items:
            if item.kind is BlockKind.HEADING:
                item.level = deepest + 1

    for level, title, page_number in toc:
        page = pages[page_number - 1]
        wanted = comparable_text(title)
        matches = [item for item in page.items if _names_entry(item, wanted)]
        if matches:
            matches[0].kind = BlockKind.HEADING
            matches[0].level = level
            matches[0].text = " ".join(title.split())
            page.items = [item for item in page.items if item not in matches[1:]]
        else:
            heading = _Item(" ".join(title.split()), 0, 0, False, False, BlockKind.HEADING, level)
            page.items.insert(0, heading)


def _names_entry(item: _Item, wanted: str) -> bool:
    if item.kind is BlockKind.TABLE or item.level == 0:
        return False
    text = comparable_text(item.text)
    if text == wanted:
        return True
    return item.kind is BlockKind.HEADING and bool(text) and (text in wanted or wanted in text)


def _to_blocks(pages: list[_Page]) -> list[Block]:
    return [
        Block(item.kind, item.text, item.level, page.number, page.number, item.margin)
        for page in pages
        for item in page.items
    ]
