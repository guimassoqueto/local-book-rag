"""Rebuilding and resetting the whole library."""

import pytest

from app.errors import (
    ConfirmationRequiredError,
    MissingOriginalError,
    NothingToReindexError,
    ReindexRequiredError,
    ServiceUnavailableError,
)
from app.retrieval.base import RetrievalFilters
from app.storage.catalog import BookStatus
from tests.fakes import FakeEmbedder
from tests.library import Library, other_text, upload


@pytest.fixture
def library(settings, tmp_path):
    return Library(settings, tmp_path / "data")


def found(library, book_id=None):
    filters = RetrievalFilters(book_ids=(book_id,) if book_id else ())
    return library.retrieval.search("dog", filters).candidates


def add_two(library, tmp_path):
    return library.add(tmp_path, "one.md"), library.add(tmp_path, "two.md", other_text("the second book"))


def test_a_rebuild_moves_every_book_to_a_new_index(library, tmp_path):
    first, second = add_two(library, tmp_path)

    report = library.library.reindex_all()

    assert report.index_version == 2
    assert report.collection == "book_chunks_v2"
    assert report.books == 2
    assert report.chunks == first.chunk_count + second.chunk_count
    assert library.server.collection_names() == ["book_chunks_v2"]
    for book in library.books.list_books():
        assert book.index_version == 2
        assert book.revision == 2
        assert book.status is BookStatus.INDEXED


def test_a_rebuild_keeps_every_book_searchable(library, tmp_path):
    first, second = add_two(library, tmp_path)

    library.library.reindex_all()

    assert {passage.chunk.book_id for passage in found(library)} == {first.book_id, second.book_id}


def test_old_revisions_leave_no_files_behind(library, tmp_path):
    first, _ = add_two(library, tmp_path)

    library.library.reindex_all()

    assert [path.name for path in (library.root / "processed" / first.book_id).iterdir()] == ["r2"]


def test_a_rebuild_applies_a_new_chunk_size(library, tmp_path):
    long_text = "\n\n".join(f"# Chapter {index}\n\n" + other_text(str(index)) for index in range(3))
    book = library.add(tmp_path, text=long_text)
    changed = library.with_settings("chunking", target_size=20, overlap=5)
    with pytest.raises(ReindexRequiredError):
        changed.books.add_book(upload(tmp_path, "two.md", other_text("x")), "two.md")

    changed.library.reindex_all()

    assert changed.books.get_book(book.book_id).chunk_count > book.chunk_count
    assert not changed.indexes.needs_reindex()


def test_a_rebuild_applies_a_new_embedding_model(settings, tmp_path):
    library = Library(settings, tmp_path / "data")
    book = library.add(tmp_path)
    changed = library.with_settings("embedding", model="bge-m3")
    assert changed.indexes.needs_reindex()

    report = changed.library.reindex_all()

    assert report.embedding_model == "bge-m3"
    assert changed.books.get_book(book.book_id).embedding_model == "bge-m3"
    assert not changed.indexes.needs_reindex()


def test_books_can_be_added_again_after_a_rebuild_with_new_settings(library, tmp_path):
    library.add(tmp_path)
    changed = library.with_settings("chunking", target_size=300)
    changed.library.reindex_all()

    added = changed.add(tmp_path, "two.md", other_text("after the rebuild"))

    assert added.status is BookStatus.INDEXED


def test_the_old_index_serves_searches_during_a_rebuild(library, tmp_path):
    book = library.add(tmp_path)
    during = []
    original = library.ingestion.ingest

    def ingest(*args, **kwargs):
        result = original(*args, **kwargs)
        during.append((library.indexes.active().version, len(found(library, book.book_id))))
        return result

    library.ingestion.ingest = ingest

    library.library.reindex_all()

    assert during[0][0] == 1
    assert during[0][1] > 0


def test_a_failed_rebuild_leaves_the_library_exactly_as_it_was(library, tmp_path):
    first, second = add_two(library, tmp_path)
    before = library.books.list_books()
    calls = {"count": 0}
    original = library.embedder.embed_documents

    def fail_on_second_book(texts, on_batch=None):
        calls["count"] += 1
        if calls["count"] == 2:
            raise ServiceUnavailableError("Ollama is down")
        return original(texts, on_batch)

    library.embedder.embed_documents = fail_on_second_book

    with pytest.raises(ServiceUnavailableError):
        library.library.reindex_all()

    assert library.books.list_books() == before
    assert library.server.collection_names() == ["book_chunks_v1"]
    assert found(library)
    assert [path.name for path in (library.root / "processed" / first.book_id).iterdir()] == ["r1"]


def test_a_missing_original_stops_a_rebuild_before_anything_changes(library, tmp_path):
    first, _ = add_two(library, tmp_path)
    before = library.books.list_books()
    (library.root / "original_books" / first.book_id / "original.md").unlink()

    with pytest.raises(MissingOriginalError, match=first.book_id):
        library.library.reindex_all()

    assert library.books.list_books() == before
    assert library.server.collection_names() == ["book_chunks_v1"]


def test_an_empty_library_has_nothing_to_rebuild(library):
    with pytest.raises(NothingToReindexError):
        library.library.reindex_all()


def test_a_book_that_was_already_failing_does_not_block_the_rest(settings, tmp_path):
    embedder = FakeEmbedder()
    library = Library(settings, tmp_path / "data", embedder)
    good = library.add(tmp_path, "one.md")
    embedder.failure = ServiceUnavailableError("down")
    with pytest.raises(ServiceUnavailableError):
        library.add(tmp_path, "two.md", other_text("the failing book"))
    embedder.failure = None
    bad = library.books.list_books()[1]
    original = embedder.embed_documents

    def fail_only_on_that_book(texts, on_batch=None):
        if any("the failing book" in text for text in texts):
            raise ServiceUnavailableError("still failing")
        return original(texts, on_batch)

    embedder.embed_documents = fail_only_on_that_book

    report = library.library.reindex_all()

    assert report.books == 1
    assert report.failed == (bad.book_id,)
    assert library.books.get_book(bad.book_id).status is BookStatus.FAILED
    assert library.books.get_book(good.book_id).status is BookStatus.INDEXED
    assert library.store().count_revision(bad.book_id, bad.revision + 1) == 0


def test_saved_summaries_can_be_written_again(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))
    calls = len(library.llm.calls)

    report = library.library.reindex_all(regenerate_summaries=True)

    assert report.summaries_regenerated == 1
    assert len(library.llm.calls) > calls


def test_summaries_are_left_alone_by_default(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))
    calls = len(library.llm.calls)

    report = library.library.reindex_all()

    assert report.summaries_regenerated == 0
    assert len(library.llm.calls) == calls


def test_resetting_the_index_needs_its_confirmation(library, tmp_path):
    library.add(tmp_path)

    with pytest.raises(ConfirmationRequiredError, match="RESET INDEX"):
        library.resets.reset_index("yes")

    assert library.books.list_books()


def test_resetting_the_index_empties_the_library_but_keeps_the_originals(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))

    library.resets.reset_index("RESET INDEX")

    assert library.books.list_books() == []
    assert library.indexes.active() is None
    assert library.server.collection_names() == []
    assert library.summary_documents.saved() == []
    assert not list((library.root / "processed").iterdir())
    assert (library.root / "original_books" / book.book_id / "original.md").exists()


def test_the_originals_rebuild_the_library_after_an_index_reset(library, tmp_path):
    first, second = add_two(library, tmp_path)
    library.resets.reset_index("RESET INDEX")

    report = library.library.reindex_all()

    assert set(report.adopted) == {first.book_id, second.book_id}
    assert report.books == 2
    books = {book.book_id: book for book in library.books.list_books()}
    assert books[first.book_id].original_filename == "one.md"
    assert books[first.book_id].checksum == first.checksum
    assert books[first.book_id].chunk_count == first.chunk_count
    assert books[first.book_id].status is BookStatus.INDEXED
    assert {passage.chunk.book_id for passage in found(library)} == {first.book_id, second.book_id}


def test_a_book_without_a_source_record_gets_one_from_a_rebuild(library, tmp_path):
    book = library.add(tmp_path)
    (library.root / "original_books" / book.book_id / "source.json").unlink()

    library.library.reindex_all()

    assert [record.book_id for record in library.originals.discover()] == [book.book_id]


def test_a_reset_never_strands_an_original_without_its_record(library, tmp_path):
    book = library.add(tmp_path)
    (library.root / "original_books" / book.book_id / "source.json").unlink()

    library.resets.reset_index("RESET INDEX")

    assert library.library.reindex_all().adopted == (book.book_id,)


def test_a_rebuilt_book_can_be_replaced_and_removed_like_any_other(library, tmp_path):
    book = library.add(tmp_path)
    library.resets.reset_index("RESET INDEX")
    library.library.reindex_all()

    updated = library.books.replace_book(book.book_id, upload(tmp_path, "n.md", other_text("new")), "n.md")
    library.books.remove_book(updated.book_id, confirmation=updated.book_id)

    assert library.books.list_books() == []


def test_new_books_after_a_reset_dont_take_the_ids_of_preserved_originals(library, tmp_path):
    book = library.add(tmp_path)
    library.resets.reset_index("RESET INDEX")

    added = library.add(tmp_path, "two.md", other_text("a new book"))

    assert added.book_id != book.book_id


def test_a_preserved_original_uploaded_again_is_not_rebuilt_twice(library, tmp_path):
    library.add(tmp_path)
    library.resets.reset_index("RESET INDEX")
    library.add(tmp_path)

    report = library.library.reindex_all()

    assert report.books == 1
    assert report.adopted == ()


def test_resetting_everything_needs_its_own_confirmation(library, tmp_path):
    library.add(tmp_path)

    with pytest.raises(ConfirmationRequiredError, match="DELETE EVERYTHING"):
        library.resets.reset_everything("RESET INDEX")

    assert library.books.list_books()


def test_resetting_everything_removes_all_library_data(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))
    second = library.add(tmp_path, "two.md", other_text("to be archived"))
    library.books.remove_book(second.book_id, confirmation=second.book_id, archive_original=True)

    library.resets.reset_everything("DELETE EVERYTHING")

    assert library.books.list_books() == []
    assert library.server.collection_names() == []
    for directory in ("original_books", "archive", "processed", "summaries"):
        assert not list((library.root / directory).iterdir())


def test_the_library_starts_over_after_resetting_everything(library, tmp_path):
    library.add(tmp_path)
    library.resets.reset_everything("DELETE EVERYTHING")

    book = library.add(tmp_path)

    assert book.book_id == "book_001"
    assert book.status is BookStatus.INDEXED
    assert found(library)


def test_index_versions_are_never_reused(library, tmp_path):
    library.add(tmp_path)
    library.resets.reset_everything("DELETE EVERYTHING")

    library.add(tmp_path)

    assert library.indexes.active().version == 2
    assert library.server.collection_names() == ["book_chunks_v2"]


def test_a_reset_only_touches_this_librarys_collections(library, tmp_path):
    library.add(tmp_path)
    library.server.create_collection("somebody_elses", {"owner": "someone"})

    library.resets.reset_everything("DELETE EVERYTHING")

    assert library.server.collection_names() == ["somebody_elses"]


def test_a_reset_keeps_the_tracked_directories(library, tmp_path):
    (library.root / "processed").mkdir(parents=True)
    keep = library.root / "processed" / ".gitkeep"
    keep.touch()
    library.add(tmp_path)

    library.resets.reset_everything("DELETE EVERYTHING")

    assert keep.exists()


def test_a_reset_with_chromadb_down_changes_nothing(library, tmp_path, monkeypatch):
    book = library.add(tmp_path)

    def unavailable(prefix):
        raise ServiceUnavailableError("ChromaDB is down")

    monkeypatch.setattr(library.server, "delete_collections", unavailable)

    with pytest.raises(ServiceUnavailableError):
        library.resets.reset_index("RESET INDEX")

    monkeypatch.undo()
    assert library.books.list_books() == [book]
    assert (library.root / "processed" / book.book_id).exists()
