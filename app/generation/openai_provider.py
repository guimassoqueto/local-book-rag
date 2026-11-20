"""OpenAI's models, through OpenAI's own SDK and its Responses API (specs/009-openai-provider,
research.md R1 to R4, R10).

Nothing here contacts OpenAI until a request streams or a check runs: the client, and each model's
provider, are built without a request. The key reaches the SDK's client and nothing else, and the
client is given OpenAI's address too, so that nothing in the environment can send either
elsewhere (FR-020, FR-023).
"""

import logging
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from time import perf_counter
from typing import Any

import openai

from app.config.settings import CloudProfile, ProviderCredentials
from app.errors import ModelFailedError
from app.generation.base import (
    FINISHED_BY_LENGTH,
    FailureReason,
    Generation,
    GenerationParameters,
    GenerationStats,
    Message,
    TextDelta,
)
from app.generation.cloud import RETRY_WAITS, ProviderCheck, retry_wait
from app.utils.logging import INFERENCE_LOGGER, get_logger, log_event
from app.utils.tokenization import TokenCounter, create_token_counter

logger = get_logger("openai")
inference_logger = logging.getLogger(INFERENCE_LOGGER)

OPENAI_ADDRESS = "https://api.openai.com/v1"

# The events that end a response; each carries it, with its usage and its status.
_TERMINAL = frozenset({"response.completed", "response.incomplete", "response.failed"})
# An account that can't pay: OpenAI sends these with the status of a rate limit (research.md R4).
_OUT_OF_CREDIT = frozenset(
    {
        "insufficient_quota",
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
    }
)
# A request that the model or OpenAI's moderation declined.
_DECLINED = frozenset({"invalid_prompt", "bio_policy", "content_filter"})
_OUTAGE = frozenset({"server_error", "server_is_overloaded"})
_VERIFIED_ONLY = "OpenAI streams this model only to a verified organization"
_SUMMARY = "reasoning.summary"


class OpenAICloud:
    """OpenAI's models, sharing one client and the provider's profile.

    Args:
        credentials: the key and the allowed models.
        profile: `cloud_profiles.openai`.
        client_factory: builds the SDK's client, `openai.OpenAI` by default.
        sleep: waits between tries, `time.sleep` by default.
    """

    name = "openai"
    label = "OpenAI"
    # OpenAI's efforts; its profile must name one, or each model would reason at its own default.
    efforts = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})

    def __init__(
        self,
        credentials: ProviderCredentials,
        profile: CloudProfile,
        client_factory: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        key = credentials.api_key.get_secret_value() if credentials.api_key else None
        # The SDK's own retries would try a timeout again too, so they are off, and the provider
        # tries again itself (research.md R4).
        self._client = (client_factory or openai.OpenAI)(
            api_key=key, base_url=OPENAI_ADDRESS, timeout=profile.request_timeout_seconds, max_retries=0
        )
        self._profile = profile
        self._sleep = sleep or time.sleep
        self._counter = create_token_counter(profile.tokenizer)

    def model(self, name: str) -> "OpenAILLMProvider":
        return OpenAILLMProvider(name, self._client, self._profile, self._counter, self._sleep, self.label)

    def check(self, models: Sequence[str]) -> list[ProviderCheck]:
        """Read each model's description, which sends the key and its name and runs no inference.

        A refused key, or OpenAI out of reach, ends the check with one row. A model OpenAI doesn't
        know, or that the key's project may not use, fails its own row. OpenAI's description holds
        no window and no settings, so the check can't compare them with the profile.
        """
        rows: list[ProviderCheck] = []
        for model in models:
            try:
                info = self._client.models.retrieve(model)
            except openai.OpenAIError as exc:
                reason, detail = _failure(exc, self._profile.request_timeout_seconds)
                words = f"{self.label} {reason.describe(detail).removeprefix('it ')}"
                if reason in (FailureReason.KEY_REFUSED, FailureReason.UNREACHABLE, FailureReason.TIMED_OUT):
                    return [*rows, ProviderCheck(self.name, False, words)]
                rows.append(ProviderCheck(f"{self.name} {model}", False, words))
                continue
            rows.append(ProviderCheck(f"{self.name} {model}", True, f"{info.id}, owned by {info.owned_by}"))
        return rows


class OpenAILLMProvider:
    """One OpenAI model. Every failure of its own raises ModelFailedError, never the SDK's errors."""

    provider = "openai"

    def __init__(
        self,
        model: str,
        client: Any,
        profile: CloudProfile,
        counter: TokenCounter,
        sleep: Callable[[float], None],
        label: str,
    ) -> None:
        self.model = model
        self.check_abstentions = profile.check_abstentions
        self._client = client
        self._profile = profile
        self._counter = counter
        self._sleep = sleep
        self._label = label

    def context_size(self) -> int:
        """The profile's window, with the reasoning's room set aside."""
        return self._profile.context_size - self._profile.reasoning_tokens

    def count_tokens(self, text: str) -> int:
        """With the profile's tokenizer, which the integration tests measure against OpenAI's count."""
        return self._counter.count(text)

    def stream(self, messages: Sequence[Message], parameters: GenerationParameters) -> Iterator[TextDelta | Generation]:
        request = self._request(messages, parameters)
        waits = iter(RETRY_WAITS)
        summary_dropped = False
        started = perf_counter()
        while True:
            first: float | None = None
            text: list[str] = []
            reasoning: list[str] = []
            refused = False
            final: Any = None
            try:
                with self._client.responses.create(**request) as events:
                    for event in events:
                        if event.type == "response.output_text.delta":
                            first = first or perf_counter()
                            text.append(event.delta)
                            yield TextDelta(event.delta)
                        elif event.type == "response.reasoning_summary_text.delta":
                            first = first or perf_counter()
                            reasoning.append(event.delta)
                        elif event.type == "response.refusal.delta":
                            refused = True
                        elif event.type in _TERMINAL:
                            final = event.response
                            break
            except openai.OpenAIError as exc:
                if first is None and not summary_dropped and getattr(exc, "param", None) == _SUMMARY:
                    # The answer matters more than its reasoning: the same request once more,
                    # without asking for the summary (FR-015). It counts against no retry.
                    summary_dropped = True
                    request = _without_summary(request)
                    log_event(
                        logger,
                        "reasoning summary refused",
                        provider=self.provider,
                        model=self.model,
                        reason=FailureReason.REJECTED.value,
                    )
                    continue
                reason, detail = _failure(exc, self._profile.request_timeout_seconds)
                headers = _headers(exc)
            else:
                outcome = _outcome(final, refused)
                if outcome is None:
                    break
                reason, detail = outcome
                headers = None
            wait = retry_wait(headers, reason, waits) if first is None else None
            if wait is None:
                # Raised without the SDK's error, whose request holds the key in its headers.
                raise ModelFailedError(self.model, self.provider, reason, detail, self._label) from None
            self._sleep(wait)

        ended = perf_counter()
        stats = GenerationStats(
            model=final.model,
            prompt_tokens=final.usage.input_tokens if final.usage else 0,
            completion_tokens=final.usage.output_tokens if final.usage else 0,
            time_to_first_token=(first or ended) - started,
            load_seconds=None,
            prompt_seconds=None,
            generation_seconds=ended - (first or ended),
            total_seconds=ended - started,
            finish_reason=FINISHED_BY_LENGTH if final.status == "incomplete" else "stop",
        )
        log_event(
            inference_logger,
            "generation finished",
            model=stats.model,
            prompt_tokens=stats.prompt_tokens,
            completion_tokens=stats.completion_tokens,
            tokens_per_second=stats.tokens_per_second,
            time_to_first_token=stats.time_to_first_token,
            total_seconds=stats.total_seconds,
            finish_reason=stats.finish_reason,
        )
        # The reasoning items, and their encrypted copy, are dropped: only the summary is kept.
        yield Generation("".join(text), "".join(reasoning), stats, thinking_summarized=True)

    def generate(self, messages: Sequence[Message], parameters: GenerationParameters) -> Generation:
        for event in self.stream(messages, parameters):
            if isinstance(event, Generation):
                return event
        raise AssertionError("stream() always ends with a Generation")

    def _request(self, messages: Sequence[Message], parameters: GenerationParameters) -> dict[str, Any]:
        """The request's arguments, and nothing more (research.md R2): the prompt as written, roles
        included; no temperature or seed, which the models refuse or the API lacks; no tools, so the
        reply can come from the passages only; not stored; and refused rather than cut when it
        doesn't fit."""
        return {
            "model": self.model,
            "input": [{"role": message.role, "content": message.content} for message in messages],
            "max_output_tokens": parameters.max_tokens + self._profile.reasoning_tokens,
            "reasoning": {"effort": self._profile.reasoning, "summary": "auto"},
            "store": False,
            "truncation": "disabled",
            "stream": True,
        }


def _without_summary(request: dict[str, Any]) -> dict[str, Any]:
    reasoning = {key: value for key, value in request["reasoning"].items() if key != "summary"}
    return {**request, "reasoning": reasoning}


def _outcome(final: Any, refused: bool) -> tuple[FailureReason, str] | None:
    """Why a stream that ended without an SDK error failed, or None when it is an answer."""
    if final is None:
        return FailureReason.UNREACHABLE, ""
    if refused:
        return FailureReason.DECLINED, ""
    if final.status == "failed":
        code = (final.error.code if final.error else None) or ""
        if code in _OUTAGE:
            return FailureReason.OUTAGE, code
        if code == "rate_limit_exceeded":
            return FailureReason.RATE_LIMITED, code
        if code in _DECLINED:
            return FailureReason.DECLINED, code
        return FailureReason.REJECTED, code
    details = final.incomplete_details
    if final.status == "incomplete" and details is not None and details.reason == "content_filter":
        return FailureReason.DECLINED, "content_filter"
    return None


def _failure(error: openai.OpenAIError, timeout: float) -> tuple[FailureReason, str]:
    """An SDK error's reason, and OpenAI's code for it, never its message (research.md R4): the
    most specific classes first, the timeout before the connection error it is a kind of."""
    if isinstance(error, openai.APITimeoutError):
        return FailureReason.TIMED_OUT, f"{timeout:g} s"
    if isinstance(error, openai.APIConnectionError):
        return FailureReason.UNREACHABLE, ""
    if not isinstance(error, openai.APIError):
        return FailureReason.REJECTED, type(error).__name__
    code = error.code or ""
    status = getattr(error, "status_code", None)
    if isinstance(error, openai.AuthenticationError):
        return FailureReason.KEY_REFUSED, code
    if _stream_refused_to_organization(error):
        return FailureReason.REJECTED, _VERIFIED_ONLY
    if isinstance(error, openai.NotFoundError) or code == "model_not_found":
        return FailureReason.UNKNOWN_MODEL, ""
    if code in _OUT_OF_CREDIT:
        return FailureReason.OUT_OF_CREDIT, code
    if isinstance(error, openai.RateLimitError) or code == "rate_limit_exceeded":
        return FailureReason.RATE_LIMITED, code
    if isinstance(error, openai.InternalServerError) or code in _OUTAGE:
        return FailureReason.OUTAGE, code or str(status)
    if code in _DECLINED:
        return FailureReason.DECLINED, code
    param = error.param or ""
    detail = f"{code} ({param})" if code and param else code or param
    return FailureReason.REJECTED, detail or (str(status) if status else type(error).__name__)


def _stream_refused_to_organization(error: openai.APIError) -> bool:
    """Whether OpenAI refused to stream the model to the key's organization, until it is verified.

    OpenAI doesn't document the error's code, so it is recognized by the parameter it names, or by
    its words, which are read here and never shown (research.md R4).
    """
    if error.param == "stream":
        return True
    body = error.body if isinstance(error.body, Mapping) else {}
    words = f"{body.get('message') or ''} {error.message}".lower()
    return "verif" in words and "organization" in words


def _headers(error: openai.OpenAIError) -> Any:
    """The failed response's headers, for its retry-after; None when no response came back."""
    response = getattr(error, "response", None)
    return response.headers if response is not None else None
