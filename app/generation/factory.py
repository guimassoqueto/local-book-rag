"""Builds the LLM provider that a configuration names."""

from app.config.settings import Settings
from app.errors import ConfigurationError
from app.generation.base import LLMProvider
from app.generation.ollama_provider import OllamaLLMProvider
from app.utils.ollama_runtime import OllamaRuntime
from app.utils.tokenization import create_token_counter


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
