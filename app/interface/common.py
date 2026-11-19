"""What every tab of the interface shares."""

import inspect
import threading
import time
from collections.abc import Callable, Generator
from functools import wraps
from typing import Any

import gradio as gr

from app.errors import BookRagError
from app.utils.progress import Progress, ProgressView


def reports_errors(handler: Callable[..., Any]) -> Callable[..., Any]:
    """Show a handler's domain errors to the user. Gradio would otherwise report a bare "Error".

    The notification stays until dismissed: most of these tell the user what to do next.
    """

    def report(exc: BookRagError) -> gr.Error:
        return gr.Error(str(exc), duration=None, print_exception=False)

    if inspect.isgeneratorfunction(handler):

        @wraps(handler)
        def stream(*args: Any, **kwargs: Any) -> Any:
            try:
                yield from handler(*args, **kwargs)
            except BookRagError as exc:
                raise report(exc) from exc

        return stream

    @wraps(handler)
    def call(*args: Any, **kwargs: Any) -> Any:
        try:
            return handler(*args, **kwargs)
        except BookRagError as exc:
            raise report(exc) from exc

    return call


def follow[T, R](
    call: Callable[[], T],
    progress: Progress,
    render: Callable[[ProgressView | None], R],
    poll: float = 0.5,
    beat: float = 1.0,
) -> Generator[R, None, T]:
    """Run an operation in a thread of its own, yielding its progress as it goes (research.md, R2, R3).

    The operation holds the library lock and its log context from start to end in that one thread,
    which a Gradio generator, whose steps may each run in a different thread, couldn't. Nothing the
    operation does waits on the page: a page closed midway only stops this generator, and the
    operation runs to its end. The thread is a daemon, as Gradio's own worker threads are, so a
    server that shuts down stops it as it would have stopped the call, and recovery finishes or
    undoes it at the next start.

    Yields:
        `render(snapshot)` when the snapshot changed or `beat` seconds have passed, every `poll`
        seconds, once the progress has begun. If the operation raised, `render` of its last
        snapshot, None for one refused before it began, and then the same exception.

    Returns:
        What the operation returned.
    """
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = call()
        except BaseException as exc:  # handed to the caller's thread, which raises it
            outcome["error"] = exc

    thread = threading.Thread(target=run, name="library operation", daemon=True)
    thread.start()
    last_view: ProgressView | None = None
    last_yield = 0.0
    while thread.is_alive():
        thread.join(poll)
        view = progress.snapshot()
        if view is None or (not thread.is_alive() and "error" in outcome):
            continue  # nothing begun yet, or a failure, which the last yield shows
        now = time.monotonic()
        if view != last_view or now - last_yield >= beat:
            last_view, last_yield = view, now
            yield render(view)
    if "error" in outcome:
        yield render(progress.snapshot())
        raise outcome["error"]
    return outcome["result"]
