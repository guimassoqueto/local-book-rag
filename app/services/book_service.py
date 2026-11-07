"""Adding books to the library, and reading what is in it."""

from pathlib import Path

from app.errors import DuplicateBookError
from app.ingestion.validation import safe_filename, validate_upload
from app.services.index_service import IndexService
from app.services.ingestion_service import IngestionService
from app.storage.catalog import Book, BookCatalog, BookStatus, utc_now
from app.storage.repositories import OriginalDocuments, ProcessedDocuments
from app.utils.hashing import file_checksum
from app.utils.logging import get_logger, log_event, operation

logger = get_logger("services.books")

_FIRST_REVISION = 1


class BookService:
    def __init__(
        self,
        catalog: BookCatalog,
        originals: OriginalDocuments,
        processed: ProcessedDocuments,
        ingestion: IngestionService,
        indexes: IndexService,
        max_upload_bytes: int,
    ) -> None:
        self._catalog = catalog
        self._originals = originals
        self._processed = processed
        self._ingestion = ingestion
        self._indexes = indexes
        self._max_upload_bytes = max_upload_bytes

    def list_books(self) -> list[Book]:
        return self._catalog.list_books()

    def add_book(self, upload: Path, filename: str) -> Book:
        """Add a document to the library.

        Args:
            upload: where the upload is on disk.
            filename: the name it arrived with.

        Returns:
            The new book.

        Raises:
            DuplicateBookError: the same file is already in the library.
            ReindexRequiredError: the configuration no longer matches the index.
            BookRagError: the document was rejected. Nothing is recorded for a file that
                failed validation; a failure after it leaves a FAILED book, whose derived
                data is removed. Uploading the file again retries it.
        """
        document_format = validate_upload(upload, filename, self._max_upload_bytes)
        checksum = file_checksum(upload)
        if (existing := self._catalog.find_by_checksum(checksum)) is not None:
            if existing.status is not BookStatus.FAILED:
                raise DuplicateBookError(existing.book_id, existing.title)
            self._forget(existing)

        index = self._indexes.require_writable()
        store = self._indexes.store(index)
        book_id = self._catalog.next_book_id()
        name = safe_filename(filename)
        with operation(logger, "add_book", book_id=book_id):
            original = self._originals.store(upload, book_id, document_format)
            self._catalog.add(
                Book(
                    book_id=book_id,
                    title=Path(name).stem,
                    author=None,
                    original_filename=name,
                    original_path=str(original),
                    checksum=checksum,
                    format=document_format.value,
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
            )
            try:
                processed = self._ingestion.ingest(
                    original, document_format, book_id, _FIRST_REVISION, Path(name).stem, index, store
                )
            except Exception as exc:
                store.delete_book(book_id)
                self._processed.delete(book_id)
                self._catalog.update(book_id, status=BookStatus.FAILED, status_detail=str(exc))
                raise

            chapters = [(chapter.number, chapter.title) for chapter in processed.structure.chapters]
            self._catalog.set_chapters(book_id, chapters)
            log_event(logger, "book added", chapters=len(chapters), chunks=len(processed.chunks))
            return self._catalog.update(
                book_id,
                title=processed.title,
                author=processed.author,
                language=processed.language,
                chapter_count=len(chapters),
                chunk_count=len(processed.chunks),
                embedding_model=index.embedding_model,
                index_version=index.version,
                status=BookStatus.INDEXED,
                indexed_at=utc_now(),
            )

    def _forget(self, book: Book) -> None:
        """Drop what a failed attempt left, so that the same file can be added afresh."""
        self._originals.delete(book.book_id)
        self._catalog.delete(book.book_id)
