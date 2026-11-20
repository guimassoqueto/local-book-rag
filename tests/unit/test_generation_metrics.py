import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config.settings import JudgeConfig
from app.evaluation.generation_metrics import RagasJudge, abstention_is_correct, citation_accuracy, language_matches
from app.generation.base import GenerationParameters
from tests.fakes import FakeLLM

PARAMETERS = GenerationParameters(temperature=0.0, max_tokens=100, seed=0)


class FakeMetric:
    def __init__(self, value=None, failure=None):
        self.value = value
        self.failure = failure

    async def ascore(self, **inputs):
        if self.failure:
            raise self.failure
        return SimpleNamespace(value=self.value)


def judge_with(**metrics):
    judge = RagasJudge(
        FakeLLM(["{}"]), PARAMETERS, JudgeConfig(model="m", embedding_model="e", max_tokens=100), "", 1.0
    )
    judge.__dict__["_metrics"] = metrics  # replaces the cached property, which would load RAGAS
    return judge


def test_citations_that_reach_the_evidence_count():
    assert citation_accuracy(["a", "x"], [{"a"}, {"b"}]) == 1.0


def test_citations_that_miss_the_evidence_dont():
    assert citation_accuracy(["x"], [{"a"}]) == 0.0
    assert citation_accuracy([], [{"a"}]) == 0.0


@pytest.mark.parametrize(
    ("text", "language", "expected"),
    [
        ("The harm principle says that power may only be used to prevent harm to others.", "en", True),
        ("O princípio do dano diz que o poder só pode ser usado para evitar danos a terceiros.", "pt", True),
        ("The harm principle says that power may only be used to prevent harm to others.", "pt", False),
        ("Sim.", "en", True),
        ("Quincas Borba diz: “Ao vencedor, as batatas” [1]. A frase resume o Humanitismo.", "pt", True),
    ],
)
def test_the_answer_language_is_checked(text, language, expected):
    assert language_matches(text, language) is expected


@pytest.mark.parametrize(
    ("answerable", "abstained", "expected"),
    [(True, False, True), (False, True, True), (True, True, False), (False, False, False)],
)
def test_a_model_should_abstain_exactly_when_it_cant_answer(answerable, abstained, expected):
    assert abstention_is_correct(answerable, abstained) is expected


def test_the_judges_scores_are_passed_on():
    judge = judge_with(faithfulness=FakeMetric(0.5), correctness=FakeMetric(0.25), relevance=FakeMetric(1.0))

    scores = judge.score("Question?", "An answer.", ["A passage."], "A reference.")

    assert (scores.faithfulness, scores.answer_correctness, scores.answer_relevance) == (0.5, 0.25, 1.0)


def test_a_metric_that_fails_or_finds_nothing_to_score_gives_no_value():
    judge = judge_with(
        faithfulness=FakeMetric(float("nan")),
        correctness=FakeMetric(failure=ValueError("malformed")),
        relevance=FakeMetric(1.0),
    )

    scores = judge.score("Question?", "An answer.", ["A passage."], "A reference.")

    assert scores.faithfulness is None
    assert scores.answer_correctness is None
    assert scores.answer_relevance == 1.0


# The key stays with OpenAI's provider (specs/009-openai-provider, FR-020, SC-008)


def test_the_judges_client_reaches_ollama_with_its_own_key_whatever_the_environment_says(monkeypatch):
    import openai

    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-be-read")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    built = []
    real = openai.AsyncOpenAI

    def recording(**options):
        built.append(options)
        return real(**options)

    monkeypatch.setattr(openai, "AsyncOpenAI", recording)
    config = JudgeConfig(model="m", embedding_model="e", max_tokens=100)
    judge = RagasJudge(FakeLLM(["{}"]), PARAMETERS, config, "http://ollama:11434", 1.0)

    assert judge._metrics  # building the metrics builds the judges' client with them

    assert built == [{"base_url": "http://ollama:11434/v1", "api_key": "local", "timeout": 1.0}]


def openai_clients_built_in(source):
    """Each construction of a client of OpenAI's library in a module's source, with its arguments."""
    calls = []
    for match in re.finditer(r"\b(?:Async)?OpenAI\)?\(", source):
        opening, depth = match.end() - 1, 0
        for position in range(opening, len(source)):
            depth += {"(": 1, ")": -1}.get(source[position], 0)
            if depth == 0:
                calls.append(source[opening : position + 1])
                break
    return calls


def test_every_client_of_openais_library_in_the_app_is_given_its_key_and_its_address():
    application = Path(__file__).resolve().parents[2] / "app"

    calls = [
        (str(path.relative_to(application)), call)
        for path in application.rglob("*.py")
        for call in openai_clients_built_in(path.read_text(encoding="utf-8"))
    ]

    assert {path for path, _ in calls} == {"evaluation/generation_metrics.py", "generation/openai_provider.py"}
    assert all("api_key=" in call and "base_url=" in call for _, call in calls)
