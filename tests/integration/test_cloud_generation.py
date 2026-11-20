"""Runs every model of every cloud provider whose settings are set, for real, as the application
reads its output.

How a model's output is read is checked on the real models before they are trusted (constitution
V; specs/008-cloud-llm-providers, SC-003, FR-033; specs/009-openai-provider, SC-003, FR-026). Each
provider runs only when its two settings, such as ANTHROPIC_API_KEY and ANTHROPIC_MODELS, or
OPENAI_API_KEY and OPENAI_MODELS, are both set in the shell that runs `make test-integration`, and
is skipped on its own otherwise. Every test here is a paid request to the provider, a few cents per
model.

The run also prints, for each model, the app's token estimate of each prompt beside the count the
provider reported, and the largest ratio, which goes into the provider's profile and
docs/decisions.md (specs/009, SC-009). Run with `-s` to see it.
"""

import os
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings, read_provider_credentials
from app.container import CLOUD_PROVIDERS
from app.generation.base import Generation, GenerationParameters
from app.generation.choices import ModelChoices
from app.generation.factory import CloudSetup
from app.generation.prompts import question_answering_messages
from app.generation.question_answering import check_abstention, read_reply
from app.generation.summarization import ChapterSummarizer
from app.ingestion.chunker import Chunk
from app.storage.catalog import Book, BookCatalog, BookStatus
from app.storage.repositories import SummaryDocuments
from tests.fakes import FakeChunks, FakeLLM, WordLocator

CREDENTIALS = {name: read_provider_credentials(name, os.environ) for name in CLOUD_PROVIDERS}
CASES = yaml.safe_load((Path(__file__).parent / "cloud_cases.yaml").read_text(encoding="utf-8"))
# For each (provider, model): what each prompt measured, as (what, the app's estimate, the
# provider's count, the tokens generated, the finish reason).
MEASURES: dict[tuple[str, str], list[tuple[str, int, int, int, str | None]]] = defaultdict(list)

pytestmark = pytest.mark.integration


def pairs():
    """Each (provider, model) to run; a provider without both its settings is one skipped case."""
    params = []
    for name, credentials in CREDENTIALS.items():
        if credentials.api_key is None or not credentials.models:
            prefix = name.upper()
            reason = f"{prefix}_API_KEY and {prefix}_MODELS aren't both set"
            params.append(pytest.param(name, None, marks=pytest.mark.skip(reason=reason), id=f"{name}"))
        else:
            params += [pytest.param(name, model, id=f"{name}-{model}") for model in credentials.models]
    return params


@pytest.fixture(scope="module")
def settings():
    return load_settings(EnvironmentSettings().config_dir)


@pytest.fixture(scope="module")
def clouds(settings):
    """Each configured provider, with the repository's profile, as the container builds it."""
    return {
        name: CLOUD_PROVIDERS[name](credentials, settings.cloud_profiles[name])
        for name, credentials in CREDENTIALS.items()
        if credentials.api_key is not None and credentials.models
    }


@pytest.fixture(scope="module", autouse=True)
def token_report():
    """Prints, after the module's tests, the app's estimates beside the providers' counts."""
    yield
    for (provider, model), rows in sorted(MEASURES.items()):
        print(f"\n{provider} {model}: estimate, counted, ratio, generated, finish")
        for what, estimate, counted, generated, finish in rows:
            print(f"  {what:<44} {estimate:>6} {counted:>6} {counted / estimate:>6.3f} {generated:>6} {finish}")
        largest = max(counted / estimate for _, estimate, counted, _, _ in rows)
        print(f"  largest ratio: {largest:.3f}")


class Measured:
    """A model's provider that records, for each prompt it is sent, the app's estimate beside the
    provider's count."""

    def __init__(self, llm, provider, what):
        self._llm = llm
        self._key = (provider, llm.model)
        self._what = what
        self.model = llm.model
        self.provider = llm.provider
        self.check_abstentions = llm.check_abstentions

    def context_size(self):
        return self._llm.context_size()

    def count_tokens(self, text):
        return self._llm.count_tokens(text)

    def stream(self, messages, parameters):
        estimate = sum(self._llm.count_tokens(message.content) for message in messages)
        for event in self._llm.stream(messages, parameters):
            if isinstance(event, Generation):
                stats = event.stats
                row = (self._what, estimate, stats.prompt_tokens, stats.completion_tokens, stats.finish_reason)
                MEASURES[self._key].append(row)
            yield event

    def generate(self, messages, parameters):
        for event in self.stream(messages, parameters):
            if isinstance(event, Generation):
                return event
        raise AssertionError("stream() always ends with a Generation")


class MeasuredCloud:
    """A provider kind whose models are `Measured`."""

    def __init__(self, cloud, what):
        self._cloud = cloud
        self._what = what
        self.name = cloud.name
        self.label = cloud.label

    def model(self, name):
        return Measured(self._cloud.model(name), self.name, self._what)


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


def reply_to(settings, clouds, chunks, provider, model, question):
    """A model's reply, read as the application reads it: the marker, the citations, and, when the
    profile asks, the model reading its reply again for an abstention written only in words."""
    llm = clouds[provider].model(model)
    task = parameters(settings)
    measured = Measured(llm, provider, f"question: {question[:34]}")
    generation = measured.generate(question_answering_messages(question, chunks, None), task)
    return generation, check_abstention(llm, question, read_reply(generation, chunks), task)


@pytest.mark.parametrize(("provider", "model"), pairs())
def test_the_key_and_the_model_pass_the_check(clouds, provider, model):
    [row] = clouds[provider].check([model])

    assert row.ok, row.detail


@pytest.mark.parametrize(("provider", "model"), pairs())
@pytest.mark.parametrize("case", CASES["answerable"], ids=lambda case: case["section"])
def test_an_answerable_question_is_answered_with_citations_that_resolve(
    settings, clouds, chunks, provider, model, case
):
    generation, reply = reply_to(settings, clouds, chunks, provider, model, case["question"])

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


@pytest.mark.parametrize(("provider", "model"), pairs())
@pytest.mark.parametrize("case", CASES["unanswerable"], ids=lambda case: case["question"][:40])
def test_an_unanswerable_question_gets_the_marker(settings, clouds, chunks, provider, model, case):
    _, reply = reply_to(settings, clouds, chunks, provider, model, case["question"])

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


@pytest.mark.parametrize(("provider", "model"), pairs())
def test_the_chapter_is_summarized_and_cited_by_lookup(settings, clouds, chunks, provider, model, tmp_path):
    catalog = BookCatalog(tmp_path / "catalog.db")
    catalog.add(excerpt_book(chunks))
    # The local model answers only if the cloud model fails, which the provider check below catches.
    cloud = MeasuredCloud(clouds[provider], "summary")
    setup = CloudSetup(((cloud, (model,)),), (), {provider: cloud.label})
    choices = ModelChoices(FakeLLM(["A local summary."]), setup)
    summarizer = ChapterSummarizer(
        settings, choices, catalog, FakeChunks(chunks), SummaryDocuments(tmp_path / "summaries"), WordLocator(chunks)
    )

    summary = summarizer.summarize("book_test", 1, CASES["summary_type"], model=model)

    # The model as the provider reported it, which may name a dated snapshot of the model asked for.
    assert summary.model.startswith(model), summary.model
    assert (summary.provider, summary.attempts) == (provider, ())
    assert summary.strategy == "direct"
    assert summary.statements > 0 and summary.citations, summary.text
    assert summary.prompt_tokens > 0 and summary.completion_tokens > 0
