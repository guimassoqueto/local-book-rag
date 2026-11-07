import json

import pytest

from app.errors import DuplicateBookError, InvalidDocumentError, UnsupportedLanguageError
from app.ingestion.base import DocumentFormat
from app.ingestion.chunker import Chunker
from app.ingestion.epub_loader import EpubLoader
from app.ingestion.markdown_loader import MarkdownLoader
from app.ingestion.normalizer import Normalizer
from app.ingestion.pdf_loader import PdfLoader
from app.ingestion.pipeline import IngestionPipeline
from app.services.book_service import BookService
from app.storage.catalog import BookCatalog, BookStatus
from app.storage.repositories import OriginalDocuments, ProcessedDocuments
from tests.documents import write_epub, write_pdf

TEXT = "The quick brown fox jumps over the lazy dog, and then it goes back to the forest to rest for the day."
MARKDOWN = f"# One\n\n{TEXT}\n\n## Sub\n\n{TEXT}\n\n# Two\n\n{TEXT}\n"


class WordCounter:
    def count(self, text):
        return len(text.split())


@pytest.fixture
def data(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def service(settings, data):
    pipeline = IngestionPipeline(
        loaders={
            DocumentFormat.PDF: PdfLoader(settings.pdf),
            DocumentFormat.EPUB: EpubLoader(),
            DocumentFormat.MARKDOWN: MarkdownLoader(),
        },
        normalizer=Normalizer(settings.normalization),
        chunker=Chunker(settings.chunking, WordCounter()),
        supported_languages=("en", "pt"),
    )
    return BookService(
        catalog=BookCatalog(data / "metadata" / "catalog.db"),
        originals=OriginalDocuments(data / "original_books"),
        processed=ProcessedDocuments(data / "processed"),
        pipeline=pipeline,
        max_upload_bytes=2**20,
    )


def upload(tmp_path, name="book.md", text=MARKDOWN):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_adding_a_book_records_it(service, tmp_path):
    book = service.add_book(upload(tmp_path), "My Book.md")

    assert book.book_id == "book_001"
    assert book.title == "My Book"
    assert book.original_filename == "My Book.md"
    assert book.format == "markdown"
    assert book.language == "en"
    assert book.chapter_count == 2
    assert book.chunk_count == 3
    assert book.status is BookStatus.PENDING
    assert service.list_books() == [book]


def test_the_original_is_stored_under_a_name_of_ours(service, tmp_path, data):
    book = service.add_book(upload(tmp_path), "../../evil name.md")

    stored = data / "original_books" / "book_001" / "original.md"
    assert stored.read_text(encoding="utf-8") == MARKDOWN
    assert book.original_path == str(stored)
    assert book.original_filename == "evil name.md"


def test_every_stage_is_kept_for_debugging(service, tmp_path, data):
    service.add_book(upload(tmp_path), "book.md")

    directory = data / "processed" / "book_001" / "r1"
    assert json.loads((directory / "extracted.json").read_text(encoding="utf-8"))["blocks"]
    assert json.loads((directory / "normalized.json").read_text(encoding="utf-8"))["blocks"]
    lines = (directory / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["chunk_id"] == "book_001_chapter_01_chunk_0000"


def test_chunks_can_be_read_back(service, tmp_path, data):
    service.add_book(upload(tmp_path), "book.md")

    chunks = ProcessedDocuments(data / "processed").load_chunks("book_001", 1)

    assert [chunk.chapter_title for chunk in chunks] == ["One", "One", "Two"]


def test_the_same_file_twice_is_a_duplicate(service, tmp_path):
    service.add_book(upload(tmp_path), "book.md")

    with pytest.raises(DuplicateBookError, match="already in the library as book_001"):
        service.add_book(upload(tmp_path), "another name.md")

    assert len(service.list_books()) == 1


def test_a_second_book_gets_its_own_id_and_leaves_the_first_alone(service, tmp_path):
    first = service.add_book(upload(tmp_path), "one.md")
    second = service.add_book(upload(tmp_path, text=MARKDOWN + "\n\nAnother paragraph."), "two.md")

    assert second.book_id == "book_002"
    assert service.list_books() == [first, second]


def test_a_rejected_upload_leaves_nothing_behind(service, tmp_path, data):
    with pytest.raises(InvalidDocumentError):
        service.add_book(upload(tmp_path, "book.pdf", "not a pdf"), "book.pdf")

    assert service.list_books() == []
    assert not (data / "original_books").exists()


def test_a_failed_book_is_marked_and_says_why(service, tmp_path):
    german = "Der schnelle braune Fuchs springt über den faulen Hund und geht dann zurück in den Wald."

    with pytest.raises(UnsupportedLanguageError):
        service.add_book(upload(tmp_path, text=f"# Eins\n\n{german}\n\n# Zwei\n\n{german}\n"), "book.md")

    [book] = service.list_books()
    assert book.status is BookStatus.FAILED
    assert "'de'" in book.status_detail


def test_pdf_books_keep_their_pages(service, tmp_path):
    pages = [
        [("Chapter One", 11), (TEXT, 11)],
        [(TEXT, 11)],
        [("Chapter Two", 11), (TEXT, 11)],
    ]
    path = write_pdf(tmp_path / "b.pdf", pages, toc=[[1, "Chapter One", 1], [1, "Chapter Two", 3]])

    book = service.add_book(path, "b.pdf")

    chunks = service._processed.load_chunks(book.book_id, book.revision)
    assert book.format == "pdf"
    assert {chunk.chapter_title for chunk in chunks} == {"Chapter One", "Chapter Two"}
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 3


def test_epub_books_have_no_pages_but_keep_their_chapters(service, tmp_path):
    path = write_epub(tmp_path / "b.epub", [("a.xhtml", "One", f"<p>{TEXT}</p>"), ("b.xhtml", "Two", f"<p>{TEXT}</p>")])

    book = service.add_book(path, "b.epub")

    chunks = service._processed.load_chunks(book.book_id, book.revision)
    assert book.title == "An EPUB Book"
    assert book.author == "An Author"
    assert [chunk.chapter_title for chunk in chunks] == ["One", "Two"]
    assert all(chunk.page_start is None for chunk in chunks)
