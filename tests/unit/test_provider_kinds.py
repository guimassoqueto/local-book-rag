"""A second provider kind, registered in one place only (specs/008-cloud-llm-providers, SC-009, FR-026).

FakeCloud is added to the container's provider kinds, given a profile and its two settings, as a
real provider would be. Nothing else names it: the tabs, the commands and the services take it as
they take Anthropic.
"""

import argparse
import re
from pathlib import Path

import gradio as gr
import pytest

from app import container as container_module
from app import main
from app.config.settings import CloudProfile, EnvironmentSettings, TokenizerConfig
from app.container import Container, assemble
from app.generation.question_answering import QuestionAnsweringService
from app.interface import formatting
from app.interface.gradio_app import build_interface
from app.services.health_service import HealthService
from tests.fakes import FakeCloud
from tests.library import Library

ENVIRON = {"FAKECLOUD_API_KEY": "fake-key", "FAKECLOUD_MODELS": "fc-a,fc-b"}
PROFILE = CloudProfile(
    tokenizer=TokenizerConfig(kind="tiktoken", name="o200k_base"),
    context_size=65536,
    reasoning="low",
    reasoning_tokens=4000,
    request_timeout_seconds=120,
)


@pytest.fixture
def settings(settings, monkeypatch):
    """FakeCloud registered as a provider kind, with a profile under its name."""
    monkeypatch.setitem(container_module.CLOUD_PROVIDERS, "fakecloud", FakeCloud)
    return settings.model_copy(update={"cloud_profiles": settings.cloud_profiles | {"fakecloud": PROFILE}})


@pytest.fixture
def library(settings, tmp_path):
    library = Library(settings, tmp_path / "data", environ=ENVIRON)
    library.add(tmp_path)
    return library


@pytest.fixture
def app_container(library):
    """The application over the test library, its models as the container chose them."""
    models = library.models
    return Container(
        settings=library.settings,
        environment=EnvironmentSettings(),
        runtime=library.runtime,
        health=HealthService(
            library.settings, library.runtime, library.server, library.indexes, lambda: None, models=models
        ),
        indexes=library.indexes,
        books=library.books,
        library=library.library,
        resets=library.resets,
        retrieval=library.retrieval,
        questions=QuestionAnsweringService(library.settings, library.retrieval, models),
        summaries=library.summarizer,
        models=models,
    )


def test_the_container_offers_the_new_kind_from_its_settings_alone(settings, tmp_path):
    assembled = assemble(settings, EnvironmentSettings(data_dir=tmp_path / "assembled"), environ=ENVIRON)

    offered = [(option.name, option.provider_label) for option in assembled.models.offered()]
    assert offered[1:] == [("fc-a", "FakeCloud"), ("fc-b", "FakeCloud")]


def test_both_tabs_offer_it_and_it_answers_summarizes_and_shows_in_the_research_tab(app_container, library):
    interface = build_interface(app_container)
    blocks = interface.blocks.values()
    dropdowns = [block for block in blocks if isinstance(block, gr.Dropdown) and block.label == "Model"]
    ask = next(fn.fn for fn in interface.fns.values() if fn.api_name == "ask")
    summarize = next(fn.fn for fn in interface.fns.values() if fn.api_name == "summarize")

    question = ("Where is the dog?", [], formatting.ALL_CHAPTERS, "Same as the question", "fc-a")
    *_, (status, text, _, _, answer) = ask(*question)
    report, _, summary, _ = summarize("book_001", 1, "brief", "Same as the book", "fc-b", ["fc-a"])

    assert len(dropdowns) == 2
    assert all(("fc-a · FakeCloud", "fc-a") in dropdown.choices for dropdown in dropdowns)
    assert status.startswith("Answered by fc-a (FakeCloud)") and text == "A cloud answer [1]."
    assert (summary.model, summary.provider) == ("fc-b", "fakecloud")
    assert "`fc-b`, FakeCloud" in report
    run = formatting.run_markdown(answer, "embedding", "reranker", app_container.models)
    assert "| LLM | `fc-a` (FakeCloud) |" in run.splitlines()


def test_the_commands_take_it_in_model_and_fallback_and_doctor_checks_it(app_container, monkeypatch, capsys):
    monkeypatch.setattr(main, "build_container", lambda console_logs=False: app_container)

    main.main(["ask", "Where is the dog?", "--model", "fc-b", "--fallback", "fc-a"])
    asked = capsys.readouterr()
    with pytest.raises(SystemExit):  # the test library's other checks fail; the provider's pass
        main._doctor(app_container, argparse.Namespace(inference=False))
    doctor = capsys.readouterr().out.splitlines()

    assert asked.err.splitlines()[0] == (
        "The question and the passages found go to FakeCloud: fc-b, then fc-a. If they fail, fake-llm answers, locally."
    )
    assert "A cloud answer [1]." in asked.out and "Answered by fc-b (FakeCloud)" in asked.out
    assert "[ ok ] fakecloud fc-a       a fake model" in doctor
    assert "[ ok ] fakecloud fc-b       a fake model" in doctor


def test_no_code_of_the_application_names_it():
    application = Path(__file__).resolve().parents[2] / "app"

    named = [str(path) for path in application.rglob("*.py") if "fakecloud" in path.read_text(encoding="utf-8").lower()]

    assert named == []


# OpenAI, through the same interfaces (specs/009-openai-provider, SC-011, Principle I)


def test_no_service_tab_or_command_names_openai():
    application = Path(__file__).resolve().parents[2] / "app"
    files = [*(application / "services").rglob("*.py"), *(application / "interface").rglob("*.py")]
    files.append(application / "main.py")

    named = [str(path) for path in files if "openai" in path.read_text(encoding="utf-8").lower()]

    assert named == []


def test_no_code_of_the_application_names_one_of_openais_models():
    application = Path(__file__).resolve().parents[2] / "app"

    named = [
        str(path)
        for path in application.rglob("*.py")
        if re.search(r"gpt-[56]", path.read_text(encoding="utf-8"), flags=re.IGNORECASE)
    ]

    assert named == []
