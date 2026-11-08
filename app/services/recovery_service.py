"""Finishes or undoes what an interrupted process left behind, and serializes all changes."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from app.errors import BookNotFoundError, LibraryBusyError
from app.services.library_data import LibraryData
from app.storage.catalog import BookStatus, Operation
from app.utils.logging import get_logger, log_event

logger = get_logger("services.recovery")

ADD_BOOK = "add_book"
REPLACE_BOOK = "replace_book"
REMOVE_BOOK = "remove_book"
REINDEX_ALL = "reindex_all"
RESET_INDEX = "reset_index"
RESET_EVERYTHING = "reset_everything"

INTERRUPTED = "Interrupted: the application stopped while indexing this book. Upload it again to retry."


class LibraryGuard:
    """Lets one change happen at a time, across every process, after cleaning up the last one.

    The web interface and the commands are separate processes, so this is a lock on a file.
    The operating system releases it when a process dies, so a crash can't leave it stuck.
    """

    def __init__(self, lock_path: Path, data: LibraryData) -> None:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(lock_path)
        self._data = data
        self._last_repairs: list[str] = []

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Run a change to the library.

        Raises:
            LibraryBusyError: another operation is running.
            ServiceUnavailableError: ChromaDB is down. Every change needs it, and finding that
                out now leaves the library untouched, instead of halfway through a change.
        """
        try:
            self._lock.acquire(timeout=0)
        except Timeout as exc:
            raise LibraryBusyError("Another operation is changing the library. Try again when it finishes.") from exc
        try:
            self._data.server.version()
            self._recover()
            yield
        finally:
            self._lock.release()

    def recover(self) -> list[str]:
        """Clean up after an interrupted process, unless a live one is still working.

        Returns:
            A description of each thing that had to be repaired.
        """
        try:
            with self.exclusive():
                pass
        except LibraryBusyError:
            return []
        return self._last_repairs

    def _recover(self) -> None:
        repairs = []
        for operation in self._data.catalog.open_operations():
            self._repair(operation)
            self._data.catalog.end_operation(operation.operation_id)
            log_event(logger, "interrupted operation repaired", kind=operation.kind, book_id=operation.book_id)
            repairs.append(f"{operation.kind} {operation.book_id or ''}".strip())
        self._last_repairs = repairs

    def _repair(self, operation: Operation) -> None:
        match operation.kind:
            case "add_book":
                self._repair_add(operation.book_id)
            case "replace_book":
                self._repair_swap(operation.book_id, operation.details)
            case "remove_book":
                self._data.delete_book(operation.book_id, operation.details["archive"])
            case "reindex_all":
                self._repair_rebuild(operation.details)
            case "reset_index":
                self._data.clear(keep_originals=True)
            case "reset_everything":
                self._data.clear(keep_originals=False)

    def _repair_add(self, book_id: str) -> None:
        data = self._data
        try:
            book = data.catalog.get(book_id)
        except BookNotFoundError:
            data.originals.delete(book_id)  # it died before the book existed
            return
        if book.status is BookStatus.INDEXED:
            return  # it finished, and only the closing of the journal was lost
        data.discard_revision(book_id, book.revision)
        if book.status is BookStatus.PROCESSING:
            data.catalog.update(book_id, status=BookStatus.FAILED, status_detail=INTERRUPTED)

    def _repair_swap(self, book_id: str, details: dict[str, Any]) -> None:
        """Finish a swap that happened, or undo one that didn't: the catalog says which."""
        data = self._data
        book = data.catalog.get(book_id)
        if book.revision == details["revision"]:
            data.drop_replaced_revision(book_id, details["previous_revision"], details["previous_original"])
            if details["staged_original"]:  # a new document, and not the same one processed again
                data.record_source(book)
                data.summaries.delete(book_id)
            return
        data.discard_revision(book_id, details["revision"], details["staged_original"])
        data.catalog.update(book_id, status=BookStatus(details["previous_status"]))

    def _repair_rebuild(self, details: dict[str, Any]) -> None:
        """Finish a rebuild that went live, or drop one that didn't: the catalog says which."""
        data = self._data
        active = data.catalog.active_index()
        if active is not None and active.collection == details["collection"]:
            if details["previous_collection"]:
                data.server.delete_collection(details["previous_collection"])
            for book_id, revision in details["previous_revisions"].items():
                data.processed.delete_revision(book_id, revision)
            return
        data.server.delete_collection(details["collection"])
        for book_id, revision in details["revisions"].items():
            data.processed.delete_revision(book_id, revision)
        for book_id, status in details["statuses"].items():
            data.catalog.update(book_id, status=BookStatus(status))
