"""What every tab of the interface shares."""

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any

import gradio as gr

from app.errors import BookRagError


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
