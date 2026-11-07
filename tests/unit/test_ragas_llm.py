import asyncio

import pytest
from pydantic import BaseModel

from app.config.settings import JudgeConfig
from app.errors import BenchmarkJudgeError
from app.evaluation.generation_metrics import RagasJudge
from app.evaluation.verdicts import JUDGE_ATTEMPTS, attempt_parameters
from app.generation.base import GenerationParameters
from tests.fakes import FakeLLM

pytest.importorskip("ragas", reason="RAGAS comes with the evaluation extra")
from app.evaluation.ragas_llm import ProviderLLM  # noqa: E402

PARAMETERS = GenerationParameters(temperature=0.0, max_tokens=100, seed=0)


class Verdicts(BaseModel):
    statements: list[str]


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


def test_relevance_asks_the_greedy_judge_for_one_question_not_the_same_one_three_times():
    judge = RagasJudge(
        FakeLLM(["{}"]), PARAMETERS, JudgeConfig(model="m", embedding_model="e", max_tokens=100), "", 1.0
    )

    assert judge._metrics["relevance"].strictness == 1
