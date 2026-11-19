"""Cleans extracted text without changing its meaning: Unicode, ligatures, invisible characters
and whitespace, the cleaning that applies to any text (specs/005-markdown-only, research.md R6).
"""

import unicodedata
from dataclasses import replace

from app.ingestion.base import Block, BlockKind, ExtractedDocument

_LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"})
# Soft hyphen, zero-width space, word joiner, BOM. Zero-width joiners stay: some scripts need them.
_INVISIBLE = dict.fromkeys(map(ord, "­​⁠﻿"))
_FREE_TEXT = (BlockKind.PARAGRAPH, BlockKind.HEADING)


class Normalizer:
    def normalize(self, document: ExtractedDocument) -> ExtractedDocument:
        cleaned = [replace(block, text=_clean(block)) for block in document.blocks]
        return replace(document, blocks=tuple(block for block in cleaned if block.text))


def _clean(block: Block) -> str:
    text = unicodedata.normalize("NFC", block.text).translate(_LIGATURES).translate(_INVISIBLE)
    if block.kind in _FREE_TEXT:
        return " ".join(text.split())
    return "\n".join(line.rstrip() for line in text.splitlines()).strip("\n")
