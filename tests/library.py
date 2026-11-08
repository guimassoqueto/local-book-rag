"""A whole library over real files, a real catalog and an embedded ChromaDB, with fake models."""

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
