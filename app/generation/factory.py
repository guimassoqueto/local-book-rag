"""Builds the LLM provider that a configuration names, and the cloud providers that the environment
configures."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.config.settings import Settings, read_provider_credentials
from app.errors import ConfigurationError
from app.generation.base import LLMProvider
from app.generation.cloud import CloudProvider
from app.generation.ollama_provider import OllamaLLMProvider
from app.utils.ollama_runtime import OllamaRuntime
from app.utils.tokenization import create_token_counter


@dataclass(frozen=True)
class MissingSetting:
    """A cloud provider with one of its two settings, which isn't offered (FR-002).

    Attributes:
        provider: the provider kind's name.
        label: its label.
        present: the setting that is set.
        missing: the one that isn't.
    """

    provider: str
    label: str
    present: str
    missing: str

    def describe(self) -> str:
        return f"{self.present} is set and {self.missing} isn't: no model of {self.label}'s is offered"


@dataclass(frozen=True)
class CloudSetup:
    """The cloud providers of a setup.

    Attributes:
        providers: each configured provider, built, with its allowed models in order.
        problems: the providers with one setting only.
        kinds: the label of every provider kind the app implements, configured or not.
    """

    providers: tuple[tuple[CloudProvider, tuple[str, ...]], ...] = ()
    problems: tuple[MissingSetting, ...] = ()
    kinds: Mapping[str, str] = field(default_factory=dict)


def create_llm_provider(settings: Settings, runtime: OllamaRuntime) -> LLMProvider:
    """Build the provider for llm.model, with that model's profile.

    Another model or reasoning level, as a benchmark variant or a judge asks for, comes in the
    settings: apply_overrides changes llm.model or the profile before this is called.

    Args:
        settings: the configuration.
        runtime: the Ollama server.

    Raises:
        ConfigurationError: the model has no entry in llm_profiles.
    """
    config = settings.llm
    profile = settings.llm_profiles.get(config.model)
    if profile is None:
        raise ConfigurationError(f"llm_profiles in config/models.yaml has no entry for '{config.model}'.")
    match config.provider:
        case "ollama":
            return OllamaLLMProvider(
                config,
                profile,
                runtime,
                create_token_counter(profile.tokenizer),
                settings.ollama.request_timeout_seconds,
            )


def create_cloud_providers(
    settings: Settings, environ: Mapping[str, str], kinds: Mapping[str, type[CloudProvider]]
) -> CloudSetup:
    """Build each provider kind whose API key and allowed models are both set, with its profile.

    Reads files and the environment only: building a provider contacts nothing, so the app starts
    without a network.

    Args:
        settings: the configuration, whose cloud_profiles names only implemented kinds.
        environ: where `<NAME>_API_KEY` and `<NAME>_MODELS` are read.
        kinds: each implemented provider kind's class, by name. Only the container names them.

    Raises:
        ConfigurationError: a profile names a provider kind the app doesn't implement, or a
            provider's models are allowed without a profile (FR-003).
    """
    if unknown := sorted(set(settings.cloud_profiles) - set(kinds)):
        raise ConfigurationError(
            "cloud_profiles in config/models.yaml names a provider the app doesn't implement: "
            f"{', '.join(unknown)} (implemented: {', '.join(kinds)})"
        )
    providers = []
    problems = []
    for name, kind in kinds.items():
        credentials = read_provider_credentials(name, environ)
        key_setting, models_setting = f"{name.upper()}_API_KEY", f"{name.upper()}_MODELS"
        profile = settings.cloud_profiles.get(name)
        if credentials.models and profile is None:
            raise ConfigurationError(
                f"{models_setting} allows {', '.join(credentials.models)}, but cloud_profiles in "
                f"config/models.yaml has no profile for {name}"
            )
        if credentials.api_key and credentials.models and profile is not None:
            providers.append((kind(credentials, profile), credentials.models))
        elif credentials.api_key:
            problems.append(MissingSetting(name, kind.label, present=key_setting, missing=models_setting))
        elif credentials.models:
            problems.append(MissingSetting(name, kind.label, present=models_setting, missing=key_setting))
    return CloudSetup(tuple(providers), tuple(problems), {name: kind.label for name, kind in kinds.items()})
