"""Claude, through Anthropic's own SDK (specs/008-cloud-llm-providers, research.md R4 and R5).

Nothing here contacts Anthropic until a request streams or a check runs: the client, and each
model's provider, are built without a request. The key reaches the SDK's client and nothing else.
"""

import logging
import time
from collections.abc import Callable, Iterator, Sequence
from time import perf_counter
from typing import Any

import anthropic

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
from app.generation.cloud import ProviderCheck
from app.utils.logging import INFERENCE_LOGGER, log_event
from app.utils.tokenization import TokenCounter, create_token_counter

inference_logger = logging.getLogger(INFERENCE_LOGGER)

# A rate limit, an overload or a lost connection is tried again, before anything has streamed,
# after each of these waits. A timeout never is: the profile's timeout is the longest wait (FR-017).
_RETRY_WAITS = (2.0, 6.0)
_RETRIED = frozenset({FailureReason.RATE_LIMITED, FailureReason.OUTAGE, FailureReason.UNREACHABLE})
# The API's retry-after replaces a wait only when it is shorter than this.
_LONGEST_RETRY_AFTER = 10.0

_FINISH_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": FINISHED_BY_LENGTH,
    "model_context_window_exceeded": FINISHED_BY_LENGTH,
}

# The API's error types, for an error that arrives in the stream, whose HTTP status is 200.
_KEY_REFUSED_TYPES = frozenset({"authentication_error", "permission_error", "billing_error"})
_OUTAGE_TYPES = frozenset({"overloaded_error", "api_error", "timeout_error"})
_KEY_REFUSED_STATUS = 402


class AnthropicCloud:
    """Anthropic's models, sharing one client and the provider's profile.

    Args:
        credentials: the key and the allowed models.
        profile: `cloud_profiles.anthropic`.
        client_factory: builds the SDK's client, `anthropic.Anthropic` by default.
        sleep: waits between tries, `time.sleep` by default.
    """

    name = "anthropic"
    label = "Anthropic"

    def __init__(
        self,
        credentials: ProviderCredentials,
        profile: CloudProfile,
        client_factory: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        key = credentials.api_key.get_secret_value() if credentials.api_key else None
        # The SDK's own retries would try a timeout again too, turning 120 s of silence into six
        # minutes, so they are off, and the provider tries again itself.
        self._client = (client_factory or anthropic.Anthropic)(
            api_key=key, timeout=profile.request_timeout_seconds, max_retries=0
        )
        self._profile = profile
        self._sleep = sleep or time.sleep
        self._counter = create_token_counter(profile.tokenizer)

    def model(self, name: str) -> "AnthropicLLMProvider":
        return AnthropicLLMProvider(name, self._client, self._profile, self._counter, self._sleep, self.label)

    def check(self, models: Sequence[str]) -> list[ProviderCheck]:
        """Read each model's description, which sends the key and its name and runs no inference.

        A refused key, or a provider that can't be reached, ends the check with one row.
        """
        rows: list[ProviderCheck] = []
        for model in models:
            try:
                info = self._client.models.retrieve(model)
            except anthropic.AnthropicError as exc:
                reason, detail = _failure(exc, self._profile.request_timeout_seconds)
                words = f"{self.label} {reason.describe(detail).removeprefix('it ')}"
                if reason in (FailureReason.KEY_REFUSED, FailureReason.UNREACHABLE, FailureReason.TIMED_OUT):
                    return [*rows, ProviderCheck(self.name, False, words)]
                rows.append(ProviderCheck(f"{self.name} {model}", False, words))
                continue
            problems = self._problems(info)
            rows.append(ProviderCheck(f"{self.name} {model}", not problems, "; ".join(problems) or _found(info)))
        return rows

    def _problems(self, info: Any) -> list[str]:
        """What the profile sends that the model doesn't take, or a window smaller than the profile's."""
        problems = []
        capabilities = info.capabilities
        if capabilities is not None:
            effort = self._profile.reasoning
            if effort is not None and not _supported(getattr(capabilities.effort, effort, None)):
                problems.append(f"doesn't take the effort `{effort}`")
            if not _supported(capabilities.thinking.types.adaptive):
                problems.append("doesn't take adaptive reasoning")
        if info.max_input_tokens is not None and info.max_input_tokens < self._profile.context_size:
            problems.append(
                f"its window, {info.max_input_tokens} tokens, is smaller than "
                f"cloud_profiles.{self.name}.context_size, {self._profile.context_size}"
            )
        return problems


class AnthropicLLMProvider:
    """One Claude model. Every failure of its own raises ModelFailedError, never the SDK's errors."""

    provider = "anthropic"

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
        """An approximation: Claude's tokenizer isn't public."""
        return self._counter.count(text)

    def stream(self, messages: Sequence[Message], parameters: GenerationParameters) -> Iterator[TextDelta | Generation]:
        request = self._request(messages, parameters)
        waits = iter(_RETRY_WAITS)
        started = perf_counter()
        while True:
            first: float | None = None
            text: list[str] = []
            thinking: list[str] = []
            try:
                with self._client.messages.stream(**request) as events:
                    for event in events:
                        if event.type != "content_block_delta":
                            continue
                        delta = event.delta
                        if delta.type == "text_delta":
                            first = first or perf_counter()
                            text.append(delta.text)
                            yield TextDelta(delta.text)
                        elif delta.type == "thinking_delta":
                            first = first or perf_counter()
                            thinking.append(delta.thinking)
                    final = events.get_final_message()
            except anthropic.AnthropicError as exc:
                reason, detail = _failure(exc, self._profile.request_timeout_seconds)
                wait = _retry_wait(exc, reason, waits) if first is None else None
                if wait is None:
                    # Raised without the SDK's error, whose request holds the key in its headers.
                    raise ModelFailedError(self.model, self.provider, reason, detail, self._label) from None
                self._sleep(wait)
                continue
            break

        if final.stop_reason == "refusal":
            category = getattr(final.stop_details, "category", None) or ""
            raise ModelFailedError(self.model, self.provider, FailureReason.DECLINED, category, self._label)
        ended = perf_counter()
        stats = GenerationStats(
            model=final.model,
            prompt_tokens=final.usage.input_tokens,
            completion_tokens=final.usage.output_tokens,
            time_to_first_token=(first or ended) - started,
            load_seconds=None,
            prompt_seconds=None,
            generation_seconds=ended - (first or ended),
            total_seconds=ended - started,
            finish_reason=_FINISH_REASONS.get(final.stop_reason or "", final.stop_reason),
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
        yield Generation("".join(text), "".join(thinking), stats, thinking_summarized=True)

    def generate(self, messages: Sequence[Message], parameters: GenerationParameters) -> Generation:
        for event in self.stream(messages, parameters):
            if isinstance(event, Generation):
                return event
        raise AssertionError("stream() always ends with a Generation")

    def _request(self, messages: Sequence[Message], parameters: GenerationParameters) -> dict[str, Any]:
        """The request's arguments. No temperature or seed: the current models refuse any sampling
        setting, and the API has no seed. No server-side fallbacks: a model outside the sequence
        would answer (FR-016)."""
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": parameters.max_tokens + self._profile.reasoning_tokens,
        }
        system = "\n\n".join(message.content for message in messages if message.role == "system")
        if system:
            request["system"] = system
        request["messages"] = [
            {"role": message.role, "content": message.content} for message in messages if message.role != "system"
        ]
        # Summarized, since the default display returns an empty reasoning, billed the same.
        request["thinking"] = {"type": "adaptive", "display": "summarized"}
        if self._profile.reasoning is not None:
            request["output_config"] = {"effort": self._profile.reasoning}
        return request


def _failure(error: anthropic.AnthropicError, timeout: float) -> tuple[FailureReason, str]:
    """An SDK error's reason, and the API's words for it: the most specific classes first, as the
    API reference advises, the timeout before the connection error it is a kind of."""
    if isinstance(error, anthropic.APITimeoutError):
        return FailureReason.TIMED_OUT, f"{timeout:g} s"
    if isinstance(error, anthropic.APIConnectionError):
        return FailureReason.UNREACHABLE, ""
    if not isinstance(error, anthropic.APIStatusError):
        return FailureReason.REJECTED, type(error).__name__
    kind = error.type or ""
    if (
        isinstance(error, (anthropic.AuthenticationError, anthropic.PermissionDeniedError))
        or error.status_code == _KEY_REFUSED_STATUS
        or kind in _KEY_REFUSED_TYPES
    ):
        return FailureReason.KEY_REFUSED, kind
    if isinstance(error, anthropic.NotFoundError) or kind == "not_found_error":
        return FailureReason.UNKNOWN_MODEL, kind
    if isinstance(error, anthropic.RateLimitError) or kind == "rate_limit_error":
        return FailureReason.RATE_LIMITED, kind
    if isinstance(error, anthropic.InternalServerError):
        return FailureReason.OUTAGE, str(error.status_code)
    if kind in _OUTAGE_TYPES:
        return FailureReason.OUTAGE, kind
    return FailureReason.REJECTED, kind or str(error.status_code)


def _retry_wait(error: anthropic.AnthropicError, reason: FailureReason, waits: Iterator[float]) -> float | None:
    """How long to wait before trying again, or None when the failure is final."""
    if reason not in _RETRIED:
        return None
    wait = next(waits, None)
    if wait is None:
        return None
    response = getattr(error, "response", None)
    retry_after = response.headers.get("retry-after") if response is not None else None
    try:
        seconds = float(retry_after) if retry_after is not None else None
    except ValueError:
        seconds = None
    return seconds if seconds is not None and 0 <= seconds < _LONGEST_RETRY_AFTER else wait


def _supported(capability: Any) -> bool:
    return bool(capability is not None and capability.supported)


def _found(info: Any) -> str:
    if info.max_input_tokens is None:
        return info.display_name
    return f"{info.display_name}, {info.max_input_tokens}-token window"
