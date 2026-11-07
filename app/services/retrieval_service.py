"""Searching the library. Everything that needs passages comes through here."""

from app.config.settings import RetrievalConfig, Settings
from app.errors import NothingToSearchError
from app.retrieval.base import BookScope, Reranker, RetrievalFilters
from app.retrieval.bm25 import ChunkSource
from app.retrieval.factory import create_pipeline
from app.retrieval.pipeline import RetrievalPipeline, RetrievalResult
from app.services.index_service import IndexService
from app.storage.catalog import Book, BookCatalog, BookStatus, IndexRecord
from app.utils.logging import get_logger, log_event, operation

logger = get_logger("services.retrieval")

# A book being reindexed stays searchable: its current revision is intact until the swap.
_SEARCHABLE = (BookStatus.INDEXED, BookStatus.REINDEXING)


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        catalog: BookCatalog,
        indexes: IndexService,
        chunks: ChunkSource,
        reranker: Reranker,
    ) -> None:
        self._settings = settings
        self._catalog = catalog
        self._indexes = indexes
        self._chunks = chunks
        self._reranker = reranker
        self._pipelines: dict[tuple[int, str], RetrievalPipeline] = {}

    def search(self, query: str, filters: RetrievalFilters, config: RetrievalConfig | None = None) -> RetrievalResult:
        """Search the library.

        Args:
            query: the question.
            filters: limits the search. No book IDs means every indexed book.
            config: a strategy other than the configured one, for experiments.

        Raises:
            NothingToSearchError: no indexed book matches the filters.
        """
        index = self._indexes.active()
        books = self._searchable_books(filters, index)
        scopes = [BookScope(book.book_id, book.revision, book.language, filters) for book in books]

        with operation(logger, "search", books=[book.book_id for book in books]):
            result = self._pipeline(index, config or self._settings.retrieval).run(query, scopes)
            log_event(
                logger,
                "search finished",
                passages=len(result.passages),
                candidates=len(result.candidates),
                retrieval_seconds=result.retrieval_seconds,
                rerank_seconds=result.rerank_seconds,
            )
        return result

    def _searchable_books(self, filters: RetrievalFilters, index: IndexRecord | None) -> list[Book]:
        if index is None:
            raise NothingToSearchError("The library is empty. Add a book first.")
        books = [
            book
            for book in self._catalog.list_books()
            if book.status in _SEARCHABLE
            and book.index_version == index.version
            and (not filters.book_ids or book.book_id in filters.book_ids)
            and (not filters.languages or book.language in filters.languages)
        ]
        if not books:
            raise NothingToSearchError("None of the selected books is indexed.")
        return books

    def _pipeline(self, index: IndexRecord, config: RetrievalConfig) -> RetrievalPipeline:
        key = (index.version, config.model_dump_json())
        if key not in self._pipelines:
            self._pipelines[key] = create_pipeline(
                config,
                self._indexes.query_embedder(index),
                self._indexes.store(index),
                self._chunks,
                self._reranker,
            )
        return self._pipelines[key]
