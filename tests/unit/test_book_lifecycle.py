"""Replacing and removing books, and what happens when those go wrong."""

import pytest

from app.errors import (
    BookNotFoundError,
    ConfirmationRequiredError,
    DuplicateBookError,
    EmptyDocumentError,
    InvalidDocumentError,
    LibraryBusyError,
    MissingOriginalError,
    ReindexRequiredError,
    ServiceUnavailableError,
)
from app.ingestion.markdown_loader import MarkdownLoader
from app.retrieval.base import RetrievalFilters
from app.storage.catalog import BookCatalog, BookStatus
from app.storage.chroma import ChunkStore
from app.storage.repositories import OriginalDocuments, ProcessedDocuments, SummaryDocuments
from app.utils.progress import Progress
from tests.fakes import FakeEmbedder
from tests.library import MARKDOWN as MARKDOWN_TEXT
from tests.library import TEXT, Library, library_state, other_text, progress_log, trace_journal, upload


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


def test_a_replacement_under_another_name_retitles_the_book(library, tmp_path):
    book = library.add(tmp_path)
    path = upload(tmp_path, "other.markdown", other_text("another name"))

    updated = library.books.replace_book(book.book_id, path, "other.markdown")

    assert updated.title == "other"
    assert updated.format == "markdown"
    assert updated.original_path.endswith("original_r2.md")


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


def test_a_replacement_that_fails_inside_the_operation_changes_nothing(library, tmp_path):
    book = library.add(tmp_path)
    before = library_state(library)

    with pytest.raises(EmptyDocumentError):
        library.books.replace_book(book.book_id, upload(tmp_path, "bad.md", "# Only\n\n## Headings\n"), "bad.md")

    assert library.books.get_book(book.book_id) == book
    assert library_state(library) == before


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


# The progress of adding, replacing and processing a book again (specs/004-library-progress, US1)

ADD = ["store", "extract", "prepare", "embed", "save"]
REPLACE = ["store", "extract", "prepare", "embed", "save", "swap"]
REPROCESS = ["extract", "prepare", "embed", "save", "swap"]


def top_stages(views):
    """The top-level stages in the order they were shown."""
    keys = []
    for view in views:
        if view.stage is not None and (not keys or keys[-1] != view.stage.key):
            keys.append(view.stage.key)
    return keys


def adding(library, tmp_path, progress=None, text=MARKDOWN_TEXT):
    path = upload(tmp_path, "book.md", text)
    kwargs = {"progress": progress} if progress is not None else {}
    return library.books.add_book(path, "book.md", **kwargs)


def replacing(library, tmp_path, progress=None):
    book = library.add(tmp_path)
    kwargs = {"progress": progress} if progress is not None else {}
    return library.books.replace_book(book.book_id, replacement(tmp_path), "new.md", **kwargs)


def reprocessing(library, tmp_path, progress=None):
    book = library.add(tmp_path)
    kwargs = {"progress": progress} if progress is not None else {}
    return library.books.reindex_book(book.book_id, **kwargs)


OPERATIONS = {"add": (adding, ADD), "replace": (replacing, REPLACE), "reprocess": (reprocessing, REPROCESS)}


@pytest.mark.parametrize("name", OPERATIONS)
def test_each_operation_reports_its_stages_in_order(settings, tmp_path, name):
    operation, expected = OPERATIONS[name]
    library = Library(settings, tmp_path / "data")
    heard = []
    progress = Progress(sink=heard.append)

    with progress_log() as log:
        book = operation(library, tmp_path, progress)

    assert top_stages(heard) == expected
    positions = {view.stage.key: (view.stage.position, view.stage.stages) for view in heard if view.stage}
    assert positions == {key: (index, len(expected)) for index, key in enumerate(expected, start=1)}
    embedded = [view.stage for view in heard if view.stage and view.stage.key == "embed" and view.stage.total]
    assert embedded[-1].done == embedded[-1].total == book.chunk_count
    assert progress.snapshot().outcome.succeeded and progress.snapshot().subject == book.book_id
    assert log.undeclared() == []


@pytest.mark.parametrize("name", OPERATIONS)
def test_progress_changes_nothing_an_operation_does(settings, tmp_path, name):
    operation, _ = OPERATIONS[name]
    without, with_ = Library(settings, tmp_path / "a"), Library(settings, tmp_path / "b")
    calls_without, calls_with = trace_journal(without), trace_journal(with_)
    (tmp_path / "in_a").mkdir(), (tmp_path / "in_b").mkdir()

    first = operation(without, tmp_path / "in_a")
    second = operation(with_, tmp_path / "in_b", Progress())

    assert library_state(without) == library_state(with_)
    assert calls_without == calls_with and calls_with
    assert (first.book_id, first.revision, first.chunk_count) == (second.book_id, second.revision, second.chunk_count)


class Broken(Exception):
    pass


def fail(*args, **kwargs):
    raise Broken("broken")


FAILURES = {
    "store": lambda monkeypatch, library: monkeypatch.setattr(OriginalDocuments, "store", fail),
    "extract": lambda monkeypatch, library: monkeypatch.setattr(MarkdownLoader, "load", fail),
    "embed": lambda monkeypatch, library: setattr(library.embedder, "failure", Broken("broken")),
    "save": lambda monkeypatch, library: monkeypatch.setattr(ChunkStore, "add", fail),
    "swap": lambda monkeypatch, library: monkeypatch.setattr(BookCatalog, "apply", fail),
}
LABELS = {
    "store": "Storing the file",
    "extract": "Extracting the text",
    "prepare": "Preparing the chunks",
    "embed": "Embedding the chunks",
    "save": "Saving to the index",
    "swap": "Swapping in the new version",
}
CASES = [("add", stage) for stage in ADD] + [("replace", "store"), ("replace", "embed"), ("replace", "swap")]
CASES += [("reprocess", "extract"), ("reprocess", "save"), ("reprocess", "swap")]


def failing(name, stage, library, directory, monkeypatch, progress=None):
    """Run an operation whose stage fails. The setup before it runs unbroken."""
    operation, _ = OPERATIONS[name]
    if name == "add":
        if stage == "prepare":
            return operation(library, directory, progress, text="# One\n\n# Two\n")
        FAILURES[stage](monkeypatch, library)
        return operation(library, directory, progress)
    book = library.add(directory)
    if stage == "prepare":
        raise AssertionError("not a case")
    FAILURES[stage](monkeypatch, library)
    kwargs = {"progress": progress} if progress is not None else {}
    if name == "replace":
        return library.books.replace_book(book.book_id, replacement(directory), "new.md", **kwargs)
    return library.books.reindex_book(book.book_id, **kwargs)


@pytest.mark.parametrize(("name", "stage"), CASES)
def test_a_failure_in_each_stage_leaves_what_it_leaves_without_progress(settings, tmp_path, monkeypatch, name, stage):
    without, with_ = Library(settings, tmp_path / "a"), Library(settings, tmp_path / "b")
    (tmp_path / "in_a").mkdir(), (tmp_path / "in_b").mkdir()
    calls_without, calls_with = trace_journal(without), trace_journal(with_)
    progress = Progress()

    with monkeypatch.context() as patched, pytest.raises(Exception) as first:
        failing(name, stage, without, tmp_path / "in_a", patched)
    with monkeypatch.context() as patched, pytest.raises(Exception) as second:
        failing(name, stage, with_, tmp_path / "in_b", patched, progress)

    assert type(first.value) is type(second.value) and str(first.value) == str(second.value)
    assert library_state(without) == library_state(with_)
    assert calls_without == calls_with
    label = "Storing the replacement" if (name, stage) == ("replace", "store") else LABELS[stage]
    assert progress.snapshot().outcome.stage == label and not progress.snapshot().outcome.succeeded


def test_a_refused_addition_shows_no_progress(library, tmp_path):
    library.add(tmp_path)
    progress = Progress()

    with pytest.raises(DuplicateBookError):
        library.books.add_book(upload(tmp_path, "again.md"), "again.md", progress=progress)

    assert progress.snapshot() is None


def test_an_addition_refused_while_another_operation_runs_shows_no_progress(library, tmp_path):
    progress = Progress()

    with library.guard.exclusive(), pytest.raises(LibraryBusyError):
        other_process = Library(library.settings, library.root)
        other_process.books.add_book(upload(tmp_path, "one.md"), "one.md", progress=progress)

    assert progress.snapshot() is None


def test_an_addition_refused_for_a_reindex_shows_no_progress(library, tmp_path):
    library.add(tmp_path)
    changed = library.with_settings("chunking", target_size=123)
    progress = Progress()

    with pytest.raises(ReindexRequiredError):
        changed.books.add_book(upload(tmp_path, "two.md", other_text("two")), "two.md", progress=progress)

    assert progress.snapshot() is None


def test_retrying_a_failed_file_starts_with_storing_it(settings, tmp_path):
    embedder = FakeEmbedder(failure=ServiceUnavailableError("Ollama is down"))
    library = Library(settings, tmp_path / "data", embedder)
    with pytest.raises(ServiceUnavailableError):
        library.add(tmp_path)
    embedder.failure = None
    heard = []

    library.books.add_book(upload(tmp_path, "one.md"), "one.md", progress=Progress(sink=heard.append))

    assert top_stages(heard) == ADD


# The progress of removing a book (specs/004-library-progress, US3)

REMOVAL = ["vectors", "processed", "summaries", "original", "catalog"]
REMOVAL_FAILURES = {
    "vectors": (ChunkStore, "delete_book"),
    "processed": (ProcessedDocuments, "delete"),
    "summaries": (SummaryDocuments, "delete"),
    "original": (OriginalDocuments, "delete"),
    "catalog": (BookCatalog, "delete"),
}


@pytest.mark.parametrize(
    ("archive", "original"), [(False, "Deleting its original"), (True, "Moving its original to the archive")]
)
def test_a_removal_shows_its_steps_by_name_without_a_count(library, tmp_path, archive, original):
    book = library.add(tmp_path)
    heard = []

    with progress_log() as log:
        library.books.remove_book(book.book_id, book.book_id, archive, progress=Progress(sink=heard.append))

    assert top_stages(heard) == REMOVAL
    labels = {view.stage.key: view.stage.label for view in heard if view.stage}
    assert labels["original"] == original and labels["vectors"] == "Deleting its chunks from the index"
    assert all(view.stage.total is None for view in heard if view.stage)
    assert heard[-1].outcome.succeeded and heard[-1].subject == book.book_id
    assert log.undeclared() == []


def test_progress_changes_nothing_a_removal_does(settings, tmp_path):
    without, with_ = Library(settings, tmp_path / "a"), Library(settings, tmp_path / "b")
    books = {}
    for library, directory in ((without, tmp_path / "in_a"), (with_, tmp_path / "in_b")):
        directory.mkdir()
        books[library] = library.add(directory)
        library.add(directory, "two.md", other_text("two"))
    calls_without, calls_with = trace_journal(without), trace_journal(with_)

    without.books.remove_book(books[without].book_id, books[without].book_id, True)
    with_.books.remove_book(books[with_].book_id, books[with_].book_id, True, progress=Progress())

    assert library_state(without) == library_state(with_)
    assert calls_without == calls_with and calls_with


@pytest.mark.parametrize("step", REMOVAL)
def test_a_removal_failing_at_each_step_leaves_and_recovers_what_it_would_without_progress(
    settings, tmp_path, monkeypatch, step
):
    without, with_ = Library(settings, tmp_path / "a"), Library(settings, tmp_path / "b")
    books = {}
    for library, directory in ((without, tmp_path / "in_a"), (with_, tmp_path / "in_b")):
        directory.mkdir()
        books[library] = library.add(directory)
    progress = Progress()
    owner, method = REMOVAL_FAILURES[step]

    with monkeypatch.context() as patched:
        patched.setattr(owner, method, fail)
        with pytest.raises(Broken):
            without.books.remove_book(books[without].book_id, books[without].book_id)
        with pytest.raises(Broken):
            with_.books.remove_book(books[with_].book_id, books[with_].book_id, progress=progress)

    assert library_state(without) == library_state(with_)
    assert progress.snapshot().outcome.stage == LABELS_REMOVAL[step]
    Library(settings, tmp_path / "a").library.recover()
    Library(settings, tmp_path / "b").library.recover()
    assert library_state(without) == library_state(with_)


LABELS_REMOVAL = {
    "vectors": "Deleting its chunks from the index",
    "processed": "Deleting its processed documents",
    "summaries": "Deleting its summaries",
    "original": "Deleting its original",
    "catalog": "Removing it from the catalog",
}


def test_a_removal_with_the_wrong_confirmation_shows_no_progress(library, tmp_path):
    book = library.add(tmp_path)
    progress = Progress()

    with pytest.raises(ConfirmationRequiredError):
        library.books.remove_book(book.book_id, "yes", progress=progress)

    assert progress.snapshot() is None


# Markdown only (specs/005-markdown-only): PDF and EPUB refused before anything changes, and a
# book's title taken from its file's name on every path that indexes it.

NAMED = "01_historia_economica_global"
SAYS_OTHERWISE = (
    f"---\ntitle: Front Title\nauthor: Someone\n---\n\n# The Book\n\n## One\n\n{TEXT}\n\n## Two\n\n{TEXT}\n"
)


@pytest.mark.parametrize(
    ("attempt", "message"),
    [
        (
            lambda library, tmp_path, book: library.books.add_book(upload(tmp_path, "b.pdf", "x"), "b.pdf"),
            "This is a PDF.",
        ),
        (
            lambda library, tmp_path, book: library.books.replace_book(
                book.book_id, upload(tmp_path, "b.epub", "x"), "b.epub"
            ),
            "This is an EPUB.",
        ),
    ],
    ids=["add a pdf", "replace with an epub"],
)
def test_a_pdf_or_an_epub_is_refused_before_anything_changes(library, tmp_path, attempt, message):
    book = library.add(tmp_path)
    before = library_state(library)
    calls = trace_journal(library)

    with pytest.raises(InvalidDocumentError) as refused:
        attempt(library, tmp_path, book)

    assert str(refused.value).startswith(message)
    assert "convert it to Markdown first" in str(refused.value)
    assert calls == []
    assert library_state(library) == before
    assert library.books.get_book(book.book_id).revision == book.revision


def test_a_busy_library_is_reported_before_the_files_type(library, tmp_path):
    with library.guard.exclusive(), pytest.raises(LibraryBusyError):
        Library(library.settings, library.root).books.add_book(upload(tmp_path, "b.pdf", "x"), "b.pdf")


def test_an_added_book_is_titled_by_its_file_and_has_no_author(library, tmp_path):
    book = library.books.add_book(upload(tmp_path, f"{NAMED}.md", SAYS_OTHERWISE), f"{NAMED}.md")

    assert (book.title, book.author) == (NAMED, None)
    assert {chunk.book_title for chunk in library.books.chunks(book.book_id)} == {NAMED}


def test_a_replacement_takes_its_files_name_and_no_author(library, tmp_path):
    book = library.add(tmp_path)

    updated = library.books.replace_book(
        book.book_id, upload(tmp_path, "Another.markdown", SAYS_OTHERWISE), "Another.markdown"
    )

    assert (updated.title, updated.author) == ("Another", None)


def test_processing_again_keeps_the_files_name(library, tmp_path):
    book = library.books.add_book(upload(tmp_path, f"{NAMED}.md", SAYS_OTHERWISE), f"{NAMED}.md")

    again = library.books.reindex_book(book.book_id)

    assert (again.title, again.author) == (NAMED, None)


def test_a_rebuild_keeps_the_files_name(library, tmp_path):
    book = library.books.add_book(upload(tmp_path, f"{NAMED}.md", SAYS_OTHERWISE), f"{NAMED}.md")

    library.library.reindex_all()

    assert (library.books.get_book(book.book_id).title, library.books.get_book(book.book_id).author) == (NAMED, None)


def test_originals_brought_back_after_an_index_reset_keep_the_files_name(library, tmp_path):
    library.books.add_book(upload(tmp_path, f"{NAMED}.md", SAYS_OTHERWISE), f"{NAMED}.md")

    library.resets.reset_index("RESET INDEX")
    library.library.reindex_all()

    [book] = library.books.list_books()
    assert (book.title, book.author) == (NAMED, None)
