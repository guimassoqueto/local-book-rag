"""Builds the LLM provider that a configuration names."""

from app.config.settings import Settings
from app.generation.base import LLMProvider
from app.generation.ollama_provider import OllamaLLMProvider
from app.utils.ollama_runtime import OllamaRuntime
from app.utils.tokenization import create_token_counter


def create_llm_provider(settings: Settings, runtime: OllamaRuntime) -> LLMProvider:
    profile = settings.llm_profile
    match settings.llm.provider:
        case "ollama":
            return OllamaLLMProvider(
                settings.llm,
                profile,
                runtime,
                create_token_counter(profile.tokenizer),
                settings.ollama.request_timeout_seconds,
            )
