import json

import pytest

from app.errors import ChapterNotFoundError, ConfigurationError, GenerationError
from app.generation.base import FINISHED_BY_LENGTH
from app.generation.summarization import ChapterSummarizer
from app.storage.catalog import Book, BookCatalog, BookStatus
from app.storage.repositories import SummaryDocuments
from tests.fakes import FakeChunks, FakeLLM, make_chunk

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
        original_filename="b.pdf",
        original_path="x",
        checksum="c",
        format="pdf",
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


def chapter(count, words=500, chapter=4, pages=True):
    return [
        make_chunk(
            f"passage{index} " + " ".join(["word"] * words),
            index=index + 10,
            chapter=chapter,
            page_start=100 + index if pages else None,
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
    return ChapterSummarizer(
        settings,
        llm,
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
    assert "[1] Section, p. 100:" in references
    assert "[2] Section, p. 101:" in references
    assert "“passage0" in references


def test_references_work_without_pages(settings, catalog, tmp_path):
    chunks = chapter(2, words=100, pages=False)

    summary = summarizer(settings, FakeLLM([FINAL]), catalog, chunks, tmp_path).summarize("book_001", 4, "standard")

    assert "p." not in summary.text.split("## References")[1].split("“")[0]
    assert "“passage0" in summary.text


def test_the_language_can_be_chosen(settings, catalog, tmp_path):
    llm = FakeLLM([FINAL])

    summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize(
        "book_001", 4, "standard", language="Portuguese"
    )

    assert "Write in Portuguese" in llm.calls[-1][0][0].content


def test_the_book_language_is_the_default(settings, catalog, tmp_path):
    llm = FakeLLM([FINAL])

    summarizer(settings, llm, catalog, chapter(2, words=100), tmp_path).summarize("book_001", 4, "standard")

    assert "Write in en" in llm.calls[-1][0][0].content


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
