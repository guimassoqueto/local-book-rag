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


def test_the_quiz_settings_load_with_their_defaults(settings):
    quiz = settings.generation.quiz
    assert (quiz.temperature, quiz.max_tokens, quiz.words_per_question) == (0.2, 1500, 300)
    assert (quiz.default_max, quiz.max_questions, quiz.attempts_per_passage) == (20, 50, 3)
    assert (quiz.check.enabled, quiz.check.model, quiz.check.reasoning, quiz.check.max_tokens) == (
        False,
        None,
        "medium",
        2000,
    )


def test_an_unknown_quiz_key_is_rejected(config_dir, edit_config):
    edit_config("generation.yaml", lambda c: c["generation"]["quiz"].update(max_questons=10))

    with pytest.raises(ConfigurationError, match="max_questons"):
        load_settings(config_dir)


def test_the_checker_model_needs_a_profile(config_dir, edit_config):
    edit_config("generation.yaml", lambda c: c["generation"]["quiz"]["check"].update(model="unknown-model"))

    with pytest.raises(ConfigurationError, match="unknown-model"):
        load_settings(config_dir)


def test_a_checker_model_with_a_profile_is_accepted(config_dir, edit_config):
    edit_config("generation.yaml", lambda c: c["generation"]["quiz"]["check"].update(model="qwen3:14b"))

    assert load_settings(config_dir).generation.quiz.check.model == "qwen3:14b"


@pytest.mark.parametrize("path", [("max_tokens",), ("check", "max_tokens")])
def test_the_quiz_limits_must_leave_room_for_the_prompt(config_dir, edit_config, path):
    def change(content):
        target = content["generation"]["quiz"]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = 8192

    edit_config("generation.yaml", change)

    with pytest.raises(ConfigurationError, match="room"):
        load_settings(config_dir)


def test_the_default_count_cannot_exceed_the_cap(config_dir, edit_config):
    edit_config("generation.yaml", lambda c: c["generation"]["quiz"].update(default_max=60))

    with pytest.raises(ConfigurationError, match="default_max"):
        load_settings(config_dir)


@pytest.mark.parametrize("reasoning", ["extreme", True])
def test_the_checker_reasoning_takes_a_level_or_nothing(config_dir, edit_config, reasoning):
    edit_config("generation.yaml", lambda c: c["generation"]["quiz"]["check"].update(reasoning=reasoning))

    with pytest.raises(ConfigurationError, match="reasoning"):
        load_settings(config_dir)


def test_the_checker_reasoning_can_be_left_to_the_profile(config_dir, edit_config):
    edit_config("generation.yaml", lambda c: c["generation"]["quiz"]["check"].update(reasoning=None))

    assert load_settings(config_dir).generation.quiz.check.reasoning is None
