"""The commands' progress on the error stream (specs/004-library-progress, US4, contracts/commands.md)."""

import argparse

import pytest

from app import main
from app.config.settings import EnvironmentSettings
from app.container import Container
from app.errors import ServiceUnavailableError
from app.services.health_service import HealthService
from tests.library import Library, other_text, upload


@pytest.fixture
def library(settings, tmp_path):
    return Library(settings, tmp_path / "data")


@pytest.fixture
def container(library):
    return Container(
        settings=library.settings,
        environment=EnvironmentSettings(),
        runtime=library.runtime,
        health=HealthService(library.settings, library.runtime, library.server, library.indexes),
        indexes=library.indexes,
        books=library.books,
        library=library.library,
        resets=library.resets,
        retrieval=library.retrieval,
        questions=None,
        summaries=library.summarizer,
        quizzes=None,
    )


def run(handler, container, capsys, **arguments):
    handler(container, argparse.Namespace(**arguments))
    captured = capsys.readouterr()
    return captured.out, captured.err.splitlines()


def test_adding_prints_its_result_and_its_stages(container, capsys, tmp_path):
    out, err = run(main._add_book, container, capsys, path=upload(tmp_path, "one.md"))

    assert out.startswith("book_001: one (") and out.endswith("chunks, INDEXED)\n") and out.count("\n") == 1
    assert err[0] == "[0:00] Adding a book, book_001: stage 1 of 5, Storing the file"
    assert any("stage 4 of 5, Embedding the chunks" in line for line in err)
    assert err[-1] == "[0:00] Adding a book, book_001: done"


def test_replacing_and_processing_again_print_their_stages(container, library, capsys, tmp_path):
    book = library.add(tmp_path)

    out, err = run(
        main._replace_book, container, capsys, book=book.book_id, path=upload(tmp_path, "n.md", other_text("n"))
    )
    assert out.startswith(f"{book.book_id}: ") and err[-1].endswith("Replacing a book, book_001: done")
    assert any("Swapping in the new version" in line for line in err)

    out, err = run(main._reindex_book, container, capsys, book=book.book_id)
    assert out.startswith(f"{book.book_id}: ") and err[-1].endswith("Processing a book again, book_001: done")


def test_reindexing_prints_only_its_report_on_standard_output(container, library, capsys, tmp_path):
    library.add(tmp_path)

    out, err = run(main._reindex_all, container, capsys, regenerate_summaries=False)

    assert out.splitlines()[0].startswith("Index v2 (book_chunks_v2) is active, built with")
    assert "Indexing" not in out
    assert any("stage 1 of 2, Indexing the books" in line for line in err)
    assert any(": step 3 of 4, Embedding the chunks" in line for line in err)
    assert err[-1].endswith("Reindexing the library: done")


def test_removing_and_resetting_print_their_steps(container, library, capsys, tmp_path):
    book = library.add(tmp_path)
    library.add(tmp_path, "two.md", other_text("two"))

    out, err = run(main._remove_book, container, capsys, book=book.book_id, confirm=book.book_id, archive=False)
    assert out == f"{book.book_id} removed.\n"
    assert any("stage 4 of 5, Deleting its original" in line for line in err) and err[-1].endswith("done")

    out, err = run(main._reset_index, container, capsys, confirm="RESET INDEX")
    assert out == "The index is gone and the originals are kept. reindex-all rebuilds the library from them.\n"
    assert any("Keeping a record of the originals" in line for line in err) and err[-1].endswith("done")

    out, err = run(main._reset_everything, container, capsys, confirm="DELETE EVERYTHING")
    assert out == "The library is empty.\n"
    assert any("Deleting the originals" in line for line in err) and err[-1].endswith("done")


def test_a_failing_addition_ends_its_error_stream_with_where_it_failed(container, library, capsys, tmp_path):
    library.embedder.failure = ServiceUnavailableError("Ollama is down")

    with pytest.raises(ServiceUnavailableError):
        main._add_book(container, argparse.Namespace(path=upload(tmp_path, "one.md")))

    # Unconfigured, as in the tests, logging also writes the failure there; a command logs to its file only.
    progress = [line for line in capsys.readouterr().err.splitlines() if line.startswith("[")]
    assert progress[-1] == "[0:00] Adding a book, book_001: failed while embedding the chunks"
