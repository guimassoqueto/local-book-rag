"""The Quiz tab: a graded quiz on one chapter or a whole book, shown question by question.

The tab reads input, calls QuizService and shows what it returns: every rule is the service's
(constitution IV, contracts/quiz-tab.md). It builds max_questions slots up front, hidden until a
question fills them. A slot is filled in place while the others are left alone, so answers already
chosen stay while the rest of the quiz arrives: gr.render would rebuild every slot on each change.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import gradio as gr

from app.container import Container
from app.interface.common import reports_errors
from app.interface.formatting import (
    ALL_CHAPTERS,
    chapter_choices,
    quiz_choices,
    quiz_feedback,
    quiz_outcome,
    quiz_progress,
    quiz_result_markdown,
    quiz_slot_markdown,
)
from app.services.quiz_service import QuestionReady, Quiz, QuizReady, Result

SAME_AS_BOOK = "Same as the book"
WHOLE_BOOK = ALL_CHAPTERS
WHOLE_BOOK_LABEL = "The whole book"
STOPPED = "Stopped. The questions shown can't be submitted: prepare a new quiz to take one."
FAILED = "Stopped by an error. The questions shown can't be submitted: prepare a new quiz to take one."


@dataclass(frozen=True)
class QuizTab:
    book: gr.Dropdown


@dataclass(frozen=True)
class _Slot:
    group: gr.Group
    text: gr.Markdown
    answer: gr.Radio
    feedback: gr.Markdown


def build_quiz_tab(container: Container) -> QuizTab:
    service = container.quizzes
    languages = [SAME_AS_BOOK, *container.settings.generation.response_languages]

    with gr.Tab("Quiz"):
        with gr.Row():
            book = gr.Dropdown(label="Book", choices=[])
            scope = gr.Dropdown(label="Quiz on", choices=[])
        with gr.Row():
            count = gr.Number(label="Questions", value=None, precision=0, minimum=1)
            language = gr.Dropdown(label="Write in", choices=languages, value=SAME_AS_BOOK)
        with gr.Row():
            prepare = gr.Button("Prepare the quiz", variant="primary")
            stop = gr.Button("Stop", variant="stop", visible=False)
        progress = gr.Markdown()
        slots: list[_Slot] = []
        for _ in range(service.max_questions):
            with gr.Group(visible=False) as group:
                text = gr.Markdown()
                answer = gr.Radio(choices=[], label="Your answer", show_label=False)
                feedback = gr.Markdown(visible=False)
            slots.append(_Slot(group, text, answer, feedback))
        submit = gr.Button("Submit", variant="primary", interactive=False)
        result = gr.Markdown()
        download = gr.DownloadButton("Download the result", interactive=False)
        current = gr.State()

    fixed = [progress, prepare, stop, submit, result, current, download]
    outputs = fixed + [component for slot in slots for component in (slot.group, slot.text, slot.answer, slot.feedback)]

    def frame(slot_updates: dict[int, tuple[Any, ...]] | None = None, **changes: Any) -> list[Any]:
        """Every output's update, in order: what isn't named stays as it is (gr.skip)."""
        names = ("progress", "prepare", "stop", "submit", "result", "current", "download")
        values = [changes.get(name, gr.skip()) for name in names]
        for index in range(len(slots)):
            values.extend((slot_updates or {}).get(index, (gr.skip(),) * 4))
        return values

    def clear_scope() -> tuple[gr.Dropdown, gr.Number]:
        return gr.Dropdown(choices=[], value=None), gr.Number(value=None, info=None)

    @reports_errors
    def on_book_change(book_id: str | None) -> gr.Dropdown:
        if not book_id:
            return gr.Dropdown(choices=[], value=None)
        service.limit(book_id, None)  # a book that isn't indexed reports why, and offers no scope
        choices = [(WHOLE_BOOK_LABEL, WHOLE_BOOK), *chapter_choices(container.books.chapters(book_id), False)]
        return gr.Dropdown(choices=choices, value=None)

    @reports_errors
    def on_scope_change(book_id: str | None, chosen: int | None) -> gr.Number:
        if not book_id or chosen is None:
            return gr.Number(value=None, info=None)
        chapter = None if chosen == WHOLE_BOOK else int(chosen)
        limit = service.limit(book_id, chapter)
        return gr.Number(value=service.default_count(book_id, chapter), maximum=limit, info=f"At most {limit} here.")

    @reports_errors
    def on_prepare(book_id: str | None, chosen: int | None, asked: float | None, target: str) -> Iterator[list[Any]]:
        if not book_id or chosen is None:
            raise gr.Error("Choose a book and what to be quizzed on first.")
        if asked is None:
            raise gr.Error("Set the number of questions.")
        chapter = None if chosen == WHOLE_BOOK else int(chosen)
        events = service.prepare(book_id, chapter, int(asked), None if target == SAME_AS_BOOK else target)
        started = next(events)  # the service's own checks run here, before anything shown is cleared
        empty = (
            gr.Group(visible=False),
            "",
            gr.Radio(choices=[], value=None, interactive=True),
            gr.Markdown("", visible=False),
        )
        yield frame(
            dict.fromkeys(range(len(slots)), empty),
            progress=quiz_progress(0, started.asked),
            prepare=gr.Button(interactive=False),
            stop=gr.Button(visible=True),
            submit=gr.Button(interactive=False),
            result="",
            current=None,
            download=gr.DownloadButton(value=None, interactive=False),
        )
        for event in events:
            if isinstance(event, QuestionReady):
                question = event.question
                filled = (
                    gr.Group(visible=True),
                    quiz_slot_markdown(question),
                    gr.Radio(choices=quiz_choices(question)),
                )
                yield frame(
                    {question.position - 1: (*filled, gr.skip())}, progress=quiz_progress(event.ready, started.asked)
                )
            elif isinstance(event, QuizReady):
                yield frame(
                    progress=quiz_outcome(event),
                    prepare=gr.Button(interactive=True),
                    stop=gr.Button(visible=False),
                    submit=gr.Button(interactive=True),
                    current=event.quiz,
                )

    def on_stopped(message: str) -> tuple[str, gr.Button, gr.Button]:
        return message, gr.Button(interactive=True), gr.Button(visible=False)

    @reports_errors
    def on_submit(taken: Quiz | Result | None, *answers: str | None) -> list[Any]:
        if taken is None:
            raise gr.Error("Prepare a quiz first.")
        quiz = taken.quiz if isinstance(taken, Result) else taken
        graded = service.grade(quiz, list(answers[: len(quiz.questions)]))
        updates = {
            index: (
                gr.skip(),
                gr.skip(),
                gr.Radio(interactive=False),
                gr.Markdown(quiz_feedback(question, graded.answers[index]), visible=True),
            )
            for index, question in enumerate(quiz.questions)
        }
        return frame(
            updates,
            submit=gr.Button(interactive=False),
            result=quiz_result_markdown(graded),
            current=graded,
            download=gr.DownloadButton(value=str(service.export(graded)), interactive=True),
        )

    book.change(clear_scope, outputs=[scope, count], api_visibility="private").then(
        on_book_change, inputs=book, outputs=scope, api_visibility="private"
    )
    scope.change(on_scope_change, inputs=[book, scope], outputs=count, api_visibility="private")
    preparing = prepare.click(
        on_prepare, inputs=[book, scope, count, language], outputs=outputs, api_name="prepare_quiz"
    )
    preparing.failure(lambda: on_stopped(FAILED), outputs=[progress, prepare, stop], api_visibility="private")
    stop.click(
        lambda: on_stopped(STOPPED), outputs=[progress, prepare, stop], cancels=[preparing], api_visibility="private"
    )
    submit.click(on_submit, inputs=[current, *(slot.answer for slot in slots)], outputs=outputs, api_name="grade_quiz")
    return QuizTab(book)
