from pathlib import Path

import pymupdf
import pytest

from app.config.settings import PdfConfig, PdfOcrConfig
from app.errors import EmptyDocumentError, InvalidDocumentError, ScannedDocumentError
from app.ingestion.base import BlockKind, DocumentFormat, ExtractedDocument
from app.ingestion.pdf_loader import PdfLoader
from tests.documents import (
    add_page_furniture,
    write_encrypted_pdf,
    write_image_pdf,
    write_pdf,
    write_table_pdf,
)

CONFIG = PdfConfig(extractor="pymupdf", extract_tables=True, ocr=PdfOcrConfig(enabled=False))
BODY = "A paragraph of ordinary body text that goes on for a while, so that it reads like a page of a real book."


def headings(document):
    return [(block.level, block.text) for block in document.blocks if block.kind is BlockKind.HEADING]


def test_reads_text_pages_and_metadata(tmp_path):
    path = write_pdf(
        tmp_path / "b.pdf", [[(BODY, 11)], [("Second page text.", 11)]], title="A Title", author="An Author"
    )

    document = PdfLoader(CONFIG).load(path)

    assert document.format is DocumentFormat.PDF
    assert document.title == "A Title"
    assert document.author == "An Author"
    assert [(block.text, block.page_start, block.page_end) for block in document.blocks] == [
        (BODY, 1, 1),
        ("Second page text.", 2, 2),
    ]


def test_table_of_contents_entries_become_headings(tmp_path):
    pages = [
        [("Chapter One", 11), (BODY, 11)],
        [("Middle of the chapter.", 11)],
        [("Chapter Two", 11), (BODY, 11)],
    ]
    toc = [[1, "Chapter One", 1], [1, "Chapter Two", 3]]
    path = write_pdf(tmp_path / "b.pdf", pages, toc=toc)

    document = PdfLoader(CONFIG).load(path)

    assert headings(document) == [(1, "Chapter One"), (1, "Chapter Two")]
    assert [b.page_start for b in document.blocks if b.kind is BlockKind.HEADING] == [1, 3]


def test_a_toc_entry_missing_from_the_page_is_added_at_its_top(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[(BODY, 11)]], toc=[[1, "Not printed", 1]])

    document = PdfLoader(CONFIG).load(path)

    assert document.blocks[0].text == "Not printed"
    assert document.blocks[0].kind is BlockKind.HEADING


def test_headings_below_the_toc_become_sections(tmp_path):
    pages = [[("Chapter One", 20), (BODY, 11), ("A Section", 14), (BODY, 11)]]
    path = write_pdf(tmp_path / "b.pdf", pages, toc=[[1, "Chapter One", 1]])

    assert headings(PdfLoader(CONFIG).load(path)) == [(1, "Chapter One"), (2, "A Section")]


def test_font_sizes_find_headings_without_a_toc(tmp_path):
    pages = [
        [("Chapter One", 20), (BODY, 11), ("A Section", 14), (BODY, 11)],
        [("Chapter Two", 20), (BODY, 11)],
    ]
    path = write_pdf(tmp_path / "b.pdf", pages)

    assert headings(PdfLoader(CONFIG).load(path)) == [
        (1, "Chapter One"),
        (2, "A Section"),
        (1, "Chapter Two"),
    ]


def test_bold_lines_at_body_size_are_headings(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[(BODY, 11), ("A Bold Heading", 0), (BODY, 11)]])

    assert [text for _, text in headings(PdfLoader(CONFIG).load(path))] == ["A Bold Heading"]


def test_large_text_with_a_full_stop_is_not_a_heading(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[("A large sentence that ends properly.", 20), (BODY, 11), (BODY, 11)]])

    assert headings(PdfLoader(CONFIG).load(path)) == []


def test_chapter_words_at_body_size_are_headings(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[("Capítulo 3", 11), (BODY, 11), (BODY, 11)]])

    assert [text for _, text in headings(PdfLoader(CONFIG).load(path))] == ["Capítulo 3"]


def test_a_heading_at_the_top_of_a_page_is_still_a_heading(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[(BODY, 11), (BODY, 11)]])
    with pymupdf.open(path) as document:
        document[0].insert_text((72, 50), "A Chapter Title", fontsize=20)
        document.saveIncr()

    blocks = PdfLoader(CONFIG).load(path).blocks

    assert [block.text for block in blocks if block.kind is BlockKind.HEADING] == ["A Chapter Title"]


def test_page_edges_are_flagged_as_margins(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[(BODY, 11)], [(BODY, 11)]])
    add_page_furniture(path, header="Running Header", page_numbers=True)

    blocks = PdfLoader(CONFIG).load(path).blocks

    assert {block.text for block in blocks if block.margin} == {"Running Header", "1", "2"}
    assert not any(block.margin for block in blocks if block.text == BODY)


def test_words_broken_across_lines_are_rejoined(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[("Filler text for the page, which is plain and long enough.", 11)]])

    with pymupdf.open(path) as document:
        document[0].insert_text((72, 200), "the oppor-", fontsize=11)
        document[0].insert_text((72, 214), "tunity cost of it all", fontsize=11)
        document.saveIncr()

    assert any("the opportunity cost of it all" in block.text for block in PdfLoader(CONFIG).load(path).blocks)


def test_compound_words_keep_their_hyphen_before_a_capital(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[("Filler text for the page, which is plain and long enough.", 11)]])

    with pymupdf.open(path) as document:
        document[0].insert_text((72, 200), "the Anglo-", fontsize=11)
        document[0].insert_text((72, 214), "Saxon world", fontsize=11)
        document.saveIncr()

    assert any("Anglo- Saxon" in block.text for block in PdfLoader(CONFIG).load(path).blocks)


def test_indented_lines_start_new_paragraphs(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[("Filler text for the page, which is plain and long enough.", 11)]])

    with pymupdf.open(path) as document:
        page = document[0]
        lines = [
            (72, 200, "the first paragraph runs along and"),
            (72, 214, "ends here on its second line."),
            (90, 228, "The second paragraph starts with an"),
            (72, 242, "indented line, the way books do."),
        ]
        for x, y, line in lines:
            page.insert_text((x, y), line, fontsize=11)
        document.saveIncr()

    texts = [block.text for block in PdfLoader(CONFIG).load(path).blocks]

    assert "the first paragraph runs along and ends here on its second line." in texts
    assert "The second paragraph starts with an indented line, the way books do." in texts


def test_tables_are_extracted_in_position(tmp_path):
    path = write_table_pdf(tmp_path / "b.pdf")

    blocks = PdfLoader(CONFIG).load(path).blocks

    assert [block.kind for block in blocks] == [BlockKind.PARAGRAPH, BlockKind.TABLE]
    assert "Brazil" in blocks[1].text and "Lisbon" in blocks[1].text


def test_table_extraction_can_be_switched_off(tmp_path):
    path = write_table_pdf(tmp_path / "b.pdf")
    config = CONFIG.model_copy(update={"extract_tables": False})

    assert not any(block.kind is BlockKind.TABLE for block in PdfLoader(config).load(path).blocks)


def test_scanned_pdfs_are_rejected_with_a_reason(tmp_path):
    path = write_image_pdf(tmp_path / "b.pdf", pages=3)

    with pytest.raises(ScannedDocumentError, match="OCR"):
        PdfLoader(CONFIG).load(path)


def test_scanned_pdfs_go_to_the_ocr_loader_when_there_is_one(tmp_path):
    class FakeOcr:
        def load(self, path: Path) -> ExtractedDocument:
            return ExtractedDocument(DocumentFormat.PDF, ())

    path = write_image_pdf(tmp_path / "b.pdf", pages=3)

    assert PdfLoader(CONFIG, ocr_loader=FakeOcr()).load(path).blocks == ()


def test_a_few_scanned_pages_do_not_reject_the_book(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[(BODY, 11)], [(BODY, 11)], [(BODY, 11)]])

    with pymupdf.open(path) as document:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
        document.new_page().insert_image(pymupdf.Rect(0, 0, 100, 100), pixmap=pixmap)
        document.save(tmp_path / "mixed.pdf")

    assert len(PdfLoader(CONFIG).load(tmp_path / "mixed.pdf").blocks) == 3


def test_blank_pdfs_are_empty_not_scanned(tmp_path):
    path = write_pdf(tmp_path / "b.pdf", [[]])

    with pytest.raises(EmptyDocumentError):
        PdfLoader(CONFIG).load(path)


def test_corrupted_pdfs_are_rejected(tmp_path):
    path = tmp_path / "b.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not really a pdf")

    with pytest.raises(InvalidDocumentError, match="corrupted"):
        PdfLoader(CONFIG).load(path)


def test_password_protected_pdfs_are_rejected(tmp_path):
    path = write_encrypted_pdf(tmp_path / "b.pdf")

    with pytest.raises(InvalidDocumentError, match="password"):
        PdfLoader(CONFIG).load(path)
