"""The Summarization tab: comprehensive summaries of whole chapters."""

from dataclasses import dataclass

import gradio as gr

from app.container import Container
from app.generation.summarization import ChapterSummary
from app.interface.common import reports_errors
from app.interface.formatting import chapter_choices, summary_report

SAME_AS_BOOK = "Same as the book"


@dataclass(frozen=True)
class SummarizationTab:
    book: gr.Dropdown


def build_summarization_tab(container: Container) -> SummarizationTab:
    types = container.summaries.summary_types()
    languages = [SAME_AS_BOOK, *container.settings.generation.response_languages]

    with gr.Tab("Summarization"):
        with gr.Row():
            book = gr.Dropdown(label="Book", choices=[])
            chapter = gr.Dropdown(label="Chapter", choices=[])
        with gr.Row():
            default = "standard" if "standard" in types else None
            summary_type = gr.Radio(label="Summary type", choices=types, value=default)
            language = gr.Dropdown(label="Write in", choices=languages, value=SAME_AS_BOOK)
        generate = gr.Button("Generate the summary", variant="primary")

        report = gr.Markdown()
        summary_text = gr.Markdown(container=True, min_height=120)
        save = gr.Button("Save the summary", interactive=False)
        current = gr.State()

    @reports_errors
    def on_book_change(book_id: str | None) -> gr.Dropdown:
        if not book_id:
            return gr.Dropdown(choices=[], value=None)
        return gr.Dropdown(choices=chapter_choices(container.books.chapters(book_id), include_all=False), value=None)

    @reports_errors
    def on_generate(
        book_id: str | None,
        number: int | None,
        chosen_type: str,
        target: str,
        progress: gr.Progress = gr.Progress(),  # noqa: B008
    ) -> tuple[str, str, ChapterSummary, gr.Button]:
        if not book_id or number is None:
            raise gr.Error("Choose a book and a chapter first.")
        summary = container.summaries.summarize(
            book_id,
            number,
            chosen_type,
            None if target == SAME_AS_BOOK else target,
            on_progress=lambda message: progress(0, desc=message),
        )
        return summary_report(summary), summary.text, summary, gr.Button(interactive=True)

    @reports_errors
    def on_save(summary: ChapterSummary | None) -> None:
        if summary is None:
            raise gr.Error("Generate a summary first.")
        gr.Info(f"Saved to {container.summaries.save(summary)}.")

    book.change(on_book_change, inputs=book, outputs=chapter, api_visibility="private")
    generate.click(
        on_generate,
        inputs=[book, chapter, summary_type, language],
        outputs=[report, summary_text, current, save],
        api_name="summarize",
    )
    save.click(on_save, inputs=current, api_name="save_summary")
    return SummarizationTab(book)
