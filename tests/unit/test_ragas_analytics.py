"""RAGAS sends no usage analytics (.specify/bugs/ragas-analytics; constitution, Principle I)."""

import importlib
import os

import pytest

import app.evaluation
from app.config.settings import JudgeConfig
from app.evaluation.generation_metrics import RagasJudge
from app.generation.base import GenerationParameters
from tests.fakes import FakeLLM

analytics = pytest.importorskip("ragas._analytics", reason="RAGAS comes with the evaluation extra")

PARAMETERS = GenerationParameters(temperature=0.0, max_tokens=100, seed=0)


@pytest.fixture
def posted(monkeypatch):
    """What RAGAS posts, recorded instead of sent, with its switch read again rather than cached."""
    calls = []
    monkeypatch.setattr(analytics.requests, "post", lambda url, **options: calls.append(url))
    analytics.do_not_track.cache_clear()
    yield calls
    analytics.do_not_track.cache_clear()


def test_building_the_judge_posts_nothing(posted):
    config = JudgeConfig(model="m", embedding_model="e", max_tokens=100)
    judge = RagasJudge(FakeLLM(["{}"]), PARAMETERS, config, "http://ollama:11434", 1.0)

    assert judge._metrics  # builds RAGAS's embeddings, whose factory tracks its own use

    assert posted == []


def test_an_embedding_request_posts_nothing(posted):
    # What RAGAS's embeddings track on each request, which needs a server to happen for real.
    analytics.track(analytics.EmbeddingUsageEvent(user_id="a-test", provider="openai", embedding_type="modern"))

    assert posted == []


def test_a_value_left_in_the_environment_doesnt_turn_the_analytics_back_on(monkeypatch):
    monkeypatch.setenv("RAGAS_DO_NOT_TRACK", "false")

    importlib.reload(app.evaluation)

    assert os.environ["RAGAS_DO_NOT_TRACK"] == "true"
