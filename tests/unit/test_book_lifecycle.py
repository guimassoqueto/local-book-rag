"""Replacing and removing books, and what happens when those go wrong."""

import pytest

from app.errors import (
    BookNotFoundError,
    ConfirmationRequiredError,
    DuplicateBookError,
    InvalidDocumentError,
    LibraryBusyError,
    MissingOriginalError,
    ReindexRequiredError,
    ServiceUnavailableError,
)
from app.retrieval.base import RetrievalFilters
from app.storage.catalog import BookStatus
from tests.documents import write_pdf
from tests.fakes import FakeEmbedder
from tests.library import Library, other_text, upload


@pytest.fixture
def library(settings, tmp_path):
    return Library(settings, tmp_path / "data")


def texts(library, book_id):
    result = library.retrieval.search("dog", RetrievalFilters(book_ids=(book_id,)))
    return " ".join(passage.chunk.text for passage in result.candidates)


def replacement(tmp_path, label="the replacement"):
    return upload(tmp_path, "new.md", other_text(label))


def test_a_replacement_keeps_the_id_and_moves_to_a_new_revision(library, tmp_path):
    book = library.add(tmp_path)

    updated = library.books.replace_book(book.book_id, replacement(tmp_path), "new.md")

    assert updated.book_id == book.book_id
    assert updated.revision == 2
    assert updated.original_filename == "new.md"
    assert updated.checksum != book.checksum
    assert updated.status is BookStatus.INDEXED


def test_only_the_new_text_is_found_after_a_replacement(library, tmp_path):
    book = library.add(tmp_path)

    library.books.replace_book(book.book_id, replacement(tmp_path), "new.md")

    assert "the replacement" in texts(library, book.book_id)
    assert library.store().count_revision(book.book_id, 1) == 0


def test_the_old_revision_leaves_no_files_behind(library, tmp_path):
    book = library.add(tmp_path)

    library.books.replace_book(book.book_id, replacement(tmp_path), "new.md")

    directory = library.root / "processed" / book.book_id
    assert [path.name for path in directory.iterdir()] == ["r2"]
    assert not (library.root / "original_books" / book.book_id / "original.md").exists()
    assert (library.root / "original_books" / book.book_id / "original_r2.md").exists()


def test_a_replacement_can_change_format(library, tmp_path):
    book = library.add(tmp_path)
    text = "The quick brown fox jumps over the lazy dog, and goes back to the forest to rest for the day."
    path = write_pdf(tmp_path / "new.pdf", [[("Chapter One", 11), (text, 11)]], toc=[[1, "Chapter One", 1]])

    updated = library.books.replace_book(book.book_id, path, "new.pdf")

    assert updated.format == "pdf"
    assert updated.original_path.endswith("original_r2.pdf")


def test_replacing_leaves_other_books_alone(library, tmp_path):
    first = library.add(tmp_path, "one.md")
    second = library.add(tmp_path, "two.md", other_text("the second book"))

    library.books.replace_book(first.book_id, replacement(tmp_path), "new.md")

    assert library.books.get_book(second.book_id) == second
    assert library.store().count_revision(second.book_id, 1) == second.chunk_count


def test_a_replacement_drops_summaries_of_the_old_text(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))

    library.books.replace_book(book.book_id, replacement(tmp_path), "new.md")

    assert library.summary_documents.saved() == []


def test_a_failed_replacement_leaves_the_book_exactly_as_it_was(library, tmp_path):
    book = library.add(tmp_path)
    before = texts(library, book.book_id)
    library.embedder.failure = ServiceUnavailableError("Ollama is down")

    with pytest.raises(ServiceUnavailableError):
        library.books.replace_book(book.book_id, replacement(tmp_path), "new.md")

    library.embedder.failure = None
    assert library.books.get_book(book.book_id) == book
    assert texts(library, book.book_id) == before
    assert library.store().count_revision(book.book_id, 2) == 0
    assert not (library.root / "processed" / book.book_id / "r2").exists()
    assert not (library.root / "original_books" / book.book_id / "original_r2.md").exists()
    assert (library.root / "original_books" / book.book_id / "original.md").exists()


def test_a_rejected_replacement_changes_nothing(library, tmp_path):
    book = library.add(tmp_path)

    with pytest.raises(InvalidDocumentError):
        library.books.replace_book(book.book_id, upload(tmp_path, "bad.pdf", "not a pdf"), "bad.pdf")

    assert library.books.get_book(book.book_id) == book


def test_a_book_stays_searchable_while_its_replacement_is_indexed(library, tmp_path):
    book = library.add(tmp_path)
    during = []
    original = library.ingestion.ingest

    def ingest(*args, **kwargs):
        result = original(*args, **kwargs)
        during.append(texts(library, book.book_id))
        return result

    library.ingestion.ingest = ingest

    library.books.replace_book(book.book_id, replacement(tmp_path), "new.md")

    assert "the replacement" not in during[0]
    assert "the replacement" in texts(library, book.book_id)


def test_replacing_with_a_document_already_there_is_refused(library, tmp_path):
    first = library.add(tmp_path, "one.md")
    second = library.add(tmp_path, "two.md", other_text("the second book"))

    with pytest.raises(DuplicateBookError):
        library.books.replace_book(first.book_id, upload(tmp_path, "copy.md", other_text("the second book")), "c.md")

    assert library.books.get_book(second.book_id) == second


def test_replacing_a_book_that_does_not_exist_is_reported(library, tmp_path):
    with pytest.raises(BookNotFoundError):
        library.books.replace_book("book_999", replacement(tmp_path), "new.md")


def test_replacing_needs_a_compatible_configuration(library, tmp_path):
    book = library.add(tmp_path)
    changed = library.with_settings("chunking", target_size=300)

    with pytest.raises(ReindexRequiredError):
        changed.books.replace_book(book.book_id, replacement(tmp_path), "new.md")


def test_reindexing_a_book_rebuilds_it_from_its_original(library, tmp_path):
    book = library.add(tmp_path)

    updated = library.books.reindex_book(book.book_id)

    assert updated.revision == 2
    assert updated.chunk_count == book.chunk_count
    assert library.store().count_revision(book.book_id, 1) == 0
    assert library.store().count_revision(book.book_id, 2) == book.chunk_count
    assert (library.root / "original_books" / book.book_id / "original.md").exists()


def test_a_summary_survives_reindexing_the_same_document(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))

    library.books.reindex_book(book.book_id)

    assert len(library.summary_documents.saved()) == 1


def test_reindexing_retries_a_failed_book(settings, tmp_path):
    embedder = FakeEmbedder(failure=ServiceUnavailableError("Ollama is down"))
    library = Library(settings, tmp_path / "data", embedder)
    with pytest.raises(ServiceUnavailableError):
        library.add(tmp_path)
    [failed] = library.books.list_books()

    embedder.failure = None
    updated = library.books.reindex_book(failed.book_id)

    assert updated.status is BookStatus.INDEXED
    assert updated.status_detail is None


def test_reindexing_a_book_whose_original_is_gone_is_reported(library, tmp_path):
    book = library.add(tmp_path)
    (library.root / "original_books" / book.book_id / "original.md").unlink()

    with pytest.raises(MissingOriginalError):
        library.books.reindex_book(book.book_id)

    assert library.books.get_book(book.book_id).status is BookStatus.INDEXED


def test_removing_needs_the_id_as_confirmation(library, tmp_path):
    book = library.add(tmp_path)

    with pytest.raises(ConfirmationRequiredError, match=book.book_id):
        library.books.remove_book(book.book_id, confirmation="yes")

    assert library.books.get_book(book.book_id) == book


def test_removing_a_book_deletes_everything_of_it(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))

    library.books.remove_book(book.book_id, confirmation=book.book_id)

    assert library.books.list_books() == []
    assert library.store().count() == 0
    for directory in ("processed", "summaries", "original_books"):
        assert not (library.root / directory / book.book_id).exists()


def test_removing_a_book_leaves_every_other_book_alone(library, tmp_path):
    first = library.add(tmp_path, "one.md")
    second = library.add(tmp_path, "two.md", other_text("the second book"))
    library.summarizer.save(library.summarizer.summarize(second.book_id, 1, "brief"))

    library.books.remove_book(first.book_id, confirmation=first.book_id)

    assert library.books.list_books() == [second]
    assert library.store().count_revision(second.book_id, 1) == second.chunk_count
    assert texts(library, second.book_id)
    assert len(library.summary_documents.saved()) == 1


def test_removing_a_book_never_deletes_the_collection(library, tmp_path):
    book = library.add(tmp_path)

    library.books.remove_book(book.book_id, confirmation=book.book_id)

    assert library.server.collection_names() == ["book_chunks_v1"]


def test_the_original_can_be_archived_on_removal(library, tmp_path):
    book = library.add(tmp_path)

    library.books.remove_book(book.book_id, confirmation=book.book_id, archive_original=True)

    assert (library.root / "archive" / book.book_id / "original.md").exists()
    assert not (library.root / "original_books" / book.book_id).exists()


def test_a_removed_books_file_can_be_added_again(library, tmp_path):
    book = library.add(tmp_path)
    library.books.remove_book(book.book_id, confirmation=book.book_id)

    again = library.add(tmp_path)

    assert again.book_id == "book_002"


def test_removing_a_book_that_does_not_exist_is_reported(library):
    with pytest.raises(BookNotFoundError):
        library.books.remove_book("book_999", confirmation="book_999")


@pytest.mark.parametrize(
    "change",
    [
        lambda library, tmp_path, book: library.add(tmp_path, "two.md", other_text("another")),
        lambda library, tmp_path, book: library.books.reindex_book(book.book_id),
        lambda library, tmp_path, book: library.books.remove_book(book.book_id, confirmation=book.book_id),
        lambda library, tmp_path, book: library.library.reindex_all(),
        lambda library, tmp_path, book: library.resets.reset_index("RESET INDEX"),
    ],
)
def test_changes_are_rejected_while_another_runs(library, tmp_path, change):
    book = library.add(tmp_path)

    with library.guard.exclusive():
        other_process = Library(library.settings, library.root)
        with pytest.raises(LibraryBusyError):
            change(other_process, tmp_path, book)


def test_searching_goes_on_during_a_change(library, tmp_path):
    book = library.add(tmp_path)

    with library.guard.exclusive():
        assert texts(library, book.book_id)


def test_the_lock_is_released_after_a_failure(library, tmp_path):
    book = library.add(tmp_path)
    with pytest.raises(ConfirmationRequiredError):
        library.books.remove_book(book.book_id, confirmation="no")

    library.books.remove_book(book.book_id, confirmation=book.book_id)

    assert library.books.list_books() == []
