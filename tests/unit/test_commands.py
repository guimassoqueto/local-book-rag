"""The commands' progress on the error stream (specs/004-library-progress, US4, contracts/commands.md)."""

import argparse
import re

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


# Markdown only (specs/005-markdown-only, FR-004, contracts/books.md)


def test_the_help_names_markdown_as_the_only_format():
    usage = main._build_parser().format_help()

    assert "add a Markdown book (.md, .markdown) to the library" in usage
    assert "swap a book for a new Markdown file, keeping its ID" in usage
    assert "PDF" not in usage and "EPUB" not in usage


def test_adding_a_pdf_exits_with_the_way_forward(container, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "build_container", lambda console_logs=False: container)

    with pytest.raises(SystemExit) as stopped:
        main.main(["add-book", str(upload(tmp_path, "book.pdf", "x"))])

    assert stopped.value.code == (
        "error: This is a PDF. Books are Markdown files: convert it to Markdown first, with MarkItDown for "
        "example, and add the .md file."
    )


def test_search_has_no_page_range(capsys):
    with pytest.raises(SystemExit):
        main._build_parser().parse_args(["search", "dog", "--page-start", "1"])

    assert "--page-start" in capsys.readouterr().err


def test_search_shows_where_each_passage_is_without_pages(container, library, capsys, tmp_path):
    library.add(tmp_path)

    out, _ = run(main._search, container, capsys, question="dog", book=[], chapter=[], section=[], language=[])

    assert re.search(r"book_001_chapter_0\d_chunk_\d{4} \((One|Two)(, Sub)?\) ", out)
    assert "p. " not in out and "no pages" not in out


def test_fetching_the_benchmark_books_is_gone(capsys):
    """The application can't read what it would download (specs/005-markdown-only, FR-018)."""
    with pytest.raises(SystemExit):
        main._build_parser().parse_args(["fetch-benchmark-books"])

    assert "invalid choice: 'fetch-benchmark-books'" in capsys.readouterr().err
