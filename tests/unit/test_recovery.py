"""What is left after a process dies in the middle of a change.

A BaseException stands in for the process dying: the handlers for ordinary failures don't see
it, so it leaves behind exactly what a kill would, and a new Library is the restarted process.
"""

from contextlib import contextmanager

import pytest

from app.errors import ServiceUnavailableError
from app.retrieval.base import RetrievalFilters
from app.services.recovery_service import INTERRUPTED
from app.storage.catalog import BookStatus
from tests.library import Library, other_text, upload


class ProcessDied(BaseException):
    pass


@pytest.fixture
def library(settings, tmp_path):
    return Library(settings, tmp_path / "data")


def restart(library):
    return Library(library.settings, library.root)


def found(library, book_id):
    return library.retrieval.search("dog", RetrievalFilters(book_ids=(book_id,))).candidates


def die_during_embedding(library):
    def embed(texts, on_batch=None):
        raise ProcessDied

    library.embedder.embed_documents = embed


def die_at(owner, name):
    def stop(*args, **kwargs):
        raise ProcessDied

    setattr(owner, name, stop)


def test_nothing_to_repair_is_the_normal_case(library, tmp_path):
    library.add(tmp_path)

    assert library.library.recover() == []


def test_a_book_interrupted_while_being_added_ends_up_failed(library, tmp_path):
    library.add(tmp_path, "one.md")
    die_during_embedding(library)
    with pytest.raises(ProcessDied):
        library.add(tmp_path, "two.md", other_text("interrupted"))

    restarted = restart(library)
    assert restarted.library.recover() == ["add_book book_002"]

    book = restarted.books.get_book("book_002")
    assert book.status is BookStatus.FAILED
    assert book.status_detail == INTERRUPTED
    assert restarted.store().count_revision("book_002", 1) == 0
    assert not (restarted.root / "processed" / "book_002").exists()


def test_an_interrupted_book_can_be_uploaded_again(library, tmp_path):
    die_during_embedding(library)
    with pytest.raises(ProcessDied):
        library.add(tmp_path, "one.md")

    restarted = restart(library)
    restarted.library.recover()
    book = restarted.add(tmp_path, "one.md")

    assert book.status is BookStatus.INDEXED


def test_dying_before_the_book_existed_leaves_nothing(library, tmp_path):
    library.add(tmp_path, "one.md")
    die_at(library.catalog, "add")
    with pytest.raises(ProcessDied):
        library.add(tmp_path, "two.md", other_text("never recorded"))

    restarted = restart(library)
    restarted.library.recover()

    assert not (restarted.root / "original_books" / "book_002").exists()
    assert len(restarted.books.list_books()) == 1


def test_a_replacement_interrupted_before_the_swap_is_undone(library, tmp_path):
    book = library.add(tmp_path)
    die_during_embedding(library)
    with pytest.raises(ProcessDied):
        library.books.replace_book(book.book_id, upload(tmp_path, "n.md", other_text("new")), "n.md")

    restarted = restart(library)
    assert restarted.library.recover() == [f"replace_book {book.book_id}"]

    assert restarted.books.get_book(book.book_id) == book
    assert restarted.store().count_revision(book.book_id, 1) == book.chunk_count
    assert not (restarted.root / "original_books" / book.book_id / "original_r2.md").exists()
    assert found(restarted, book.book_id)


def test_a_replacement_interrupted_after_the_swap_is_finished(library, tmp_path):
    book = library.add(tmp_path)
    die_at(library.data, "drop_replaced_revision")
    with pytest.raises(ProcessDied):
        library.books.replace_book(book.book_id, upload(tmp_path, "n.md", other_text("the new text")), "n.md")

    restarted = restart(library)
    restarted.library.recover()

    updated = restarted.books.get_book(book.book_id)
    assert updated.revision == 2
    assert updated.status is BookStatus.INDEXED
    assert restarted.store().count_revision(book.book_id, 1) == 0
    assert not (restarted.root / "original_books" / book.book_id / "original.md").exists()
    assert (restarted.root / "original_books" / book.book_id / "original_r2.md").exists()
    assert any("the new text" in passage.chunk.text for passage in found(restarted, book.book_id))


def test_a_replacement_finished_by_recovery_also_finishes_what_comes_after_the_swap(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))
    die_at(library.data, "record_source")
    with pytest.raises(ProcessDied):
        library.books.replace_book(book.book_id, upload(tmp_path, "n.md", other_text("the new text")), "n.md")

    restarted = restart(library)
    restarted.library.recover()

    assert restarted.summary_documents.saved() == []
    [record] = restarted.originals.discover()
    assert record.original_path.endswith("original_r2.md")
    assert record.original_filename == "n.md"


def test_a_summary_survives_recovery_of_a_reindex_of_the_same_document(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))
    die_at(library.data, "drop_replaced_revision")
    with pytest.raises(ProcessDied):
        library.books.reindex_book(book.book_id)

    restarted = restart(library)
    restarted.library.recover()

    assert len(restarted.summary_documents.saved()) == 1


def test_a_reindex_interrupted_before_the_swap_is_undone(library, tmp_path):
    book = library.add(tmp_path)
    die_during_embedding(library)
    with pytest.raises(ProcessDied):
        library.books.reindex_book(book.book_id)

    restarted = restart(library)
    restarted.library.recover()

    assert restarted.books.get_book(book.book_id) == book
    assert (restarted.root / "original_books" / book.book_id / "original.md").exists()


def test_a_reindex_interrupted_after_the_swap_keeps_the_original(library, tmp_path):
    book = library.add(tmp_path)
    die_at(library.data, "drop_replaced_revision")
    with pytest.raises(ProcessDied):
        library.books.reindex_book(book.book_id)

    restarted = restart(library)
    restarted.library.recover()

    assert restarted.books.get_book(book.book_id).revision == 2
    assert (restarted.root / "original_books" / book.book_id / "original.md").exists()


def test_an_interrupted_removal_is_finished(library, tmp_path):
    first = library.add(tmp_path, "one.md")
    second = library.add(tmp_path, "two.md", other_text("stays"))
    die_at(library.processed, "delete")
    with pytest.raises(ProcessDied):
        library.books.remove_book(first.book_id, confirmation=first.book_id)

    restarted = restart(library)
    assert restarted.books.get_book(first.book_id).status is BookStatus.REMOVING
    restarted.library.recover()

    assert restarted.books.list_books() == [second]
    assert restarted.store().count_revision(second.book_id, 1) == second.chunk_count


def test_a_rebuild_interrupted_before_the_swap_is_dropped(library, tmp_path):
    book = library.add(tmp_path)
    die_during_embedding(library)
    with pytest.raises(ProcessDied):
        library.library.reindex_all()

    restarted = restart(library)
    assert restarted.library.recover() == ["reindex_all"]

    assert restarted.books.get_book(book.book_id) == book
    assert restarted.server.collection_names() == ["book_chunks_v1"]
    assert found(restarted, book.book_id)


def test_a_rebuild_interrupted_after_the_swap_is_finished(library, tmp_path):
    book = library.add(tmp_path)
    die_at(library.library, "_drop_previous")
    with pytest.raises(ProcessDied):
        library.library.reindex_all()

    restarted = restart(library)
    restarted.library.recover()

    assert restarted.indexes.active().version == 2
    assert restarted.server.collection_names() == ["book_chunks_v2"]
    assert restarted.books.get_book(book.book_id).revision == 2
    assert [path.name for path in (restarted.root / "processed" / book.book_id).iterdir()] == ["r2"]
    assert found(restarted, book.book_id)


def test_an_interrupted_index_reset_is_finished(library, tmp_path):
    book = library.add(tmp_path)
    die_at(library.processed, "delete_all")
    with pytest.raises(ProcessDied):
        library.resets.reset_index("RESET INDEX")

    restarted = restart(library)
    restarted.library.recover()

    assert restarted.books.list_books() == []
    assert (restarted.root / "original_books" / book.book_id / "original.md").exists()


def test_an_interrupted_full_reset_is_finished(library, tmp_path):
    book = library.add(tmp_path)
    die_at(library.processed, "delete_all")
    with pytest.raises(ProcessDied):
        library.resets.reset_everything("DELETE EVERYTHING")

    restarted = restart(library)
    restarted.library.recover()

    assert restarted.books.list_books() == []
    assert not (restarted.root / "original_books" / book.book_id).exists()


def test_the_next_change_repairs_too_without_waiting_for_a_restart(library, tmp_path):
    die_during_embedding(library)
    with pytest.raises(ProcessDied):
        library.add(tmp_path, "one.md")

    restarted = restart(library)
    added = restarted.add(tmp_path, "two.md", other_text("a later book"))

    assert added.status is BookStatus.INDEXED
    assert restarted.catalog.open_operations() == []


def test_a_live_operation_is_never_mistaken_for_an_interrupted_one(library, tmp_path):
    book = library.add(tmp_path)
    library.catalog.begin_operation("replace_book", book.book_id, revision=2)

    with _held(library):
        assert restart(library).library.recover() == []

    assert len(library.catalog.open_operations()) == 1


@contextmanager
def _held(library):
    """Hold the lock as a running operation would, without repairing anything first."""
    library.guard._lock.acquire(timeout=0)
    try:
        yield
    finally:
        library.guard._lock.release()


def test_recovery_retries_later_if_chromadb_is_down(library, tmp_path, monkeypatch):
    die_during_embedding(library)
    with pytest.raises(ProcessDied):
        library.add(tmp_path, "one.md")

    restarted = restart(library)

    def unavailable(self, book_id, revision):
        raise ServiceUnavailableError("ChromaDB is down")

    monkeypatch.setattr("app.storage.chroma.ChunkStore.delete_revision", unavailable)
    with pytest.raises(ServiceUnavailableError):
        restarted.library.recover()
    monkeypatch.undo()

    assert len(restarted.catalog.open_operations()) == 1
    restarted.library.recover()
    assert restarted.catalog.open_operations() == []


def lose_chromadb_during(monkeypatch, method):
    """ChromaDB answers when a change starts, and goes away in the middle of it."""

    def unavailable(*args, **kwargs):
        raise ServiceUnavailableError("ChromaDB is down")

    monkeypatch.setattr(f"app.storage.chroma.ChunkStore.{method}", unavailable)


def test_changes_are_refused_up_front_while_chromadb_is_down(library, tmp_path, monkeypatch):
    book = library.add(tmp_path)

    def unavailable():
        raise ServiceUnavailableError("ChromaDB is down")

    monkeypatch.setattr(library.server, "version", unavailable)

    for change in (
        lambda: library.add(tmp_path, "two.md", other_text("refused")),
        lambda: library.books.reindex_book(book.book_id),
        lambda: library.books.remove_book(book.book_id, confirmation=book.book_id),
        lambda: library.library.reindex_all(),
    ):
        with pytest.raises(ServiceUnavailableError):
            change()

    monkeypatch.undo()
    assert library.books.list_books() == [book]
    assert library.catalog.open_operations() == []


def test_a_book_that_loses_chromadb_halfway_is_failed_not_stuck(library, tmp_path, monkeypatch):
    lose_chromadb_during(monkeypatch, "add")
    lose_chromadb_during(monkeypatch, "delete_revision")

    with pytest.raises(ServiceUnavailableError):
        library.add(tmp_path)

    [book] = library.books.list_books()
    assert book.status is BookStatus.FAILED
    assert "ChromaDB is down" in book.status_detail
    assert len(library.catalog.open_operations()) == 1

    monkeypatch.undo()
    library.library.recover()

    assert library.catalog.open_operations() == []
    assert library.books.get_book(book.book_id).status is BookStatus.FAILED
    assert library.store().count_revision(book.book_id, 1) == 0


def test_a_replacement_that_loses_chromadb_halfway_is_undone_when_it_returns(library, tmp_path, monkeypatch):
    book = library.add(tmp_path)
    lose_chromadb_during(monkeypatch, "add")
    lose_chromadb_during(monkeypatch, "delete_revision")

    with pytest.raises(ServiceUnavailableError):
        library.books.replace_book(book.book_id, upload(tmp_path, "n.md", other_text("new")), "n.md")

    assert library.books.get_book(book.book_id) == book
    monkeypatch.undo()
    library.library.recover()

    assert library.catalog.open_operations() == []
    assert not (library.root / "original_books" / book.book_id / "original_r2.md").exists()
    assert found(library, book.book_id)


def test_a_finished_book_survives_losing_the_end_of_its_journal(library, tmp_path):
    die_at(library.catalog, "end_operation")
    with pytest.raises(ProcessDied):
        library.add(tmp_path)

    restarted = restart(library)
    restarted.library.recover()

    [book] = restarted.books.list_books()
    assert book.status is BookStatus.INDEXED
    assert found(restarted, book.book_id)
