"""Runs every Claude model in ANTHROPIC_MODELS for real, as the application reads its output.

How a model's output is read is checked on the real models before they are trusted (constitution
V; specs/008-cloud-llm-providers, SC-003, FR-033). Skipped unless ANTHROPIC_API_KEY and
ANTHROPIC_MODELS are both set, in the shell that runs `make test-integration`. Every test here is a
paid request to Anthropic, a few cents per model.
"""

import os
from pathlib import Path

import pytest
import yaml

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings, read_provider_credentials
from app.generation.anthropic_provider import AnthropicCloud
from app.generation.base import GenerationParameters
from app.generation.choices import ModelChoices
from app.generation.factory import CloudSetup
from app.generation.prompts import question_answering_messages
from app.generation.question_answering import read_reply
from app.generation.summarization import ChapterSummarizer
from app.ingestion.chunker import Chunk
from app.storage.catalog import Book, BookCatalog, BookStatus
from app.storage.repositories import SummaryDocuments
from tests.fakes import FakeChunks, FakeLLM, WordLocator

CREDENTIALS = read_provider_credentials("anthropic", os.environ)
CASES = yaml.safe_load((Path(__file__).parent / "cloud_cases.yaml").read_text(encoding="utf-8"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        CREDENTIALS.api_key is None or not CREDENTIALS.models,
        reason="ANTHROPIC_API_KEY and ANTHROPIC_MODELS aren't both set",
    ),
]


@pytest.fixture(scope="module")
def settings():
    return load_settings(EnvironmentSettings().config_dir)


@pytest.fixture(scope="module")
def cloud(settings):
    """Anthropic, with the repository's profile, as the container builds it."""
    return AnthropicCloud(CREDENTIALS, settings.cloud_profiles["anthropic"])


@pytest.fixture(scope="module")
def chunks():
    excerpt = CASES["excerpt"]
    return [
        Chunk(
            chunk_id=f"book_test_chapter_01_chunk_{index:04d}",
            book_id="book_test",
            book_title=excerpt["book_title"],
            chapter_number=1,
            chapter_title=excerpt["chapter_title"],
            section_title=section["title"],
            chunk_index=index,
            language="en",
            text=" ".join(section["text"].split()),
        )
        for index, section in enumerate(excerpt["sections"])
    ]


def parameters(settings):
    task = settings.generation.question_answering
    return GenerationParameters(
        temperature=settings.llm.temperature if task.temperature is None else task.temperature,
        max_tokens=task.max_tokens or settings.llm.max_tokens,
    )


def models():
    return CREDENTIALS.models or ("none",)


@pytest.mark.parametrize("model", models())
def test_the_key_and_the_model_pass_the_check(cloud, model):
    [row] = cloud.check([model])

    assert row.ok, row.detail


@pytest.mark.parametrize("model", models())
@pytest.mark.parametrize("case", CASES["answerable"], ids=lambda case: case["section"])
def test_an_answerable_question_is_answered_with_citations_that_resolve(settings, cloud, chunks, model, case):
    messages = question_answering_messages(case["question"], chunks, None)
    generation = cloud.model(model).generate(messages, parameters(settings))

    reply = read_reply(generation, chunks)

    assert not reply.insufficient_evidence, reply.text
    assert reply.citations, f"no citation the app recognizes: {reply.text}"
    assert not reply.invented_citations, reply.text
    cited = {citation.number for citation in reply.citations}
    answering = next(number for number, chunk in enumerate(chunks, start=1) if chunk.section_title == case["section"])
    assert answering in cited, f"cites {sorted(cited)}, not the passage that answers: {reply.text}"
    stats = generation.stats
    assert stats.prompt_tokens > 0 and stats.completion_tokens > 0 and stats.time_to_first_token > 0
    assert stats.load_seconds is None and stats.prompt_seconds is None
    assert generation.thinking_summarized


@pytest.mark.parametrize("model", models())
@pytest.mark.parametrize("case", CASES["unanswerable"], ids=lambda case: case["question"][:40])
def test_an_unanswerable_question_gets_the_marker(settings, cloud, chunks, model, case):
    messages = question_answering_messages(case["question"], chunks, None)
    generation = cloud.model(model).generate(messages, parameters(settings))

    reply = read_reply(generation, chunks)

    assert reply.insufficient_evidence, reply.text


def excerpt_book(chunks):
    return Book(
        book_id="book_test",
        title=CASES["excerpt"]["book_title"],
        author=None,
        original_filename="excerpt.md",
        original_path="excerpt.md",
        checksum="excerpt",
        format="markdown",
        language="en",
        chapter_count=1,
        chunk_count=len(chunks),
        embedding_model="none",
        index_version=1,
        status=BookStatus.INDEXED,
        status_detail=None,
        revision=1,
        created_at="now",
        indexed_at="now",
    )


@pytest.mark.parametrize("model", models())
def test_the_chapter_is_summarized_and_cited_by_lookup(settings, cloud, chunks, model, tmp_path):
    catalog = BookCatalog(tmp_path / "catalog.db")
    catalog.add(excerpt_book(chunks))
    # The local model answers only if Claude fails, which the provider check below catches.
    setup = CloudSetup(((cloud, (model,)),), (), {"anthropic": "Anthropic"})
    choices = ModelChoices(FakeLLM(["A local summary."]), setup)
    summarizer = ChapterSummarizer(
        settings, choices, catalog, FakeChunks(chunks), SummaryDocuments(tmp_path / "summaries"), WordLocator(chunks)
    )

    summary = summarizer.summarize("book_test", 1, CASES["summary_type"], model=model)

    assert (summary.model, summary.provider, summary.attempts) == (model, "anthropic", ())
    assert summary.strategy == "direct"
    assert summary.statements > 0 and summary.citations, summary.text
    assert summary.prompt_tokens > 0 and summary.completion_tokens > 0
