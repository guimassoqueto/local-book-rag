"""The library's data as a whole: operations across its stores, all of them safe to repeat.

They have to be: a process that dies halfway through one leaves it to be run again on the next
start, without knowing how far it got.
"""

from pathlib import Path

from app.services.index_service import COLLECTION_PREFIX
from app.storage.catalog import Book, BookCatalog
from app.storage.chroma import ChromaServer, ChunkStore
from app.storage.repositories import OriginalDocuments, OriginalRecord, ProcessedDocuments, SummaryDocuments


class LibraryData:
    def __init__(
        self,
        catalog: BookCatalog,
        originals: OriginalDocuments,
        processed: ProcessedDocuments,
        summaries: SummaryDocuments,
        server: ChromaServer,
    ) -> None:
        self.catalog = catalog
        self.originals = originals
        self.processed = processed
        self.summaries = summaries
        self.server = server

    def record_source(self, book: Book) -> None:
        """Write down what a rebuild needs to bring a book back, should a reset clear the catalog."""
        self.originals.record(
            OriginalRecord(
                book_id=book.book_id,
                original_filename=book.original_filename,
                original_path=book.original_path,
                checksum=book.checksum,
                format=book.format,
                created_at=book.created_at,
            )
        )

    def _active_store(self) -> ChunkStore | None:
        index = self.catalog.active_index()
        return ChunkStore(self.server, index.collection) if index else None

    def discard_revision(self, book_id: str, revision: int, staged_original: str | None = None) -> None:
        """Remove a revision that will never go live, leaving the book's other revisions alone."""
        store = self._active_store()
        if store is not None:
            store.delete_revision(book_id, revision)
        self.processed.delete_revision(book_id, revision)
        if staged_original:
            self.originals.delete_file(Path(staged_original))

    def drop_replaced_revision(self, book_id: str, revision: int, replaced_original: str | None) -> None:
        """Remove the revision a swap left behind, keeping the original if it is still the current one."""
        current = self.catalog.get(book_id).original_path
        stale_original = replaced_original if replaced_original != current else None
        self.discard_revision(book_id, revision, stale_original)

    def delete_book(self, book_id: str, archive: bool) -> None:
        """Remove a book completely. Only its own vectors go: the collection stays."""
        store = self._active_store()
        if store is not None:
            store.delete_book(book_id)
        self.processed.delete(book_id)
        self.summaries.delete(book_id)
        if archive:
            self.originals.archive(book_id)
        else:
            self.originals.delete(book_id)
        self.catalog.delete(book_id)

    def clear(self, keep_originals: bool) -> None:
        """Return the library to empty. ChromaDB goes first: if it is down, nothing has changed."""
        self.server.delete_collections(COLLECTION_PREFIX)
        self.processed.delete_all()
        self.summaries.delete_all()
        if keep_originals:
            for book in self.catalog.list_books():  # the catalog is about to go, and a rebuild needs this
                self.record_source(book)
        else:
            self.originals.delete_all()
        self.catalog.clear(keep_counters=keep_originals)
