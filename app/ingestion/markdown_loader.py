"""Markdown extraction: headings are real structure, so a parser finds them, not a regex.

A book's title is its file's name and it has no author (specs/005-markdown-only), so front matter
gives only the language. It is still removed from the text.
"""

from pathlib import Path
from typing import Any

import markdown
import yaml

from app.errors import EmptyDocumentError
from app.ingestion.base import DocumentFormat, ExtractedDocument
from app.ingestion.html_blocks import html_to_blocks

_EXTENSIONS = ["tables", "fenced_code", "sane_lists"]
_FRONT_MATTER_FENCE = "---"


class MarkdownLoader:
    def load(self, path: Path) -> ExtractedDocument:
        metadata, body = _split_front_matter(path.read_text(encoding="utf-8"))
        blocks = html_to_blocks(markdown.markdown(body, extensions=_EXTENSIONS))
        if not blocks:
            raise EmptyDocumentError(f"{path.name} holds no text.")

        return ExtractedDocument(
            format=DocumentFormat.MARKDOWN,
            blocks=tuple(blocks),
            language=_text(metadata.get("language") or metadata.get("lang")),
        )


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.lstrip("﻿").splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONT_MATTER_FENCE:
        return {}, "".join(lines)
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _FRONT_MATTER_FENCE:
            try:
                metadata = yaml.safe_load("".join(lines[1:index]))
            except yaml.YAMLError:
                break  # a horizontal rule on the first line, not metadata
            if isinstance(metadata, dict):
                return metadata, "".join(lines[index + 1 :])
            break
    return {}, "".join(lines)


def _text(value: Any) -> str | None:
    return str(value).strip() or None if value is not None else None
