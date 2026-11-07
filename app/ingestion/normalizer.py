"""Cleans extracted text without changing its meaning."""

import re
import unicodedata
from collections import Counter
from dataclasses import replace

from app.config.settings import NormalizationConfig
from app.ingestion.base import Block, BlockKind, ExtractedDocument

_MIN_MARGIN_REPEATS = 3  # the same text on this many pages is a running header, not content
_PAGE_NUMBER = re.compile(r"^(#|[ivxlcdm]+|[-–—\s]*#[-–—\s]*)$", re.IGNORECASE)
_NUMBER_AT_EDGE = re.compile(r"^\d+\b|\b\d+$")
_ROMAN_AT_EDGE = re.compile(r"^[ivxlc]+\b|\b[ivxlc]+$")
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
_LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"})
# Soft hyphen, zero-width space, word joiner, BOM. Zero-width joiners stay: some scripts need them.
_INVISIBLE = dict.fromkeys(map(ord, "­​⁠﻿"))
_SENTENCE_END = (".", "!", "?", "…", ":", ";", '"', "”", "»", ")")
_FREE_TEXT = (BlockKind.PARAGRAPH, BlockKind.HEADING)


class Normalizer:
    def __init__(self, config: NormalizationConfig) -> None:
        self._config = config

    def normalize(self, document: ExtractedDocument) -> ExtractedDocument:
        blocks = list(document.blocks)
        if self._config.remove_repeated_margins:
            blocks = _drop_running_margins(blocks)
        cleaned = [replace(block, text=_clean(block), margin=False) for block in blocks]
        merged = _merge_across_pages([block for block in cleaned if block.text])
        return replace(document, blocks=tuple(merged))


def _drop_running_margins(blocks: list[Block]) -> list[Block]:
    margins = [block for block in blocks if block.margin]
    repeats = Counter(_margin_key(block.text) for block in margins)
    offsets = _printed_page_offsets(margins)

    def is_running(block: Block) -> bool:
        key = _margin_key(block.text)
        return bool(_PAGE_NUMBER.match(key)) or repeats[key] >= _MIN_MARGIN_REPEATS or bool(offsets & _offsets(block))

    return [block for block in blocks if not (block.margin and is_running(block))]


def _printed_page_offsets(margins: list[Block]) -> set[tuple[str, int]]:
    """Find how far printed page numbers sit from physical ones.

    A running head like "10.13. Debugging 99" is unique to its section, so it never
    repeats. What gives it away is its number, which follows the page at a fixed distance.
    Front matter counts separately, in Roman numerals.
    """
    votes = Counter(offset for block in margins for offset in _offsets(block))
    return {offset for offset, count in votes.items() if count >= _MIN_MARGIN_REPEATS}


def _offsets(block: Block) -> set[tuple[str, int]]:
    """The distance to the physical page of each number at the edges of a block."""
    if block.page_start is None:
        return set()
    text = block.text.strip()
    arabic = {("arabic", block.page_start - int(number)) for number in _NUMBER_AT_EDGE.findall(text)}
    roman = {("roman", block.page_start - _roman_value(number)) for number in _ROMAN_AT_EDGE.findall(text)}
    return arabic | roman


def _roman_value(numeral: str) -> int:
    values = [_ROMAN_VALUES[letter] for letter in numeral]
    return sum(
        -value if value < following else value for value, following in zip(values, [*values[1:], 0], strict=True)
    )


def _margin_key(text: str) -> str:
    """Running headers repeat with a changing page number, so numbers don't tell them apart."""
    return re.sub(r"\d+", "#", " ".join(text.casefold().split()))


def _clean(block: Block) -> str:
    text = unicodedata.normalize("NFC", block.text).translate(_LIGATURES).translate(_INVISIBLE)
    if block.kind in _FREE_TEXT:
        return " ".join(text.split())
    return "\n".join(line.rstrip() for line in text.splitlines()).strip("\n")


def _merge_across_pages(blocks: list[Block]) -> list[Block]:
    """Rejoin paragraphs that a page break cut in two."""
    merged: list[Block] = []
    for block in blocks:
        if merged and _continues(merged[-1], block):
            previous = merged[-1]
            separator = "" if previous.text.endswith("-") else " "
            text = previous.text.removesuffix("-") + separator + block.text
            merged[-1] = replace(previous, text=text, page_end=block.page_end)
        else:
            merged.append(block)
    return merged


def _continues(previous: Block, block: Block) -> bool:
    if previous.kind is not BlockKind.PARAGRAPH or block.kind is not BlockKind.PARAGRAPH:
        return False
    if previous.page_end is None or block.page_start != previous.page_end + 1:
        return False
    return not previous.text.endswith(_SENTENCE_END) and block.text[0].islower()
