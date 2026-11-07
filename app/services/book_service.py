"""Adding books to the library, and reading what is in it."""

from pathlib import Path

from app.errors import DuplicateBookError
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.validation import safe_filename, validate_upload
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
        pipeline: IngestionPipeline,
        max_upload_bytes: int,
    ) -> None:
        self._catalog = catalog
        self._originals = originals
        self._processed = processed
        self._pipeline = pipeline
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
            BookRagError: the document was rejected. Nothing is recorded for a file that
                failed validation; a failure after it leaves a FAILED book.
        """
        document_format = validate_upload(upload, filename, self._max_upload_bytes)
        checksum = file_checksum(upload)
        if (existing := self._catalog.find_by_checksum(checksum)) is not None:
            raise DuplicateBookError(existing.book_id, existing.title)

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
                processed = self._pipeline.process(original, document_format, book_id, Path(name).stem)
                self._processed.save(book_id, _FIRST_REVISION, processed)
            except Exception as exc:
                self._catalog.update(book_id, status=BookStatus.FAILED, status_detail=str(exc))
                raise

            chapters = [(chapter.number, chapter.title) for chapter in processed.structure.chapters]
            self._catalog.set_chapters(book_id, chapters)
            log_event(logger, "book processed", chapters=len(chapters), chunks=len(processed.chunks))
            return self._catalog.update(
                book_id,
                title=processed.title,
                author=processed.author,
                language=processed.language,
                chapter_count=len(chapters),
                chunk_count=len(processed.chunks),
                status=BookStatus.PENDING,
            )
