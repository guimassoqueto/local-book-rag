"""The Library tab: everything that changes what the library holds."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr

from app.container import Container
from app.interface.common import follow, reports_errors
from app.interface.formatting import (
    BOOK_COLUMN_WIDTHS,
    BOOK_COLUMNS,
    PROGRESS_CSS,
    added_line,
    everything_reset_line,
    index_reset_line,
    kept_summaries_notice,
    outcome_html,
    progress_html,
    reindexed_line,
    removed_line,
    replaced_line,
    reprocessed_line,
    starting_html,
)
from app.services.book_service import ADDING, REMOVING, REPLACING, REPROCESSING
from app.services.library_service import REINDEXING
from app.services.reset_service import (
    CONFIRM_RESET_EVERYTHING,
    CONFIRM_RESET_INDEX,
    RESETTING_EVERYTHING,
    RESETTING_INDEX,
)
from app.utils.progress import Progress, ProgressView


@dataclass(frozen=True)
class LibraryTab:
    """What the rest of the interface needs from this tab.

    Attributes:
        table: the list of books.
        status: the state of the index.
        progress: what the running operation is doing, and how the last one ended.
        book: the book that the actions on this tab apply to.
        changes: the events after which what the library holds may be different. That includes
            failed ones: a book that fails while indexing stays in the list, saying why.
    """

    table: gr.Dataframe
    status: gr.Markdown
    progress: gr.HTML
    book: gr.Dropdown
    changes: list[Any]


# The browser's dialog offers only these. A file forced past it is refused by Gradio's own type
# check before any handler runs, and the service refuses whatever reaches it (specs/005, R3).
MARKDOWN_TYPES = [".md", ".markdown"]
MARKDOWN_PICKER = "Markdown book (.md, .markdown)"
BOOKS_ARE_MARKDOWN = (
    "Books are Markdown files. Convert a PDF or an EPUB to Markdown first, with MarkItDown for example. "
    "The file's name becomes the book's title."
)


def build_library_tab(container: Container) -> LibraryTab:
    books = container.books

    with gr.Tab("Library"):
        status = gr.Markdown()
        area = gr.HTML(css_template=PROGRESS_CSS)
        table = gr.Dataframe(headers=BOOK_COLUMNS, column_widths=BOOK_COLUMN_WIDTHS, interactive=False, label="Books")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### Add a book")
                gr.Markdown(BOOKS_ARE_MARKDOWN)
                upload = gr.File(label=MARKDOWN_PICKER, file_types=MARKDOWN_TYPES)
                add = gr.Button("Add to the library", variant="primary")

            with gr.Column():
                gr.Markdown("### Change a book")
                book = gr.Dropdown(label="Book", choices=[])
                replacement = gr.File(label=MARKDOWN_PICKER, file_types=MARKDOWN_TYPES)
                replace = gr.Button("Replace the book")
                reindex_book = gr.Button("Process again from its original")

        with gr.Accordion("Remove a book", open=False):
            gr.Markdown("Deletes the book and everything derived from it. Other books are not affected.")
            archive = gr.Checkbox(label="Keep the original document in data/archive")
            remove_confirmation = gr.Textbox(label="Type the book's ID to confirm, such as book_001")
            remove = gr.Button("Remove the book", variant="stop")

        with gr.Accordion("Reindex the library", open=False):
            gr.Markdown(
                "Rebuilds the index from the original documents with the current configuration, which is "
                "how a new embedding model or chunk size takes effect. Questions keep working on the "
                "current index until the new one is ready, and a failure leaves everything as it was."
            )
            regenerate = gr.Checkbox(label="Also write the saved summaries again")
            reindex_all = gr.Button("Reindex the library")

        with gr.Accordion("Reset", open=False):
            gr.Markdown(
                "Neither of these touches the downloaded models or the Docker volumes.\n\n"
                "**Reset the index** deletes the vectors, processed documents, summaries and catalog, and "
                "keeps the original documents. **Reindex the library** then rebuilds it, without uploading "
                "anything again."
            )
            reset_index_confirmation = gr.Textbox(label=f"Type {CONFIRM_RESET_INDEX} to confirm")
            reset_index = gr.Button("Reset the index", variant="stop")
            gr.Markdown("**Reset everything** also deletes the original documents. This cannot be undone.")
            reset_everything_confirmation = gr.Textbox(label=f"Type {CONFIRM_RESET_EVERYTHING} to confirm")
            reset_everything = gr.Button("Reset everything", variant="stop")

    buttons = [add, replace, reindex_book, remove, reindex_all, reset_index, reset_everything]

    def wire(button: gr.Button, label: str, handler: Any, inputs: Any, outputs: list[Any], api_name: str) -> Any:
        """Disable the seven buttons and show the operation starting, run it, and enable them again.

        Gradio's `then` doesn't run after an error, so the enabling follows success and failure both.
        """

        def disable() -> tuple[Any, ...]:
            return (*(gr.update(interactive=False) for _ in buttons), starting_html(label))

        def enable() -> tuple[Any, ...]:
            return tuple(gr.update(interactive=True) for _ in buttons)

        started = button.click(disable, outputs=[*buttons, area], queue=False, api_visibility="private")
        event = started.then(
            handler, inputs=inputs, outputs=[area, *outputs], api_name=api_name, show_progress="hidden"
        )
        event.success(enable, outputs=buttons, api_visibility="private")
        event.failure(enable, outputs=buttons, api_visibility="private")
        return event

    @reports_errors
    def on_add(path: str | None) -> Iterator[str]:
        if path is None:
            yield ""  # the starting line goes: nothing started
            raise gr.Error("Choose a file first.")
        progress = Progress()
        added = yield from follow(
            lambda: books.add_book(Path(path), Path(path).name, progress=progress), progress, progress_html
        )
        gr.Info(f"{added.book_id}: {added.title}, with {added.chapter_count} chapters and {added.chunk_count} chunks.")
        yield outcome_html(added_line(added, _elapsed(progress)), succeeded=True)

    @reports_errors
    def on_replace(book_id: str | None, path: str | None) -> Iterator[str]:
        if not book_id or path is None:
            yield ""
            raise gr.Error("Choose a book and its replacement first.")
        progress = Progress()
        replaced = yield from follow(
            lambda: books.replace_book(book_id, Path(path), Path(path).name, progress=progress),
            progress,
            progress_html,
        )
        gr.Info(f"{replaced.book_id} is now {replaced.title}, with {replaced.chunk_count} chunks.")
        yield outcome_html(replaced_line(replaced, _elapsed(progress)), succeeded=True)

    @reports_errors
    def on_reindex_book(book_id: str | None) -> Iterator[str]:
        if not book_id:
            yield ""
            raise gr.Error("Choose a book first.")
        progress = Progress()
        reindexed = yield from follow(lambda: books.reindex_book(book_id, progress=progress), progress, progress_html)
        gr.Info(f"{reindexed.book_id} was processed again: {reindexed.chunk_count} chunks.")
        yield outcome_html(reprocessed_line(reindexed, _elapsed(progress)), succeeded=True)

    def with_confirmation(view: ProgressView | None) -> tuple[str, Any]:
        """The area, and the confirmation box left as it is until the operation has ended."""
        return progress_html(view), gr.skip()

    @reports_errors
    def on_remove(book_id: str | None, confirmation: str, keep_original: bool) -> Iterator[tuple[str, Any]]:
        if not book_id:
            yield "", gr.skip()
            raise gr.Error("Choose a book first.")
        progress = Progress()
        yield from follow(
            lambda: books.remove_book(book_id, confirmation, archive_original=keep_original, progress=progress),
            progress,
            with_confirmation,
        )
        gr.Info(f"{book_id} was removed.")
        yield outcome_html(removed_line(book_id, keep_original, _elapsed(progress)), succeeded=True), ""

    @reports_errors
    def on_reindex_all(summaries: bool) -> Iterator[str]:
        progress = Progress()
        report = yield from follow(
            lambda: container.library.reindex_all(summaries, progress=progress), progress, progress_html
        )
        notes = [f"Index v{report.index_version} is active: {report.books} books, {report.chunks} chunks."]
        if report.adopted:
            notes.append(f"Brought back from their originals: {', '.join(report.adopted)}.")
        gr.Info(" ".join(notes))
        if report.failed:
            gr.Warning(f"Still failing: {', '.join(report.failed)}.")
        for failure in report.summaries_failed:
            gr.Warning(f"Summary not written: {failure}")
        if kept := kept_summaries_notice(report):
            gr.Info(kept)
        yield outcome_html(reindexed_line(report, _elapsed(progress)), succeeded=True)

    @reports_errors
    def on_reset_index(confirmation: str) -> Iterator[tuple[str, Any]]:
        progress = Progress()
        yield from follow(
            lambda: container.resets.reset_index(confirmation, progress=progress), progress, with_confirmation
        )
        gr.Info("The index is gone and the originals are kept. Reindex the library to rebuild it.")
        yield outcome_html(index_reset_line(_elapsed(progress)), succeeded=True), ""

    @reports_errors
    def on_reset_everything(confirmation: str) -> Iterator[tuple[str, Any]]:
        progress = Progress()
        yield from follow(
            lambda: container.resets.reset_everything(confirmation, progress=progress), progress, with_confirmation
        )
        gr.Info("The library is empty.")
        yield outcome_html(everything_reset_line(_elapsed(progress)), succeeded=True), ""

    added = wire(add, ADDING, on_add, upload, [], "add_book")
    replaced = wire(replace, REPLACING, on_replace, [book, replacement], [], "replace_book")
    added.success(lambda: None, outputs=upload, api_visibility="private")
    replaced.success(lambda: None, outputs=replacement, api_visibility="private")

    changes = [
        added,
        replaced,
        wire(reindex_book, REPROCESSING, on_reindex_book, book, [], "reindex_book"),
        wire(remove, REMOVING, on_remove, [book, remove_confirmation, archive], [remove_confirmation], "remove_book"),
        wire(reindex_all, REINDEXING, on_reindex_all, regenerate, [], "reindex_all"),
        wire(
            reset_index,
            RESETTING_INDEX,
            on_reset_index,
            reset_index_confirmation,
            [reset_index_confirmation],
            "reset_index",
        ),
        wire(
            reset_everything,
            RESETTING_EVERYTHING,
            on_reset_everything,
            reset_everything_confirmation,
            [reset_everything_confirmation],
            "reset_everything",
        ),
    ]
    return LibraryTab(table, status, area, book, changes)


def _elapsed(progress: Progress) -> float:
    view = progress.snapshot()
    return view.elapsed if view is not None else 0.0
