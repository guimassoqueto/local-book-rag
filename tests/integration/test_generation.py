"""Runs the configured LLM for real."""

import os

import pytest

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings
from app.generation.base import GenerationParameters, Message
from app.generation.factory import create_llm_provider
from app.utils.ollama_runtime import OllamaRuntime

pytestmark = pytest.mark.integration


@pytest.fixture
def settings():
    return load_settings(EnvironmentSettings().config_dir)


@pytest.fixture
def llm(settings, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    runtime = OllamaRuntime(EnvironmentSettings().ollama_base_url, settings.ollama.request_timeout_seconds)
    return create_llm_provider(settings, runtime)


def test_the_token_estimate_matches_the_runtime_count(llm):
    text = "Opportunity cost is the value of the best alternative given up when making a choice. " * 20
    parameters = GenerationParameters(temperature=0, max_tokens=5)

    baseline = llm.generate([Message("user", "x")], parameters).stats.prompt_tokens
    measured = llm.generate([Message("user", text)], parameters).stats.prompt_tokens

    assert measured - baseline == pytest.approx(llm.count_tokens(text) - llm.count_tokens("x"), abs=2)


def test_a_reply_reports_its_statistics(llm):
    generation = llm.generate(
        [Message("user", "Reply with one word: hello")], GenerationParameters(temperature=0, max_tokens=200)
    )

    assert generation.text.strip()
    assert generation.stats.prompt_tokens > 0
    assert generation.stats.completion_tokens > 0
    assert generation.stats.tokens_per_second > 0
    assert generation.stats.time_to_first_token > 0
    assert generation.stats.finish_reason == "stop"
