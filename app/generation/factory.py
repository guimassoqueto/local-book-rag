"""Builds the LLM provider that a configuration names."""

from typing import Literal

from app.config.settings import Settings
from app.errors import ConfigurationError
from app.generation.base import LLMProvider
from app.generation.ollama_provider import OllamaLLMProvider
from app.utils.ollama_runtime import OllamaRuntime
from app.utils.tokenization import create_token_counter


def create_llm_provider(
    settings: Settings,
    runtime: OllamaRuntime,
    model: str | None = None,
    reasoning: Literal["low", "medium", "high"] | None = None,
) -> LLMProvider:
    """Build a provider for llm.model, or for another model with a profile.

    Reasoning is a profile setting, sent with every call, so a task that has to reason
    differently from the model's profile, such as the quiz's key check, needs a provider of its
    own.

    Args:
        settings: the configuration.
        runtime: the Ollama server.
        model: the model. None means llm.model; another one runs with llm's other settings.
        reasoning: replaces the profile's reasoning setting. None keeps the profile's.

    Raises:
        ConfigurationError: the model has no entry in llm_profiles.
    """
    name = model or settings.llm.model
    profile = settings.llm_profiles.get(name)
    if profile is None:
        raise ConfigurationError(f"llm_profiles in config/models.yaml has no entry for '{name}'.")
    if reasoning is not None:
        profile = profile.model_copy(update={"reasoning": reasoning})
    config = settings.llm if name == settings.llm.model else settings.llm.model_copy(update={"model": name})
    match config.provider:
        case "ollama":
            return OllamaLLMProvider(
                config,
                profile,
                runtime,
                create_token_counter(profile.tokenizer),
                settings.ollama.request_timeout_seconds,
            )
