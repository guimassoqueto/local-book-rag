import gradio as gr
import pytest

from app.config.settings import EnvironmentSettings
from app.container import Container
from app.errors import BookNotFoundError
from app.generation.base import Generation, Message
from app.generation.citations import citation_for
from app.generation.question_answering import Answer, QuestionAnsweringService
from app.generation.summarization import ChapterSummary
from app.interface import formatting
from app.interface.common import reports_errors
from app.interface.gradio_app import build_interface
from app.retrieval.base import Passage
from app.retrieval.pipeline import RetrievalResult
from app.services.health_service import HealthService
from app.storage.catalog import Book, BookStatus, IndexRecord
from app.utils.gpu import GpuStatus
from app.utils.ollama_runtime import LoadedModel
from tests.fakes import FakeLLM, make_chunk, make_stats
from tests.library import Library, other_text, upload


def book(**overrides):
    values = {
        "book_id": "book_001",
        "title": "The Title",
        "author": None,
        "original_filename": "b.pdf",
        "original_path": "x",
        "checksum": "c",
        "format": "pdf",
        "language": "en",
        "chapter_count": 3,
        "chunk_count": 30,
        "embedding_model": "model",
        "index_version": 2,
        "status": BookStatus.INDEXED,
        "status_detail": None,
        "revision": 1,
        "created_at": "2026-11-06T10:20:30+00:00",
        "indexed_at": "2026-11-06T10:21:30+00:00",
    }
    return Book(**(values | overrides))


def passage(index=0, **scores):
    return Passage(make_chunk(f"Text of passage {index}.", index=index, page_start=10 + index), **scores)


def answer(passages=None, citations=None, candidates=None, generation=True, **overrides):
    passages = passages if passages is not None else [passage(0, rerank_score=0.9)]
    retrieval = RetrievalResult("Q?", tuple(passages), tuple(candidates or passages), 0.5, 4.0)
    stats = make_stats(prompt_tokens=2000, completion_tokens=500)
    values = {
        "question": "Q?",
        "text": "An answer [1].",
        "citations": tuple(citations or [citation_for(1, passages[0].chunk)] if passages else ()),
        "invented_citations": (),
        "insufficient_evidence": False,
        "retrieval": retrieval,
        "passages": tuple(passages),
        "messages": (Message("system", "Be careful."), Message("user", "Passages")),
        "thinking": "",
        "generation": Generation("An answer [1].", "", stats) if generation else None,
        "total_seconds": 12.5,
    }
    return Answer(**(values | overrides))


def summary(**overrides):
    values = {
        "book_id": "book_001",
        "book_title": "T",
        "chapter_number": 1,
        "chapter_title": "One",
        "summary_type": "brief",
        "language": None,
        "text": "Text.",
        "citations": (),
        "chunks_total": 10,
        "chunks_covered": 10,
        "strategy": "map_reduce",
        "statements_without_source": 0,
        "steps": 4,
        "incomplete_steps": 0,
        "verification": None,
        "model": "m",
        "total_seconds": 30.0,
    }
    return ChapterSummary(**(values | overrides))


def test_a_book_row_lines_up_with_the_columns():
    [row] = formatting.book_rows([book()])

    assert len(row) == len(formatting.BOOK_COLUMNS) == len(formatting.BOOK_COLUMN_WIDTHS)
    assert dict(zip(formatting.BOOK_COLUMNS, row, strict=True))["Status"] == "INDEXED"
    assert dict(zip(formatting.BOOK_COLUMNS, row, strict=True))["Index"] == "v2"
    assert dict(zip(formatting.BOOK_COLUMNS, row, strict=True))["Added"] == "2026-11-06 10:20"


def test_a_failed_book_says_why():
    [row] = formatting.book_rows([book(status=BookStatus.FAILED, status_detail="Ollama is down", indexed_at=None)])

    assert "Ollama is down" in row
    assert "FAILED" in row


def test_book_choices_show_the_title_and_return_the_id():
    assert formatting.book_choices([book()]) == [("book_001 · The Title", "book_001")]


def test_chapter_choices_can_offer_all_chapters():
    assert formatting.chapter_choices([(4, "Costs")]) == [("All chapters", formatting.ALL_CHAPTERS), ("Costs", 4)]
    assert formatting.chapter_choices([(4, "Costs")], include_all=False) == [("Costs", 4)]


def index(version=1):
    return IndexRecord(version, f"book_chunks_v{version}", "model", "d", 1024, "{}", "f", True, "now")


def test_the_index_status_warns_when_a_reindex_is_needed():
    assert formatting.index_status(None, False).startswith("No index")
    assert "⚠️" not in formatting.index_status(index(), False)
    assert "Reindex the library" in formatting.index_status(index(), True)


def test_sources_list_what_the_answer_cites():
    assert "**[1]** Title, Chapter 1, Section, p. 10" in formatting.sources_markdown(answer())


def test_an_answer_without_sources_is_flagged():
    assert "cites no source" in formatting.sources_markdown(answer(citations=[], text="Claim.", passages=[]))


def test_a_model_that_found_nothing_is_not_flagged_as_uncited():
    text = formatting.sources_markdown(answer(passages=[], insufficient_evidence=True))

    assert "found no answer" in text
    assert "cites no source" not in text


def test_invented_citations_are_flagged():
    assert "don't exist: 9" in formatting.sources_markdown(answer(invented_citations=(9,)))


def test_passages_show_the_original_text_and_what_was_cited():
    passages = [passage(0), passage(1)]
    text = formatting.passages_markdown(passages, [citation_for(1, passages[0].chunk)])

    assert "**[1]** Title, Chapter 1, Section, p. 10 · cited" in text
    assert "> Text of passage 0." in text
    assert "**[2]** Title, Chapter 1, Section, p. 11\n" in text


def test_timing_reports_the_inference():
    assert formatting.timing_markdown(answer()) == "Answered in **12.5 s** · 500 tokens at 2500 tokens/s"
    assert formatting.timing_markdown(answer(generation=False)) == "Answered in **12.5 s**"


def test_scores_show_every_stage_with_the_best_first():
    candidates = [passage(0, dense_score=0.5, rerank_score=0.2), passage(1, bm25_score=4.0, rerank_score=0.9)]

    rows = formatting.score_rows(answer(passages=candidates[1:], candidates=candidates))

    assert [row[1] for row in rows] == [candidates[1].chunk.chunk_id, candidates[0].chunk.chunk_id]
    assert rows[0][0] == "[1]"
    assert rows[1][0] == ""
    assert rows[0][5] == "4.000"
    assert rows[0][4] == ""


def test_the_run_report_covers_what_the_spec_asks_for():
    text = formatting.run_markdown(answer(), "llm-model", "embedding-model", "reranker-model")

    for expected in (
        "llm-model",
        "embedding-model",
        "reranker-model",
        "Candidates retrieved",
        "Prompt tokens | 2000",
        "Generated tokens | 500",
        "Time to first token",
        "Generation speed",
        "Total",
    ):
        assert expected in text


def test_gpu_memory_is_reported_when_available():
    gpu = GpuStatus("RTX", 13000, 16000)
    loaded = [LoadedModel("gpt-oss:20b", 12_700_000_000, 12_700_000_000, 8192)]

    text = formatting.gpu_markdown(gpu, loaded)

    assert "13000 of 16000 MiB" in text
    assert "100% on the GPU" in text
    assert "No GPU" in formatting.gpu_markdown(None, [])


def test_the_final_context_shows_each_message():
    assert formatting.prompt_text([Message("user", "Hello")]) == "=== user ===\nHello"


def test_a_clean_summary_report_has_no_warnings():
    text = formatting.summary_report(summary())

    assert "**10 of 10**" in text
    assert "⚠️" not in text


def test_a_summary_report_warns_about_what_went_wrong():
    text = formatting.summary_report(summary(chunks_covered=8, incomplete_steps=1, statements_without_source=1))

    assert "2 chunks cut off" in text
    assert "1 step hit" in text
    assert "1 statement resembling" in text


def test_errors_reach_the_user_with_their_message():
    @reports_errors
    def handler():
        raise BookNotFoundError("There is no book with ID book_999.")

    with pytest.raises(gr.Error, match="book_999"):
        handler()


def test_errors_during_streaming_reach_the_user_too():
    @reports_errors
    def handler():
        yield "first"
        raise BookNotFoundError("There is no book with ID book_999.")

    stream = handler()
    assert next(stream) == "first"
    with pytest.raises(gr.Error, match="book_999"):
        next(stream)


@pytest.fixture
def library(settings, tmp_path):
    return Library(settings, tmp_path / "data")


@pytest.fixture
def interface(library):
    llm = FakeLLM(["An answer about the dog [1]."])
    container = Container(
        settings=library.settings,
        environment=EnvironmentSettings(),
        runtime=library.runtime,
        health=HealthService(library.settings, library.runtime, library.server, library.indexes),
        indexes=library.indexes,
        books=library.books,
        library=library.library,
        resets=library.resets,
        retrieval=library.retrieval,
        questions=QuestionAnsweringService(library.settings, library.retrieval, llm),
        summaries=library.summarizer,
    )
    return build_interface(container)


def handler(interface, name):
    return next(fn.fn for fn in interface.fns.values() if fn.api_name == name)


def test_every_primary_operation_is_reachable(interface):
    names = {fn.api_name for fn in interface.fns.values()}

    assert {
        "add_book",
        "replace_book",
        "reindex_book",
        "remove_book",
        "reindex_all",
        "reset_index",
        "reset_everything",
        "ask",
        "summarize",
        "save_summary",
        "system_status",
    } <= names


def test_the_list_of_books_refreshes_after_a_failure_too(interface):
    """Gradio's `then` doesn't run after an error, which is exactly when a failed book appears."""
    changes = {
        fn._id: fn.api_name
        for fn in interface.fns.values()
        if fn.api_name in ("add_book", "replace_book", "reindex_book", "remove_book", "reindex_all")
        or fn.api_name in ("reset_index", "reset_everything")
    }
    on_failure = {fn.trigger_after for fn in interface.fns.values() if fn.trigger_only_on_failure}

    assert set(changes) <= on_failure


def test_adding_through_the_interface_uses_the_service(interface, library, tmp_path):
    path = upload(tmp_path, "my book.md")

    handler(interface, "add_book")(str(path))

    assert [book.original_filename for book in library.books.list_books()] == ["my book.md"]


def test_a_duplicate_upload_is_a_visible_error(interface, library, tmp_path):
    library.add(tmp_path)

    with pytest.raises(gr.Error, match="already in the library"):
        handler(interface, "add_book")(str(upload(tmp_path, "one.md")))


def test_adding_nothing_is_a_visible_error(interface):
    with pytest.raises(gr.Error, match="Choose a file"):
        handler(interface, "add_book")(None)


def test_removing_with_the_wrong_confirmation_keeps_the_book(interface, library, tmp_path):
    book = library.add(tmp_path)

    with pytest.raises(gr.Error, match="confirmation"):
        handler(interface, "remove_book")(book.book_id, "yes", False)

    assert library.books.list_books() == [book]


def test_removing_with_the_right_confirmation_clears_the_field(interface, library, tmp_path):
    book = library.add(tmp_path)

    assert handler(interface, "remove_book")(book.book_id, book.book_id, False) == ""
    assert library.books.list_books() == []


@pytest.mark.parametrize(
    ("name", "phrase"), [("reset_index", "RESET INDEX"), ("reset_everything", "DELETE EVERYTHING")]
)
def test_resets_need_their_exact_phrase(interface, library, tmp_path, name, phrase):
    library.add(tmp_path)

    with pytest.raises(gr.Error, match=phrase):
        handler(interface, name)("yes")
    assert library.books.list_books()

    handler(interface, name)(phrase)
    assert library.books.list_books() == []


def test_a_question_streams_and_ends_with_the_full_answer(interface, library, tmp_path):
    library.add(tmp_path)

    updates = list(handler(interface, "ask")("Where is the dog?", [], formatting.ALL_CHAPTERS, "Same as the question"))

    assert "Searching" in updates[0][0]
    assert any("Writing the answer" in update[0] for update in updates)
    status, text, sources, passages, full = updates[-1]
    assert "Answered in" in status
    assert text == "An answer about the dog [1]."
    assert "**[1]**" in sources
    assert ">" in passages
    assert isinstance(full, Answer)


def test_an_empty_question_is_a_visible_error(interface):
    with pytest.raises(gr.Error, match="Write a question"):
        list(handler(interface, "ask")("  ", [], formatting.ALL_CHAPTERS, "Same as the question"))


def test_asking_an_empty_library_is_a_visible_error(interface):
    with pytest.raises(gr.Error, match="empty"):
        list(handler(interface, "ask")("Q?", [], formatting.ALL_CHAPTERS, "Same as the question"))


def test_a_summary_can_be_generated_and_saved(interface, library, tmp_path):
    book = library.add(tmp_path)

    report, text, generated, _ = handler(interface, "summarize")(book.book_id, 1, "brief", "Same as the book")
    handler(interface, "save_summary")(generated)

    assert "of" in report
    assert "Chapter overview" in text
    assert len(library.summary_documents.saved()) == 1


def test_summarizing_needs_a_chapter(interface):
    with pytest.raises(gr.Error, match="Choose a book"):
        handler(interface, "summarize")("book_001", None, "brief", "Same as the book")


def test_replacing_through_the_interface_uses_the_service(interface, library, tmp_path):
    book = library.add(tmp_path)

    handler(interface, "replace_book")(book.book_id, str(upload(tmp_path, "new.md", other_text("new"))))

    assert library.books.get_book(book.book_id).revision == 2
