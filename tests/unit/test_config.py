from pathlib import Path

import pytest

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings
from app.errors import ConfigurationError


def test_the_project_configuration_is_valid(settings):
    assert settings.llm.context_size == 8192
    assert settings.chunking.target_size == 500
    assert "{text}" in settings.embedding_profile.query_template


def test_unknown_key_is_rejected(config_dir, edit_config):
    edit_config("retrieval.yaml", lambda c: c["retrieval"].update(stratgy="dense"))

    with pytest.raises(ConfigurationError, match="stratgy"):
        load_settings(config_dir)


def test_missing_file_is_reported(config_dir):
    (config_dir / "models.yaml").unlink()

    with pytest.raises(ConfigurationError, match="models.yaml"):
        load_settings(config_dir)


def test_invalid_yaml_is_reported(config_dir):
    (config_dir / "ingestion.yaml").write_text("chunking: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="not valid YAML"):
        load_settings(config_dir)


def test_a_key_defined_in_two_files_is_rejected(config_dir, edit_config):
    edit_config("ingestion.yaml", lambda c: c.update(llm={}))

    with pytest.raises(ConfigurationError, match="repeats keys"):
        load_settings(config_dir)


def test_overlap_must_be_smaller_than_the_chunk(config_dir, edit_config):
    edit_config("ingestion.yaml", lambda c: c["chunking"].update(overlap=500))

    with pytest.raises(ConfigurationError, match="overlap"):
        load_settings(config_dir)


def test_context_size_is_capped(config_dir, edit_config):
    edit_config("models.yaml", lambda c: c["llm"].update(context_size=32768))

    with pytest.raises(ConfigurationError, match="max_size"):
        load_settings(config_dir)


def test_max_tokens_must_leave_room_for_the_prompt(config_dir, edit_config):
    edit_config("generation.yaml", lambda c: c["generation"]["summarization"].update(max_tokens=8192))

    with pytest.raises(ConfigurationError, match="max_tokens"):
        load_settings(config_dir)


def test_embedding_model_needs_a_profile(config_dir, edit_config):
    edit_config("models.yaml", lambda c: c["embedding"].update(model="unknown-model"))

    with pytest.raises(ConfigurationError, match="embedding_profiles"):
        load_settings(config_dir)


def test_template_needs_a_placeholder(config_dir, edit_config):
    edit_config("models.yaml", lambda c: c["embedding_profiles"]["bge-m3"].update(query_template="no placeholder"))

    with pytest.raises(ConfigurationError, match="placeholder"):
        load_settings(config_dir)


def test_historical_spelling_is_on_in_the_project_configuration(settings):
    assert settings.retrieval.bm25.historical_spelling


def test_historical_spelling_must_be_set(config_dir, edit_config):
    edit_config("retrieval.yaml", lambda c: c["retrieval"]["bm25"].pop("historical_spelling"))

    with pytest.raises(ConfigurationError, match="historical_spelling"):
        load_settings(config_dir)


def test_historical_spelling_needs_stemming(config_dir, edit_config):
    edit_config("retrieval.yaml", lambda c: c["retrieval"]["bm25"].update(stemming=False, historical_spelling=True))

    with pytest.raises(ConfigurationError, match="bm25.stemming"):
        load_settings(config_dir)


def test_environment_defaults_use_the_compose_network(monkeypatch):
    for name in ("OLLAMA_BASE_URL", "CHROMA_HOST", "CHROMA_PORT"):
        monkeypatch.delenv(name, raising=False)

    environment = EnvironmentSettings()

    assert environment.ollama_base_url == "http://ollama:11434"
    assert environment.chroma_host == "chromadb"
    assert environment.chroma_port == 8000


def test_environment_variables_override_the_defaults(monkeypatch):
    monkeypatch.setenv("CHROMA_HOST", "elsewhere")
    monkeypatch.setenv("DATA_DIR", "/tmp/library")

    environment = EnvironmentSettings()

    assert environment.chroma_host == "elsewhere"
    assert environment.data_dir == Path("/tmp/library")
