import threading
import time
from pathlib import Path

import gradio as gr
import pytest

from app.config.settings import EnvironmentSettings
from app.container import Container
from app.errors import BookNotFoundError, ServiceUnavailableError
from app.generation.base import Generation, Message
from app.generation.citations import citation_for
from app.generation.question_answering import Answer, QuestionAnsweringService
from app.generation.quiz import QuizWriter
from app.generation.summarization import ChapterSummary
from app.interface import formatting
from app.interface.common import follow, reports_errors
from app.interface.gradio_app import build_interface
from app.retrieval.base import Passage
from app.retrieval.pipeline import RetrievalResult
from app.services.health_service import HealthService
from app.services.library_service import ReindexReport
from app.services.quiz_service import QuizService
from app.storage.catalog import Book, BookStatus, IndexRecord
from app.utils.gpu import GpuStatus
from app.utils.ollama_runtime import LoadedModel
from app.utils.progress import Outcome, Progress, ProgressView, StageSpec, StageView
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
        "statements": 12,
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
        quizzes=QuizService(
            library.settings.generation.quiz,
            library.settings.generation.response_languages,
            library.catalog,
            library.processed,
            QuizWriter(library.settings.generation.quiz, 0.1, llm),
            library.root / "quiz_downloads",
        ),
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
        "prepare_quiz",
        "grade_quiz",
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

    list(handler(interface, "add_book")(str(path)))

    assert [book.original_filename for book in library.books.list_books()] == ["my book.md"]


def test_a_duplicate_upload_is_a_visible_error(interface, library, tmp_path):
    library.add(tmp_path)

    with pytest.raises(gr.Error, match="already in the library"):
        list(handler(interface, "add_book")(str(upload(tmp_path, "one.md"))))


def test_adding_nothing_is_a_visible_error(interface):
    values = []

    with pytest.raises(gr.Error, match="Choose a file"):
        for value in handler(interface, "add_book")(None):
            values.append(value)

    assert values == [""]  # the starting line goes


def test_removing_with_the_wrong_confirmation_keeps_the_book(interface, library, tmp_path):
    book = library.add(tmp_path)

    with pytest.raises(gr.Error, match="confirmation"):
        list(handler(interface, "remove_book")(book.book_id, "yes", False))

    assert library.books.list_books() == [book]


def test_removing_with_the_right_confirmation_clears_the_field(interface, library, tmp_path):
    book = library.add(tmp_path)

    area, confirmation = list(handler(interface, "remove_book")(book.book_id, book.book_id, False))[-1]
    assert confirmation == "" and "Removed in" in area
    assert library.books.list_books() == []


@pytest.mark.parametrize(
    ("name", "phrase"), [("reset_index", "RESET INDEX"), ("reset_everything", "DELETE EVERYTHING")]
)
def test_resets_need_their_exact_phrase(interface, library, tmp_path, name, phrase):
    library.add(tmp_path)

    with pytest.raises(gr.Error, match=phrase):
        list(handler(interface, name)("yes"))
    assert library.books.list_books()

    area, confirmation = list(handler(interface, name)(phrase))[-1]
    assert confirmation == "" and "Reset in" in area
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

    list(handler(interface, "replace_book")(book.book_id, str(upload(tmp_path, "new.md", other_text("new")))))

    assert library.books.get_book(book.book_id).revision == 2


# The Quiz tab's formatting (specs/003-chapter-quiz, contracts/quiz-tab.md)


def quiz_question(position=7, key="C"):
    from app.services.quiz_service import Question

    passage = make_chunk(
        "Wages were high in Britain and energy was cheap, so machines paid.",
        section="Salários reais",
        page_start=12,
        page_end=13,
    )
    return Question(
        position=position,
        text="Por que as máquinas compensavam na Grã-Bretanha?",
        options=("Pelo crédito.", "Pelo clima.", "Pelos salários altos.", "Pela guerra.", "Pelo ouro."),
        key=key,
        explanation="Salários altos e energia barata tornavam as máquinas lucrativas.",
        passage=passage,
    )


def test_a_quiz_slot_shows_its_number_and_question():
    assert formatting.quiz_slot_markdown(quiz_question()) == "**7.** Por que as máquinas compensavam na Grã-Bretanha?"


def test_a_quiz_slots_choices_are_lettered():
    choices = formatting.quiz_choices(quiz_question())

    assert [label for label, _ in choices] == [
        "A) Pelo crédito.",
        "B) Pelo clima.",
        "C) Pelos salários altos.",
        "D) Pela guerra.",
        "E) Pelo ouro.",
    ]
    assert [value for _, value in choices] == list("ABCDE")


def test_the_progress_line_counts_the_questions_ready():
    assert formatting.quiz_progress(7, 20) == "Preparing: 7 of 20 questions ready"


def test_a_slot_shows_nothing_of_its_answer_before_submission():
    question = quiz_question()
    shown = formatting.quiz_slot_markdown(question) + " ".join(label for label, _ in formatting.quiz_choices(question))

    assert question.explanation not in shown
    assert question.passage.text not in shown
    assert "Salários reais" not in shown
    assert "12" not in shown
    assert "✓" not in shown


def test_a_missed_question_shows_the_answers_the_explanation_and_the_passage():
    feedback = formatting.quiz_feedback(quiz_question(), "B")

    assert "✗" in feedback
    assert "**Your answer**: B" in feedback
    assert "**Right answer**: C" in feedback
    assert "Salários altos e energia barata" in feedback
    assert "Wages were high in Britain" in feedback
    assert "Title" in feedback
    assert "Chapter 1" in feedback
    assert "Salários reais" in feedback
    assert "pp. 12–13" in feedback


def test_an_unanswered_question_says_so():
    assert "**Your answer**: not answered" in formatting.quiz_feedback(quiz_question(), None)


def test_a_right_answer_shows_only_that_it_is_right():
    feedback = formatting.quiz_feedback(quiz_question(), "C")

    assert "✓" in feedback
    assert "Wages were high" not in feedback


ENGLISH_DRAFT = (
    '{"question": "Why does the fox go back to the forest, according to the book?",'
    ' "correct": "To rest there for the rest of the day.",'
    ' "wrong": ["To hunt for food in the evening.", "To hide from the farmer and his dog.",'
    ' "To meet the other foxes of the valley.", "To sleep through the cold winter."],'
    ' "explanation": "The book says the fox goes back to the forest to rest for the day."}'
)


@pytest.fixture
def quiz_interface(library):
    llm = FakeLLM([ENGLISH_DRAFT])
    quiz = library.settings.generation.quiz
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
        quizzes=QuizService(
            quiz,
            library.settings.generation.response_languages,
            library.catalog,
            library.processed,
            QuizWriter(quiz, 0.1, llm),
            library.root / "quiz_downloads",
        ),
    )
    return build_interface(container)


CURRENT = 5  # the tab's outputs: progress, prepare, stop, submit, result, current, download, then the slots
DOWNLOAD = 6
SLOTS = 7


def test_a_quiz_is_prepared_shown_and_graded_through_the_tab(quiz_interface, library, tmp_path):
    book = library.add(tmp_path)

    frames = list(handler(quiz_interface, "prepare_quiz")(book.book_id, 1, 1, "Same as the book"))

    quiz = frames[-1][CURRENT]
    assert len(quiz.questions) == 1
    assert frames[-1][3].interactive is True  # Submit
    filled = frames[-2]
    assert filled[SLOTS].visible is True  # the first slot's group
    assert filled[SLOTS + 1] == formatting.quiz_slot_markdown(quiz.questions[0])
    assert filled[SLOTS + 4] == {"__type__": "update"}  # the second slot is left alone

    answers = [quiz.questions[0].key] + [None] * 49
    graded = handler(quiz_interface, "grade_quiz")(quiz, *answers)

    assert graded[CURRENT].score == 100
    assert "1 of 1" in graded[4]
    served = graded[DOWNLOAD].value  # Gradio's own copy, in its cache
    [written] = (library.root / "quiz_downloads").iterdir()  # the service's file
    assert served["orig_name"] == written.name
    assert Path(served["path"]).read_text(encoding="utf-8") == written.read_text(encoding="utf-8")
    assert written.read_text(encoding="utf-8").startswith("# Quiz:")
    with pytest.raises(gr.Error, match="new quiz"):
        handler(quiz_interface, "grade_quiz")(graded[CURRENT], *answers)


def test_the_tab_reports_the_services_refusal_before_clearing_anything(quiz_interface, library, tmp_path):
    book = library.add(tmp_path)

    with pytest.raises(gr.Error, match="between 1 and"):
        next(handler(quiz_interface, "prepare_quiz")(book.book_id, 1, 99, "Same as the book"))


def quiz_result(ranking=()):
    from datetime import UTC, datetime

    from app.services.quiz_service import ChapterTally, Quiz, QuizState, Result, Scope

    questions = (quiz_question(1), quiz_question(2), quiz_question(3))
    quiz = Quiz(
        Scope("book_001", None if ranking else 1), "Title", None, "Portuguese", "w", None, 3, questions,
        datetime.now(UTC), QuizState.GRADED,
    )  # fmt: skip
    tallies = tuple(ChapterTally(number, f"Chapter {number}", asked, missed) for number, asked, missed in ranking)
    return Result(quiz, ("C", "B", None), (True, False, False), 100 / 3, tallies, datetime.now(UTC))


def test_the_result_shows_the_score():
    assert formatting.quiz_result_markdown(quiz_result()).startswith("**Score**: 1 of 3 (33%)")


def test_a_one_chapter_result_has_no_ranking():
    assert "Chapters to reread" not in formatting.quiz_result_markdown(quiz_result())


def test_a_whole_book_result_ranks_the_chapters_to_reread():
    shown = formatting.quiz_result_markdown(quiz_result(ranking=[(2, 2, 2), (1, 1, 0)]))

    assert "**Chapters to reread**" in shown
    assert "| Chapter | Questions | Missed |" in shown
    assert shown.index("| Chapter 2 | 2 | 2 |") < shown.index("| Chapter 1 | 1 | 0 |")


def test_the_interface_clears_gradios_copies_of_downloads_within_the_hour(interface):
    frequency, age = interface.delete_cache

    assert frequency + age <= 3600


def test_sigterm_shuts_gradio_down_as_an_interrupt_does():
    from app.interface.gradio_app import stop_on_sigterm

    with pytest.raises(KeyboardInterrupt):
        stop_on_sigterm(15, None)


# The progress of library operations (specs/004-library-progress): the formatting


def stage_view(key="extract", label="Extracting the text", position=2, stages=5, **values):
    return StageView(key=key, label=label, position=position, stages=stages, **values)


def progress_view(stage=None, step=None, elapsed=12.0, outcome=None, **values):
    defaults = {"operation": "Adding a book", "subject": "book_003", "meanwhile": None}
    return ProgressView(stage=stage, step=step, elapsed=elapsed, outcome=outcome, **{**defaults, **values})


@pytest.mark.parametrize(
    ("seconds", "text"), [(0, "0:00"), (38, "0:38"), (38.9, "0:38"), (125, "2:05"), (3725, "1:02:05")]
)
def test_the_elapsed_time_reads_as_minutes_and_seconds(seconds, text):
    assert formatting.elapsed_text(seconds) == text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (12.1, "about 15 s left"),
        (5, "about 5 s left"),
        (0.4, "about 5 s left"),
        (59, "about 60 s left"),
        (61, "about 1 min left"),
        (89, "about 1 min left"),
        (91, "about 2 min left"),
        (0, "almost done"),
    ],
)
def test_the_time_left_is_rounded(seconds, text):
    assert formatting.time_left_text(seconds) == text


def test_a_counted_stage_has_a_filling_bar():
    view = progress_view(stage_view(done=130, total=244, unit="pages", time_left=9.2))

    html = formatting.progress_html(view)

    assert '<progress value="130" max="244">' in html
    assert "130 of 244 pages" in html and "about 10 s left" in html
    assert "Extracting the text" in html and "stage 2 of 5" in html
    assert "Adding a book" in html and "book_003" in html and "0:12" in html


def test_an_uncounted_stage_has_a_moving_bar():
    html = formatting.progress_html(progress_view(stage_view(key="prepare", label="Preparing the chunks", position=3)))

    assert "<progress></progress>" in html and " of " not in html.split("stage 3 of 5")[1]


def test_an_empty_count_reads_zero_of_zero_with_a_full_bar():
    html = formatting.progress_html(progress_view(stage_view(key="summaries", done=0, total=0, unit="summaries")))

    assert "0 of 0 summaries" in html and '<progress value="1" max="1">' in html


def test_a_stage_without_a_position_shows_none():
    html = formatting.progress_html(progress_view(stage_view(key="bogus", label="bogus", position=None, stages=None)))

    assert "bogus" in html and "stage" not in html.split("bogus", 1)[1]


def test_a_reindex_shows_its_stage_its_step_and_what_keeps_working():
    view = progress_view(
        stage_view(
            key="books",
            label="Indexing the books",
            position=2,
            stages=3,
            done=1,
            total=5,
            unit="books",
            note="Quincas Borba",
        ),
        step=stage_view(
            key="embed", label="Embedding the chunks", position=3, stages=4, done=120, total=454, unit="chunks"
        ),
        operation="Reindexing the library",
        subject=None,
        meanwhile="Questions keep working on the current index meanwhile.",
    )

    html = formatting.progress_html(view)

    assert "Indexing the books" in html and "stage 2 of 3" in html and "1 of 5 books" in html
    assert "Quincas Borba" in html and "Embedding the chunks" in html and "step 3 of 4" in html
    assert '<progress value="120" max="454">' in html and "Questions keep working" in html


def test_text_from_a_book_is_escaped():
    html = formatting.progress_html(progress_view(stage_view(note="<b>Fish & Chips</b>")))

    assert "&lt;b&gt;Fish &amp; Chips&lt;/b&gt;" in html


def test_the_starting_line():
    html = formatting.starting_html("Adding a book")

    assert "Adding a book: starting" in html and "<progress></progress>" in html


def test_a_failure_names_the_stage():
    view = progress_view(
        stage_view(key="embed", label="Embedding the chunks"),
        elapsed=15,
        outcome=Outcome(succeeded=False, stage="Embedding the chunks", error="Ollama is down."),
    )

    assert formatting.failed_line(view) == "Failed after 0:15, while embedding the chunks: Ollama is down."
    assert "Failed after 0:15" in formatting.progress_html(view)


def test_a_failed_reindex_names_the_book_and_the_step():
    outcome = Outcome(
        succeeded=False,
        stage="Indexing the books",
        step="Embedding the chunks",
        item="book_002, Quincas Borba",
        error="Ollama is down.",
    )

    line = formatting.failed_line(progress_view(elapsed=40, outcome=outcome, operation="Reindexing the library"))

    assert line == (
        "Failed after 0:40, while indexing the books, at book_002, Quincas Borba, while embedding the chunks: "
        "Ollama is down."
    )


def test_a_failure_before_any_stage():
    view = progress_view(elapsed=1, outcome=Outcome(succeeded=False, error="No."))

    assert formatting.failed_line(view) == "Failed after 0:01: No."


def test_the_outcome_lines_of_each_operation():
    added = book(title="Think Python", chapter_count=23, chunk_count=425, book_id="book_003")
    report = ReindexReport(
        4, "book_chunks_v4", "qwen3-embedding:0.6b", 4, 1313, ("book_001",), ("book_005",), 0, ("x",)
    )

    assert formatting.added_line(added, 38) == "Added in 0:38. book_003: Think Python, with 23 chapters and 425 chunks."
    assert formatting.replaced_line(added, 40) == "Replaced in 0:40. book_003 is now Think Python, with 425 chunks."
    assert formatting.reprocessed_line(added, 29) == "Processed again in 0:29. book_003: 425 chunks."
    assert formatting.removed_line("book_003", True, 1) == (
        "Removed in 0:01. book_003 is gone; its original is in the archive."
    )
    assert (
        formatting.removed_line("book_003", False, 1) == "Removed in 0:01. book_003 is gone; its original was deleted."
    )
    assert formatting.reindexed_line(report, 72) == (
        "Reindexed in 1:12. Index v4 is active: 4 books, 1313 chunks. Brought back from their originals: book_001. "
        "Still failing: book_005. 1 summary not written."
    )
    assert formatting.index_reset_line(1) == (
        "Reset in 0:01. The index is gone and the originals are kept. Reindex the library to rebuild it."
    )
    assert formatting.everything_reset_line(1) == "Reset in 0:01. The library is empty."
    assert "Added in 0:38." in formatting.outcome_html("Added in 0:38.", succeeded=True)


def test_the_commands_lines():
    count = progress_view(stage_view(done=58, total=244, unit="pages", time_left=17.5), elapsed=4)
    reindex = progress_view(
        stage_view(
            key="books",
            label="Indexing the books",
            position=2,
            stages=3,
            done=2,
            total=5,
            unit="books",
            note="Quincas Borba",
        ),
        step=stage_view(
            key="embed", label="Embedding the chunks", position=3, stages=4, done=120, total=454, unit="chunks"
        ),
        operation="Reindexing the library",
        subject=None,
        elapsed=40,
    )

    assert formatting.progress_text(progress_view(elapsed=0)) == "[0:00] Adding a book, book_003: starting"
    assert formatting.progress_text(count) == (
        "[0:04] Adding a book, book_003: stage 2 of 5, Extracting the text, 58 of 244 pages, about 20 s left"
    )
    assert formatting.progress_text(reindex) == (
        "[0:40] Reindexing the library: stage 2 of 3, Indexing the books, 2 of 5 books, Quincas Borba: "
        "step 3 of 4, Embedding the chunks, 120 of 454 chunks"
    )
    assert formatting.progress_text(progress_view(elapsed=28, outcome=Outcome(succeeded=True))) == (
        "[0:28] Adding a book, book_003: done"
    )
    failed = progress_view(elapsed=15, outcome=Outcome(succeeded=False, stage="Embedding the chunks", error="x"))
    assert formatting.progress_text(failed) == "[0:15] Adding a book, book_003: failed while embedding the chunks"


# The progress of library operations: following an operation from the tab


STAGES = (StageSpec("embed", "Embedding the chunks", unit="chunks", estimate=True),)


def test_following_yields_while_the_operation_runs_and_returns_its_result():
    progress = Progress()

    def call():
        with progress.operation("Adding a book", STAGES), progress.stage("embed") as stage:
            stage.count(3)
            for _ in range(3):
                time.sleep(0.05)
                stage.advance()
        return "the book"

    stream = follow(call, progress, lambda view: view.stage.done if view and view.stage else None, poll=0.02)
    seen = []
    with pytest.raises(StopIteration) as stopped:
        while True:
            seen.append(next(stream))

    counts = [value for value in seen if value is not None]
    assert stopped.value.value == "the book"
    assert counts and counts == sorted(counts)


def test_following_yields_at_least_once_a_second_even_without_change():
    progress = Progress()
    release = threading.Event()

    def call():
        with progress.operation("Removing a book", ()):
            release.wait(5)

    stream = follow(call, progress, lambda view: view.elapsed if view else None, poll=0.05, beat=0.2)
    started = time.monotonic()
    first, second = next(stream), next(stream)
    release.set()
    list(stream)

    assert second > first and time.monotonic() - started < 2


def test_following_a_failure_yields_its_final_view_then_raises_the_same_error():
    progress = Progress()
    error = ConnectionError("Ollama is down")

    def call():
        with progress.operation("Adding a book", STAGES), progress.stage("embed"):
            raise error

    stream = follow(call, progress, lambda view: view.outcome if view else "nothing", poll=0.02)
    values = []
    with pytest.raises(ConnectionError) as raised:
        for value in stream:
            values.append(value)

    assert raised.value is error and values[-1] == Outcome(False, stage="Embedding the chunks", error="Ollama is down")


def test_following_a_refusal_yields_an_empty_view_then_raises():
    def call():
        raise BookNotFoundError("There is no book with ID book_999.")

    stream = follow(call, Progress(), lambda view: "empty" if view is None else "shown", poll=0.02)

    with pytest.raises(BookNotFoundError):
        assert list(stream) == ["empty"]


def test_closing_the_page_leaves_the_operation_running():
    progress = Progress()
    finished = threading.Event()
    release = threading.Event()

    def call():
        with progress.operation("Reindexing the library", ()):
            release.wait(5)
        finished.set()

    stream = follow(call, progress, lambda view: view, poll=0.02)
    next(stream)
    stream.close()  # what Gradio does when the page goes away
    release.set()

    assert finished.wait(5)


# The progress of library operations: the Library tab (specs/004-library-progress, contracts/library-tab.md)

BUTTONS = (
    "Add to the library",
    "Replace the book",
    "Process again from its original",
    "Remove the book",
    "Reindex the library",
    "Reset the index",
    "Reset everything",
)


def library_buttons(interface):
    return {block._id for block in interface.blocks.values() if isinstance(block, gr.Button) and block.value in BUTTONS}


def chain(interface, name):
    """The events of a button: the one that disables, the operation, and those that enable again."""
    fns = {fn._id: fn for fn in interface.fns.values()}
    operation = next(fn for fn in fns.values() if fn.api_name == name)
    disable = fns[operation.trigger_after]
    after = [fn for fn in fns.values() if fn.trigger_after == operation._id]
    buttons = library_buttons(interface)
    enabling = [fn for fn in after if {output._id for output in fn.outputs} == buttons]
    return disable, operation, enabling


@pytest.mark.parametrize(
    ("name", "label"),
    [
        ("add_book", "Adding a book"),
        ("replace_book", "Replacing a book"),
        ("reindex_book", "Processing a book again"),
        ("reindex_all", "Reindexing the library"),
        ("remove_book", "Removing a book"),
        ("reset_index", "Resetting the index"),
        ("reset_everything", "Resetting everything"),
    ],
)
def test_a_book_button_disables_the_seven_runs_and_enables_them_again(interface, name, label):
    disable, operation, enabling = chain(interface, name)

    assert len(library_buttons(interface)) == 7
    assert not disable.queue and disable.api_visibility == "private"
    outputs = {output._id for output in disable.outputs}
    assert library_buttons(interface) < outputs and len(outputs) == 8  # the seven buttons and the area
    *updates, area = disable.fn()
    assert all(update.get("interactive") is False for update in updates) and f"{label}: starting" in area
    assert operation.show_progress == "hidden" and operation.outputs[0].__class__ is gr.HTML
    assert sorted((fn.trigger_only_on_success, fn.trigger_only_on_failure) for fn in enabling) == [
        (False, True),
        (True, False),
    ]
    assert all(update.get("interactive") is True for fn in enabling for update in fn.fn())


def test_adding_yields_the_outcome_line(interface, tmp_path):
    values = list(handler(interface, "add_book")(str(upload(tmp_path, "my book.md"))))

    assert "Added in" in values[-1] and "book_001" in values[-1] and "chunks" in values[-1]


def test_replacing_and_processing_again_yield_their_outcome_lines(interface, library, tmp_path):
    book = library.add(tmp_path)

    replaced = list(handler(interface, "replace_book")(book.book_id, str(upload(tmp_path, "n.md", other_text("n")))))
    reprocessed = list(handler(interface, "reindex_book")(book.book_id))

    assert "Replaced in" in replaced[-1] and "Processed again in" in reprocessed[-1]


def test_a_refused_addition_empties_the_area_and_raises(interface, library, tmp_path):
    library.add(tmp_path)
    values = []

    with pytest.raises(gr.Error, match="already in the library"):
        for value in handler(interface, "add_book")(str(upload(tmp_path, "one.md"))):
            values.append(value)

    assert values == [""]


def test_a_failed_addition_shows_where_it_failed(interface, library, tmp_path):
    library.embedder.failure = ServiceUnavailableError("Ollama is down")
    values = []

    with pytest.raises(gr.Error, match="Ollama is down"):
        for value in handler(interface, "add_book")(str(upload(tmp_path, "one.md"))):
            values.append(value)

    assert "while embedding the chunks" in values[-1] and "Ollama is down" in values[-1]


def test_reindexing_yields_its_outcome_line(interface, library, tmp_path):
    library.add(tmp_path)

    values = list(handler(interface, "reindex_all")(False))

    assert "Reindexed in" in values[-1] and "Index v2 is active: 1 books" in values[-1]


def test_a_removal_yields_its_outcome_line_and_empties_the_confirmation(interface, library, tmp_path):
    book = library.add(tmp_path)

    values = list(handler(interface, "remove_book")(book.book_id, book.book_id, True))

    area, confirmation = values[-1]
    assert confirmation == "" and "Removed in" in area and "its original is in the archive" in area


def test_a_refused_removal_empties_the_area_and_keeps_the_confirmation(interface, library, tmp_path):
    book = library.add(tmp_path)
    values = []

    with pytest.raises(gr.Error, match="confirmation"):
        for value in handler(interface, "remove_book")(book.book_id, "yes", False):
            values.append(value)

    assert values == [("", gr.skip())]
