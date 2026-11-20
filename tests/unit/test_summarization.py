import json
import logging
import re

import openai
import pytest

from app.errors import (
    AllModelsFailedError,
    ChapterNotFoundError,
    ConfigurationError,
    GenerationError,
    ModelChoiceError,
    ModelFailedError,
    ServiceUnavailableError,
)
from app.generation.base import FINISHED_BY_LENGTH, Attempt, FailureReason
from app.generation.choices import ModelChoices
from app.generation.factory import CloudSetup, create_cloud_providers
from app.generation.summarization import ChapterSummarizer, _Run
from app.storage.catalog import Book, BookCatalog, BookStatus
from app.storage.repositories import SummaryDocuments
from app.utils.logging import INFERENCE_LOGGER, configure_logging
from tests.fakes import FakeChunks, FakeCloud, FakeLLM, FakeResponse, make_chunk, openai_status_error

FINAL = """## Chapter overview
The chapter explains how costs work in practice.

## Main thesis
Every choice has a cost that is easy to overlook.

- The first point is about the things you give up.
1. **Second** – The second point is about the time you spend.
"""


def book():
    return Book(
        book_id="book_001",
        title="The Book",
        author=None,
        original_filename="b.md",
        original_path="x",
        checksum="c",
        format="markdown",
        language="en",
        chapter_count=1,
        chunk_count=1,
        embedding_model="m",
        index_version=1,
        status=BookStatus.INDEXED,
        status_detail=None,
        revision=1,
        created_at="now",
        indexed_at="now",
    )


def chapter(count, words=500, chapter=4, section="Section"):
    return [
        make_chunk(
            f"passage{index} " + " ".join(["word"] * words),
            index=index + 10,
            chapter=chapter,
            section=section,
        )
        for index in range(count)
    ]


class FirstChunkLocator:
    """Cites by a rule that tests can read: a statement mentioning a point cites the second chunk."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.statements = []

    def closest_chunk(self, statement, book_id, chapter_number):
        self.statements.append(statement)
        if "unsupported" in statement:
            return None
        return self.chunks[1 if "point" in statement else 0]


@pytest.fixture
def catalog(tmp_path):
    catalog = BookCatalog(tmp_path / "catalog.db")
    catalog.add(book())
    return catalog


def summarizer(settings, llm, catalog, chunks, tmp_path, locator=None):
    """The summarizer, on the local model alone, or on given choices."""
    models = llm if isinstance(llm, ModelChoices) else ModelChoices.local_only(llm)
    return ChapterSummarizer(
        settings,
        models,
        catalog,
        FakeChunks(chunks),
        SummaryDocuments(tmp_path / "summaries"),
        locator or FirstChunkLocator(chunks),
    )


def prompts(llm):
    return [messages[-1].content for messages, _ in llm.calls]


def test_a_short_chapter_is_summarized_directly(settings, catalog, tmp_path):
    chunks = chapter(2, words=100)
    llm = FakeLLM([FINAL])

    summary = summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert summary.strategy == "direct"
    assert summary.steps == 1
    assert "passage0" in prompts(llm)[0] and "passage1" in prompts(llm)[0]


def test_a_long_chapter_goes_through_map_reduce(settings, catalog, tmp_path):
    chunks = chapter(30)
    llm = FakeLLM(respond=lambda messages, parameters: FINAL)

    summary = summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert summary.strategy == "map_reduce"
    assert summary.steps > 2


def test_every_chunk_is_read_in_order_and_exactly_once(settings, catalog, tmp_path):
    chunks = chapter(30)
    llm = FakeLLM(respond=lambda messages, parameters: "A short partial summary.")

    summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    sent = " ".join(prompts(llm)[:-1])
    positions = [sent.index(f"passage{index} ") for index in range(30)]
    assert positions == sorted(positions)
    assert all(sent.count(f"passage{index} ") == 1 for index in range(30))


def test_only_the_requested_chapter_is_read(settings, catalog, tmp_path):
    chunks = chapter(2, words=50) + [make_chunk("other chapter text", index=99, chapter=5)]
    llm = FakeLLM([FINAL])

    summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert "other chapter text" not in prompts(llm)[0]


def test_parts_are_sized_to_fit_the_final_prompt_together(settings, catalog, tmp_path):
    llm = FakeLLM(respond=lambda messages, parameters: "Partial.")

    summarizer(settings, llm, catalog, chapter(30), tmp_path).summarize("book_001", 4, "standard")

    limits = {int(prompt.split("at most ")[1].split()[0]) for prompt in prompts(llm)[:-1]}
    budget = 8192 * 0.9 - settings.generation.summarization.max_tokens
    assert all(limit <= budget / 4 for limit in limits)


def test_batches_leave_room_for_the_reply_to_do_them_justice(settings, catalog, tmp_path):
    chunks = chapter(30)
    llm = FakeLLM(respond=lambda messages, parameters: "Partial.")
    limit = settings.generation.summarization.map_max_tokens

    summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    for prompt in prompts(llm)[:-1]:
        assert llm.count_tokens(prompt) <= limit * 4 + 100


def test_a_reply_cut_off_by_its_limit_is_redone_in_halves(settings, catalog, tmp_path):
    chunks = chapter(30)
    llm = FakeLLM(respond=lambda m, p: "Partial.", finish_reasons=[FINISHED_BY_LENGTH])

    summary = summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    first_attempt, first_half, second_half = prompts(llm)[:3]
    assert "passage0 " in first_attempt and "passage5 " in first_attempt
    assert "passage0 " in first_half and "passage5 " not in first_half
    assert "passage5 " in second_half and "passage0 " not in second_half
    assert summary.chunks_covered == 30
    assert summary.incomplete_steps == 0


def test_a_single_chunk_cut_off_counts_as_lost(settings, catalog, tmp_path):
    chunks = chapter(30)
    llm = FakeLLM(
        respond=lambda m, p: "Partial.",
        finish=lambda prompt: FINISHED_BY_LENGTH if "passage0 " in prompt else "stop",
    )

    summary = summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert summary.chunks_covered == 29
    assert summary.incomplete_steps == 1


def test_partials_too_long_for_the_final_prompt_are_merged(settings, catalog, tmp_path):
    chunks = chapter(80)
    partial = " ".join(["partial"] * 600)
    llm = FakeLLM(respond=lambda messages, parameters: partial if "Summarize" in messages[-1].content else "Merged.")

    summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert any(prompt.startswith("Merge") for prompt in prompts(llm))


def test_a_merge_gets_room_to_overrun_its_word_target(settings, catalog, tmp_path):
    chunks = chapter(80)
    partial = " ".join(["partial"] * 600)
    llm = FakeLLM(respond=lambda messages, parameters: partial if "Summarize" in messages[-1].content else "Merged.")
    limit = settings.generation.summarization.map_max_tokens

    summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    merges = [parameters for messages, parameters in llm.calls if messages[-1].content.startswith("Merge")]
    assert {parameters.max_tokens for parameters in merges} == {limit * 2}


def test_a_cut_off_merge_keeps_its_parts_instead_of_losing_the_last(settings, catalog, tmp_path):
    chunks = chapter(80)
    partial = " ".join(["partial"] * 600)
    merges = []

    def finish(prompt):
        if not prompt.startswith("Merge"):
            return "stop"
        merges.append(prompt)
        return FINISHED_BY_LENGTH if len(merges) == 1 else "stop"

    llm = FakeLLM(
        respond=lambda messages, parameters: partial if "Summarize" in messages[-1].content else "Merged.",
        finish=finish,
    )

    summary = summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert len(merges) > 1
    assert summary.incomplete_steps == 0


def test_parts_that_no_merge_can_hold_are_condensed_one_by_one(settings, catalog, tmp_path):
    # gpt-oss merged three parts into a text as long as all three, and hit its limit every time.
    chunks = chapter(80)
    partial = " ".join(["partial"] * 600)

    def several_parts(prompt):
        return prompt.startswith("Merge") and "\n---\n" in prompt

    def respond(messages, parameters):
        prompt = messages[-1].content
        if prompt.startswith("Merge"):
            return " ".join(["merged"] * 3000) if several_parts(prompt) else "A condensed part."
        return partial if "Summarize" in prompt else FINAL

    llm = FakeLLM(respond=respond, finish=lambda prompt: FINISHED_BY_LENGTH if several_parts(prompt) else "stop")

    summary = summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert summary.strategy == "map_reduce"
    assert any(prompt.startswith("Merge") and not several_parts(prompt) for prompt in prompts(llm))


def test_a_merge_prompt_leaves_room_for_its_reply(settings, catalog, tmp_path):
    llm = FakeLLM(["Unused."])
    partials = [" ".join(["partial"] * 2000)] * 5

    run = _Run(llm, "en", "en", "A chapter")
    groups = summarizer(settings, llm, catalog, chapter(1), tmp_path)._groups(run, partials)

    reply = settings.generation.summarization.map_max_tokens * 2
    assert [len(group) for group in groups] == [2, 2, 1]
    assert all(sum(llm.count_tokens(part) for part in group) + reply < llm.context_size() for group in groups)


def test_merges_that_barely_condense_end_in_an_error_instead_of_endless_rounds(settings, catalog, tmp_path):
    chunks = chapter(80)
    partial = " ".join(["partial"] * 600)

    def respond(messages, parameters):
        prompt = messages[-1].content
        if prompt.startswith("Merge"):
            return " ".join(["merged"] * (len(prompt.split()) - 60))  # a little shorter than what it read
        return partial if "Summarize" in prompt else FINAL

    llm = FakeLLM(respond=respond)

    with pytest.raises(GenerationError, match="too long"):
        summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert sum(prompt.startswith("Merge") for prompt in prompts(llm)) < 20


def test_merges_that_overrun_their_length_are_asked_for_less(settings, catalog, tmp_path):
    # Asked for 540 words, gpt-oss merged two parts into 1,200: no shorter than the parts.
    chunks = chapter(80)
    partial = " ".join(["partial"] * 600)

    def asked(prompt):
        return int(re.search(r"at most (\d+) words", prompt).group(1))

    def respond(messages, parameters):
        prompt = messages[-1].content
        if prompt.startswith("Merge"):
            return " ".join(["merged"] * asked(prompt) * 4)
        return partial if "Summarize" in prompt else FINAL

    llm = FakeLLM(respond=respond)

    summary = summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    lengths = [asked(prompt) for prompt in prompts(llm) if prompt.startswith("Merge")]
    assert summary.strategy == "map_reduce"
    assert min(lengths) < max(lengths)


def test_a_merge_no_shorter_than_its_parts_keeps_them(settings, catalog, tmp_path):
    llm = FakeLLM(["word " * 3000])
    parts = ["first part " * 200, "second part " * 200]
    run = _Run(llm, "en", "en", "A chapter")

    merged = summarizer(settings, llm, catalog, chapter(1), tmp_path)._merge(run, parts, 300)

    assert merged == parts


def test_partials_that_cannot_shrink_end_in_an_error(settings, catalog, tmp_path):
    chunks = chapter(80)
    huge = " ".join(["partial"] * 5000)
    llm = FakeLLM(
        respond=lambda messages, parameters: huge,
        finish=lambda prompt: FINISHED_BY_LENGTH if prompt.startswith("Merge") else "stop",
    )

    with pytest.raises(GenerationError, match="too long"):
        summarizer(settings, llm, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")


def test_the_final_prompt_asks_for_the_required_structure(settings, catalog, tmp_path):
    llm = FakeLLM([FINAL])

    summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "standard")

    prompt = prompts(llm)[-1]
    for section in (
        "Chapter overview",
        "Main thesis",
        "Main arguments",
        "Important concepts and definitions",
        "Supporting examples",
        "Relationships between concepts",
        "Important conclusions",
    ):
        assert f"## {section}" in prompt


@pytest.mark.parametrize("summary_type", ["brief", "standard", "comprehensive", "analytical"])
def test_each_type_sets_its_length(settings, catalog, tmp_path, summary_type):
    llm = FakeLLM([FINAL])
    expected = settings.generation.summarization.types[summary_type]

    summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, summary_type)

    assert f"about {expected.target_words} words" in prompts(llm)[-1]
    assert expected.style in prompts(llm)[-1]


def test_a_type_can_have_a_higher_limit(settings, catalog, tmp_path):
    llm = FakeLLM([FINAL])

    summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "analytical")

    assert llm.calls[-1][1].max_tokens == 4000


def test_an_unknown_type_is_reported(settings, catalog, tmp_path):
    with pytest.raises(ConfigurationError, match="analytical"):
        summarizer(settings, FakeLLM([FINAL]), catalog, chapter(2), tmp_path).summarize("book_001", 4, "epic")


def test_an_unknown_chapter_is_reported(settings, catalog, tmp_path):
    with pytest.raises(ChapterNotFoundError):
        summarizer(settings, FakeLLM([FINAL]), catalog, chapter(2), tmp_path).summarize("book_001", 9, "standard")


def test_citations_come_from_looking_statements_up_not_from_the_model(settings, catalog, tmp_path):
    chunks = chapter(2, words=100)

    summary = summarizer(settings, FakeLLM([FINAL]), catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert "how costs work in practice. [1]" in summary.text
    assert "the things you give up. [2]" in summary.text
    assert [citation.number for citation in summary.citations] == [1, 2]


def test_tags_a_model_counts_up_on_its_own_mean_nothing(settings, catalog, tmp_path):
    llm = FakeLLM(["A statement with enough words to look up [S7] [S8]."])

    summary = summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "standard")

    assert [citation.number for citation in summary.citations] == [1]


def test_the_prompts_ask_for_no_tags_at_all(settings, catalog, tmp_path):
    llm = FakeLLM(respond=lambda messages, parameters: "Partial.")

    summarizer(settings, llm, catalog, chapter(30), tmp_path).summarize("book_001", 4, "standard")

    assert not any("[S" in message.content for messages, _ in llm.calls for message in messages)


def test_headings_and_list_markers_survive_citing(settings, catalog, tmp_path):
    summary = summarizer(settings, FakeLLM([FINAL]), catalog, chapter(2, words=100), tmp_path).summarize(
        "book_001", 4, "standard"
    )

    assert "## Chapter overview\n" in summary.text
    assert "\n- The first point" in summary.text
    assert "\n1. **Second**" in summary.text


def test_a_heading_wrapped_in_bold_becomes_a_real_heading(settings, catalog, tmp_path):
    reply = "**## Chapter overview** The chapter explains how costs work in practice.\n\n**## Main thesis**\nA claim."
    llm = FakeLLM([reply])

    summary = summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "standard")

    assert summary.text.startswith("## Chapter overview\n\nThe chapter explains how costs work in practice. [1]")
    assert "\n## Main thesis\n" in summary.text
    assert "**" not in summary.text.split("## References")[0]


def test_headings_are_not_looked_up(settings, catalog, tmp_path):
    chunks = chapter(2, words=100)
    locator = FirstChunkLocator(chunks)

    summarizer(settings, FakeLLM([FINAL]), catalog, chunks, tmp_path, locator).summarize("book_001", 4, "standard")

    assert not any("Chapter overview" in statement for statement in locator.statements)


def test_statements_without_a_source_are_counted_and_left_uncited(settings, catalog, tmp_path):
    llm = FakeLLM(["An unsupported claim that came from nowhere at all."])

    summary = summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "standard")

    assert summary.statements_without_source == 1
    assert summary.citations == ()
    assert "[" not in summary.text


def test_references_are_built_from_what_is_cited(settings, catalog, tmp_path):
    summary = summarizer(settings, FakeLLM([FINAL]), catalog, chapter(2, words=100), tmp_path).summarize(
        "book_001", 4, "standard"
    )

    references = summary.text.split("## References")[1]
    assert "[1] Section: “passage0" in references
    assert "[2] Section: “passage1" in references
    assert "p." not in references.replace("passage", "")
    assert "“passage0" in references


def test_references_work_without_a_section(settings, catalog, tmp_path):
    chunks = chapter(2, words=100, section=None)

    summary = summarizer(settings, FakeLLM([FINAL]), catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert "- [1] “passage0" in summary.text.split("## References")[1]


def test_the_language_can_be_chosen(settings, catalog, tmp_path):
    llm = FakeLLM([FINAL])

    summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize(
        "book_001", 4, "standard", language="Portuguese"
    )

    system, user = llm.calls[-1][0]
    assert "Write in Portuguese" in system.content
    assert "## Visão geral do capítulo" in user.content  # asked to translate them, qwen3.5 didn't
    assert "## Chapter overview" not in user.content


def test_the_book_language_is_the_default(settings, catalog, tmp_path):
    llm = FakeLLM([FINAL])

    summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "standard")

    assert "Write in English" in llm.calls[-1][0][0].content


def test_a_book_language_without_a_name_falls_back_to_the_text(settings, catalog, tmp_path):
    # Told "Write in pt", gpt-oss and qwen3.5 summarized Portuguese chapters in English.
    catalog.update("book_001", language="nl")
    llm = FakeLLM([FINAL])

    summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "standard")

    system, user = llm.calls[-1][0]
    assert "Write in the language of the text" in system.content
    assert "Write in nl" not in system.content
    assert "## Chapter overview" in user.content
    assert "translated into the language of your reply" in user.content


def test_claims_are_checked_when_that_is_enabled(settings, catalog, tmp_path):
    config = settings.generation.summarization.model_copy(update={"verify_claims": True})
    generation = settings.generation.model_copy(update={"summarization": config})
    checked = settings.model_copy(update={"generation": generation})
    llm = FakeLLM([FINAL, "All claims are supported."])

    summary = summarizer(checked, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "standard")

    assert summary.verification == "All claims are supported."
    assert "passage0" in prompts(llm)[-1]


def test_claims_are_not_checked_by_default(settings, catalog, tmp_path):
    summary = summarizer(settings, FakeLLM([FINAL]), catalog, chapter(2, words=100), tmp_path).summarize(
        "book_001", 4, "standard"
    )

    assert summary.verification is None


def test_progress_is_reported(settings, catalog, tmp_path):
    messages = []
    llm = FakeLLM(respond=lambda m, p: "Partial.")

    summarizer(settings, llm, catalog, chapter(30), tmp_path).summarize(
        "book_001", 4, "standard", on_progress=messages.append
    )

    assert messages[0].startswith("Reading part 1 of")
    assert "Writing the final summary" in messages


def test_a_model_that_returns_nothing_fails_clearly(settings, catalog, tmp_path):
    with pytest.raises(GenerationError, match="no text"):
        summarizer(settings, FakeLLM([" "]), catalog, chapter(2, words=100), tmp_path).summarize(
            "book_001", 4, "standard"
        )


def test_a_final_summary_cut_off_is_flagged(settings, catalog, tmp_path):
    llm = FakeLLM([FINAL], finish_reasons=[FINISHED_BY_LENGTH])

    summary = summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "standard")

    assert summary.incomplete_steps == 1


def test_a_summary_can_be_saved_with_how_it_was_made(settings, catalog, tmp_path):
    service = summarizer(settings, FakeLLM([FINAL]), catalog, chapter(2, words=100), tmp_path)
    summary = service.summarize("book_001", 4, "brief")

    path = service.save(summary)

    assert path.endswith("summaries/book_001/chapter_04_brief.md")
    assert "Chapter overview" in (tmp_path / "summaries/book_001/chapter_04_brief.md").read_text(encoding="utf-8")
    metadata = json.loads((tmp_path / "summaries/book_001/chapter_04_brief.json").read_text(encoding="utf-8"))
    assert metadata["model"] == "fake-llm"
    assert metadata["chunks_covered"] == 2


# Cloud models (specs/008-cloud-llm-providers, research.md R8)

RATE_LIMITED = ModelFailedError("fc-a", "fakecloud", FailureReason.RATE_LIMITED, label="FakeCloud")


def cloud(name="fc-a", replies=(FINAL,), context_size=65536 - 4000, **options):
    return FakeLLM(list(replies), model=name, provider="fakecloud", cloud=True, context_size=context_size, **options)


def choices(local_llm, *cloud_llms):
    """The local model, and FakeCloud offering each given model, scripted."""
    provider = FakeCloud(models={llm.model: llm for llm in cloud_llms})
    names = tuple(llm.model for llm in cloud_llms)
    return ModelChoices(local_llm, CloudSetup(((provider, names),), (), {"fakecloud": "FakeCloud"}))


def test_without_a_model_the_local_model_writes_it_and_says_so(settings, catalog, tmp_path):
    local, fc = FakeLLM([FINAL]), cloud()

    summary = summarizer(settings, choices(local, fc), catalog, chapter(2, words=100), tmp_path).summarize(
        "book_001", 4, "standard"
    )

    assert (summary.model, summary.provider, summary.attempts) == ("fake-llm", "ollama", ())
    assert fc.calls == []


def test_a_cloud_model_makes_it_as_a_local_one_does_within_its_own_window(settings, catalog, tmp_path):
    chunks = chapter(30)
    local, fc = FakeLLM(respond=lambda messages, parameters: FINAL), cloud()

    by_local = summarizer(settings, local, catalog, chunks, tmp_path).summarize("book_001", 4, "standard")
    by_cloud = summarizer(settings, choices(FakeLLM([FINAL]), fc), catalog, chunks, tmp_path).summarize(
        "book_001", 4, "standard", model="fc-a"
    )

    assert (by_local.strategy, by_cloud.strategy) == ("map_reduce", "direct")
    assert (by_cloud.model, by_cloud.provider, by_cloud.attempts) == ("fc-a", "fakecloud", ())
    assert (by_cloud.steps, by_cloud.prompt_tokens, by_cloud.completion_tokens) == (1, 100, 20)
    assert by_cloud.citations and by_cloud.statements


def test_a_cloud_model_failing_at_its_second_step_hands_the_whole_summary_on(settings, catalog, tmp_path):
    chunks = chapter(30)
    local = FakeLLM(respond=lambda messages, parameters: FINAL)
    fc = cloud(context_size=8192, fail=RATE_LIMITED, fail_after_calls=1, respond=lambda messages, parameters: FINAL)
    progress = []

    summary = summarizer(settings, choices(local, fc), catalog, chunks, tmp_path).summarize(
        "book_001", 4, "standard", on_progress=progress.append, model="fc-a"
    )

    assert "fc-a (FakeCloud) failed: it limited the rate. Starting again with fake-llm." in progress
    assert (summary.model, summary.provider) == ("fake-llm", "ollama")
    assert summary.attempts == (Attempt("fc-a", "fakecloud", FailureReason.RATE_LIMITED, "", 100, 20, step=2),)
    assert "passage0" in prompts(local)[0]
    assert len(fc.calls) == 2


def test_a_saved_summary_records_its_provider_its_failures_and_a_cloud_models_tokens(settings, catalog, tmp_path):
    chunks = chapter(30)
    failing = cloud(
        context_size=8192, fail=RATE_LIMITED, fail_after_calls=1, respond=lambda messages, parameters: FINAL
    )
    service = summarizer(settings, choices(FakeLLM([FINAL]), failing, cloud("fc-b")), catalog, chunks, tmp_path)

    service.save(service.summarize("book_001", 4, "brief", model="fc-a", fallbacks=["fc-b"]))
    by_cloud = json.loads((tmp_path / "summaries/book_001/chapter_04_brief.json").read_text(encoding="utf-8"))
    service.save(service.summarize("book_001", 4, "standard"))
    by_local = json.loads((tmp_path / "summaries/book_001/chapter_04_standard.json").read_text(encoding="utf-8"))

    assert (by_cloud["model"], by_cloud["provider"], by_cloud["tokens"]) == (
        "fc-b",
        "fakecloud",
        {"read": 100, "generated": 20},
    )
    assert by_cloud["failed_attempts"] == [
        {
            "model": "fc-a",
            "provider": "fakecloud",
            "reason": "rate limited",
            "detail": "",
            "step": 2,
            "tokens": {"read": 100, "generated": 20},
        }
    ]
    assert (by_local["provider"], by_local["failed_attempts"]) == ("ollama", [])
    assert "tokens" not in by_local


def test_a_refused_sequence_stops_before_the_chapter_is_read(settings, catalog, tmp_path):
    source = FakeChunks(chapter(2, words=100))
    service = ChapterSummarizer(
        settings, choices(FakeLLM([FINAL]), cloud()), catalog, source, SummaryDocuments(tmp_path), FirstChunkLocator([])
    )

    with pytest.raises(ModelChoiceError, match="fc-x isn't offered"):
        service.summarize("book_001", 4, "standard", model="fc-x")

    assert source.loads == 0


def test_when_every_model_fails_each_failure_is_listed_the_local_one_last(settings, catalog, tmp_path):
    local = FakeLLM([FINAL], fail=ServiceUnavailableError("Ollama is down."))

    with pytest.raises(AllModelsFailedError) as failed:
        summarizer(settings, choices(local, cloud(fail=RATE_LIMITED)), catalog, chapter(2), tmp_path).summarize(
            "book_001", 4, "standard", model="fc-a"
        )

    assert [(attempt.model, attempt.step) for attempt in failed.value.attempts] == [("fc-a", 1), ("fake-llm", 1)]
    assert str(failed.value).endswith("fake-llm (local) failed: Ollama is down.")


def test_the_summary_is_logged_with_its_provider_and_no_text_or_reasoning(settings, catalog, tmp_path):
    configure_logging("DEBUG", "DEBUG", tmp_path / "logs", console=False)
    fc = cloud(thinking="A private line of reasoning.")
    try:
        summarizer(settings, choices(FakeLLM([FINAL]), fc), catalog, chapter(2, words=100), tmp_path).summarize(
            "book_001", 4, "standard", model="fc-a"
        )
    finally:
        for name in ("book_rag", INFERENCE_LOGGER):
            for handler in logging.getLogger(name).handlers:
                handler.close()
            logging.getLogger(name).handlers.clear()

    logged = (tmp_path / "logs" / "app.jsonl").read_text(encoding="utf-8")
    [event] = [json.loads(line) for line in logged.splitlines() if '"chapter summarized"' in line]
    assert (event["provider"], event["failed_attempts"]) == ("fakecloud", 0)
    assert (event["prompt_tokens"], event["completion_tokens"]) == (100, 20)
    assert "private line of reasoning" not in logged
    assert "passage0" not in logged and "Chapter overview" not in logged


# Sequences of fallbacks (specs/008-cloud-llm-providers, US3, SC-006)

UNKNOWN = {
    name: ModelFailedError(name, "fakecloud", FailureReason.UNKNOWN_MODEL, label="FakeCloud")
    for name in ("fc-a", "fc-b")
}


def test_a_working_fallback_writes_the_summary_and_the_local_model_isnt_called(settings, catalog, tmp_path):
    local = FakeLLM([FINAL])
    models = choices(local, cloud("fc-a", fail=UNKNOWN["fc-a"]), cloud("fc-b"))

    summary = summarizer(settings, models, catalog, chapter(2, words=100), tmp_path).summarize(
        "book_001", 4, "standard", model="fc-a", fallbacks=["fc-b"]
    )

    assert (summary.model, [attempt.model for attempt in summary.attempts]) == ("fc-b", ["fc-a"])
    assert local.calls == []


def test_when_every_fallback_fails_the_local_model_writes_it_listing_them_in_order(settings, catalog, tmp_path):
    models = choices(FakeLLM([FINAL]), cloud("fc-a", fail=UNKNOWN["fc-a"]), cloud("fc-b", fail=UNKNOWN["fc-b"]))

    summary = summarizer(settings, models, catalog, chapter(2, words=100), tmp_path).summarize(
        "book_001", 4, "standard", model="fc-a", fallbacks=["fc-b"]
    )

    assert summary.model == "fake-llm"
    assert [attempt.model for attempt in summary.attempts] == ["fc-a", "fc-b"]


# The model that wrote a summary (specs/008, Phase 8: Convergence, T071 and T072)


def test_a_summary_records_the_model_its_provider_reported(settings, catalog, tmp_path):
    fc = cloud(reported_model="fc-a-20261101")

    summary = summarizer(settings, choices(FakeLLM([FINAL]), fc), catalog, chapter(2, words=100), tmp_path).summarize(
        "book_001", 4, "standard", model="fc-a"
    )

    assert (summary.model, summary.provider) == ("fc-a-20261101", "fakecloud")


def test_after_a_fallback_the_summary_is_logged_with_the_model_that_wrote_it(settings, catalog, tmp_path):
    configure_logging("INFO", "INFO", tmp_path / "logs", console=False)
    models = choices(FakeLLM([FINAL]), cloud(fail=RATE_LIMITED))
    try:
        summarizer(settings, models, catalog, chapter(2, words=100), tmp_path).summarize(
            "book_001", 4, "standard", model="fc-a"
        )
    finally:
        for name in ("book_rag", INFERENCE_LOGGER):
            for handler in logging.getLogger(name).handlers:
                handler.close()
            logging.getLogger(name).handlers.clear()

    entries = [json.loads(line) for line in (tmp_path / "logs" / "app.jsonl").read_text(encoding="utf-8").splitlines()]
    [failed] = [entry for entry in entries if entry["message"] == "model failed"]
    [summarized] = [entry for entry in entries if entry["message"] == "chapter summarized"]
    assert (failed["model"], failed["provider"]) == ("fc-a", "fakecloud")
    assert (summarized["model"], summarized["provider"], summarized["failed_attempts"]) == ("fake-llm", "ollama", 1)


# OpenAI's models (specs/009-openai-provider, US2, FR-009, FR-013)

OPENAI_ENVIRON = {"OPENAI_API_KEY": "sk-test-openai", "OPENAI_MODELS": "gpt-a"}


def openai_window(settings, context_size):
    """The settings, with OpenAI's profile set to a given window."""
    profile = settings.cloud_profiles["openai"].model_copy(update={"context_size": context_size})
    return settings.model_copy(update={"cloud_profiles": settings.cloud_profiles | {"openai": profile}})


def openai_choices(settings, local):
    from app.container import CLOUD_PROVIDERS

    return ModelChoices(local, create_cloud_providers(settings, OPENAI_ENVIRON, CLOUD_PROVIDERS))


def test_an_openai_model_summarizes_in_one_step_and_records_its_provider_and_tokens(
    settings, catalog, tmp_path, openai_client
):
    openai_client.script(FakeResponse(text=FINAL, model="gpt-a-20261101", input_tokens=900, output_tokens=200))

    summary = summarizer(settings, openai_choices(settings, FakeLLM([FINAL])), catalog, chapter(2, words=100), tmp_path)
    summary = summary.summarize("book_001", 4, "standard", model="gpt-a")

    assert (summary.model, summary.provider, summary.attempts) == ("gpt-a-20261101", "openai", ())
    assert (summary.strategy, summary.steps) == ("direct", 1)
    assert (summary.prompt_tokens, summary.completion_tokens) == (900, 200)
    assert summary.citations and summary.statements
    [request] = openai_client.create_calls
    assert request["model"] == "gpt-a" and request["store"] is False


def test_an_openai_model_summarizes_a_long_chapter_in_several_steps_its_tokens_summed(
    settings, catalog, tmp_path, openai_client
):
    small = openai_window(settings, 8192)
    openai_client.script(FakeResponse(text=FINAL, model="gpt-a", input_tokens=900, output_tokens=200))

    summary = summarizer(small, openai_choices(small, FakeLLM([FINAL])), catalog, chapter(30), tmp_path)
    summary = summary.summarize("book_001", 4, "standard", model="gpt-a")

    steps = len(openai_client.create_calls)
    assert summary.strategy == "map_reduce" and summary.steps == steps > 1
    assert (summary.prompt_tokens, summary.completion_tokens) == (900 * steps, 200 * steps)
    assert summary.provider == "openai" and summary.attempts == ()


def test_an_openai_model_out_of_credit_at_its_second_step_hands_the_whole_summary_on(
    settings, catalog, tmp_path, openai_client
):
    small = openai_window(settings, 8192)
    broke = openai_status_error(openai.RateLimitError, 429, code="credit_balance_exhausted")
    openai_client.script(
        FakeResponse(text=FINAL, model="gpt-a", input_tokens=900, output_tokens=200), FakeResponse(error=broke)
    )
    local = FakeLLM(respond=lambda messages, parameters: FINAL)
    progress = []

    summary = summarizer(small, openai_choices(small, local), catalog, chapter(30), tmp_path).summarize(
        "book_001", 4, "standard", on_progress=progress.append, model="gpt-a"
    )

    assert (summary.model, summary.provider) == ("fake-llm", "ollama")
    assert summary.attempts == (
        Attempt("gpt-a", "openai", FailureReason.OUT_OF_CREDIT, "credit_balance_exhausted", 900, 200, step=2),
    )
    assert (
        "gpt-a (OpenAI) failed: its account is out of credit or over a spending or usage limit "
        "(credit_balance_exhausted). Starting again with fake-llm."
    ) in progress
    assert len(openai_client.create_calls) == 2


def test_a_saved_openai_summary_records_its_provider_its_reported_model_and_its_tokens(
    settings, catalog, tmp_path, openai_client
):
    """specs/009-openai-provider, SC-012, FR-013."""
    openai_client.script(FakeResponse(text=FINAL, model="gpt-a-20261101", input_tokens=900, output_tokens=200))
    service = summarizer(settings, openai_choices(settings, FakeLLM([FINAL])), catalog, chapter(2, words=100), tmp_path)

    service.save(service.summarize("book_001", 4, "brief", model="gpt-a"))

    record = json.loads((tmp_path / "summaries/book_001/chapter_04_brief.json").read_text(encoding="utf-8"))
    assert (record["model"], record["provider"], record["tokens"]) == (
        "gpt-a-20261101",
        "openai",
        {"read": 900, "generated": 200},
    )
    assert record["failed_attempts"] == []
    assert "sk-test-openai" not in json.dumps(record)
