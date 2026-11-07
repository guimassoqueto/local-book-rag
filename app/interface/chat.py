"""The Chat tab: questions about one book, a chapter, or several books."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import gradio as gr

from app.container import Container
from app.generation.base import TextDelta
from app.generation.question_answering import Answer
from app.interface.common import reports_errors
from app.interface.formatting import (
    ALL_CHAPTERS,
    chapter_choices,
    passages_markdown,
    sources_markdown,
    timing_markdown,
)
from app.retrieval.base import RetrievalFilters
from app.retrieval.pipeline import RetrievalResult

SAME_AS_QUESTION = "Same as the question"


@dataclass(frozen=True)
class ChatTab:
    """What the rest of the interface needs from this tab.

    Attributes:
        books: the books selected for questions.
        last_answer: the latest answer, in full, for the diagnostics.
        answered: the event that ends with a new answer.
    """

    books: gr.Dropdown
    last_answer: gr.State
    answered: Any


def build_chat_tab(container: Container) -> ChatTab:
    languages = [SAME_AS_QUESTION, *container.settings.generation.response_languages]

    with gr.Tab("Chat"):
        with gr.Row():
            books = gr.Dropdown(
                label="Books", choices=[], multiselect=True, info="Leave it empty to search the whole library."
            )
            chapter = gr.Dropdown(
                label="Chapter",
                choices=chapter_choices([]),
                value=ALL_CHAPTERS,
                info="Select a single book to choose one of its chapters.",
            )
            language = gr.Dropdown(label="Answer in", choices=languages, value=SAME_AS_QUESTION)
        question = gr.Textbox(label="Question", lines=2, placeholder="What does the author mean by…")
        ask = gr.Button("Ask", variant="primary")

        status = gr.Markdown()
        answer = gr.Markdown(label="Answer", container=True, min_height=120)
        sources = gr.Markdown(label="Sources")
        with gr.Accordion("Retrieved passages", open=False):
            passages = gr.Markdown()
        last_answer = gr.State()

    @reports_errors
    def on_books_change(selected: list[str]) -> gr.Dropdown:
        if len(selected) != 1:
            return gr.Dropdown(choices=chapter_choices([]), value=ALL_CHAPTERS, interactive=False)
        chapters = container.books.chapters(selected[0])
        return gr.Dropdown(choices=chapter_choices(chapters), value=ALL_CHAPTERS, interactive=True)

    @reports_errors
    def on_ask(text: str, selected: list[str], number: int, target: str) -> Iterator[tuple[Any, ...]]:
        if not text.strip():
            raise gr.Error("Write a question first.")
        filters = RetrievalFilters(
            book_ids=tuple(selected),
            chapter_numbers=() if number == ALL_CHAPTERS else (number,),
        )
        written = ""
        yield "Searching the books…", "", "", "", None
        for event in container.questions.stream(text, filters, None if target == SAME_AS_QUESTION else target):
            if isinstance(event, RetrievalResult):
                yield f"Found {len(event.passages)} passages. Writing the answer…", "", "", "", None
            elif isinstance(event, TextDelta):
                written += event.text
                yield gr.skip(), written, "", "", None
            elif isinstance(event, Answer):
                yield (
                    timing_markdown(event),
                    event.text,
                    sources_markdown(event),
                    passages_markdown(event.passages, event.citations),
                    event,
                )

    books.change(on_books_change, inputs=books, outputs=chapter, api_visibility="private")
    outputs = [status, answer, sources, passages, last_answer]
    inputs = [question, books, chapter, language]
    answered = ask.click(on_ask, inputs=inputs, outputs=outputs, api_name="ask")
    return ChatTab(books, last_answer, answered)
