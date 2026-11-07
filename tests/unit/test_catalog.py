import pytest

from app.errors import BookNotFoundError
from app.storage.catalog import Book, BookCatalog, BookStatus, BookUpdate


@pytest.fixture
def catalog(tmp_path):
    return BookCatalog(tmp_path / "metadata" / "catalog.db")


def book(book_id="book_001", checksum="abc"):
    return Book(
        book_id=book_id,
        title="Title",
        author=None,
        original_filename="book.pdf",
        original_path="data/original_books/book_001/original.pdf",
        checksum=checksum,
        format="pdf",
        language="en",
        chapter_count=3,
        chunk_count=30,
        embedding_model=None,
        index_version=None,
        status=BookStatus.PENDING,
        status_detail=None,
        revision=1,
        created_at="2026-11-06T00:00:00+00:00",
        indexed_at=None,
    )


def test_a_book_round_trips(catalog):
    catalog.add(book())

    assert catalog.get("book_001") == book()


def test_ids_are_sequential_and_never_reused(catalog):
    first = catalog.next_book_id()
    catalog.add(book(first))
    catalog.delete(first)

    assert first == "book_001"
    assert catalog.next_book_id() == "book_002"


def test_finds_a_book_by_checksum(catalog):
    catalog.add(book())

    assert catalog.find_by_checksum("abc").book_id == "book_001"
    assert catalog.find_by_checksum("other") is None


def test_lists_books_in_id_order(catalog):
    catalog.add(book("book_002", "b"))
    catalog.add(book("book_001", "a"))

    assert [item.book_id for item in catalog.list_books()] == ["book_001", "book_002"]


def test_updates_fields(catalog):
    catalog.add(book())

    updated = catalog.update("book_001", status=BookStatus.INDEXED, chunk_count=31)

    assert updated.status is BookStatus.INDEXED
    assert catalog.get("book_001").chunk_count == 31


def test_unknown_ids_are_reported(catalog):
    with pytest.raises(BookNotFoundError):
        catalog.get("book_999")
    with pytest.raises(BookNotFoundError):
        catalog.update("book_999", status=BookStatus.FAILED)


def test_chapters_are_replaced_as_a_set(catalog):
    catalog.add(book())
    catalog.apply(BookUpdate("book_001", [(1, "One"), (2, "Two")], {}))

    catalog.apply(BookUpdate("book_001", [(1, "Only")], {"chunk_count": 9}))

    assert catalog.chapters("book_001") == [(1, "Only")]
    assert catalog.get("book_001").chunk_count == 9


def test_deleting_a_book_takes_its_chapters(catalog):
    catalog.add(book())
    catalog.apply(BookUpdate("book_001", [(1, "One")], {}))

    catalog.delete("book_001")

    assert catalog.chapters("book_001") == []


def test_the_catalog_survives_reopening(tmp_path):
    path = tmp_path / "catalog.db"
    BookCatalog(path).add(book())

    assert BookCatalog(path).get("book_001").title == "Title"


def test_operations_stay_open_until_they_end(catalog):
    operation = catalog.begin_operation("add_book", "book_001", revision=1)

    [found] = catalog.open_operations()
    assert (found.kind, found.book_id, found.details) == ("add_book", "book_001", {"revision": 1})

    catalog.end_operation(operation)

    assert catalog.open_operations() == []


def test_clearing_keeps_the_book_counter_when_originals_stay(catalog):
    catalog.add(book(catalog.next_book_id()))

    catalog.clear(keep_counters=True)

    assert catalog.list_books() == []
    assert catalog.next_book_id() == "book_002"


def test_clearing_everything_restarts_the_book_ids_but_never_the_index_versions(catalog):
    catalog.next_book_id()
    catalog.next_index_version()

    catalog.clear(keep_counters=False)

    assert catalog.next_book_id() == "book_001"
    assert catalog.next_index_version() == 2
