"""The Research tab: what happened inside the latest question, and the state of the system."""

import gradio as gr

from app.container import Container
from app.generation.question_answering import Answer
from app.interface.common import reports_errors
from app.interface.formatting import (
    SCORE_COLUMNS,
    gpu_markdown,
    prompt_text,
    reasoning_label,
    reasoning_text,
    run_markdown,
    score_rows,
)
from app.utils.gpu import query_gpu

_CHECK_COLUMNS = ["Check", "OK", "Detail"]
_NO_QUESTION = "Ask a question in the Chat tab to see what happened inside it."


def build_diagnostics_tab(container: Container, last_answer: gr.State, answered: object) -> None:
    settings = container.settings

    with gr.Tab("Research"):
        gr.Markdown("### Latest question")
        run = gr.Markdown(_NO_QUESTION)
        scores = gr.Dataframe(headers=SCORE_COLUMNS, interactive=False, wrap=True, label="Retrieved chunks")
        with gr.Accordion("Final context, as sent to the model", open=False):
            context = gr.Code(language=None, wrap_lines=True, interactive=False)
        with gr.Accordion("The model's reasoning", open=False):
            thinking = gr.Textbox(show_label=False, lines=6, interactive=False)

        gr.Markdown("### System")
        gpu = gr.Markdown()
        checks = gr.Dataframe(headers=_CHECK_COLUMNS, interactive=False, wrap=True, label="Health checks")
        refresh = gr.Button("Check again")

    def on_answer(answer: Answer | None) -> tuple[str, list[list[object]], str, gr.Textbox]:
        if answer is None:
            return _NO_QUESTION, [], "", gr.Textbox("", show_label=False)
        reranker = settings.reranker.model if settings.retrieval.reranker.enabled else "disabled"
        index = container.indexes.active()
        embedding = index.embedding_model if index else settings.embedding.model
        label = reasoning_label(answer, container.models)
        return (
            run_markdown(answer, embedding, reranker, container.models),
            score_rows(answer),
            prompt_text(answer.messages),
            gr.Textbox(reasoning_text(answer, container.models), label=label or None, show_label=bool(label)),
        )

    def system(providers: bool) -> tuple[str, list[list[str]]]:
        loaded = container.runtime.loaded_models()
        results = container.health.run(providers=providers)
        rows = [[check.name, "yes" if check.ok else "no", check.detail] for check in results]
        return gpu_markdown(query_gpu(), loaded), rows

    @reports_errors
    def on_answer_checks() -> tuple[str, list[list[str]]]:
        """After each answer: no provider is contacted (FR-021)."""
        return system(providers=False)

    @reports_errors
    def on_check_again() -> tuple[str, list[list[str]]]:
        """Asked for: each cloud provider's key and models are checked too."""
        return system(providers=True)

    answered.then(  # type: ignore[attr-defined]
        on_answer, inputs=last_answer, outputs=[run, scores, context, thinking], api_visibility="private"
    ).then(on_answer_checks, outputs=[gpu, checks], api_visibility="private")
    refresh.click(on_check_again, outputs=[gpu, checks], api_name="system_status")
