"""The Library tab: everything that changes what the library holds."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr

from app.container import Container
from app.interface.common import reports_errors
from app.interface.formatting import BOOK_COLUMN_WIDTHS, BOOK_COLUMNS
from app.services.reset_service import CONFIRM_RESET_EVERYTHING, CONFIRM_RESET_INDEX


@dataclass(frozen=True)
class LibraryTab:
    """What the rest of the interface needs from this tab.

    Attributes:
        table: the list of books.
        status: the state of the index.
        book: the book that the actions on this tab apply to.
        changes: the events after which what the library holds may be different. That includes
            failed ones: a book that fails while indexing stays in the list, saying why.
    """

    table: gr.Dataframe
    status: gr.Markdown
    book: gr.Dropdown
    changes: list[Any]


def build_library_tab(container: Container) -> LibraryTab:
    books = container.books

    with gr.Tab("Library"):
        status = gr.Markdown()
        table = gr.Dataframe(headers=BOOK_COLUMNS, column_widths=BOOK_COLUMN_WIDTHS, interactive=False, label="Books")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### Add a book")
                upload = gr.File(label="PDF, EPUB or Markdown", file_types=[".pdf", ".epub", ".md", ".markdown"])
                add = gr.Button("Add to the library", variant="primary")

            with gr.Column():
                gr.Markdown("### Change a book")
                book = gr.Dropdown(label="Book", choices=[])
                replacement = gr.File(label="Replacement document", file_types=[".pdf", ".epub", ".md", ".markdown"])
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

    @reports_errors
    def on_add(path: str | None, progress: gr.Progress = gr.Progress()) -> None:  # noqa: B008
        if path is None:
            raise gr.Error("Choose a file first.")
        progress(0, desc="Indexing the book")
        added = books.add_book(Path(path), Path(path).name)
        gr.Info(f"{added.book_id}: {added.title}, with {added.chapter_count} chapters and {added.chunk_count} chunks.")

    @reports_errors
    def on_replace(book_id: str | None, path: str | None, progress: gr.Progress = gr.Progress()) -> None:  # noqa: B008
        if not book_id or path is None:
            raise gr.Error("Choose a book and its replacement first.")
        progress(0, desc="Indexing the replacement")
        replaced = books.replace_book(book_id, Path(path), Path(path).name)
        gr.Info(f"{replaced.book_id} is now {replaced.title}, with {replaced.chunk_count} chunks.")

    @reports_errors
    def on_reindex_book(book_id: str | None, progress: gr.Progress = gr.Progress()) -> None:  # noqa: B008
        if not book_id:
            raise gr.Error("Choose a book first.")
        progress(0, desc="Indexing the book")
        reindexed = books.reindex_book(book_id)
        gr.Info(f"{reindexed.book_id} was processed again: {reindexed.chunk_count} chunks.")

    @reports_errors
    def on_remove(book_id: str | None, confirmation: str, keep_original: bool) -> str:
        if not book_id:
            raise gr.Error("Choose a book first.")
        books.remove_book(book_id, confirmation, archive_original=keep_original)
        gr.Info(f"{book_id} was removed.")
        return ""

    @reports_errors
    def on_reindex_all(summaries: bool, progress: gr.Progress = gr.Progress()) -> None:  # noqa: B008
        report = container.library.reindex_all(summaries, on_progress=lambda message: progress(0, desc=message))
        notes = [f"Index v{report.index_version} is active: {report.books} books, {report.chunks} chunks."]
        if report.adopted:
            notes.append(f"Brought back from their originals: {', '.join(report.adopted)}.")
        gr.Info(" ".join(notes))
        if report.failed:
            gr.Warning(f"Still failing: {', '.join(report.failed)}.")
        for failure in report.summaries_failed:
            gr.Warning(f"Summary not written: {failure}")

    @reports_errors
    def on_reset_index(confirmation: str) -> str:
        container.resets.reset_index(confirmation)
        gr.Info("The index is gone and the originals are kept. Reindex the library to rebuild it.")
        return ""

    @reports_errors
    def on_reset_everything(confirmation: str) -> str:
        container.resets.reset_everything(confirmation)
        gr.Info("The library is empty.")
        return ""

    added = add.click(on_add, inputs=upload, api_name="add_book")
    replaced = replace.click(on_replace, inputs=[book, replacement], api_name="replace_book")
    added.success(lambda: None, outputs=upload, api_visibility="private")
    replaced.success(lambda: None, outputs=replacement, api_visibility="private")

    changes = [
        added,
        replaced,
        reindex_book.click(on_reindex_book, inputs=book, api_name="reindex_book"),
        remove.click(
            on_remove, inputs=[book, remove_confirmation, archive], outputs=remove_confirmation, api_name="remove_book"
        ),
        reindex_all.click(on_reindex_all, inputs=regenerate, api_name="reindex_all"),
        reset_index.click(
            on_reset_index, inputs=reset_index_confirmation, outputs=reset_index_confirmation, api_name="reset_index"
        ),
        reset_everything.click(
            on_reset_everything,
            inputs=reset_everything_confirmation,
            outputs=reset_everything_confirmation,
            api_name="reset_everything",
        ),
    ]
    return LibraryTab(table, status, book, changes)
