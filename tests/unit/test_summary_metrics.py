import json
import re

from app.errors import ServiceUnavailableError
from app.evaluation.summary_metrics import SummaryJudge, citation_traceability
from app.evaluation.verdicts import attempt_parameters
from app.generation.base import GenerationParameters
from app.generation.summarization import ChapterSummary
from tests.fakes import FakeLLM


def summary(statements=10, unsourced=2):
    return ChapterSummary(
        book_id="b",
        book_title="T",
        chapter_number=1,
        chapter_title="One",
        summary_type="standard",
        language=None,
        text="The summary text.",
        citations=(),
        chunks_total=4,
        chunks_covered=4,
        strategy="direct",
        statements=statements,
        statements_without_source=unsourced,
        steps=1,
        incomplete_steps=0,
        verification=None,
        model="m",
        total_seconds=1.0,
    )


PARAMETERS = GenerationParameters(temperature=0.0, max_tokens=1500, seed=0)


def judge(respond):
    llm = FakeLLM(respond=lambda messages, parameters: respond(messages[-1].content))
    return SummaryJudge(llm, PARAMETERS)


def replies(prompt):
    if "Does the summary" in prompt:
        return json.dumps({"covered": "first" in prompt})
    return json.dumps({"concept_preservation": 5, "factual_consistency": 3, "coherence": 1, "completeness": 4})


def test_traceability_is_the_share_of_sourced_statements():
    assert citation_traceability(summary(10, 2)) == 0.8
    assert citation_traceability(summary(0, 0)) == 0.0


def test_coverage_is_the_share_of_key_points_the_judge_finds():
    scores = judge(replies).score(summary(), ["first point", "second point"], ["A passage."])

    assert scores.argument_coverage == 0.5


def test_ratings_are_scaled_from_0_to_1():
    scores = judge(replies).score(summary(), ["first"], ["A passage."])

    assert scores.concept_preservation == 1.0
    assert scores.factual_consistency == 0.5
    assert scores.coherence == 0.0
    assert scores.completeness == 0.75


def test_json_is_found_inside_a_chatty_reply():
    reply = 'Sure! Here it is: {"covered": true} Hope that helps.'

    scores = judge(lambda prompt: reply).score(summary(), ["first"], ["A passage."])

    assert scores.argument_coverage == 1.0


def test_a_judge_that_replies_nonsense_gives_no_score():
    scores = judge(lambda prompt: "I cannot do that.").score(summary(), ["first"], ["A passage."])

    assert scores.argument_coverage is None
    assert scores.coherence is None


def test_a_reply_without_a_verdict_is_tried_again():
    llm = FakeLLM(["Thinking too long.", '{"covered": true}'])

    scores = SummaryJudge(llm, PARAMETERS)._coverage("The summary.", ["first"])

    assert scores == 1.0
    assert [parameters for _, parameters in llm.calls] == [PARAMETERS, attempt_parameters(PARAMETERS, 1)]


def test_ratings_out_of_range_are_ignored():
    reply = json.dumps({"coherence": 9, "completeness": 0})

    scores = judge(lambda prompt: reply).score(summary(), [], ["A passage."])

    assert scores.coherence is None
    assert scores.completeness is None


def test_a_judge_that_fails_gives_no_score_and_doesnt_stop_the_run():
    def fail(prompt):
        raise ServiceUnavailableError("Ollama timed out")

    scores = judge(fail).score(summary(), ["first"], ["A passage."])

    assert scores.argument_coverage is None
    assert scores.coherence is None
    assert scores.citation_traceability == 0.8


def test_the_judge_generates_with_the_parameters_it_was_given():
    llm = FakeLLM(respond=lambda messages, parameters: replies(messages[-1].content))

    SummaryJudge(llm, PARAMETERS).score(summary(), ["first"], ["A passage."])

    assert {parameters for _, parameters in llm.calls} == {PARAMETERS}


def test_the_judge_is_never_shown_a_sample_rating_to_copy():
    llm = FakeLLM(respond=lambda messages, parameters: "{}")

    SummaryJudge(llm, PARAMETERS).score(summary(), [], ["A passage."])

    assert not re.search(r'"\w+": ?\d', llm.calls[-1][0][-1].content)


def test_passages_are_spread_over_the_chapter_when_they_dont_all_fit():
    sources = [f"source{index} " + " ".join(["word"] * 400) for index in range(100)]
    llm = FakeLLM(respond=lambda messages, parameters: "{}", context_size=8192)

    SummaryJudge(llm, PARAMETERS).score(summary(), [], sources)

    prompt = llm.calls[-1][0][-1].content
    assert "source0 " in prompt
    assert any(f"source{index} " in prompt for index in range(85, 100))
    assert llm.count_tokens(prompt) < 8192
