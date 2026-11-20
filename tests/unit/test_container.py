import json
import logging

import pytest

from app.config.settings import CloudProfile, EnvironmentSettings, TokenizerConfig
from app.container import CLOUD_PROVIDERS, assemble, build_container
from app.errors import ConfigurationError
from app.generation import anthropic_provider
from app.utils.logging import INFERENCE_LOGGER, configure_logging
from tests.fakes import FakeAnthropicClient

KEY = "sk-ant-sentinel-0123456789"
BOTH = {"ANTHROPIC_API_KEY": KEY, "ANTHROPIC_MODELS": "claude-a,claude-b"}


@pytest.fixture
def client(monkeypatch):
    """Anthropic's client, as the container builds it: a fake that counts every call."""
    fake = FakeAnthropicClient()
    monkeypatch.setattr(anthropic_provider.anthropic, "Anthropic", fake.factory)
    return fake


@pytest.fixture
def logs_dir(tmp_path):
    directory = tmp_path / "logs"
    configure_logging("INFO", "INFO", directory, console=False)
    yield directory
    for name in ("book_rag", INFERENCE_LOGGER):
        for handler in logging.getLogger(name).handlers:
            handler.close()
        logging.getLogger(name).handlers.clear()


def test_the_container_builds_one_provider_for_the_configured_model(settings, tmp_path):
    container = assemble(settings, EnvironmentSettings(data_dir=tmp_path))

    llm = container.models.local
    assert container.questions._models is container.models
    assert container.summaries._models is container.models
    assert llm.model == settings.llm.model
    assert llm._profile == settings.llm_profile


# Cloud providers (specs/008-cloud-llm-providers, research.md R1 and R15)


def test_anthropic_is_the_one_cloud_provider_kind():
    assert list(CLOUD_PROVIDERS) == ["anthropic"]


def test_without_an_environment_no_cloud_model_is_offered(settings, tmp_path, client):
    container = assemble(settings, EnvironmentSettings(data_dir=tmp_path))

    assert [option.name for option in container.models.offered()] == [settings.llm.model]
    assert container.models.local.model == settings.llm.model
    assert client.options is None


def test_with_both_settings_the_allowed_models_are_offered_and_nothing_is_contacted(settings, tmp_path, client):
    container = assemble(settings, EnvironmentSettings(data_dir=tmp_path), environ=BOTH)

    assert [option.name for option in container.models.offered()] == [settings.llm.model, "claude-a", "claude-b"]
    assert client.options["api_key"] == KEY
    assert client.calls == 0


def test_a_profile_for_a_provider_the_app_doesnt_implement_stops_it(settings, tmp_path, client):
    profile = settings.cloud_profiles.get("anthropic") or CloudProfile(
        tokenizer=TokenizerConfig(kind="tiktoken", name="o200k_base"),
        context_size=65536,
        reasoning="low",
        reasoning_tokens=4000,
        request_timeout_seconds=120,
    )
    unknown = settings.model_copy(update={"cloud_profiles": {"anthropic": profile, "openai": profile}})

    with pytest.raises(ConfigurationError) as stopped:
        assemble(unknown, EnvironmentSettings(data_dir=tmp_path))

    assert str(stopped.value) == (
        "cloud_profiles in config/models.yaml names a provider the app doesn't implement: openai "
        "(implemented: anthropic)"
    )


def test_allowed_models_without_a_profile_stop_it(settings, tmp_path, client):
    without = settings.model_copy(update={"cloud_profiles": {}})

    with pytest.raises(ConfigurationError) as stopped:
        assemble(without, EnvironmentSettings(data_dir=tmp_path), environ={"ANTHROPIC_MODELS": "claude-a,claude-b"})

    assert str(stopped.value) == (
        "ANTHROPIC_MODELS allows claude-a, claude-b, but cloud_profiles in config/models.yaml has no profile for "
        "anthropic"
    )


@pytest.mark.parametrize(
    ("environ", "missing"),
    [({"ANTHROPIC_API_KEY": KEY}, "ANTHROPIC_MODELS"), ({"ANTHROPIC_MODELS": "claude-a"}, "ANTHROPIC_API_KEY")],
)
def test_one_setting_alone_offers_nothing_and_logs_what_is_missing(
    settings, tmp_path, client, logs_dir, environ, missing
):
    container = assemble(settings, EnvironmentSettings(data_dir=tmp_path), environ=environ)

    assert not container.models.has_cloud()
    logged = (logs_dir / "app.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in logged.splitlines()]
    [event] = [entry for entry in events if entry["message"] == "cloud provider not offered"]
    assert (event["provider"], event["missing"]) == ("anthropic", missing)
    assert KEY not in logged
    assert client.options is None


def test_build_container_reads_the_processs_environment(settings, tmp_path, client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    for name, value in BOTH.items():
        monkeypatch.setenv(name, value)

    try:
        container = build_container()
    finally:
        for name in ("book_rag", INFERENCE_LOGGER):
            for handler in logging.getLogger(name).handlers:
                handler.close()
            logging.getLogger(name).handlers.clear()

    assert container.models.has_cloud()
    assert client.calls == 0
