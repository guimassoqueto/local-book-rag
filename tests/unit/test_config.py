from pathlib import Path

import pytest

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings, read_provider_credentials
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


def test_the_abstention_check_takes_only_a_boolean(config_dir, edit_config):
    edit_config("models.yaml", lambda c: c["llm_profiles"]["gpt-oss:20b"].update(check_abstentions="sometimes"))

    with pytest.raises(ConfigurationError, match="check_abstentions"):
        load_settings(config_dir)


def test_the_abstention_check_is_off_unless_a_profile_asks(config_dir, edit_config):
    edit_config("models.yaml", lambda c: c["llm_profiles"]["gpt-oss:20b"].pop("check_abstentions", None))

    assert load_settings(config_dir).llm_profiles["gpt-oss:20b"].check_abstentions is False


def test_template_needs_a_placeholder(config_dir, edit_config):
    edit_config("models.yaml", lambda c: c["embedding_profiles"]["bge-m3"].update(query_template="no placeholder"))

    with pytest.raises(ConfigurationError, match="placeholder"):
        load_settings(config_dir)


def test_historical_spelling_ships_switched_off(settings):
    # The benchmark showed no gain beyond noise (specs/001-historical-spelling, SC-001).
    assert not settings.retrieval.bm25.historical_spelling


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


def test_an_unknown_section_under_generation_is_rejected(config_dir, edit_config):
    edit_config("generation.yaml", lambda c: c["generation"].update(retired={}))

    with pytest.raises(ConfigurationError, match="generation.retired"):
        load_settings(config_dir)


def test_the_shipped_generation_settings_hold_the_tasks_the_context_and_the_languages(settings):
    assert set(settings.generation.model_dump()) == {
        "question_answering",
        "summarization",
        "context",
        "response_languages",
    }


# Settings removed when books became Markdown only (specs/005-markdown-only, FR-008, FR-014): any left in a
# configuration stops the app, naming it, as any unknown key does.


@pytest.mark.parametrize(
    ("change", "key"),
    [
        (lambda c: c.update(pdf={"extractor": "pymupdf"}), "pdf"),
        (lambda c: c.update(normalization={"remove_repeated_margins": True}), "normalization"),
        (lambda c: c["chunking"]["preserve"].update(page_numbers=True), "page_numbers"),
    ],
    ids=["pdf", "normalization", "page_numbers"],
)
def test_a_removed_setting_stops_the_app_naming_it(config_dir, edit_config, change, key):
    edit_config("ingestion.yaml", change)

    with pytest.raises(ConfigurationError, match=key):
        load_settings(config_dir)


def test_the_shipped_ingestion_settings_hold_only_languages_and_chunking(settings):
    assert not hasattr(settings, "pdf") and not hasattr(settings, "normalization")
    assert set(settings.chunking.preserve.model_dump()) == {"chapters", "sections", "paragraphs"}


# Cloud providers (specs/008-cloud-llm-providers): one profile per provider, and two settings in the
# environment, read apart from the rest (research.md R1, R2).

ANTHROPIC_PROFILE = {
    "tokenizer": {"kind": "tiktoken", "name": "o200k_base"},
    "context_size": 65536,
    "reasoning": "low",
    "reasoning_tokens": 4000,
    "check_abstentions": False,
    "request_timeout_seconds": 120,
}


def with_profile(**changes):
    """Anthropic's profile, with some fields changed or, given None, removed."""
    profile = {**ANTHROPIC_PROFILE, **changes}
    return {key: value for key, value in profile.items() if value is not None}


def test_the_shipped_configuration_holds_anthropics_profile(settings):
    profile = settings.cloud_profiles["anthropic"]

    assert profile.tokenizer.kind == "tiktoken" and profile.tokenizer.name == "o200k_base"
    assert profile.context_size == 65536
    assert profile.reasoning == "low"
    assert profile.reasoning_tokens == 4000
    assert profile.check_abstentions is False
    assert profile.request_timeout_seconds == 120


def test_without_cloud_profiles_no_provider_has_one(config_dir, edit_config):
    edit_config("models.yaml", lambda c: c.pop("cloud_profiles", None))

    assert load_settings(config_dir).cloud_profiles == {}


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"temperature": 0.2}, "temperature"),
        ({"reasoning": "extreme"}, "reasoning"),
        ({"reasoning_tokens": -1}, "reasoning_tokens"),
        ({"context_size": 0}, "context_size"),
        ({"request_timeout_seconds": 0}, "request_timeout_seconds"),
    ],
)
def test_a_profile_out_of_bounds_stops_the_app_naming_the_field(config_dir, edit_config, change, field):
    edit_config("models.yaml", lambda c: c.update(cloud_profiles={"anthropic": with_profile(**change)}))

    with pytest.raises(ConfigurationError, match=field):
        load_settings(config_dir)


@pytest.mark.parametrize("reasoning", ["low", "medium", "high", "xhigh", "max", None])
def test_a_profile_takes_each_effort_or_none(config_dir, edit_config, reasoning):
    profile = {**ANTHROPIC_PROFILE, "reasoning": reasoning}
    edit_config("models.yaml", lambda c: c.update(cloud_profiles={"anthropic": profile}))

    assert load_settings(config_dir).cloud_profiles["anthropic"].reasoning == reasoning


def test_a_profile_must_leave_room_for_the_prompt(config_dir, edit_config):
    profile = with_profile(context_size=6000)  # the summaries' 3000 plus 4000 for reasoning don't fit
    edit_config("models.yaml", lambda c: c.update(cloud_profiles={"anthropic": profile}))

    with pytest.raises(
        ConfigurationError,
        match="max_tokens and reasoning_tokens leave no room for the prompt in cloud_profiles.anthropic.context_size",
    ):
        load_settings(config_dir)


def credentials(**environ):
    return read_provider_credentials("anthropic", environ)


def test_both_settings_are_read_by_the_providers_name():
    read = credentials(ANTHROPIC_API_KEY="sk-ant-test", ANTHROPIC_MODELS="claude-a,claude-b")

    assert read.name == "anthropic"
    assert read.api_key.get_secret_value() == "sk-ant-test"
    assert read.models == ("claude-a", "claude-b")


def test_settings_left_out_or_empty_read_as_missing():
    assert credentials().api_key is None and credentials().models == ()
    assert credentials(ANTHROPIC_API_KEY="", ANTHROPIC_MODELS=" , ").api_key is None
    assert credentials(ANTHROPIC_API_KEY="", ANTHROPIC_MODELS=" , ").models == ()
    assert credentials(ANTHROPIC_MODELS="claude-a").api_key is None


def test_model_names_are_stripped_kept_once_in_order_and_compared_as_written():
    read = credentials(ANTHROPIC_MODELS=" claude-b , claude-a,,claude-b, Claude-A ")

    assert read.models == ("claude-b", "claude-a", "Claude-A")


def test_the_keys_representation_hides_it():
    read = credentials(ANTHROPIC_API_KEY="sk-ant-secret-value")

    assert "sk-ant-secret-value" not in repr(read)
    assert "sk-ant-secret-value" not in str(read)
