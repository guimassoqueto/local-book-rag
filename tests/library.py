"""A whole library over real files, a real catalog and an embedded ChromaDB, with fake models."""

import dataclasses
import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager

import chromadb

from app.config.settings import Settings
from app.generation.summarization import ChapterSummarizer
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
from app.services.library_data import LibraryData
from app.services.library_service import LibraryService
from app.services.recovery_service import LibraryGuard
from app.services.reset_service import ResetService
from app.services.retrieval_service import RetrievalService
from app.storage.catalog import BookCatalog
from app.storage.chroma import ChromaServer
from app.storage.repositories import OriginalDocuments, ProcessedDocuments, SummaryDocuments
from tests.fakes import FakeEmbedder, FakeLLM, FakeReranker, FakeRuntime, WordCounter

TEXT = "The quick brown fox jumps over the lazy dog, and then it goes back to the forest to rest for the day."
MARKDOWN = f"# One\n\n{TEXT}\n\n## Sub\n\n{TEXT}\n\n# Two\n\n{TEXT}\n"


class Library:
    """Everything a process would build at startup, so a new one acts like a restart."""

    def __init__(self, settings: Settings, data, embedder=None):
        self.root = data
        self.settings = settings
        self.runtime = FakeRuntime()
        self.embedder = embedder or FakeEmbedder()
        self.server = ChromaServer("embedded", 0, client=chromadb.PersistentClient(path=str(data / "chroma")))
        self.catalog = BookCatalog(data / "metadata" / "catalog.db")
        self.processed = ProcessedDocuments(data / "processed")
        self.originals = OriginalDocuments(data / "original_books", data / "archive")
        self.summary_documents = SummaryDocuments(data / "summaries")
        self.data = LibraryData(self.catalog, self.originals, self.processed, self.summary_documents, self.server)
        self.guard = LibraryGuard(data / "metadata" / "library.lock", self.data)
        self.indexes = IndexService(settings, self.catalog, self.server, self.runtime)
        self.indexes.query_embedder = lambda record: self.embedder
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
        self.ingestion = IngestionService(settings, pipeline, self.processed, self.embedder, self.runtime)
        self.books = BookService(self.data, self.guard, self.ingestion, self.indexes, max_upload_bytes=2**20)
        self.retrieval = RetrievalService(settings, self.catalog, self.indexes, self.processed, FakeReranker())
        self.llm = FakeLLM(["## Chapter overview\nA summary with enough words to look up."])
        self.summarizer = ChapterSummarizer(
            settings, self.llm, self.catalog, self.processed, self.summary_documents, self.retrieval
        )
        self.library = LibraryService(self.data, self.guard, self.ingestion, self.indexes, self.summarizer)
        self.resets = ResetService(self.data, self.guard)

    def store(self):
        return self.indexes.store(self.indexes.active())

    def add(self, directory, name="one.md", text=MARKDOWN):
        return self.books.add_book(upload(directory, name, text), name)

    def with_settings(self, section, **values):
        """The same data seen by a process started with another configuration."""
        current = getattr(self.settings, section)
        return Library(
            self.settings.model_copy(update={section: current.model_copy(update=values)}), self.root, self.embedder
        )


def upload(directory, name="book.md", text=MARKDOWN):
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def other_text(label):
    """A different document, so that its checksum differs."""
    return MARKDOWN + f"\n\nOne more paragraph, about {label}, to tell this book from the others.\n"


# The progress of library operations (specs/004-library-progress): comparing an operation run with
# progress and without it.


class ProgressLog(logging.Handler):
    """The progress logger's records. The application's logger stops propagating once configured."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages(self) -> list[str]:
        return [record.getMessage() for record in self.records]

    def undeclared(self) -> list[str]:
        return [
            getattr(record, "fields", {}).get("stage") for record in self.records if "undeclared" in record.getMessage()
        ]


@contextmanager
def progress_log() -> Iterator[ProgressLog]:
    logger = logging.getLogger("book_rag.progress")
    handler, level = ProgressLog(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def trace_journal(library: "Library") -> list[tuple]:
    """Record every journal entry opened and closed, with the library's root path written as <root>."""
    calls: list[tuple] = []
    catalog = library.catalog
    begin, end = catalog.begin_operation, catalog.end_operation
    root = str(library.root)

    def begin_operation(kind, book_id=None, **details):
        calls.append(("begin", kind, book_id, json.loads(json.dumps(details, default=str).replace(root, "<root>"))))
        return begin(kind, book_id, **details)

    def end_operation(operation_id):
        calls.append(("end",))
        return end(operation_id)

    catalog.begin_operation = begin_operation
    catalog.end_operation = end_operation
    return calls


def library_state(library: "Library") -> dict:
    """What the library holds: its books, its files, its vectors and its open journal entries."""
    root = library.root
    files = {
        str(path.relative_to(root)): _comparable(path.read_bytes(), root)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not {"chroma", "metadata"} & set(path.relative_to(root).parts)
    }
    books = []
    for book in library.catalog.list_books():
        row = {key: value for key, value in dataclasses.asdict(book).items() if key not in ("created_at", "indexed_at")}
        books.append(json.loads(json.dumps(row, default=str).replace(str(root), "<root>")))
    collections = sorted(getattr(item, "name", item) for item in library.server.client.list_collections())
    index = library.catalog.active_index()
    vectors: dict | str = {}
    if index is not None and index.collection not in collections:
        vectors = "the active collection is gone"  # a reset that failed halfway can leave the catalog naming it
    elif index is not None:
        store = library.indexes.store(index)
        books_now = library.catalog.list_books()
        vectors = {book.book_id: store.count_revision(book.book_id, book.revision) for book in books_now}
    journal = [(operation.kind, operation.book_id) for operation in library.catalog.open_operations()]
    return {"books": books, "files": files, "vectors": vectors, "collections": collections, "journal": journal}


def _comparable(content: bytes, root) -> bytes:
    """A file as two libraries in different places, at different times, would both write it."""
    content = content.replace(str(root).encode(), b"<root>")
    return re.sub(rb'"created_at": "[^"]*"', b'"created_at": "<time>"', content)
