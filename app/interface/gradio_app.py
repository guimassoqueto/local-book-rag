"""The Gradio interface."""

import gradio as gr

from app.container import Container
from app.errors import BookRagError
from app.utils.logging import get_logger, log_event


def build_interface(container: Container) -> gr.Blocks:
    with gr.Blocks(title=container.settings.application.name) as interface:
        gr.Markdown(f"# {container.settings.application.name}")
        with gr.Tab("Status"):
            table = gr.Dataframe(headers=["Check", "OK", "Detail"], interactive=False)
            refresh = gr.Button("Refresh")

        def run_checks() -> list[list[str]]:
            return [[check.name, "yes" if check.ok else "no", check.detail] for check in container.health.run()]

        refresh.click(run_checks, outputs=table)
        interface.load(run_checks, outputs=table)
    return interface


def serve(container: Container) -> None:
    """Clean up after any interrupted operation, and run the interface until the process stops."""
    try:
        container.library.recover()
    except BookRagError as exc:  # ChromaDB may still be starting: the next change to the library retries it
        log_event(get_logger("interface"), "recovery postponed", reason=str(exc))
    server = container.settings.server
    build_interface(container).launch(
        server_name=server.host,
        server_port=server.port,
        max_file_size=f"{container.settings.uploads.max_size_mb}mb",
        show_error=True,
        quiet=True,
        ssr_mode=False,
    )
