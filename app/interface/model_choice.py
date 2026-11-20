"""The models a tab's request goes to, chosen in that tab (specs/008-cloud-llm-providers, R13).

The Chat and Summarization tabs each build their own, so each keeps its own choice (FR-009). Without
a cloud model offered, nothing shows, and every request goes to the local model (FR-006).
"""

from collections.abc import Sequence
from dataclasses import dataclass

import gradio as gr

from app.errors import ModelChoiceError
from app.generation.choices import ModelChoices
from app.interface.formatting import Subject, model_notice, option_label


@dataclass(frozen=True)
class ModelChoice:
    """One tab's components.

    Attributes:
        model: the model picked; the local one on every page load.
        fallbacks: the cloud models to ask, in the order chosen, if it fails; shown while a cloud
            model is picked.
        notice: what goes where, shown while a cloud model is picked.
    """

    model: gr.Dropdown
    fallbacks: gr.Dropdown
    notice: gr.Markdown


def build_model_choice(models: ModelChoices, subject: Subject) -> ModelChoice:
    """The Model dropdown, its fallbacks and its notice, in the tab being built."""
    offered = models.offered()
    model = gr.Dropdown(
        label="Model",
        choices=[(option_label(option), option.name) for option in offered],
        value=offered[0].name,
        visible=models.has_cloud(),
        info="The local model unless you pick another for this tab.",
    )
    fallbacks = gr.Dropdown(
        label="If it fails, then",
        choices=[],
        value=[],
        multiselect=True,
        visible=False,
        info="Asked in the order chosen. The local model answers last.",
    )
    notice = gr.Markdown(visible=False)

    def on_model_change(name: str) -> tuple[gr.Dropdown, gr.Markdown]:
        others = [(option_label(option), option.name) for option in models.fallback_options(name)]
        text = notice_text(models, name, (), subject)
        offered_after = gr.Dropdown(choices=others, value=[], multiselect=True, visible=picks_cloud(models, name))
        return offered_after, _notice(text)

    def on_fallbacks_change(name: str, chosen: list[str] | None) -> gr.Markdown:
        return _notice(notice_text(models, name, chosen or (), subject))

    model.change(on_model_change, inputs=model, outputs=[fallbacks, notice], api_visibility="private")
    fallbacks.change(on_fallbacks_change, inputs=[model, fallbacks], outputs=notice, api_visibility="private")
    return ModelChoice(model, fallbacks, notice)


def notice_text(models: ModelChoices, model: str | None, fallbacks: Sequence[str], subject: Subject) -> str:
    """The notice for a sequence, or why it is refused, as the service would refuse it (FR-010)."""
    try:
        return model_notice(models.describe(model, fallbacks), subject)
    except ModelChoiceError as exc:
        return str(exc)


def picks_cloud(models: ModelChoices, model: str | None) -> bool:
    """Whether the model picked is a cloud model, which can have fallbacks."""
    try:
        return not models.describe(model, ())[0].local
    except ModelChoiceError:
        return False


def _notice(text: str) -> gr.Markdown:
    return gr.Markdown(text, visible=bool(text))
