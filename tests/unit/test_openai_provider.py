"""The OpenAI provider, on a fake client (specs/009-openai-provider, research.md R1 to R4, R10)."""

import logging

import openai
import pytest
from pydantic import SecretStr

from app.config.settings import CloudProfile, ProviderCredentials, TokenizerConfig
from app.errors import ModelFailedError
from app.generation import openai_provider
from app.generation.base import FINISHED_BY_LENGTH, FailureReason, GenerationParameters, Message, TextDelta
from app.generation.cloud import ProviderCheck
from app.generation.openai_provider import OpenAICloud
from tests.fakes import (
    FakeOpenAIClient,
    FakeResponse,
    WordCounter,
    openai_connection_error,
    openai_model,
    openai_stream_error,
    openai_timeout_error,
)
from tests.fakes import openai_status_error as status

KEY = "sk-proj-test-key-0123456789"
MODEL = "gpt-test-1"
MESSAGES = [
    Message("system", "You answer from passages."),
    Message("system", "Cite them."),
    Message("user", "Passages: [1] Mill on liberty. Question: What does Mill defend?"),
]
PARAMETERS = GenerationParameters(temperature=0.2, max_tokens=1500, seed=7)
VERIFIED_ONLY = "OpenAI streams this model only to a verified organization"
CREDIT_CODES = [
    "insufficient_quota",
    "credit_balance_exhausted",
    "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
]


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
    credentials = ProviderCredentials(name="openai", api_key=SecretStr(KEY), models=(MODEL,))
    return OpenAICloud(
        credentials,
        make_profile(**profile_changes),
        client_factory=client.factory,
        sleep=(waits if waits is not None else []).append,
    )


def run(provider, messages=MESSAGES, parameters=PARAMETERS):
    events = list(provider.stream(messages, parameters))
    return [event.text for event in events if isinstance(event, TextDelta)], events[-1]


def failing(error, error_after=None):
    return FakeOpenAIClient([FakeResponse(error=error, error_after=error_after)])


def failed(code):
    """A response that ends failed, with its error's code, before any text."""
    return FakeResponse(text="", status="failed", error_code=code)


def failure_of(client, waits=None):
    with pytest.raises(ModelFailedError) as failure:
        run(make_cloud(client, waits).model(MODEL))
    return failure.value


@pytest.fixture
def logged(monkeypatch):
    """Every event the provider logs, as (logger, message, fields): whatever handlers other tests
    left on the app's loggers."""
    events = []

    def record(logger, message, level=logging.INFO, **fields):
        events.append((logger.name, message, fields))

    monkeypatch.setattr(openai_provider, "log_event", record)
    return events


# The client


def test_the_client_takes_the_key_openais_address_the_timeout_and_no_retries_and_calls_nothing(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://elsewhere.example/v1")
    client = FakeOpenAIClient()

    make_cloud(client).model(MODEL)

    assert client.options == {
        "api_key": KEY,
        "base_url": "https://api.openai.com/v1",
        "timeout": 120,
        "max_retries": 0,
    }
    assert client.calls == 0


def test_the_kind_is_named_openai_and_takes_every_effort_but_none_at_all():
    assert (OpenAICloud.name, OpenAICloud.label) == ("openai", "OpenAI")
    assert OpenAICloud.efforts == frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})


# The request (research.md R2)


def test_the_request_carries_the_prompt_as_written_the_limit_the_reasoning_and_nothing_else():
    client = FakeOpenAIClient()

    run(make_cloud(client).model(MODEL))

    assert client.create_calls == [
        {
            "model": MODEL,
            "input": [{"role": message.role, "content": message.content} for message in MESSAGES],
            "max_output_tokens": 1500 + 4000,
            "reasoning": {"effort": "low", "summary": "auto"},
            "store": False,
            "truncation": "disabled",
            "stream": True,
        }
    ]


# The stream (research.md R3)


def test_the_text_streams_and_the_generation_holds_the_reasoning_summary_and_the_stats():
    reply = FakeResponse(text="Mill defends liberty [1].", reasoning="He reads the passage.", model="gpt-test-1-2026")
    client = FakeOpenAIClient([reply])

    deltas, generation = run(make_cloud(client).model(MODEL))

    assert "".join(deltas).split() == ["Mill", "defends", "liberty", "[1]."]
    assert generation.text.strip() == "Mill defends liberty [1]."
    assert generation.thinking.strip() == "He reads the passage."
    assert generation.thinking_summarized is True
    stats = generation.stats
    assert (stats.model, stats.prompt_tokens, stats.completion_tokens) == ("gpt-test-1-2026", 120, 30)
    assert stats.load_seconds is None and stats.prompt_seconds is None
    assert stats.time_to_first_token > 0
    assert stats.generation_seconds >= 0
    assert stats.total_seconds >= stats.time_to_first_token
    assert stats.finish_reason == "stop"


def test_the_encrypted_reasoning_is_dropped():
    client = FakeOpenAIClient([FakeResponse(reasoning="A summary.")])

    _, generation = run(make_cloud(client).model(MODEL))

    assert "ENCRYPTED" not in generation.thinking and "ENCRYPTED" not in generation.text


def test_a_reply_without_reasoning_has_none():
    _, generation = run(make_cloud(FakeOpenAIClient([FakeResponse(reasoning="")])).model(MODEL))

    assert generation.thinking == ""


@pytest.mark.parametrize("text", ["A long answer", ""])
def test_a_reply_cut_off_by_its_limit_ends_by_length_with_or_without_text(text):
    reply = FakeResponse(text=text, status="incomplete", incomplete_reason="max_output_tokens")

    _, generation = run(make_cloud(FakeOpenAIClient([reply])).model(MODEL))

    assert generation.stats.finish_reason == FINISHED_BY_LENGTH
    assert generation.text.strip() == text


def test_the_finished_generation_is_logged_without_the_text_or_the_reasoning(logged):
    client = FakeOpenAIClient([FakeResponse(text="Secret words [1].", reasoning="Private thoughts.")])

    run(make_cloud(client).model(MODEL))

    [(logger, _, fields)] = [event for event in logged if event[1] == "generation finished"]
    assert logger == "book_rag.inference"
    assert fields["model"] == MODEL and fields["prompt_tokens"] == 120 and fields["finish_reason"] == "stop"
    assert "Secret" not in str(logged) and "Private" not in str(logged) and KEY not in str(logged)


def test_generate_returns_the_streams_generation():
    client = FakeOpenAIClient([FakeResponse(text="Whole answer [1].")])

    generation = make_cloud(client).model(MODEL).generate(MESSAGES, PARAMETERS)

    assert generation.text.strip() == "Whole answer [1]."


def test_the_window_sets_the_reasoning_aside_and_the_tokens_come_from_the_profiles_tokenizer(monkeypatch):
    monkeypatch.setattr(openai_provider, "create_token_counter", lambda config: WordCounter())
    provider = make_cloud(FakeOpenAIClient()).model(MODEL)

    assert provider.context_size() == 65536 - 4000
    assert provider.count_tokens("three words here") == 3
    assert provider.provider == "openai" and provider.model == MODEL
    assert provider.check_abstentions is False
    assert make_cloud(FakeOpenAIClient(), check_abstentions=True).model(MODEL).check_abstentions is True


# Failures (research.md R4)


@pytest.mark.parametrize(
    ("error", "reason", "words"),
    [
        (openai_timeout_error(), FailureReason.TIMED_OUT, "it sent nothing for 120 s"),
        (openai_connection_error(), FailureReason.UNREACHABLE, "it can't be reached"),
        (
            status(openai.AuthenticationError, 401, code="invalid_api_key"),
            FailureReason.KEY_REFUSED,
            "it refused the API key",
        ),
        (
            status(openai.PermissionDeniedError, 403, code="model_not_allowed"),
            FailureReason.REJECTED,
            "it rejected the request: model_not_allowed",
        ),
        (
            status(openai.PermissionDeniedError, 403, code="unsupported_country_region_territory"),
            FailureReason.REJECTED,
            "it rejected the request: unsupported_country_region_territory",
        ),
        (
            status(openai.NotFoundError, 404, code="model_not_found"),
            FailureReason.UNKNOWN_MODEL,
            "it doesn't know this model",
        ),
        (
            status(openai.RateLimitError, 429, code="rate_limit_exceeded"),
            FailureReason.RATE_LIMITED,
            "it limited the rate",
        ),
        (
            status(openai.InternalServerError, 503, code="server_is_overloaded"),
            FailureReason.OUTAGE,
            "it is down or overloaded (server_is_overloaded)",
        ),
        (status(openai.InternalServerError, 500), FailureReason.OUTAGE, "it is down or overloaded (500)"),
        (
            status(openai.BadRequestError, 400, code="unsupported_value", param="reasoning.effort"),
            FailureReason.REJECTED,
            "it rejected the request: unsupported_value (reasoning.effort)",
        ),
        (openai_stream_error("server_error"), FailureReason.OUTAGE, "it is down or overloaded (server_error)"),
        (openai_stream_error("invalid_prompt"), FailureReason.DECLINED, "it declined the request (invalid_prompt)"),
    ],
)
def test_each_failure_has_its_reason_and_words_and_never_the_key(error, reason, words):
    failure = failure_of(failing(error))

    assert failure.reason == reason
    assert str(failure) == f"{MODEL} (OpenAI) failed: {words}."
    assert KEY not in str(failure) and "A message." not in str(failure)
    assert failure.__cause__ is None and failure.__suppress_context__


@pytest.mark.parametrize("code", CREDIT_CODES)
def test_an_account_that_cant_pay_is_out_of_credit_and_tried_once(code):
    client, waits = failing(status(openai.RateLimitError, 429, code=code)), []

    failure = failure_of(client, waits)

    assert failure.reason == FailureReason.OUT_OF_CREDIT
    assert str(failure) == (
        f"{MODEL} (OpenAI) failed: its account is out of credit or over a spending or usage limit ({code})."
    )
    assert len(client.create_calls) == 1 and waits == []


def test_a_refused_keys_message_is_never_shown():
    message = "Incorrect API key provided: sk-proj-****6789. You can find your API key at platform.openai.com."
    error = status(openai.AuthenticationError, 401, code="invalid_api_key", message=message)

    failure = failure_of(failing(error))

    assert "6789" not in str(failure) and "Incorrect" not in failure.detail


@pytest.mark.parametrize(
    ("reply", "reason", "words"),
    [
        (failed("server_error"), FailureReason.OUTAGE, "it is down or overloaded (server_error)"),
        (failed("rate_limit_exceeded"), FailureReason.RATE_LIMITED, "it limited the rate"),
        (failed("invalid_prompt"), FailureReason.DECLINED, "it declined the request (invalid_prompt)"),
        (failed("bio_policy"), FailureReason.DECLINED, "it declined the request (bio_policy)"),
        (
            failed("data_residency_mismatch"),
            FailureReason.REJECTED,
            "it rejected the request: data_residency_mismatch",
        ),
        (
            FakeResponse(text="", status="incomplete", incomplete_reason="content_filter"),
            FailureReason.DECLINED,
            "it declined the request (content_filter)",
        ),
        (FakeResponse(text="", refusal="I can't help with that."), FailureReason.DECLINED, "it declined the request"),
        (FakeResponse(terminal=False), FailureReason.UNREACHABLE, "it can't be reached"),
    ],
)
def test_a_failed_declined_or_unfinished_response_has_its_reason(reply, reason, words):
    failure = failure_of(FakeOpenAIClient([reply]), waits=[])

    assert failure.reason == reason
    assert str(failure) == f"{MODEL} (OpenAI) failed: {words}."


def test_a_refusal_after_text_has_streamed_is_still_a_decline():
    client = FakeOpenAIClient([FakeResponse(text="Mill says", refusal="Actually, I can't.")])
    deltas = []

    with pytest.raises(ModelFailedError) as failure:
        for event in make_cloud(client).model(MODEL).stream(MESSAGES, PARAMETERS):
            deltas.append(event)

    assert failure.value.reason == FailureReason.DECLINED
    assert [delta.text.strip() for delta in deltas] == ["Mill", "says"]


@pytest.mark.parametrize(
    "error",
    [
        status(openai.BadRequestError, 400, code="unsupported_value", param="stream"),
        status(
            openai.BadRequestError,
            400,
            code="invalid_request_error",
            message="Your organization must be verified to stream this model. Please go to the settings page.",
        ),
        status(
            openai.PermissionDeniedError, 403, message="Organization verification is required to stream this model."
        ),
    ],
)
def test_a_stream_refused_to_an_unverified_organization_says_so_and_is_never_asked_without_streaming(error):
    client, waits = failing(error), []

    failure = failure_of(client, waits)

    assert failure.reason == FailureReason.REJECTED
    assert str(failure) == f"{MODEL} (OpenAI) failed: it rejected the request: {VERIFIED_ONLY}."
    assert len(client.create_calls) == 1 and client.create_calls[0]["stream"] is True
    assert waits == []


# Retries


@pytest.mark.parametrize(
    "error",
    [
        status(openai.RateLimitError, 429, code="rate_limit_exceeded"),
        status(openai.InternalServerError, 503, code="server_is_overloaded"),
        openai_connection_error(),
    ],
)
def test_a_rate_limit_an_overload_or_a_lost_connection_is_tried_twice_more(error):
    client, waits = failing(error), []

    failure_of(client, waits)

    assert len(client.create_calls) == 3
    assert waits == [2.0, 6.0]


def test_a_failed_response_from_an_outage_is_tried_again_before_any_text():
    client = FakeOpenAIClient(
        [FakeResponse(text="", status="failed", error_code="server_error"), FakeResponse(text="Recovered [1].")]
    )
    waits = []

    _, generation = run(make_cloud(client, waits).model(MODEL))

    assert generation.text.strip() == "Recovered [1]."
    assert waits == [2.0]


@pytest.mark.parametrize(("retry_after", "wait"), [("1", 1.0), ("30", 2.0)])
def test_a_short_retry_after_is_waited_and_a_long_one_is_not(retry_after, wait):
    limited = status(openai.RateLimitError, 429, code="rate_limit_exceeded", headers={"retry-after": retry_after})
    client = FakeOpenAIClient([FakeResponse(error=limited), FakeResponse()])
    waits = []

    run(make_cloud(client, waits).model(MODEL))

    assert waits == [wait]


def test_a_timeout_is_never_tried_again():
    client, waits = failing(openai_timeout_error()), []

    failure_of(client, waits)

    assert len(client.create_calls) == 1 and waits == []


def test_nothing_is_tried_again_once_text_has_arrived():
    client = failing(status(openai.RateLimitError, 429, code="rate_limit_exceeded"), error_after=1)
    waits = []

    failure_of(client, waits)

    assert len(client.create_calls) == 1 and waits == []


# The reasoning summary refused (FR-015)


def summary_refused():
    return status(openai.BadRequestError, 400, code="unsupported_parameter", param="reasoning.summary")


def test_a_refused_summary_is_asked_once_more_without_it_and_the_answer_stands(logged):
    answer = FakeResponse(text="The answer [1].", reasoning="")
    client = FakeOpenAIClient([FakeResponse(error=summary_refused()), answer])

    _, generation = run(make_cloud(client, waits=[]).model(MODEL))

    first, second = client.create_calls
    assert first["reasoning"] == {"effort": "low", "summary": "auto"}
    assert second == first | {"reasoning": {"effort": "low"}}
    assert second["stream"] is True
    assert generation.text.strip() == "The answer [1]." and generation.thinking == ""
    [(_, _, fields)] = [event for event in logged if event[1] == "reasoning summary refused"]
    assert fields == {"provider": "openai", "model": MODEL, "reason": FailureReason.REJECTED.value}
    assert "Mill" not in str(logged) and "The answer" not in str(logged) and KEY not in str(logged)


def test_the_summary_retry_counts_against_no_other_retry():
    limited = status(openai.RateLimitError, 429, code="rate_limit_exceeded")
    refused, limited = FakeResponse(error=summary_refused()), FakeResponse(error=limited)
    client = FakeOpenAIClient([refused, limited, limited, FakeResponse()])
    waits = []

    _, generation = run(make_cloud(client, waits).model(MODEL))

    assert len(client.create_calls) == 4
    assert waits == [2.0, 6.0]
    assert all("summary" not in call["reasoning"] for call in client.create_calls[1:])
    assert generation.text.strip() == "An answer [1]."


def test_the_summary_is_asked_without_again_only_once():
    client = FakeOpenAIClient([FakeResponse(error=summary_refused())])

    failure = failure_of(client, waits=[])

    assert len(client.create_calls) == 2
    assert failure.reason == FailureReason.REJECTED


# The check (research.md R10)


def test_the_check_reads_each_model_once_and_runs_no_inference():
    client = FakeOpenAIClient(models={"gpt-a": openai_model("gpt-a"), "gpt-b": openai_model("gpt-b", "system")})

    rows = make_cloud(client).check(["gpt-a", "gpt-b"])

    assert rows == [
        ProviderCheck("openai gpt-a", True, "gpt-a, owned by openai"),
        ProviderCheck("openai gpt-b", True, "gpt-b, owned by system"),
    ]
    assert client.retrieve_calls == ["gpt-a", "gpt-b"] and client.create_calls == []


def test_an_unknown_or_forbidden_model_fails_its_own_row_and_the_check_goes_on():
    forbidden = status(openai.PermissionDeniedError, 403, code="model_not_allowed")
    client = FakeOpenAIClient(models={"gpt-y": forbidden, "gpt-a": openai_model("gpt-a")})

    rows = make_cloud(client).check(["gpt-x", "gpt-y", "gpt-a"])

    assert rows == [
        ProviderCheck("openai gpt-x", False, "OpenAI doesn't know this model"),
        ProviderCheck("openai gpt-y", False, "OpenAI rejected the request: model_not_allowed"),
        ProviderCheck("openai gpt-a", True, "gpt-a, owned by openai"),
    ]


@pytest.mark.parametrize(
    ("error", "words"),
    [
        (status(openai.AuthenticationError, 401, code="invalid_api_key"), "OpenAI refused the API key"),
        (openai_connection_error(), "OpenAI can't be reached"),
        (openai_timeout_error(), "OpenAI sent nothing for 120 s"),
    ],
)
def test_a_refused_key_or_openai_out_of_reach_is_one_failing_row_and_ends_the_check(error, words):
    client = FakeOpenAIClient(models={"gpt-a": error, "gpt-b": openai_model("gpt-b")})

    rows = make_cloud(client).check(["gpt-a", "gpt-b"])

    assert rows == [ProviderCheck("openai", False, words)]
    assert client.retrieve_calls == ["gpt-a"]
