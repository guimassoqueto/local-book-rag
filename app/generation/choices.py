"""The models a request may go to, and the rules of a sequence (specs/008-cloud-llm-providers, R6).

The local model is offered always, and each allowed cloud model when its provider is configured.
A request names a model and its fallbacks; the local model answers last in every sequence. The
services resolve the names here before they search or send anything, so the tabs and the commands
can't differ on a rule (Principle IV).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.errors import (
    AllModelsFailedError,
    BookRagError,
    GenerationError,
    ModelChoiceError,
    ModelFailedError,
    ModelNotFoundError,
    ServiceUnavailableError,
)
from app.generation.base import Attempt, FailureReason, LLMProvider
from app.generation.cloud import CloudProvider, ProviderCheck
from app.generation.factory import CloudSetup

LOCAL_LABEL = "local"


@dataclass(frozen=True)
class ModelOption:
    """A model that a request may name.

    Attributes:
        name: the model, as `config/models.yaml` names the local one, or its provider's allow-list a
            cloud one.
        provider: its provider's name, such as `ollama` or `anthropic`.
        provider_label: its provider as the interface shows it, `local` for the local model.
        local: whether it is the local model.
    """

    name: str
    provider: str
    provider_label: str
    local: bool


class ModelChoices:
    """The local model, and each cloud model that the setup offers.

    Args:
        local: the local model, which answers alone or last.
        setup: the configured cloud providers, from create_cloud_providers().
    """

    def __init__(self, local: LLMProvider, setup: CloudSetup) -> None:
        self._local = local
        self._setup = setup
        self._clouds: dict[str, tuple[CloudProvider, ModelOption]] = {}
        for provider, models in setup.providers:
            for model in models:
                self._clouds.setdefault(model, (provider, ModelOption(model, provider.name, provider.label, False)))

    @classmethod
    def local_only(cls, llm: LLMProvider) -> "ModelChoices":
        """The choices of a setup without cloud models, such as a benchmark's."""
        return cls(llm, CloudSetup())

    @property
    def local(self) -> LLMProvider:
        return self._local

    @property
    def cloud_setup(self) -> CloudSetup:
        return self._setup

    def offered(self) -> list[ModelOption]:
        """The local model first, then each allowed model, in its provider's list's order."""
        return [self._local_option(), *(option for _, option in self._clouds.values())]

    def has_cloud(self) -> bool:
        return bool(self._clouds)

    def fallback_options(self, model: str | None) -> list[ModelOption]:
        """The models that may follow a picked model, in the order offered: the other cloud models.

        The local model, or a name not offered, takes none: the local model answers last in every
        sequence (FR-007).
        """
        if model not in self._clouds:
            return []
        return [option for name, (_, option) in self._clouds.items() if name != model]

    def describe(self, model: str | None, fallbacks: Sequence[str]) -> list[ModelOption]:
        """The models a request would go to, in order, building no provider.

        Raises:
            ModelChoiceError: a name isn't offered, or is given twice; the local model is named as a
                fallback, or picked with fallbacks.
        """
        local = self._local_option()
        if model is None or model == local.name:
            if fallbacks:
                raise self._refusal(f"{local.name} answers alone, so it takes no fallback.")
            return [local]
        named = [model, *fallbacks]
        for name in named:
            if name == local.name:
                raise self._refusal(f"{local.name} answers last in every sequence, so it can't be a fallback.")
            if name not in self._clouds:
                raise self._refusal(f"{name} isn't offered.")
            if named.count(name) > 1:
                raise self._refusal(f"{name} is given more than once.")
        return [*(self._clouds[name][1] for name in named), local]

    def sequence(self, model: str | None, fallbacks: Sequence[str]) -> list[LLMProvider]:
        """The providers a request goes to, in order: the model, its fallbacks, then the local model.

        Raises:
            ModelChoiceError: as describe() does.
        """
        return [
            self._local if option.local else self._clouds[option.name][0].model(option.name)
            for option in self.describe(model, fallbacks)
        ]

    def is_cloud_provider(self, provider: str | None) -> bool:
        """Whether a provider's name is that of a cloud provider kind the app implements, configured
        now or not."""
        return provider is not None and provider in self._setup.kinds

    def label_of(self, provider: str) -> str:
        """A provider's label, `local` for the local one."""
        if provider == self._local.provider:
            return LOCAL_LABEL
        return self._setup.kinds.get(provider, provider)

    def check(self) -> list[ProviderCheck]:
        """Each configured provider's check, which contacts it."""
        return [row for provider, models in self._setup.providers for row in provider.check(models)]

    def setting_problems(self) -> list[ProviderCheck]:
        """A failing row for each provider with one setting only. Contacts nothing."""
        return [ProviderCheck(problem.provider, False, problem.describe()) for problem in self._setup.problems]

    def all_failed(self, attempts: Sequence[Attempt], last_error: BookRagError) -> AllModelsFailedError:
        """The error that ends a sequence whose every model failed, each failure listed in order.

        The last line keeps the local model's own error, which says more than a reason would.
        """
        *earlier, last = attempts
        lines = [attempt.describe(self.label_of(attempt.provider)) for attempt in earlier]
        if isinstance(last_error, ModelFailedError):
            lines.append(last.describe(self.label_of(last.provider)))
        else:
            lines.append(f"{last.model} ({self.label_of(last.provider)}) failed: {last_error}")
        return AllModelsFailedError(attempts, lines)

    def _local_option(self) -> ModelOption:
        return ModelOption(self._local.model, self._local.provider, LOCAL_LABEL, True)

    def _refusal(self, problem: str) -> ModelChoiceError:
        offered = ", ".join(f"{option.name} ({option.provider_label})" for option in self.offered())
        return ModelChoiceError(f"{problem} Offered: {offered}.")


def moves_on(error: BookRagError) -> bool:
    """Whether a failure sends the request to the next model: a cloud provider's failure, or a reply
    with no text (FR-017)."""
    return isinstance(error, ModelFailedError | GenerationError)


def failed_attempt(
    llm: LLMProvider,
    error: BookRagError,
    step: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> Attempt:
    """A model's failure, as a sequence records it.

    Args:
        llm: the model that failed.
        error: its failure: a cloud provider's, with its reason, or a model's own error.
        step: for a summary, the step that failed.
        prompt_tokens: for a summary, the tokens its finished steps read.
        completion_tokens: likewise, the tokens they generated.
    """
    tokens = {"step": step, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
    if isinstance(error, ModelFailedError):
        return Attempt(error.model, error.provider, error.reason, error.detail, **tokens)
    if isinstance(error, GenerationError):
        reason = FailureReason.NO_ANSWER
    elif isinstance(error, ServiceUnavailableError):
        reason = FailureReason.UNREACHABLE
    elif isinstance(error, ModelNotFoundError):
        reason = FailureReason.UNKNOWN_MODEL
    else:
        reason = FailureReason.REJECTED
    return Attempt(llm.model, llm.provider, reason, str(error), **tokens)
