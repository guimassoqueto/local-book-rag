import json

import chromadb
import pytest

from app.config.settings import Settings
from app.errors import (
    DuplicateBookError,
    InvalidDocumentError,
    ReindexRequiredError,
    ServiceUnavailableError,
    UnsupportedLanguageError,
)
from app.ingestion.base import DocumentFormat
from app.ingestion.chunker import Chunker
from app.ingestion.epub_loader import EpubLoader
from app.ingestion.markdown_loader import MarkdownLoader
from app.ingestion.normalizer import Normalizer
from app.ingestion.pdf_loader import PdfLoader
from app.ingestion.pipeline import IngestionPipeline
from app.services.book_service import BookService
from app.services.index_service import IndexService
from app.services.ingestion_service import IngestionService
from app.storage.catalog import BookCatalog, BookStatus
from app.storage.chroma import ChromaServer, revision_filter, revision_key
from app.storage.repositories import OriginalDocuments, ProcessedDocuments
from tests.documents import write_epub, write_pdf
from tests.fakes import FakeEmbedder, FakeRuntime, WordCounter

TEXT = "The quick brown fox jumps over the lazy dog, and then it goes back to the forest to rest for the day."
MARKDOWN = f"# One\n\n{TEXT}\n\n## Sub\n\n{TEXT}\n\n# Two\n\n{TEXT}\n"


class Library:
    """A book service over real files, a real catalog and an embedded ChromaDB."""

    def __init__(self, settings: Settings, data, embedder=None):
        self.data = data
        self.settings = settings
        self.runtime = FakeRuntime()
        self.embedder = embedder or FakeEmbedder()
        self.server = ChromaServer("embedded", 0, client=chromadb.PersistentClient(path=str(data / "chroma")))
        self.catalog = BookCatalog(data / "metadata" / "catalog.db")
        self.processed = ProcessedDocuments(data / "processed")
        self.indexes = IndexService(settings, self.catalog, self.server, self.runtime)
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
        ingestion = IngestionService(settings, pipeline, self.processed, self.embedder, self.runtime)
        self.books = BookService(
            catalog=self.catalog,
            originals=OriginalDocuments(data / "original_books"),
            processed=self.processed,
            ingestion=ingestion,
            indexes=self.indexes,
            max_upload_bytes=2**20,
        )

    def store(self):
        return self.indexes.store(self.indexes.active())


@pytest.fixture
def data(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def library(settings, data):
    return Library(settings, data)


@pytest.fixture
def service(library):
    return library.books


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
    assert book.status is BookStatus.INDEXED
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


def test_a_book_is_recorded_with_what_indexed_it(library, tmp_path):
    book = library.books.add_book(upload(tmp_path), "book.md")

    assert book.embedding_model == library.settings.embedding.model
    assert book.index_version == 1
    assert book.indexed_at is not None
    assert book.status_detail is None


def test_every_chunk_gets_a_vector(library, tmp_path):
    book = library.books.add_book(upload(tmp_path), "book.md")

    assert library.store().count_revision(book.book_id, book.revision) == book.chunk_count


def test_stored_chunks_can_be_found(library, tmp_path):
    book = library.books.add_book(upload(tmp_path), "book.md")

    results = library.store().query(
        library.embedder.embed_query(TEXT), 10, revision_filter([revision_key(book.book_id, book.revision)])
    )

    assert {item.chunk.chapter_title for item in results} == {"One", "Two"}
    assert all(item.chunk.book_id == book.book_id for item in results)


def test_the_chapters_are_recorded_for_the_interface(library, tmp_path):
    book = library.books.add_book(upload(tmp_path), "book.md")

    assert library.catalog.chapters(book.book_id) == [(1, "One"), (2, "Two")]


def test_the_llm_leaves_the_gpu_before_bulk_embedding(library, tmp_path):
    library.books.add_book(upload(tmp_path), "book.md")

    assert library.runtime.unloaded == [library.settings.llm.model]


def test_a_failed_embedding_leaves_no_vectors_and_keeps_the_original(settings, data, tmp_path):
    library = Library(settings, data, FakeEmbedder(failure=ServiceUnavailableError("Ollama is down")))

    with pytest.raises(ServiceUnavailableError):
        library.books.add_book(upload(tmp_path), "book.md")

    [book] = library.books.list_books()
    assert book.status is BookStatus.FAILED
    assert book.status_detail == "Ollama is down"
    assert library.store().count() == 0
    assert (data / "original_books" / book.book_id / "original.md").exists()
    assert not (data / "processed" / book.book_id).exists()


def test_uploading_a_failed_book_again_retries_it(settings, data, tmp_path):
    embedder = FakeEmbedder(failure=ServiceUnavailableError("Ollama is down"))
    library = Library(settings, data, embedder)
    with pytest.raises(ServiceUnavailableError):
        library.books.add_book(upload(tmp_path), "book.md")

    embedder.failure = None
    book = library.books.add_book(upload(tmp_path), "book.md")

    assert book.book_id == "book_002"
    assert book.status is BookStatus.INDEXED
    assert library.books.list_books() == [book]


def test_a_changed_configuration_stops_new_books_until_a_reindex(settings, data, tmp_path):
    Library(settings, data).books.add_book(upload(tmp_path), "one.md")

    chunking = settings.chunking.model_copy(update={"target_size": 300})
    changed = Library(settings.model_copy(update={"chunking": chunking}), data)

    with pytest.raises(ReindexRequiredError):
        changed.books.add_book(upload(tmp_path, text=MARKDOWN + "\n\nAnother paragraph."), "two.md")

    assert len(changed.books.list_books()) == 1


def test_adding_a_second_book_leaves_the_first_ones_vectors_alone(library, tmp_path):
    first = library.books.add_book(upload(tmp_path), "one.md")
    library.books.add_book(upload(tmp_path, text=MARKDOWN + "\n\nAnother paragraph."), "two.md")

    assert library.store().count_revision(first.book_id, first.revision) == first.chunk_count


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


def test_pdf_books_keep_their_pages(library, tmp_path):
    pages = [
        [("Chapter One", 11), (TEXT, 11)],
        [(TEXT, 11)],
        [("Chapter Two", 11), (TEXT, 11)],
    ]
    path = write_pdf(tmp_path / "b.pdf", pages, toc=[[1, "Chapter One", 1], [1, "Chapter Two", 3]])

    book = library.books.add_book(path, "b.pdf")

    chunks = library.processed.load_chunks(book.book_id, book.revision)
    assert book.format == "pdf"
    assert {chunk.chapter_title for chunk in chunks} == {"Chapter One", "Chapter Two"}
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 3


def test_epub_books_have_no_pages_but_keep_their_chapters(library, tmp_path):
    path = write_epub(tmp_path / "b.epub", [("a.xhtml", "One", f"<p>{TEXT}</p>"), ("b.xhtml", "Two", f"<p>{TEXT}</p>")])

    book = library.books.add_book(path, "b.epub")

    chunks = library.processed.load_chunks(book.book_id, book.revision)
    assert book.title == "An EPUB Book"
    assert book.author == "An Author"
    assert [chunk.chapter_title for chunk in chunks] == ["One", "Two"]
    assert all(chunk.page_start is None for chunk in chunks)
