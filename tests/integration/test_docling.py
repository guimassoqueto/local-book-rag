"""Runs Docling's real models, which the first run downloads."""

import pytest

from app.ingestion.base import BlockKind
from app.ingestion.docling_loader import DoclingLoader
from app.ingestion.structure_extractor import build_structure
from tests.documents import write_pdf

pytestmark = pytest.mark.integration

BODY = "A paragraph of ordinary body text that goes on for a while, so that it reads like a page of a real book."


def test_extracts_a_hierarchy_that_the_structure_extractor_can_use(tmp_path):
    pages = [
        [("Chapter One", 22), (BODY, 11), ("1.1 A Section", 14), (BODY, 11)],
        [("Chapter Two", 22), (BODY, 11), ("2.1 Another Section", 14), (BODY, 11)],
    ]
    path = write_pdf(tmp_path / "book.pdf", pages, toc=[[1, "Chapter One", 1], [1, "Chapter Two", 2]])

    document = DoclingLoader(ocr=False).load(path)

    levels = {block.level for block in document.blocks if block.kind is BlockKind.HEADING}
    assert len(levels) > 1
    assert [chapter.title for chapter in build_structure(document).chapters] == ["Chapter One", "Chapter Two"]
    assert all(block.page_start for block in document.blocks)
