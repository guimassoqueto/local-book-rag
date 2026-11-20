"""The Anthropic provider, on a fake client (specs/008-cloud-llm-providers, research.md R4, R12)."""

import anthropic
import pytest
from pydantic import SecretStr

from app.config.settings import CloudProfile, ProviderCredentials, TokenizerConfig
from app.errors import ModelFailedError
from app.generation import anthropic_provider
from app.generation.anthropic_provider import AnthropicCloud
from app.generation.base import FINISHED_BY_LENGTH, FailureReason, GenerationParameters, Message, TextDelta
from tests.fakes import (
    FakeAnthropicClient,
    FakeReply,
    WordCounter,
    anthropic_connection_error,
    anthropic_model_info,
    anthropic_timeout_error,
)
from tests.fakes import anthropic_status_error as status

KEY = "sk-ant-test-key-0123456789"
MODEL = "claude-test-1"
MESSAGES = [
    Message("system", "You answer from passages."),
    Message("system", "Cite them."),
    Message("user", "Passages: [1] Mill on liberty. Question: What does Mill defend?"),
]
PARAMETERS = GenerationParameters(temperature=0.2, max_tokens=1500, seed=7)


def make_profile(**changes):
    values = {
        "tokenizer": TokenizerConfig(kind="tiktoken", name="o200k_base"),
        "context_size": 65536,
        "reasoning": "low",
        "reasoning_tokens": 4000,
        "check_abstentions": False,
        "request_timeout_seconds": 120,
    }
    values.update(changes)
    return CloudProfile(**values)


def make_cloud(client, waits=None, **profile_changes):
    credentials = ProviderCredentials(name="anthropic", api_key=SecretStr(KEY), models=(MODEL,))
    return AnthropicCloud(
        credentials,
        make_profile(**profile_changes),
        client_factory=client.factory,
        sleep=(waits if waits is not None else []).append,
    )


def run(provider, messages=MESSAGES, parameters=PARAMETERS):
    events = list(provider.stream(messages, parameters))
    return [event.text for event in events if isinstance(event, TextDelta)], events[-1]


def failing(error, error_after=None):
    return FakeAnthropicClient([FakeReply(error=error, error_after=error_after)])


# The client


def test_the_client_takes_the_key_the_timeout_and_no_retries_of_its_own_and_calls_nothing():
    client = FakeAnthropicClient()

    make_cloud(client).model(MODEL)

    assert client.options == {"api_key": KEY, "timeout": 120, "max_retries": 0}
    assert client.calls == 0


# The request


def test_the_request_carries_the_prompt_the_limit_the_reasoning_and_nothing_else():
    client = FakeAnthropicClient()

    run(make_cloud(client).model(MODEL))

    assert client.stream_calls == [
        {
            "model": MODEL,
            "max_tokens": 1500 + 4000,
            "system": "You answer from passages.\n\nCite them.",
            "messages": [{"role": "user", "content": MESSAGES[-1].content}],
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": "low"},
        }
    ]


def test_a_profile_without_reasoning_sends_no_effort():
    client = FakeAnthropicClient()

    run(make_cloud(client, reasoning=None).model(MODEL))

    assert "output_config" not in client.stream_calls[0]


# The stream


def test_the_text_streams_and_the_generation_holds_the_reasoning_and_the_stats():
    reply = FakeReply(text="Mill defends liberty [1].", thinking="He reads the passage.", model="claude-test-1-v2")
    client = FakeAnthropicClient([reply])

    deltas, generation = run(make_cloud(client).model(MODEL))

    assert "".join(deltas).split() == ["Mill", "defends", "liberty", "[1]."]
    assert generation.text.strip() == "Mill defends liberty [1]."
    assert generation.thinking.strip() == "He reads the passage."
    assert generation.thinking_summarized is True
    stats = generation.stats
    assert (stats.model, stats.prompt_tokens, stats.completion_tokens) == ("claude-test-1-v2", 120, 30)
    assert stats.load_seconds is None and stats.prompt_seconds is None
    assert stats.time_to_first_token > 0
    assert stats.generation_seconds >= 0
    assert stats.total_seconds >= stats.time_to_first_token
    assert stats.finish_reason == "stop"


@pytest.mark.parametrize("stop_reason", ["max_tokens", "model_context_window_exceeded"])
def test_a_reply_cut_off_keeps_its_text(stop_reason):
    client = FakeAnthropicClient([FakeReply(text="A long answer", stop_reason=stop_reason)])

    _, generation = run(make_cloud(client).model(MODEL))

    assert generation.stats.finish_reason == FINISHED_BY_LENGTH
    assert generation.text.strip() == "A long answer"


def test_a_refusal_is_a_declined_request_with_its_category():
    client = FakeAnthropicClient([FakeReply(text="", stop_reason="refusal", category="cyber")])

    with pytest.raises(ModelFailedError) as failure:
        run(make_cloud(client).model(MODEL))

    assert failure.value.reason == FailureReason.DECLINED
    assert str(failure.value) == f"{MODEL} (Anthropic) failed: it declined the request (cyber)."


# Failures


@pytest.mark.parametrize(
    ("error", "reason", "words"),
    [
        (status(anthropic.AuthenticationError, 401), FailureReason.KEY_REFUSED, "it refused the API key"),
        (status(anthropic.APIStatusError, 402), FailureReason.KEY_REFUSED, "it refused the API key"),
        (status(anthropic.PermissionDeniedError, 403), FailureReason.KEY_REFUSED, "it refused the API key"),
        (status(anthropic.NotFoundError, 404), FailureReason.UNKNOWN_MODEL, "it doesn't know this model"),
        (status(anthropic.RateLimitError, 429), FailureReason.RATE_LIMITED, "it limited the rate"),
        (anthropic_timeout_error(), FailureReason.TIMED_OUT, "it sent nothing for 120 s"),
        (anthropic_connection_error(), FailureReason.UNREACHABLE, "it can't be reached"),
        (status(anthropic.InternalServerError, 529), FailureReason.OUTAGE, "it is down or overloaded (529)"),
        (
            status(anthropic.BadRequestError, 400, error_type="invalid_request_error"),
            FailureReason.REJECTED,
            "it rejected the request: invalid_request_error",
        ),
        (
            status(anthropic.APIStatusError, 200, error_type="overloaded_error"),
            FailureReason.OUTAGE,
            "it is down or overloaded (overloaded_error)",
        ),
    ],
)
def test_each_failure_has_its_reason_and_words_and_never_the_key(error, reason, words):
    with pytest.raises(ModelFailedError) as failure:
        run(make_cloud(failing(error)).model(MODEL))

    assert failure.value.reason == reason
    assert failure.value.model == MODEL and failure.value.provider == "anthropic"
    assert str(failure.value).startswith(f"{MODEL} (Anthropic) failed: {words}")
    assert KEY not in str(failure.value) and KEY not in failure.value.detail


@pytest.mark.parametrize(
    "error",
    [
        status(anthropic.RateLimitError, 429),
        status(anthropic.InternalServerError, 529),
        anthropic_connection_error(),
    ],
)
def test_a_rate_limit_an_overload_or_a_lost_connection_is_tried_twice_more(error):
    client, waits = failing(error), []

    with pytest.raises(ModelFailedError):
        run(make_cloud(client, waits).model(MODEL))

    assert len(client.stream_calls) == 3
    assert waits == [2.0, 6.0]


def test_a_retry_that_succeeds_answers():
    client = FakeAnthropicClient(
        [FakeReply(error=status(anthropic.RateLimitError, 429)), FakeReply(text="Late but here")]
    )
    waits = []

    _, generation = run(make_cloud(client, waits).model(MODEL))

    assert generation.text.strip() == "Late but here"
    assert waits == [2.0]


@pytest.mark.parametrize(("retry_after", "wait"), [("3", 3.0), ("30", 2.0)])
def test_a_short_retry_after_is_waited_and_a_long_one_is_not(retry_after, wait):
    error = status(anthropic.RateLimitError, 429, headers={"retry-after": retry_after})
    client = FakeAnthropicClient([FakeReply(error=error), FakeReply()])
    waits = []

    run(make_cloud(client, waits).model(MODEL))

    assert waits == [wait]


def test_a_timeout_is_never_tried_again():
    client, waits = failing(anthropic_timeout_error()), []

    with pytest.raises(ModelFailedError):
        run(make_cloud(client, waits).model(MODEL))

    assert len(client.stream_calls) == 1
    assert waits == []


def test_nothing_is_tried_again_once_a_delta_has_arrived():
    client = failing(status(anthropic.RateLimitError, 429), error_after=1)
    waits, deltas = [], []

    with pytest.raises(ModelFailedError) as failure:
        for event in make_cloud(client, waits).model(MODEL).stream(MESSAGES, PARAMETERS):
            deltas.append(event)

    assert failure.value.reason == FailureReason.RATE_LIMITED
    assert len(deltas) == 1
    assert len(client.stream_calls) == 1 and waits == []


# The rest of the interface


def test_the_window_sets_the_reasoning_aside_and_the_tokens_come_from_the_profiles_tokenizer(monkeypatch):
    monkeypatch.setattr(anthropic_provider, "create_token_counter", lambda config: WordCounter())
    provider = make_cloud(FakeAnthropicClient(), check_abstentions=True).model(MODEL)

    assert provider.context_size() == 65536 - 4000
    assert provider.count_tokens("three words here") == 3
    assert provider.provider == "anthropic"
    assert provider.model == MODEL
    assert provider.check_abstentions is True


def test_generate_returns_the_streams_generation():
    generation = make_cloud(FakeAnthropicClient([FakeReply(text="Whole")])).model(MODEL).generate(MESSAGES, PARAMETERS)

    assert generation.text.strip() == "Whole"


# The check (research.md R12)


def test_the_check_reads_each_model_once_and_runs_no_inference():
    client = FakeAnthropicClient(models={"claude-a": anthropic_model_info("claude-a")})

    rows = make_cloud(client).check(["claude-a", "claude-b"])

    assert client.retrieve_calls == ["claude-a", "claude-b"] and client.stream_calls == []
    assert [(row.name, row.ok) for row in rows] == [("anthropic claude-a", True), ("anthropic claude-b", False)]
    assert "Display claude-a" in rows[0].detail and "1000000" in rows[0].detail
    assert rows[1].detail == "Anthropic doesn't know this model"


def test_a_refused_key_is_one_failing_row_and_ends_the_check():
    client = FakeAnthropicClient(models={"claude-a": status(anthropic.AuthenticationError, 401)})

    rows = make_cloud(client).check(["claude-a", "claude-b"])

    assert [(row.name, row.ok, row.detail) for row in rows] == [("anthropic", False, "Anthropic refused the API key")]
    assert client.retrieve_calls == ["claude-a"]


@pytest.mark.parametrize(
    ("info", "words"),
    [
        (anthropic_model_info("claude-a", efforts=("medium", "high")), "effort `low`"),
        (anthropic_model_info("claude-a", adaptive=False), "adaptive"),
        (anthropic_model_info("claude-a", window=32768), "32768"),
    ],
)
def test_a_model_the_profile_cant_serve_fails_its_row_saying_why(info, words):
    rows = make_cloud(FakeAnthropicClient(models={"claude-a": info})).check(["claude-a"])

    assert not rows[0].ok
    assert words in rows[0].detail
