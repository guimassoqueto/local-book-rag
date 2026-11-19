"""Rebuilding and resetting the whole library."""

import pytest

from app.errors import (
    ConfirmationRequiredError,
    GenerationError,
    MissingOriginalError,
    NothingToReindexError,
    ReindexRequiredError,
    ServiceUnavailableError,
    UnsupportedLanguageError,
)
from app.retrieval.base import RetrievalFilters
from app.storage.catalog import BookCatalog, BookStatus
from app.storage.chroma import ChromaServer
from app.storage.repositories import OriginalDocuments, ProcessedDocuments, SummaryDocuments
from app.utils.progress import Outcome, Progress
from tests.fakes import FakeEmbedder
from tests.library import Library, library_state, other_text, progress_log, trace_journal, upload


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


def test_a_summary_keeps_its_language_when_written_again(library, tmp_path):
    book = library.add(tmp_path)
    saved = library.summarizer.summarize(book.book_id, 1, "brief", language="Portuguese")
    library.summarizer.save(saved)

    library.library.reindex_all(regenerate_summaries=True)

    assert "Write in Portuguese" in library.llm.calls[-1][0][0].content


def test_a_summary_that_fails_doesnt_turn_a_finished_rebuild_into_an_error(library, tmp_path, monkeypatch):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))

    def fail(*args, **kwargs):
        raise GenerationError("The model finished without an answer.")

    monkeypatch.setattr(library.summarizer, "summarize", fail)

    report = library.library.reindex_all(regenerate_summaries=True)

    assert report.index_version == 2
    assert report.summaries_regenerated == 0
    assert "without an answer" in report.summaries_failed[0]


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


def test_a_book_that_never_worked_doesnt_block_a_rebuild_after_a_reset(library, tmp_path):
    finnish = "Nopea ruskea kettu hyppää laiskan koiran yli ja palaa sitten takaisin metsään lepäämään."
    good = library.add(tmp_path, "good.md")
    with pytest.raises(UnsupportedLanguageError):
        library.add(tmp_path, "bad.md", f"# Yksi\n\n{finnish}\n\n# Kaksi\n\n{finnish} Mehiläiset keräävät.\n")
    bad = next(book for book in library.books.list_books() if book.status is BookStatus.FAILED)
    library.resets.reset_index("RESET INDEX")

    report = library.library.reindex_all()

    assert report.books == 1
    assert report.failed == (bad.book_id,)
    assert library.books.get_book(good.book_id).status is BookStatus.INDEXED
    assert library.books.get_book(bad.book_id).status is BookStatus.FAILED
    assert found(library)


def test_a_book_that_worked_still_stops_a_rebuild_if_it_fails(library, tmp_path, monkeypatch):
    library.add(tmp_path)

    def fail(*args, **kwargs):
        raise ServiceUnavailableError("Ollama is down")

    monkeypatch.setattr(library.embedder, "embed_documents", fail)

    with pytest.raises(ServiceUnavailableError):
        library.library.reindex_all()


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


def chromadb_down(monkeypatch, library):
    def unavailable():
        raise ServiceUnavailableError("ChromaDB is down")

    monkeypatch.setattr(library.server, "version", unavailable)


def test_a_reset_with_chromadb_down_changes_nothing(library, tmp_path, monkeypatch):
    book = library.add(tmp_path)
    chromadb_down(monkeypatch, library)

    with pytest.raises(ServiceUnavailableError):
        library.resets.reset_index("RESET INDEX")

    monkeypatch.undo()
    assert library.books.list_books() == [book]
    assert (library.root / "processed" / book.book_id).exists()


def test_a_refused_reset_never_happens_later_on_its_own(library, tmp_path, monkeypatch):
    """The user saw an error and believes nothing changed, so a restart must not reset anything."""
    book = library.add(tmp_path)
    chromadb_down(monkeypatch, library)
    with pytest.raises(ServiceUnavailableError):
        library.resets.reset_index("RESET INDEX")
    monkeypatch.undo()

    restarted = Library(library.settings, library.root)
    assert restarted.library.recover() == []

    assert restarted.books.list_books() == [book]
    assert restarted.store().count_revision(book.book_id, book.revision) == book.chunk_count


# The progress of reindexing the library (specs/004-library-progress, US2)

MEANWHILE = "Questions keep working on the current index meanwhile."


def top_stages(views):
    keys = []
    for view in views:
        if view.stage is not None and (not keys or keys[-1] != view.stage.key):
            keys.append(view.stage.key)
    return keys


def last(views, key):
    return [view.stage for view in views if view.stage is not None and view.stage.key == key][-1]


def test_a_reindex_shows_each_book_with_its_steps(library, tmp_path):
    first, second = add_two(library, tmp_path)
    heard = []

    with progress_log() as log:
        library.library.reindex_all(progress=Progress(sink=heard.append))

    assert top_stages(heard) == ["books", "switch"]
    books = last(heard, "books")
    assert (books.done, books.total, books.unit, books.time_left) == (2, 2, "books", None)
    assert {view.stage.note for view in heard if view.stage and view.stage.key == "books" and view.stage.note} == {
        first.title,
        second.title,
    }
    assert {view.step.key for view in heard if view.step} == {"extract", "prepare", "embed", "save"}
    assert {(view.step.position, view.step.stages) for view in heard if view.step and view.step.key == "embed"} == {
        (3, 4)
    }
    steps = [record.fields for record in log.records if getattr(record, "fields", {}).get("within") == "books"]
    assert {fields["item"] for fields in steps} == {first.book_id, second.book_id} and len(steps) == 8
    assert all(view.meanwhile == MEANWHILE for view in heard)
    assert log.undeclared() == []


def test_originals_brought_back_are_shown_done_first(library, tmp_path):
    add_two(library, tmp_path)
    library.resets.reset_index("RESET INDEX")
    heard = []

    library.library.reindex_all(progress=Progress(sink=heard.append))

    assert top_stages(heard) == ["adopt", "books", "switch"]
    adopt = last(heard, "adopt")
    assert (adopt.done, adopt.total, adopt.unit) == (2, 2, "originals")


def test_saved_summaries_are_counted_without_a_time_left(library, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))
    heard = []

    with progress_log() as log:
        library.library.reindex_all(regenerate_summaries=True, progress=Progress(sink=heard.append))

    assert top_stages(heard) == ["books", "switch", "summaries"]
    summaries = last(heard, "summaries")
    assert (summaries.done, summaries.total, summaries.unit, summaries.time_left) == (1, 1, "summaries", None)
    assert log.undeclared() == []


def test_no_summary_left_to_write_reads_zero_of_zero(library, tmp_path, monkeypatch):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 2, "brief"))
    monkeypatch.setattr(library.catalog, "chapters", lambda book_id: [(1, "One")])
    heard = []

    library.library.reindex_all(regenerate_summaries=True, progress=Progress(sink=heard.append))

    assert (last(heard, "summaries").done, last(heard, "summaries").total) == (0, 0)


def test_a_summary_that_fails_doesnt_stop_the_count(library, tmp_path, monkeypatch):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))

    def fail(*args, **kwargs):
        raise GenerationError("The model finished without an answer.")

    monkeypatch.setattr(library.summarizer, "summarize", fail)
    heard = []

    library.library.reindex_all(regenerate_summaries=True, progress=Progress(sink=heard.append))

    assert (last(heard, "summaries").done, last(heard, "summaries").total) == (1, 1)


def test_progress_changes_nothing_a_reindex_does(settings, tmp_path):
    without, with_ = Library(settings, tmp_path / "a"), Library(settings, tmp_path / "b")
    for library, directory in ((without, tmp_path / "in_a"), (with_, tmp_path / "in_b")):
        directory.mkdir()
        add_two(library, directory)
        library.resets.reset_index("RESET INDEX")
    calls_without, calls_with = trace_journal(without), trace_journal(with_)

    without.library.reindex_all()
    with_.library.reindex_all(progress=Progress())

    assert library_state(without) == library_state(with_)
    assert calls_without == calls_with and calls_with


def test_a_book_that_worked_and_fails_names_the_book_and_the_step(settings, tmp_path, monkeypatch):
    without, with_ = Library(settings, tmp_path / "a"), Library(settings, tmp_path / "b")
    books = {}
    for library, directory in ((without, tmp_path / "in_a"), (with_, tmp_path / "in_b")):
        directory.mkdir()
        books[library] = library.add(directory)

        def fail(*args, **kwargs):
            raise ServiceUnavailableError("Ollama is down")

        monkeypatch.setattr(library.embedder, "embed_documents", fail)
    progress = Progress()

    with pytest.raises(ServiceUnavailableError):
        without.library.reindex_all()
    with pytest.raises(ServiceUnavailableError):
        with_.library.reindex_all(progress=progress)

    book = books[with_]
    assert library_state(without) == library_state(with_)
    assert progress.snapshot().outcome == Outcome(
        succeeded=False,
        stage="Indexing the books",
        step="Embedding the chunks",
        item=f"{book.book_id}, {book.title}",
        error="Ollama is down",
    )


def test_a_book_with_nothing_to_lose_that_fails_doesnt_stop_the_count(settings, tmp_path):
    embedder = FakeEmbedder()
    library = Library(settings, tmp_path / "data", embedder)
    library.add(tmp_path, "one.md")
    embedder.failure = ServiceUnavailableError("down")
    with pytest.raises(ServiceUnavailableError):
        library.add(tmp_path, "two.md", other_text("the failing book"))
    embedder.failure = None
    original = embedder.embed_documents

    def fail_only_on_that_book(texts, on_batch=None):
        if any("the failing book" in text for text in texts):
            raise ServiceUnavailableError("still failing")
        return original(texts, on_batch)

    embedder.embed_documents = fail_only_on_that_book
    heard = []

    report = library.library.reindex_all(progress=Progress(sink=heard.append))

    assert report.failed and (last(heard, "books").done, last(heard, "books").total) == (2, 2)
    assert heard[-1].outcome.succeeded


def test_an_empty_library_shows_no_progress(library):
    progress = Progress()

    with pytest.raises(NothingToReindexError):
        library.library.reindex_all(progress=progress)

    assert progress.snapshot() is None


# The progress of the resets (specs/004-library-progress, US3)

RESETS = {
    "reset_index": ("RESET INDEX", ["collections", "processed", "summaries", "sources", "catalog"]),
    "reset_everything": ("DELETE EVERYTHING", ["collections", "processed", "summaries", "originals", "catalog"]),
}
RESET_FAILURES = {
    "collections": (ChromaServer, "delete_collections", "Deleting the index"),
    "processed": (ProcessedDocuments, "delete_all", "Deleting the processed documents"),
    "summaries": (SummaryDocuments, "delete_all", "Deleting the summaries"),
    "sources": (OriginalDocuments, "record", "Keeping a record of the originals"),
    "originals": (OriginalDocuments, "delete_all", "Deleting the originals"),
    "catalog": (BookCatalog, "clear", "Clearing the catalog"),
}


def broken(*args, **kwargs):
    raise RuntimeError("broken")


@pytest.mark.parametrize("name", RESETS)
def test_a_reset_shows_its_steps_by_name_without_a_count(library, tmp_path, name):
    add_two(library, tmp_path)
    phrase, steps = RESETS[name]
    heard = []

    with progress_log() as log:
        getattr(library.resets, name)(phrase, progress=Progress(sink=heard.append))

    assert top_stages(heard) == steps
    assert all(view.stage.total is None for view in heard if view.stage)
    assert heard[-1].outcome.succeeded and log.undeclared() == []


@pytest.mark.parametrize("name", RESETS)
def test_progress_changes_nothing_a_reset_does(settings, tmp_path, name):
    without, with_ = Library(settings, tmp_path / "a"), Library(settings, tmp_path / "b")
    for library, directory in ((without, tmp_path / "in_a"), (with_, tmp_path / "in_b")):
        directory.mkdir()
        add_two(library, directory)
    calls_without, calls_with = trace_journal(without), trace_journal(with_)
    phrase, _ = RESETS[name]

    getattr(without.resets, name)(phrase)
    getattr(with_.resets, name)(phrase, progress=Progress())

    assert library_state(without) == library_state(with_)
    assert calls_without == calls_with and calls_with


@pytest.mark.parametrize(("name", "step"), [(name, step) for name, (_, steps) in RESETS.items() for step in steps])
def test_a_reset_failing_at_each_step_leaves_and_recovers_what_it_would_without_progress(
    settings, tmp_path, monkeypatch, name, step
):
    without, with_ = Library(settings, tmp_path / "a"), Library(settings, tmp_path / "b")
    for library, directory in ((without, tmp_path / "in_a"), (with_, tmp_path / "in_b")):
        directory.mkdir()
        add_two(library, directory)
    phrase, _ = RESETS[name]
    owner, method, label = RESET_FAILURES[step]
    progress = Progress()

    with monkeypatch.context() as patched:
        patched.setattr(owner, method, broken)
        with pytest.raises(RuntimeError):
            getattr(without.resets, name)(phrase)
        with pytest.raises(RuntimeError):
            getattr(with_.resets, name)(phrase, progress=progress)

    assert library_state(without) == library_state(with_)
    assert progress.snapshot().outcome.stage == label
    Library(settings, tmp_path / "a").library.recover()
    Library(settings, tmp_path / "b").library.recover()
    assert library_state(without) == library_state(with_)


@pytest.mark.parametrize("name", RESETS)
def test_a_reset_with_the_wrong_phrase_shows_no_progress(library, tmp_path, name):
    progress = Progress()

    with pytest.raises(ConfirmationRequiredError):
        getattr(library.resets, name)("yes", progress=progress)

    assert progress.snapshot() is None
