"""The Summarization tab: comprehensive summaries of whole chapters."""

from dataclasses import dataclass

import gradio as gr

from app.container import Container
from app.interface.common import reports_errors
from app.interface.formatting import chapter_choices, summary_report
from app.interface.model_choice import build_model_choice

SAME_AS_BOOK = "Same as the book"

# The browser makes the file, from the name and text the service built. Gradio's download button
# serves a file from its cache, which the app sweeps of copies older than 50 minutes, so a summary
# read for an hour would download nothing. Made in the page, the file can't expire, and the click
# reaches no server (specs/011-summary-download, research.md R1 and R2).
_DOWNLOAD = """
(name, text) => {
    const url = URL.createObjectURL(new Blob([text], {type: "text/markdown;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
"""


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
        choice = build_model_choice(container.models, "chapter")
        generate = gr.Button("Generate the summary", variant="primary")

        report = gr.Markdown()
        summary_text = gr.Markdown(container=True, min_height=120)
        download = gr.Button("Download the summary", interactive=False)
        # The file of the summary shown, for the download: a JavaScript function reads its inputs from
        # the page, where a gr.State never goes.
        file_name = gr.Textbox(visible=False)
        file_text = gr.Textbox(visible=False)

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
        model: str | None = None,
        fallbacks: list[str] | None = None,
        progress: gr.Progress = gr.Progress(),  # noqa: B008
    ) -> tuple[str, str, str, str, gr.Button]:
        if not book_id or number is None:
            raise gr.Error("Choose a book and a chapter first.")
        # The progress shows what the service says, a model's failure and the next one included.
        summary = container.summaries.summarize(
            book_id,
            number,
            chosen_type,
            None if target == SAME_AS_BOOK else target,
            on_progress=lambda message: progress(0, desc=message),
            model=model,
            fallbacks=tuple(fallbacks or ()),
        )
        file = container.summaries.summary_file(summary)
        report_text = summary_report(summary, container.models)
        return report_text, summary.text, file.name, file.text, gr.Button(interactive=True)

    book.change(on_book_change, inputs=book, outputs=chapter, api_visibility="private")
    generate.click(
        on_generate,
        inputs=[book, chapter, summary_type, language, choice.model, choice.fallbacks],
        outputs=[report, summary_text, file_name, file_text, download],
        api_name="summarize",
    )
    download.click(None, inputs=[file_name, file_text], js=_DOWNLOAD, api_visibility="private")
    return SummarizationTab(book)
