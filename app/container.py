"""Composition root: the one place that builds the application's object graph."""

from dataclasses import dataclass

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings, Settings
from app.services.health_service import HealthService
from app.storage.chroma import ChromaServer
from app.utils.logging import configure_logging
from app.utils.ollama_runtime import OllamaRuntime


@dataclass(frozen=True)
class Container:
    settings: Settings
    environment: EnvironmentSettings
    runtime: OllamaRuntime
    health: HealthService


def build_container() -> Container:
    """Validate the configuration and wire the application together."""
    environment = EnvironmentSettings()
    settings = load_settings(environment.config_dir)
    configure_logging(environment.log_level, settings.logging.inference_level, environment.logs_dir)

    runtime = OllamaRuntime(environment.ollama_base_url, settings.ollama.request_timeout_seconds)
    chroma = ChromaServer(environment.chroma_host, environment.chroma_port)
    return Container(
        settings=settings,
        environment=environment,
        runtime=runtime,
        health=HealthService(settings, runtime, chroma),
    )
