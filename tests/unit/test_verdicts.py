from app.evaluation.verdicts import attempt_parameters, read_verdict
from app.generation.base import GenerationParameters

PARAMETERS = GenerationParameters(temperature=0.0, max_tokens=100, seed=0)


def test_the_first_attempt_is_made_as_configured():
    assert attempt_parameters(PARAMETERS, 0) == PARAMETERS


def test_a_retry_samples_since_greedy_decoding_would_repeat_the_reply():
    retry = attempt_parameters(PARAMETERS, 1)

    assert retry.temperature > 0
    assert retry.seed == 1


def test_a_list_left_open_when_its_object_closes_is_closed():
    assert read_verdict('{"statements": ["one", "two"}') == {"statements": ["one", "two"]}


def test_a_list_of_objects_left_open_is_closed_too():
    reply = '{"statements": [{"statement": "one", "verdict": 1}}'

    assert read_verdict(reply) == {"statements": [{"statement": "one", "verdict": 1}]}


def test_brackets_inside_strings_are_not_repaired():
    reply = '{"statements": ["t[0] is the first element", "a dict is written {}"}'

    assert read_verdict(reply) == {"statements": ["t[0] is the first element", "a dict is written {}"]}


def test_a_reply_cut_off_is_not_completed_into_a_shorter_verdict():
    assert read_verdict('{"statements": ["a dict is written {}", "the second statem') == {}
