"""Changing one book at a time: adding, replacing, reindexing and removing."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from app.errors import ConfirmationRequiredError, DuplicateBookError, MissingOriginalError
from app.ingestion.base import DocumentFormat
from app.ingestion.chunker import Chunk
from app.ingestion.pipeline import ProcessedDocument
from app.ingestion.validation import safe_filename, validate_upload
from app.services.index_service import IndexService
from app.services.ingestion_service import IngestionService
from app.services.library_data import LibraryData
from app.services.recovery_service import ADD_BOOK, REMOVE_BOOK, REPLACE_BOOK, LibraryGuard
from app.storage.catalog import Book, BookStatus, BookUpdate, IndexRecord, utc_now
from app.utils.hashing import file_checksum
from app.utils.logging import get_logger, log_event, operation

logger = get_logger("services.books")

_FIRST_REVISION = 1


@dataclass(frozen=True)
class _Upload:
    path: Path
    name: str
    format: DocumentFormat
    checksum: str


def indexed_update(
    book: Book, revision: int, processed: ProcessedDocument, index: IndexRecord, **extra: Any
) -> BookUpdate:
    """What the catalog records once a revision of a book is indexed and verified."""
    chapters = [(chapter.number, chapter.title) for chapter in processed.structure.chapters]
    return BookUpdate(
        book_id=book.book_id,
        chapters=chapters,
        fields={
            "title": processed.title,
            "author": processed.author,
            "language": processed.language,
            "chapter_count": len(chapters),
            "chunk_count": len(processed.chunks),
            "embedding_model": index.embedding_model,
            "index_version": index.version,
            "status": BookStatus.INDEXED,
            "status_detail": None,
            "revision": revision,
            "indexed_at": utc_now(),
            **extra,
        },
    )


class BookService:
    def __init__(
        self,
        data: LibraryData,
        guard: LibraryGuard,
        ingestion: IngestionService,
        indexes: IndexService,
        max_upload_bytes: int,
    ) -> None:
        self._data = data
        self._catalog = data.catalog
        self._guard = guard
        self._ingestion = ingestion
        self._indexes = indexes
        self._max_upload_bytes = max_upload_bytes

    def list_books(self) -> list[Book]:
        return self._catalog.list_books()

    def get_book(self, book_id: str) -> Book:
        return self._catalog.get(book_id)

    def chapters(self, book_id: str) -> list[tuple[int, str]]:
        return self._catalog.chapters(book_id)

    def chunks(self, book_id: str) -> list[Chunk]:
        book = self._catalog.get(book_id)
        return self._data.processed.load_chunks(book_id, book.revision)

    def add_book(self, upload: Path, filename: str) -> Book:
        """Add a document to the library, leaving every other book as it was.

        Args:
            upload: where the upload is on disk.
            filename: the name it arrived with.

        Returns:
            The new book.

        Raises:
            DuplicateBookError: the same file is already in the library.
            ReindexRequiredError: the configuration no longer matches the index.
            LibraryBusyError: another operation is running.
            BookRagError: the document was rejected. Nothing is recorded for a file that
                failed validation; a failure after it leaves a FAILED book, whose derived
                data is removed. Uploading the file again retries it.
        """
        with self._guard.exclusive():
            document = self._read_upload(upload, filename)
            existing = self._catalog.find_by_checksum(document.checksum)
            if existing is not None and existing.status is not BookStatus.FAILED:
                raise DuplicateBookError(existing.book_id, existing.title)

            # Checked first: a failed book must not vanish because its retry can't go ahead.
            index = self._indexes.require_writable()
            if existing is not None:
                with self._journal(REMOVE_BOOK, existing.book_id, archive=False):
                    self._data.delete_book(existing.book_id, archive=False)

            book_id = self._catalog.next_book_id()
            with operation(logger, ADD_BOOK, book_id=book_id), self._journal(ADD_BOOK, book_id) as journal:
                original = self._data.originals.store(document.path, book_id, document.format, _FIRST_REVISION)
                book = self._new_book(book_id, document, original)
                self._catalog.add(book)
                self._data.record_source(book)
                try:
                    processed = self._ingest(book, original, _FIRST_REVISION, index)
                except Exception as exc:
                    self._catalog.update(book_id, status=BookStatus.FAILED, status_detail=str(exc))
                    self._data.discard_revision(book_id, _FIRST_REVISION)
                    self._catalog.end_operation(journal)
                    raise
                log_event(logger, "book added", chunks=len(processed.chunks))
                return self._catalog.apply(indexed_update(book, _FIRST_REVISION, processed, index))

    def replace_book(self, book_id: str, upload: Path, filename: str) -> Book:
        """Swap a book for a new document, keeping its ID.

        The replacement is indexed next to the book as a new revision, which stays out of
        searches until it is verified. The swap is one transaction, so at every moment a search
        finds one whole revision, and the old one only goes after that.

        Raises:
            DuplicateBookError: the document is already in the library.
            ReindexRequiredError: the configuration no longer matches the index.
            LibraryBusyError: another operation is running.
            BookRagError: the replacement failed. The book is as it was.
        """
        with self._guard.exclusive():
            book = self._catalog.get(book_id)
            document = self._read_upload(upload, filename)
            if (existing := self._catalog.find_by_checksum(document.checksum)) is not None:
                raise DuplicateBookError(existing.book_id, existing.title)

            index = self._indexes.require_writable()
            revision = book.revision + 1
            staged_path = self._data.originals.path_for(book_id, document.format, revision)
            with (
                operation(logger, REPLACE_BOOK, book_id=book_id),
                self._swap_journal(book, revision, staged_path) as journal,
            ):
                staged = self._data.originals.store(document.path, book_id, document.format, revision)
                replacement = _replaced(book, document, staged)
                processed = self._index_revision(book, replacement, revision, index, staged, journal)
                extra = {
                    "original_filename": document.name,
                    "original_path": str(staged),
                    "checksum": document.checksum,
                    "format": document.format.value,
                }
                updated = self._catalog.apply(indexed_update(book, revision, processed, index, **extra))
                self._data.record_source(updated)
                self._data.drop_replaced_revision(book.book_id, book.revision, book.original_path)
                self._data.summaries.delete(book_id)  # they describe the text that just went away
                return updated

    def reindex_book(self, book_id: str) -> Book:
        """Process a book again from its original, as a new revision of the active index.

        This retries a failed book. Changing what the whole index is made of takes reindex_all.

        Raises:
            MissingOriginalError: the original document is gone.
            ReindexRequiredError: the configuration no longer matches the index.
            LibraryBusyError: another operation is running.
            BookRagError: reindexing failed. The book is as it was.
        """
        with self._guard.exclusive():
            book = self._catalog.get(book_id)
            original = Path(book.original_path)
            if not original.exists():
                raise MissingOriginalError(f"The original of {book_id} is no longer at {original}.")

            index = self._indexes.require_writable()
            revision = book.revision + 1
            with (
                operation(logger, "reindex_book", book_id=book_id),
                self._swap_journal(book, revision, None) as journal,
            ):
                processed = self._index_revision(book, book, revision, index, None, journal)
                updated = self._catalog.apply(indexed_update(book, revision, processed, index))
                self._data.drop_replaced_revision(book.book_id, book.revision, None)
                return updated

    def remove_book(self, book_id: str, confirmation: str, archive_original: bool = False) -> None:
        """Remove a book and everything derived from it, leaving every other book as it was.

        Args:
            book_id: the book.
            confirmation: has to repeat the book's ID.
            archive_original: keep the original in data/archive instead of deleting it.

        Raises:
            ConfirmationRequiredError: the confirmation doesn't match.
            LibraryBusyError: another operation is running.
        """
        if confirmation != book_id:
            raise ConfirmationRequiredError(f"Removing a book needs its ID as confirmation: {book_id}.")
        with self._guard.exclusive():
            self._catalog.get(book_id)
            with operation(logger, REMOVE_BOOK, book_id=book_id):
                with self._journal(REMOVE_BOOK, book_id, archive=archive_original):
                    self._catalog.update(book_id, status=BookStatus.REMOVING)
                    self._data.delete_book(book_id, archive_original)

    def _read_upload(self, upload: Path, filename: str) -> _Upload:
        document_format = validate_upload(upload, filename, self._max_upload_bytes)
        return _Upload(upload, safe_filename(filename), document_format, file_checksum(upload))

    def _new_book(self, book_id: str, document: _Upload, original: Path) -> Book:
        return Book(
            book_id=book_id,
            title=Path(document.name).stem,
            author=None,
            original_filename=document.name,
            original_path=str(original),
            checksum=document.checksum,
            format=document.format.value,
            language=None,
            chapter_count=0,
            chunk_count=0,
            embedding_model=None,
            index_version=None,
            status=BookStatus.PROCESSING,
            status_detail=None,
            revision=_FIRST_REVISION,
            created_at=utc_now(),
            indexed_at=None,
        )

    def _ingest(self, book: Book, path: Path, revision: int, index: IndexRecord) -> ProcessedDocument:
        return self._ingestion.ingest(
            path,
            DocumentFormat(book.format),
            book.book_id,
            revision,
            Path(book.original_filename).stem,
            index,
            self._indexes.store(index),
        )

    def _index_revision(
        self, book: Book, source: Book, revision: int, index: IndexRecord, staged: Path | None, journal: int
    ) -> ProcessedDocument:
        """Index a new revision next to the live one, undoing it completely if anything fails."""
        self._catalog.update(book.book_id, status=BookStatus.REINDEXING)
        try:
            return self._ingest(source, Path(source.original_path), revision, index)
        except Exception:
            self._catalog.update(book.book_id, status=book.status)
            self._data.discard_revision(book.book_id, revision, str(staged) if staged else None)
            self._catalog.end_operation(journal)
            raise

    def _swap_journal(self, book: Book, revision: int, staged: Path | None) -> Any:
        """Journal a swap through to its cleanup, with what recovery needs on either side of it."""
        return self._journal(
            REPLACE_BOOK,
            book.book_id,
            revision=revision,
            previous_revision=book.revision,
            previous_status=book.status.value,
            previous_original=book.original_path if staged else None,
            staged_original=str(staged) if staged else None,
        )

    @contextmanager
    def _journal(self, kind: str, book_id: str, **details: Any) -> Iterator[int]:
        """Record an operation while it runs.

        The record only goes when the work is done, or when a handler has undone all of it and
        ends the operation itself. Anything else leaves the record for recovery: an error in
        the middle of a cleanup is no different from a crash.
        """
        operation_id = self._catalog.begin_operation(kind, book_id, **details)
        yield operation_id
        self._catalog.end_operation(operation_id)


def _replaced(book: Book, document: _Upload, staged: Path) -> Book:
    """The book as seen by ingestion: the new document under the existing ID."""
    return replace(book, original_filename=document.name, original_path=str(staged), format=document.format.value)
