"""Rebuilding the whole library from its original documents."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.errors import MissingOriginalError, NothingToReindexError
from app.generation.summarization import ChapterSummarizer
from app.ingestion.base import DocumentFormat
from app.services.book_service import indexed_update
from app.services.index_service import IndexService
from app.services.ingestion_service import IngestionService
from app.services.library_data import LibraryData
from app.services.recovery_service import REINDEX_ALL, LibraryGuard
from app.storage.catalog import Book, BookStatus, BookUpdate, IndexRecord
from app.storage.chroma import ChunkStore
from app.storage.repositories import OriginalRecord
from app.utils.logging import get_logger, log_event, operation

logger = get_logger("services.library")

_NO_REVISION = 0


@dataclass(frozen=True)
class ReindexReport:
    """What a rebuild did.

    Attributes:
        index_version: the index now active.
        collection: the collection that holds it.
        embedding_model: the model that built it.
        books: how many books it holds.
        chunks: how many chunks they came to.
        adopted: books brought back from preserved originals.
        failed: books that were already failed and stayed that way, with the reason.
        summaries_regenerated: saved summaries written again.
    """

    index_version: int
    collection: str
    embedding_model: str
    books: int
    chunks: int
    adopted: tuple[str, ...]
    failed: tuple[str, ...]
    summaries_regenerated: int


class LibraryService:
    def __init__(
        self,
        data: LibraryData,
        guard: LibraryGuard,
        ingestion: IngestionService,
        indexes: IndexService,
        summarizer: ChapterSummarizer,
    ) -> None:
        self._data = data
        self._catalog = data.catalog
        self._guard = guard
        self._ingestion = ingestion
        self._indexes = indexes
        self._summarizer = summarizer

    def reindex_all(
        self, regenerate_summaries: bool = False, on_progress: Callable[[str], None] | None = None
    ) -> ReindexReport:
        """Rebuild the whole index from the original documents, with the current configuration.

        This is what changes the embedding model, its dimensions, the chunking or the metadata
        schema. The new index fills up in a staging collection while the old one keeps serving
        searches, and every book moves to it in one transaction. A failure leaves the library
        exactly as it was.

        Originals that a reset kept, and the catalog no longer knows about, come back here.

        Args:
            regenerate_summaries: write the saved summaries again, from the new chunks.
            on_progress: told what is happening.

        Raises:
            MissingOriginalError: an original is gone. Nothing has changed.
            NothingToReindexError: the library has no documents.
            LibraryBusyError: another operation is running.
            BookRagError: a book failed. Nothing has changed.
        """
        report = on_progress or (lambda message: None)
        with self._guard.exclusive(), operation(logger, REINDEX_ALL):
            adopted = self._adopt_preserved_originals()
            books = self._catalog.list_books()
            if not books:
                raise NothingToReindexError("The library has no documents to rebuild from.")
            _require_originals(books)

            staging = self._indexes.create_staging()
            store = self._indexes.store(staging)
            revisions = {book.book_id: book.revision + 1 for book in books}
            statuses = {book.book_id: book.status.value for book in books}
            previous = self._catalog.active_index()
            journal = self._catalog.begin_operation(
                REINDEX_ALL,
                collection=staging.collection,
                revisions=revisions,
                statuses=statuses,
                previous_collection=previous.collection if previous else None,
                previous_revisions={book.book_id: book.revision for book in books},
            )
            changes: list[BookUpdate] = []
            failed: list[str] = []
            try:
                for position, book in enumerate(books, start=1):
                    report(f"Indexing {book.title} ({position} of {len(books)})")
                    change = self._rebuild_book(book, revisions[book.book_id], staging, store)
                    if change is None:
                        failed.append(book.book_id)
                    else:
                        changes.append(change)
            except Exception:
                self._abandon(staging, revisions, statuses)
                self._catalog.end_operation(journal)
                raise

            self._catalog.finish_rebuild(staging.version, changes)
            for book in books:
                self._data.record_source(book)
            self._drop_previous(previous, books, changes)
            self._catalog.end_operation(journal)

            result = ReindexReport(
                index_version=staging.version,
                collection=staging.collection,
                embedding_model=staging.embedding_model,
                books=len(changes),
                chunks=sum(change.fields["chunk_count"] for change in changes),
                adopted=tuple(adopted),
                failed=tuple(failed),
                summaries_regenerated=self._regenerate_summaries(report) if regenerate_summaries else 0,
            )
            log_event(logger, "library rebuilt", books=result.books, chunks=result.chunks)
            return result

    def recover(self) -> list[str]:
        """Clean up after an interrupted process. Call this when the application starts."""
        return self._guard.recover()

    def _adopt_preserved_originals(self) -> list[str]:
        """Bring back the originals that a reset kept while it cleared the catalog."""
        known = {book.book_id for book in self._catalog.list_books()}
        checksums = {book.checksum for book in self._catalog.list_books()}
        adopted = []
        for record in self._data.originals.discover():
            if record.book_id not in known and record.checksum not in checksums:
                self._catalog.add(_book_from(record))
                checksums.add(record.checksum)
                adopted.append(record.book_id)
        return adopted

    def _rebuild_book(self, book: Book, revision: int, staging: IndexRecord, store: ChunkStore) -> BookUpdate | None:
        """Index one book into the staging index.

        Returns:
            What to record for it, or None for a book that was failing already: a book that
            never worked must not stand in the way of the rest of the library.
        """
        self._catalog.update(book.book_id, status=BookStatus.REINDEXING)
        try:
            processed = self._ingestion.ingest(
                Path(book.original_path),
                DocumentFormat(book.format),
                book.book_id,
                revision,
                Path(book.original_filename).stem,
                staging,
                store,
            )
        except Exception as exc:
            if book.status is not BookStatus.FAILED:
                raise
            store.delete_revision(book.book_id, revision)
            self._data.processed.delete_revision(book.book_id, revision)
            self._catalog.update(book.book_id, status=BookStatus.FAILED, status_detail=str(exc))
            return None
        return indexed_update(book, revision, processed, staging)

    def _abandon(self, staging: IndexRecord, revisions: dict[str, int], statuses: dict[str, str]) -> None:
        self._data.server.delete_collection(staging.collection)
        for book_id, revision in revisions.items():
            self._data.processed.delete_revision(book_id, revision)
        for book_id, status in statuses.items():
            self._catalog.update(book_id, status=BookStatus(status))

    def _drop_previous(self, previous: IndexRecord | None, books: list[Book], changes: list[BookUpdate]) -> None:
        if previous is not None:
            self._data.server.delete_collection(previous.collection)
        rebuilt = {change.book_id for change in changes}
        for book in books:
            if book.book_id in rebuilt and book.revision != _NO_REVISION:
                self._data.processed.delete_revision(book.book_id, book.revision)

    def _regenerate_summaries(self, report: Callable[[str], None]) -> int:
        """Write saved summaries again, skipping any whose chapter no longer exists."""
        count = 0
        for book_id, path in self._data.summaries.saved():
            number, summary_type = _parse_summary_name(path)
            if number in {chapter for chapter, _ in self._catalog.chapters(book_id)}:
                report(f"Summarizing {book_id}, chapter {number} again")
                self._summarizer.save(self._summarizer.summarize(book_id, number, summary_type))
                count += 1
        return count


def _require_originals(books: list[Book]) -> None:
    missing = [book.book_id for book in books if not Path(book.original_path).exists()]
    if missing:
        raise MissingOriginalError(f"The original documents of {', '.join(missing)} are gone. Nothing was changed.")


def _book_from(record: OriginalRecord) -> Book:
    return Book(
        book_id=record.book_id,
        title=Path(record.original_filename).stem,
        author=None,
        original_filename=record.original_filename,
        original_path=record.original_path,
        checksum=record.checksum,
        format=record.format,
        language=None,
        chapter_count=0,
        chunk_count=0,
        embedding_model=None,
        index_version=None,
        status=BookStatus.PENDING,
        status_detail=None,
        revision=_NO_REVISION,
        created_at=record.created_at,
        indexed_at=None,
    )


def _parse_summary_name(path: Path) -> tuple[int, str]:
    """Read back the chapter and type from a name like chapter_04_standard."""
    _, number, summary_type = path.stem.split("_", 2)
    return int(number), summary_type
