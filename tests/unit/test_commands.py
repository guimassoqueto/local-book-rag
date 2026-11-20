"""The commands' progress on the error stream (specs/004-library-progress, US4, contracts/commands.md)."""

import argparse
import dataclasses
import json
import re

import anthropic
import openai
import pytest
from pydantic import SecretStr

from app import main
from app.config.settings import EnvironmentSettings, ProviderCredentials
from app.container import Container
from app.errors import AllModelsFailedError, ModelFailedError, ServiceUnavailableError
from app.generation.anthropic_provider import AnthropicCloud
from app.generation.base import FailureReason
from app.generation.choices import ModelChoices
from app.generation.factory import CloudSetup, create_cloud_providers
from app.generation.question_answering import QuestionAnsweringService
from app.generation.summarization import ChapterSummarizer
from app.services.health_service import CheckResult, HealthService
from tests.fakes import (
    FakeAnthropicClient,
    FakeCloud,
    FakeLLM,
    FakeResponse,
    WordCounter,
    anthropic_model_info,
    openai_model,
    openai_status_error,
)
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
        models=ModelChoices.local_only(library.llm),
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


def test_a_report_on_a_kind_the_benchmark_doesnt_run_fails_and_prints_nothing(container, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(main, "build_container", lambda console_logs=False: container)
    experiment = {"name": "old", "kind": "extraction", "description": "An old run."}
    (tmp_path / "results.json").write_text(json.dumps({"experiment": experiment}), encoding="utf-8")
    (tmp_path / "reading.csv").write_text("variant,question,mark\n", encoding="utf-8")

    with pytest.raises(SystemExit) as stopped:
        main.main(["benchmark-report", str(tmp_path)])

    assert "'extraction' kind" in stopped.value.code
    assert capsys.readouterr().out == ""


# Cloud models (specs/008-cloud-llm-providers, research.md R5)


def pull(container, monkeypatch, capsys):
    """Run pull-models with nothing downloaded, recording each tokenizer it readies."""
    monkeypatch.setattr(container.runtime, "pull", lambda model: iter(()), raising=False)
    monkeypatch.setattr(main, "local_snapshot", lambda model: "ready")
    readied = []
    monkeypatch.setattr(main, "create_token_counter", lambda config: readied.append(config.name) or WordCounter())
    out, _ = run(main._pull_models, container, capsys, all=False)
    return out.splitlines(), readied


def test_without_cloud_settings_pull_models_readies_no_cloud_tokenizer(container, monkeypatch, capsys):
    lines, readied = pull(container, monkeypatch, capsys)

    assert "tokenizer o200k_base: ready" not in lines
    assert "o200k_base" not in readied


def test_pull_models_readies_a_configured_providers_tokenizer_contacting_no_provider(
    container, library, monkeypatch, capsys
):
    client = FakeAnthropicClient()
    credentials = ProviderCredentials("anthropic", SecretStr("sk-ant-test"), ("claude-a",))
    cloud = AnthropicCloud(credentials, library.settings.cloud_profiles["anthropic"], client.factory)
    models = ModelChoices(library.llm, CloudSetup(((cloud, ("claude-a",)),), (), {"anthropic": "Anthropic"}))

    lines, readied = pull(dataclasses.replace(container, models=models), monkeypatch, capsys)

    assert "tokenizer o200k_base: ready" in lines
    assert readied.count("o200k_base") == 1
    assert client.calls == 0


# Cloud models in ask and doctor (specs/008-cloud-llm-providers, research.md R14, contracts/interface.md)

LOCAL_ANSWER = "An answer about the dog [1]."
CLOUD_ANSWER = "A cloud answer about the dog [1]."
TIMING = re.compile(r"^\d+\.\ds in total, \d+ \+ \d+ tokens at \d+ tokens/s$")


def cloud_models():
    """The local model, and FakeCloud's fc-a, which fails after two words, and fc-b, which answers."""
    failure = ModelFailedError("fc-a", "fakecloud", FailureReason.RATE_LIMITED, label="FakeCloud")
    failing = FakeLLM(model="fc-a", provider="fakecloud", cloud=True, fail=failure, text_before_failure="Half an")
    answering = FakeLLM([CLOUD_ANSWER], model="fc-b", provider="fakecloud", cloud=True)
    provider = FakeCloud(models={"fc-a": failing, "fc-b": answering})
    local = FakeLLM([LOCAL_ANSWER], model="fake-llm")
    return ModelChoices(local, CloudSetup(((provider, ("fc-a", "fc-b")),), (), {"fakecloud": "FakeCloud"}))


def asking(container, library, models):
    questions = QuestionAnsweringService(library.settings, library.retrieval, models)
    return dataclasses.replace(container, questions=questions, models=models)


def ask(container, capsys, model=None, fallbacks=()):
    arguments = {"question": "Where is the dog?", "book": [], "chapter": [], "language": None}
    return run(main._ask, container, capsys, **arguments, model=model, fallback=list(fallbacks))


@pytest.mark.parametrize("models", [lambda: ModelChoices.local_only(FakeLLM([LOCAL_ANSWER])), cloud_models])
def test_ask_without_a_model_prints_what_it_printed_before(container, library, capsys, tmp_path, models):
    library.add(tmp_path)

    out, err = ask(asking(container, library, models()), capsys)

    lines = out.splitlines()
    assert lines[0].strip() == LOCAL_ANSWER
    assert lines[1:3] == ["", "Sources:"]
    assert lines[3].startswith("  [1] ")
    assert TIMING.match(lines[4]) and len(lines) == 5
    assert err == []


def test_ask_with_a_cloud_model_says_where_the_question_goes_and_who_answered(container, library, capsys, tmp_path):
    library.add(tmp_path)

    out, err = ask(asking(container, library, cloud_models()), capsys, model="fc-b")

    assert err == ["The question and the passages found go to FakeCloud: fc-b. If it fails, fake-llm answers, locally."]
    lines = out.splitlines()
    assert lines[0].strip() == CLOUD_ANSWER
    assert lines[-2] == "Answered by fc-b (FakeCloud)"
    assert TIMING.match(lines[-1])


def test_ask_marks_a_failed_models_text_as_discarded(container, library, capsys, tmp_path):
    library.add(tmp_path)

    out, err = ask(asking(container, library, cloud_models()), capsys, model="fc-a")

    assert err[-1] == (
        "fc-a (FakeCloud) failed: it limited the rate. The text above is discarded: fake-llm answers from the start."
    )
    assert out.startswith("Half an ") and LOCAL_ANSWER in out
    assert out.splitlines()[-2] == "Answered by fake-llm (local)"


def test_ask_with_a_model_not_offered_stops_before_searching(container, library, monkeypatch, capsys, tmp_path):
    asked = asking(container, library, cloud_models())
    monkeypatch.setattr(main, "build_container", lambda console_logs=False: asked)

    with pytest.raises(SystemExit) as stopped:
        main.main(["ask", "Where is the dog?", "--model", "fc-x"])

    assert stopped.value.code == (
        "error: fc-x isn't offered. Offered: fake-llm (local), fc-a (FakeCloud), fc-b (FakeCloud)."
    )
    assert capsys.readouterr().out == ""


class Health:
    """Health checks that answer with given rows, and record how they were asked."""

    def __init__(self, rows):
        self.rows = rows
        self.asked = []

    def run(self, inference=False, providers=False):
        self.asked.append((inference, providers))
        return self.rows


def test_doctor_checks_the_providers_and_fails_on_a_failing_row(container, capsys):
    health = Health(
        [
            CheckResult("ollama", True, "version 0.40.15"),
            CheckResult("fakecloud fc-a", True, "Fake A, 1000000-token window"),
            CheckResult("fakecloud fc-x", False, "FakeCloud doesn't know this model"),
        ]
    )

    with pytest.raises(SystemExit) as stopped:
        main._doctor(dataclasses.replace(container, health=health), argparse.Namespace(inference=False))

    out = capsys.readouterr().out.splitlines()
    assert stopped.value.code == 1
    assert health.asked == [(False, True)]
    assert out[1:] == [
        "[ ok ] fakecloud fc-a       Fake A, 1000000-token window",
        "[FAIL] fakecloud fc-x       FakeCloud doesn't know this model",
    ]


# Cloud models in summarize and reindex-all (specs/008-cloud-llm-providers, contracts/interface.md)

LAST_LINE = re.compile(r"^direct: \d+/\d+ chunks in \d+ steps, \d+ cited, \d+ statements without a source, \d+\.\ds")


def summarizing(container, library, models):
    summarizer = ChapterSummarizer(
        library.settings, models, library.catalog, library.processed, library.summary_documents, library.retrieval
    )
    return dataclasses.replace(container, summaries=summarizer, models=models)


def summarize(container, capsys, book_id, model=None, fallbacks=()):
    arguments = {"book": book_id, "chapter": 1, "type": "brief", "language": None, "save": False}
    return run(main._summarize, container, capsys, **arguments, model=model, fallback=list(fallbacks))


def test_summarize_without_a_model_prints_what_it_printed_before(container, library, capsys, tmp_path):
    book = library.add(tmp_path)

    out, err = summarize(summarizing(container, library, cloud_models()), capsys, book.book_id)

    assert out.strip().startswith(LOCAL_ANSWER)
    assert LAST_LINE.match(err[-1]) and err[-1].endswith("s")
    assert not any("FakeCloud" in line or "goes to" in line for line in err)


def test_summarize_with_a_cloud_model_says_where_the_chapter_goes_and_its_tokens(container, library, capsys, tmp_path):
    book = library.add(tmp_path)

    out, err = summarize(summarizing(container, library, cloud_models()), capsys, book.book_id, model="fc-b")

    assert err[0] == "The chapter's text goes to FakeCloud: fc-b. If it fails, fake-llm summarizes it, locally."
    assert out.strip().startswith(CLOUD_ANSWER)
    assert LAST_LINE.match(err[-1])
    assert err[-1].endswith(", fc-b (FakeCloud), 100 tokens read and 20 generated")


def test_summarize_reports_a_failure_and_the_model_that_wrote_it(container, library, capsys, tmp_path):
    book = library.add(tmp_path)

    _, err = summarize(summarizing(container, library, cloud_models()), capsys, book.book_id, model="fc-a")

    assert "fc-a (FakeCloud) failed: it limited the rate. Starting again with fake-llm." in err
    assert "fc-a (FakeCloud) failed at step 1: it limited the rate." in err
    assert err[-1].endswith(", fake-llm (local)")


def test_reindex_all_lists_the_summaries_a_cloud_model_wrote_and_kept(container, library, capsys, tmp_path):
    book = library.add(tmp_path)
    library.summarizer.save(library.summarizer.summarize(book.book_id, 1, "brief"))
    path = library.root / "summaries" / book.book_id / "chapter_01_brief.json"
    metadata = json.loads(path.read_text(encoding="utf-8")) | {"provider": "anthropic", "model": "claude-sonnet-5-5"}
    path.write_text(json.dumps(metadata), encoding="utf-8")

    out, _ = run(main._reindex_all, container, capsys, regenerate_summaries=True)

    assert out.splitlines()[-2:] == [
        "  kept as they were, written by a cloud model: book_001, chapter_01_brief (claude-sonnet-5-5, Anthropic)",
        "  their references may name sections that the rebuild changed: summarize a chapter again to refresh it",
    ]


# Fallbacks in ask and summarize (specs/008-cloud-llm-providers, US3, FR-008)


def test_ask_takes_its_fallbacks_in_order(container, library, capsys, tmp_path):
    library.add(tmp_path)

    out, err = ask(asking(container, library, cloud_models()), capsys, model="fc-a", fallbacks=["fc-b"])

    assert err[0] == (
        "The question and the passages found go to FakeCloud: fc-a, then fc-b. If they fail, fake-llm answers, locally."
    )
    discarded = (
        "fc-a (FakeCloud) failed: it limited the rate. The text above is discarded: fc-b answers from the start."
    )
    assert discarded in err
    assert CLOUD_ANSWER in out and out.splitlines()[-2] == "Answered by fc-b (FakeCloud)"


def test_summarize_takes_its_fallbacks_in_order(container, library, capsys, tmp_path):
    book = library.add(tmp_path)

    out, err = summarize(summarizing(container, library, cloud_models()), capsys, book.book_id, "fc-a", ["fc-b"])

    assert err[0] == (
        "The chapter's text goes to FakeCloud: fc-a, then fc-b. If they fail, fake-llm summarizes it, locally."
    )
    assert out.strip().startswith(CLOUD_ANSWER)
    assert err[-1].endswith(", fc-b (FakeCloud), 100 tokens read and 20 generated")


OFFERED = "Offered: fake-llm (local), fc-a (FakeCloud), fc-b (FakeCloud)."


@pytest.mark.parametrize("command", ["ask", "summarize"])
@pytest.mark.parametrize(
    ("names", "problem"),
    [
        (["--model", "fc-a", "--fallback", "fc-x"], "fc-x isn't offered."),
        (["--model", "fc-a", "--fallback", "fc-b", "--fallback", "fc-b"], "fc-b is given more than once."),
        (
            ["--model", "fc-a", "--fallback", "fake-llm"],
            "fake-llm answers last in every sequence, so it can't be a fallback.",
        ),
        (["--fallback", "fc-a"], "fake-llm answers alone, so it takes no fallback."),
        (["--model", "fake-llm", "--fallback", "fc-a"], "fake-llm answers alone, so it takes no fallback."),
    ],
)
def test_a_refused_sequence_ends_the_command_naming_the_models_offered(
    container, library, monkeypatch, capsys, command, names, problem
):
    models = cloud_models()
    asked = summarizing(asking(container, library, models), library, models)
    monkeypatch.setattr(main, "build_container", lambda console_logs=False: asked)
    arguments = ["ask", "Where is the dog?"] if command == "ask" else ["summarize", "book_001", "1"]

    with pytest.raises(SystemExit) as stopped:
        main.main([*arguments, *names])

    assert stopped.value.code == f"error: {problem} {OFFERED}"
    assert capsys.readouterr().out == ""


# The last model's text, when every model fails (specs/008, Phase 9: Convergence, T075; FR-017)

QUESTION = {"question": "Where is the dog?", "book": [], "chapter": [], "language": None}


def failing_local():
    error = ServiceUnavailableError("Ollama went away.")
    return FakeLLM(model="fake-llm", fail=error, text_before_failure="Half an answer")


def test_ask_says_the_last_models_text_is_discarded_when_every_model_fails(container, library, capsys, tmp_path):
    library.add(tmp_path)
    failure = ModelFailedError("fc-a", "fakecloud", FailureReason.RATE_LIMITED, label="FakeCloud")
    cloud = FakeLLM(model="fc-a", provider="fakecloud", cloud=True, fail=failure)
    provider = FakeCloud(models={"fc-a": cloud})
    models = ModelChoices(failing_local(), CloudSetup(((provider, ("fc-a",)),), (), {"fakecloud": "FakeCloud"}))

    with pytest.raises(AllModelsFailedError):
        main._ask(asking(container, library, models), argparse.Namespace(**QUESTION, model="fc-a", fallback=[]))

    captured = capsys.readouterr()
    assert captured.out.startswith("Half an answer")
    assert captured.err.splitlines()[-1] == "The text above is discarded: no model could answer."


def test_ask_with_the_local_model_failing_alone_prints_as_on_main(container, library, capsys, tmp_path):
    library.add(tmp_path)

    with pytest.raises(ServiceUnavailableError):
        local_only = asking(container, library, ModelChoices.local_only(failing_local()))
        main._ask(local_only, argparse.Namespace(**QUESTION, model=None, fallback=[]))

    assert capsys.readouterr().err == ""


# OpenAI in ask (specs/009-openai-provider, US1, SC-001)

OPENAI_ENVIRON = {"OPENAI_API_KEY": "sk-test-openai", "OPENAI_MODELS": "gpt-a,gpt-b"}


def openai_models(library, environ=None):
    """The local model, and the cloud models that an environment configures, built as the container
    builds them: OpenAI's on the `openai_client` fixture's fake client."""
    from app.container import CLOUD_PROVIDERS

    local = FakeLLM([LOCAL_ANSWER], model="fake-llm")
    setup = create_cloud_providers(library.settings, OPENAI_ENVIRON if environ is None else environ, CLOUD_PROVIDERS)
    return ModelChoices(local, setup)


def test_ask_with_an_openai_model_says_it_goes_to_openai_and_names_the_reported_model(
    container, library, capsys, tmp_path, openai_client
):
    library.add(tmp_path)
    openai_client.script(FakeResponse(text=CLOUD_ANSWER, model="gpt-a-2026-11-01"))

    out, err = ask(asking(container, library, openai_models(library)), capsys, model="gpt-a")

    assert err == ["The question and the passages found go to OpenAI: gpt-a. If it fails, fake-llm answers, locally."]
    lines = out.splitlines()
    assert lines[0].strip() == CLOUD_ANSWER
    assert lines[-2] == "Answered by gpt-a-2026-11-01 (OpenAI)"
    assert openai_client.options["api_key"] == "sk-test-openai"
    assert len(openai_client.create_calls) == 1


@pytest.mark.parametrize(
    ("error", "words"),
    [
        (
            openai_status_error(openai.RateLimitError, 429, code="credit_balance_exhausted"),
            "its account is out of credit or over a spending or usage limit (credit_balance_exhausted)",
        ),
        (openai_status_error(openai.AuthenticationError, 401, code="invalid_api_key"), "it refused the API key"),
    ],
)
def test_ask_with_a_failing_openai_model_is_answered_by_the_local_one(
    container, library, capsys, tmp_path, openai_client, error, words
):
    library.add(tmp_path)
    openai_client.script(FakeResponse(error=error))

    out, err = ask(asking(container, library, openai_models(library)), capsys, model="gpt-a")

    assert err[-1] == f"gpt-a (OpenAI) failed: {words}. The text above is discarded: fake-llm answers from the start."
    assert LOCAL_ANSWER in out and out.splitlines()[-2] == "Answered by fake-llm (local)"
    assert "sk-test-openai" not in out + " ".join(err)


def test_ask_with_a_name_openai_doesnt_offer_lists_its_models(container, library, monkeypatch, capsys, openai_client):
    asked = asking(container, library, openai_models(library))
    monkeypatch.setattr(main, "build_container", lambda console_logs=False: asked)

    with pytest.raises(SystemExit) as stopped:
        main.main(["ask", "Where is the dog?", "--model", "gpt-x"])

    assert stopped.value.code == (
        "error: gpt-x isn't offered. Offered: fake-llm (local), gpt-a (OpenAI), gpt-b (OpenAI)."
    )
    assert openai_client.calls == 0


@pytest.mark.parametrize(
    "environ", [{}, {"ANTHROPIC_API_KEY": "sk-ant-test", "ANTHROPIC_MODELS": "claude-a"}], ids=["none", "claude"]
)
def test_without_openais_settings_ask_prints_as_before_and_openai_is_never_reached(
    container, library, capsys, tmp_path, openai_client, environ
):
    library.add(tmp_path)
    models = openai_models(library, environ=environ)

    out, err = ask(asking(container, library, models), capsys)

    assert "OpenAI" not in " ".join(f"{option.name} ({option.provider_label})" for option in models.offered())
    assert out.splitlines()[0].strip() == LOCAL_ANSWER and err == []
    assert openai_client.options is None and openai_client.calls == 0


# OpenAI in doctor (specs/009-openai-provider, US4, FR-017)

BOTH = OPENAI_ENVIRON | {"ANTHROPIC_API_KEY": "sk-ant-test", "ANTHROPIC_MODELS": "claude-a"}


@pytest.fixture
def anthropic_client(monkeypatch):
    client = FakeAnthropicClient(models={"claude-a": anthropic_model_info("claude-a")})
    monkeypatch.setattr(anthropic, "Anthropic", client.factory)
    return client


def health_of(library, environ):
    models = openai_models(library, environ)
    return HealthService(library.settings, library.runtime, library.server, library.indexes, models=models)


def provider_rows(results):
    return [(row.name, row.ok, row.detail) for row in results if row.name.split()[0] in ("anthropic", "openai")]


def test_doctor_checks_openai_after_claude_model_by_model(library, openai_client, anthropic_client):
    openai_client.script(FakeResponse(), models={"gpt-a": openai_model("gpt-a"), "gpt-b": openai_model("gpt-b")})

    rows = provider_rows(health_of(library, BOTH).run(providers=True))

    assert [name for name, _, _ in rows] == ["anthropic claude-a", "openai gpt-a", "openai gpt-b"]
    assert rows[1:] == [
        ("openai gpt-a", True, "gpt-a, owned by openai"),
        ("openai gpt-b", True, "gpt-b, owned by openai"),
    ]
    assert openai_client.create_calls == []


def test_a_key_openai_refuses_is_one_failing_row_and_claudes_are_unchanged(library, openai_client, anthropic_client):
    refused = openai_status_error(openai.AuthenticationError, 401, code="invalid_api_key")
    openai_client.script(FakeResponse(), models={"gpt-a": refused, "gpt-b": openai_model("gpt-b")})

    rows = provider_rows(health_of(library, BOTH).run(providers=True))

    assert rows[0][:2] == ("anthropic claude-a", True)
    assert rows[1:] == [("openai", False, "OpenAI refused the API key")]


def test_a_model_the_project_may_not_use_fails_its_row_only(library, openai_client, anthropic_client):
    forbidden = openai_status_error(openai.PermissionDeniedError, 403, code="model_not_allowed")
    openai_client.script(FakeResponse(), models={"gpt-a": forbidden, "gpt-b": openai_model("gpt-b")})

    rows = provider_rows(health_of(library, OPENAI_ENVIRON).run(providers=True))

    assert rows == [
        ("openai gpt-a", False, "OpenAI rejected the request: model_not_allowed"),
        ("openai gpt-b", True, "gpt-b, owned by openai"),
    ]


def test_one_openai_setting_alone_is_a_failing_row_naming_the_other(library, openai_client):
    rows = provider_rows(health_of(library, {"OPENAI_MODELS": "gpt-a"}).run(providers=True))

    assert rows == [("openai", False, "OPENAI_MODELS is set and OPENAI_API_KEY isn't: no model of OpenAI's is offered")]
    assert openai_client.calls == 0


def test_the_checks_that_run_on_their_own_leave_openai_alone(library, openai_client):
    health_of(library, OPENAI_ENVIRON).run()

    assert openai_client.calls == 0


def test_doctor_prints_openais_rows_and_fails_on_a_failing_one(container, library, capsys, openai_client):
    refused = openai_status_error(openai.AuthenticationError, 401, code="invalid_api_key")
    openai_client.script(FakeResponse(), models={"gpt-a": refused})
    checked = dataclasses.replace(container, health=health_of(library, OPENAI_ENVIRON))

    with pytest.raises(SystemExit) as stopped:
        main._doctor(checked, argparse.Namespace(inference=False))

    out = capsys.readouterr().out
    assert stopped.value.code == 1
    assert "[FAIL] openai" in out and "OpenAI refused the API key" in out
    assert "sk-test-openai" not in out
