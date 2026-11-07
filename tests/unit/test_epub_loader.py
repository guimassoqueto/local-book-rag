import pytest
from ebooklib import epub

from app.errors import EmptyDocumentError, InvalidDocumentError
from app.ingestion.base import BlockKind, DocumentFormat
from app.ingestion.epub_loader import EpubLoader
from tests.documents import write_epub


def headings(document):
    return [(block.level, block.text) for block in document.blocks if block.kind is BlockKind.HEADING]


def test_reads_the_book_metadata(tmp_path):
    path = write_epub(
        tmp_path / "b.epub",
        [("a.xhtml", "One", "<p>Text.</p>")],
        title="O Livro",
        author="Alguém",
        language="pt",
    )

    document = EpubLoader().load(path)

    assert document.format is DocumentFormat.EPUB
    assert document.title == "O Livro"
    assert document.author == "Alguém"
    assert document.language == "pt"


def test_chapters_follow_the_reading_order(tmp_path):
    path = write_epub(
        tmp_path / "b.epub",
        [("a.xhtml", "One", "<p>First.</p>"), ("b.xhtml", "Two", "<p>Second.</p>")],
    )

    document = EpubLoader().load(path)

    assert [block.text for block in document.blocks] == ["One", "First.", "Two", "Second."]
    assert headings(document) == [(1, "One"), (1, "Two")]


def test_the_table_of_contents_decides_what_is_a_chapter(tmp_path):
    path = write_epub(
        tmp_path / "b.epub",
        [("a.xhtml", "Chapter One", "<h1>Chapter One</h1><p>Text.</p><h1>A heading in the text</h1><p>More.</p>")],
    )

    document = EpubLoader().load(path)

    assert headings(document) == [(1, "Chapter One"), (2, "A heading in the text")]


def test_a_chapter_title_buried_in_a_small_heading_is_promoted(tmp_path):
    path = write_epub(tmp_path / "b.epub", [("a.xhtml", "Chapter One", "<h4>Chapter One</h4><p>Text.</p>")])

    assert headings(EpubLoader().load(path)) == [(1, "Chapter One")]


def test_documents_outside_the_toc_continue_the_previous_chapter(tmp_path):
    chapters = [("a.xhtml", "One", "<p>Start.</p>"), ("b.xhtml", "Continued", "<p>Rest of it.</p>")]
    path = write_epub(tmp_path / "b.epub", chapters, toc=[epub.Link("a.xhtml", "One", "a")])

    document = EpubLoader().load(path)

    assert [block.text for block in document.blocks] == ["One", "Start.", "Rest of it."]
    assert headings(document) == [(1, "One")]


def test_nested_toc_entries_become_deeper_headings(tmp_path):
    chapters = [
        ("a.xhtml", "One", '<h1>One</h1><p>Intro.</p><h2 id="s1">Section</h2><p>Body.</p>'),
    ]
    toc = [(epub.Section("One", "a.xhtml"), [epub.Link("a.xhtml#s1", "Section", "s1")])]
    path = write_epub(tmp_path / "b.epub", chapters, toc=toc)

    assert headings(EpubLoader().load(path)) == [(1, "One"), (2, "Section")]


def test_an_entry_with_nothing_to_promote_adds_a_heading(tmp_path):
    path = write_epub(tmp_path / "b.epub", [("a.xhtml", "One", "<p>No heading in the text.</p>")])

    document = EpubLoader().load(path)

    assert document.blocks[0].kind is BlockKind.HEADING
    assert document.blocks[0].text == "One"
    assert document.blocks[1].text == "No heading in the text."


def test_without_a_toc_the_html_headings_are_kept(tmp_path):
    path = write_epub(tmp_path / "b.epub", [("a.xhtml", "One", "<h1>One</h1><p>T.</p><h2>Sub</h2><p>T.</p>")], toc=[])

    assert headings(EpubLoader().load(path)) == [(1, "One"), (2, "Sub")]


def test_pages_are_unavailable(tmp_path):
    path = write_epub(tmp_path / "b.epub", [("a.xhtml", "One", "<p>Text.</p>")])

    assert all(block.page_start is None for block in EpubLoader().load(path).blocks)


def test_a_book_without_text_is_rejected(tmp_path):
    path = write_epub(tmp_path / "b.epub", [("a.xhtml", "One", "<img src='x.png'/>")], toc=[])

    with pytest.raises(EmptyDocumentError):
        EpubLoader().load(path)


def test_a_corrupted_book_is_rejected(tmp_path):
    path = tmp_path / "b.epub"
    path.write_bytes(b"PK\x03\x04 this is not really a zip")

    with pytest.raises(InvalidDocumentError, match="corrupted"):
        EpubLoader().load(path)
