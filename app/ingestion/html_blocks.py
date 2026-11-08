"""Turns HTML into blocks. Both EPUB chapters and rendered Markdown arrive as HTML."""

import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from bs4.element import NavigableString, Tag

from app.ingestion.base import Block, BlockKind

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)  # every EPUB chapter is XHTML

_HEADING_LEVELS = {f"h{level}": level for level in range(1, 7)}
_SKIPPED = {"head", "script", "style", "template", "svg", "nav", "noscript", "object", "embed", "iframe"}
_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "body",
    "dd",
    "details",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "header",
    "hr",
    "li",
    "main",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "ul",
    *_HEADING_LEVELS,
}


def html_to_blocks(html: str | bytes, anchors: frozenset[str] = frozenset()) -> tuple[list[Block], dict[str, int]]:
    """Extract the blocks of an HTML document.

    Args:
        html: the document.
        anchors: element IDs whose position the caller needs.

    Returns:
        The blocks in reading order, and for each anchor found, the index of the first
        block at or after it.
    """
    soup = BeautifulSoup(html, "lxml")
    blocks: list[Block] = []
    positions: dict[str, int] = {}
    _walk(soup.body or soup, blocks, anchors, positions)
    return blocks, positions


def _walk(node: Tag, blocks: list[Block], anchors: frozenset[str], positions: dict[str, int]) -> None:
    inline: list[str] = []

    def flush_inline() -> None:
        if text := _collapse("".join(inline)):
            blocks.append(Block(BlockKind.PARAGRAPH, text))
        inline.clear()

    for child in node.children:
        if isinstance(child, NavigableString):
            if type(child) is NavigableString:  # subclasses are comments, doctypes and the like
                inline.append(str(child))
            continue
        if not isinstance(child, Tag) or child.name in _SKIPPED:
            continue
        if child.name not in _BLOCK_TAGS and not child.find(_BLOCK_TAGS):
            for tag in (child, *child.find_all(id=True)):
                _record_anchor(tag, len(blocks) + (1 if "".join(inline).strip() else 0), anchors, positions)
            inline.append(child.get_text())
            continue

        flush_inline()
        _record_anchor(child, len(blocks), anchors, positions)
        _append_block(child, blocks, anchors, positions)

    flush_inline()


def _append_block(tag: Tag, blocks: list[Block], anchors: frozenset[str], positions: dict[str, int]) -> None:
    for inner in tag.find_all(id=True):
        if tag.name in _HEADING_LEVELS or tag.name in {"p", "pre", "table", "ul", "ol"}:
            _record_anchor(inner, len(blocks), anchors, positions)

    if tag.name in _HEADING_LEVELS:
        if text := _collapse(tag.get_text()):
            blocks.append(Block(BlockKind.HEADING, text, level=_HEADING_LEVELS[tag.name]))
    elif tag.name == "pre":
        if text := tag.get_text().strip("\n"):
            blocks.append(Block(BlockKind.CODE, text))
    elif tag.name == "table":
        if text := _table_text(tag):
            blocks.append(Block(BlockKind.TABLE, text))
    elif tag.name in {"ul", "ol"}:
        if text := _list_text(tag):
            blocks.append(Block(BlockKind.LIST, text))
    elif tag.find(_BLOCK_TAGS):
        _walk(tag, blocks, anchors, positions)
    elif text := _collapse(tag.get_text()):
        blocks.append(Block(BlockKind.PARAGRAPH, text))


def _record_anchor(tag: Tag, position: int, anchors: frozenset[str], positions: dict[str, int]) -> None:
    if (identifier := tag.get("id")) in anchors:
        positions.setdefault(identifier, position)


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _list_text(tag: Tag, depth: int = 0) -> str:
    lines: list[str] = []
    ordered = tag.name == "ol"
    for number, item in enumerate(tag.find_all("li", recursive=False), start=1):
        nested = item.find_all(["ul", "ol"], recursive=False)
        own_text = _collapse("".join(_own_strings(item)))
        marker = f"{number}." if ordered else "-"
        if own_text:
            lines.append(f"{'  ' * depth}{marker} {own_text}")
        lines.extend(_list_text(inner, depth + 1) for inner in nested)
    return "\n".join(line for line in lines if line)


def _own_strings(item: Tag) -> list[str]:
    """The text of a list item, without the lists nested inside it."""
    strings = []
    for child in item.children:
        if isinstance(child, Tag):
            if child.name not in {"ul", "ol"}:
                strings.append(child.get_text())
        elif isinstance(child, NavigableString):
            strings.append(str(child))
    return strings


def _table_text(tag: Tag) -> str:
    """Render a table as a Markdown pipe table, so that its rows stay aligned with its header."""
    rows = [
        [_collapse(cell.get_text()).replace("|", "\\|") for cell in row.find_all(["th", "td"], recursive=False)]
        for row in tag.find_all("tr")
    ]
    rows = [row for row in rows if row]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = [f"| {' | '.join(row)} |" for row in rows]
    lines.insert(1, f"|{' --- |' * width}")
    return "\n".join(lines)
