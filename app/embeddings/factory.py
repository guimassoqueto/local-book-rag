"""Builds the embedding provider that a configuration names."""

from app.config.settings import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.ollama_provider import OllamaEmbeddingProvider
from app.errors import ConfigurationError
from app.utils.ollama_runtime import OllamaRuntime


def create_embedding_provider(
    settings: Settings, runtime: OllamaRuntime, model: str | None = None
) -> EmbeddingProvider:
    """Create a provider.

    Args:
        settings: the application's configuration.
        runtime: the Ollama server.
        model: a model other than embedding.model. Queries need the one the active index
            was built with, even after the configuration moved on to another.

    Raises:
        ConfigurationError: embedding_profiles has no entry for the model.
    """
    config = settings.embedding if model is None else settings.embedding.model_copy(update={"model": model})
    profile = settings.embedding_profiles.get(config.model)
    if profile is None:
        raise ConfigurationError(f"embedding_profiles has no entry for '{config.model}', which the index uses.")
    match config.provider:
        case "ollama":
            return OllamaEmbeddingProvider(config, profile, runtime, settings.ollama.request_timeout_seconds)
