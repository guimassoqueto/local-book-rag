import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.config.settings import JudgeConfig
from app.errors import BenchmarkJudgeError
from app.evaluation.generation_metrics import RagasJudge, abstention_is_correct, citation_accuracy, language_matches
from app.evaluation.ragas_llm import ProviderLLM
from app.evaluation.verdicts import JUDGE_ATTEMPTS, attempt_parameters
from app.generation.base import GenerationParameters
from tests.fakes import FakeLLM

PARAMETERS = GenerationParameters(temperature=0.0, max_tokens=100, seed=0)


class Verdicts(BaseModel):
    statements: list[str]


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


def test_ragas_gets_the_judges_reply_as_its_own_type():
    llm = FakeLLM(['Here it is: {"statements": ["one"]}'])

    assert ProviderLLM(llm, PARAMETERS).generate("Judge this.", Verdicts).statements == ["one"]
    assert llm.calls[0][1] == PARAMETERS


def test_ragas_can_call_the_judge_asynchronously():
    judge = ProviderLLM(FakeLLM(['{"statements": []}']), PARAMETERS)

    assert asyncio.run(judge.agenerate("Judge this.", Verdicts)).statements == []


def test_a_malformed_reply_is_tried_again():
    llm = FakeLLM(["I cannot do that.", '{"statements": ["one"]}'])

    assert ProviderLLM(llm, PARAMETERS).generate("Judge this.", Verdicts).statements == ["one"]
    assert [parameters for _, parameters in llm.calls] == [PARAMETERS, attempt_parameters(PARAMETERS, 1)]


def test_a_list_of_statements_left_open_is_read_without_a_retry():
    llm = FakeLLM(['{"statements": ["one", "two"}'])

    assert ProviderLLM(llm, PARAMETERS).generate("Judge this.", Verdicts).statements == ["one", "two"]
    assert len(llm.calls) == 1


def test_a_judge_that_never_gives_a_valid_verdict_is_an_error_for_the_metric_to_report():
    llm = FakeLLM(["I cannot do that."])

    with pytest.raises(BenchmarkJudgeError, match="Verdicts"):
        ProviderLLM(llm, PARAMETERS).generate("Judge this.", Verdicts)

    assert len(llm.calls) == JUDGE_ATTEMPTS


def test_a_prompt_the_window_cant_hold_is_refused_instead_of_silently_cut():
    llm = FakeLLM(["{}"], context_size=120)

    with pytest.raises(BenchmarkJudgeError):
        ProviderLLM(llm, PARAMETERS).generate("word " * 21, Verdicts)

    assert llm.calls == []
