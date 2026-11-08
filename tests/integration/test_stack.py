"""Runs against the Compose stack, from the host: `make up`, `make pull-models`, then `make test-integration`."""

import os

import pytest

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings
from app.services.health_service import HealthService
from app.services.index_service import IndexService
from app.storage.catalog import BookCatalog
from app.storage.chroma import ChromaServer
from app.utils.ollama_runtime import OllamaRuntime

pytestmark = pytest.mark.integration


@pytest.fixture
def health(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_BASE_URL", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    monkeypatch.setenv("CHROMA_HOST", os.environ.get("CHROMA_HOST", "localhost"))
    environment = EnvironmentSettings()
    settings = load_settings(environment.config_dir)
    runtime = OllamaRuntime(environment.ollama_base_url, settings.ollama.request_timeout_seconds)
    chroma = ChromaServer(environment.chroma_host, environment.chroma_port)
    indexes = IndexService(settings, BookCatalog(tmp_path / "catalog.db"), chroma, runtime)
    return HealthService(settings, runtime, chroma, indexes)


def test_every_service_and_model_answers(health):
    failures = [result for result in health.run(inference=True) if not result.ok]

    assert not failures
