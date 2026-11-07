"""The Gradio interface. Every tab is a thin layer over the same services as the commands."""

from typing import Any

import gradio as gr

from app.container import Container
from app.errors import BookRagError
from app.interface.chat import build_chat_tab
from app.interface.diagnostics import build_diagnostics_tab
from app.interface.formatting import book_choices, book_rows, index_status
from app.interface.library import build_library_tab
from app.interface.summarization import build_summarization_tab
from app.utils.logging import get_logger, log_event

logger = get_logger("interface")


def build_interface(container: Container) -> gr.Blocks:
    with gr.Blocks(title=container.settings.application.name) as interface:
        gr.Markdown(f"# {container.settings.application.name}")
        library = build_library_tab(container)
        chat = build_chat_tab(container)
        summarization = build_summarization_tab(container)
        build_diagnostics_tab(container, chat.last_answer, chat.answered)

        def refresh(library_book: str | None, chat_books: list[str], summary_book: str | None) -> tuple[Any, ...]:
            """Show what the library holds now, keeping each selection that still exists."""
            books = container.books.list_books()
            choices = book_choices(books)
            existing = {book.book_id for book in books}
            return (
                book_rows(books),
                _index_status(container),
                gr.Dropdown(choices=choices, value=library_book if library_book in existing else None),
                gr.Dropdown(choices=choices, value=[book for book in chat_books or [] if book in existing]),
                gr.Dropdown(choices=choices, value=summary_book if summary_book in existing else None),
            )

        selections = [library.book, chat.books, summarization.book]
        outputs = [library.table, library.status, library.book, chat.books, summarization.book]
        interface.load(refresh, inputs=selections, outputs=outputs, api_visibility="private")
        for change in library.changes:
            # Gradio's `then` doesn't run after an error, which is when a failed book appears.
            change.success(refresh, inputs=selections, outputs=outputs, api_visibility="private")
            change.failure(refresh, inputs=selections, outputs=outputs, api_visibility="private")
    return interface


def _index_status(container: Container) -> str:
    """Report the index, without letting a service that is down stop the page from loading."""
    try:
        return index_status(container.indexes.active(), container.indexes.needs_reindex())
    except BookRagError as exc:
        return f"⚠️ {exc}"


def serve(container: Container) -> None:
    """Clean up after any interrupted operation, and run the interface until the process stops."""
    try:
        repaired = container.library.recover()
        if repaired:
            log_event(logger, "repaired interrupted operations", operations=repaired)
    except BookRagError as exc:  # ChromaDB may still be starting: the next change to the library retries it
        log_event(logger, "recovery postponed", reason=str(exc))

    server = container.settings.server
    build_interface(container).queue().launch(
        server_name=server.host,
        server_port=server.port,
        max_file_size=f"{container.settings.uploads.max_size_mb}mb",
        show_error=True,
        quiet=True,
        ssr_mode=False,
        theme=gr.themes.Soft(),
    )
