"""The generation layer's interface. Nothing above it knows which runtime serves the model."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

FINISHED_BY_LENGTH = "length"


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class GenerationParameters:
    """Attributes:
    temperature: how far replies may vary.
    max_tokens: the limit for a reply, reasoning included.
    seed: fixes the sampling, for benchmarks to repeat a run.
    """

    temperature: float
    max_tokens: int
    seed: int | None = None


@dataclass(frozen=True)
class GenerationStats:
    """What an inference cost, as the runtime reported it.

    Attributes:
        model: the model that ran.
        prompt_tokens: tokens read.
        completion_tokens: tokens produced, reasoning included.
        time_to_first_token: seconds until anything came back, reasoning included.
        load_seconds: seconds spent loading the model; None when the provider doesn't report it.
        prompt_seconds: seconds spent reading the prompt; None when the provider doesn't report it.
        generation_seconds: seconds spent producing tokens. For a cloud model, measured by the app
            from the first delta to the end, so it includes the network.
        total_seconds: wall-clock seconds.
        finish_reason: why it stopped, in the runtime's words.
    """

    model: str
    prompt_tokens: int
    completion_tokens: int
    time_to_first_token: float
    load_seconds: float | None
    prompt_seconds: float | None
    generation_seconds: float
    total_seconds: float
    finish_reason: str | None

    @property
    def tokens_per_second(self) -> float:
        return self.completion_tokens / self.generation_seconds if self.generation_seconds else 0.0


@dataclass(frozen=True)
class TextDelta:
    """The next piece of a streamed answer."""

    text: str


@dataclass(frozen=True)
class Generation:
    """A finished inference. `thinking` is the model's reasoning, kept apart from its answer.

    `thinking_summarized` is true when `thinking` is the provider's summary of the reasoning, not
    the reasoning itself.
    """

    text: str
    thinking: str
    stats: GenerationStats
    thinking_summarized: bool = False


class FailureReason(StrEnum):
    """Why a model of a sequence failed, and the next one was asked (research.md R7 of specs/008)."""

    KEY_REFUSED = "key refused"
    UNKNOWN_MODEL = "unknown model"
    RATE_LIMITED = "rate limited"
    TIMED_OUT = "timed out"
    UNREACHABLE = "unreachable"
    OUTAGE = "outage"
    DECLINED = "declined"
    REJECTED = "rejected"
    NO_ANSWER = "no answer"

    def describe(self, detail: str = "") -> str:
        """The reason in the words every interface shows, such as "it limited the rate"."""
        if self is FailureReason.TIMED_OUT:
            return f"it sent nothing for {detail}" if detail else "it sent nothing in time"
        if self is FailureReason.OUTAGE:
            return f"it is down or overloaded ({detail})" if detail else "it is down or overloaded"
        if self is FailureReason.DECLINED:
            return f"it declined the request ({detail})" if detail else "it declined the request"
        if self is FailureReason.REJECTED:
            return f"it rejected the request: {detail}" if detail else "it rejected the request"
        return _FIXED_WORDS[self]


_FIXED_WORDS = {
    FailureReason.KEY_REFUSED: "it refused the API key",
    FailureReason.UNKNOWN_MODEL: "it doesn't know this model",
    FailureReason.RATE_LIMITED: "it limited the rate",
    FailureReason.UNREACHABLE: "it can't be reached",
    FailureReason.NO_ANSWER: "it gave no answer",
}


@dataclass(frozen=True)
class Attempt:
    """A model's failed try at a request.

    Attributes:
        model: the model that failed.
        provider: its provider.
        reason: why it failed.
        detail: the provider's words, such as a refusal's category or the API's error type. Never
            the key.
        prompt_tokens: for a summary's attempt, the tokens its finished steps read; None for an
            answer's.
        completion_tokens: likewise, the tokens they generated.
        step: for a summary's attempt, the step that failed; None for an answer's.
    """

    model: str
    provider: str
    reason: FailureReason
    detail: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    step: int | None = None

    def describe(self, label: str) -> str:
        """The failure as every interface words it: "<model> (<provider label>) failed: it limited the rate."."""
        return f"{self.model} ({label}) failed: {self.reason.describe(self.detail)}."


@dataclass(frozen=True)
class AttemptFailed:
    """A streamed answer's event: a model failed, and the next one starts from the beginning.

    The text streamed before this event is withdrawn.
    """

    attempt: Attempt
    next_model: str
    next_provider: str


class LLMProvider(Protocol):
    """One model, through one provider.

    Attributes:
        model: the model's name.
        provider: its provider's name, such as "ollama" or "anthropic".
        check_abstentions: from the model's profile, or its provider's: read a reply without the
            no-evidence marker again, for an abstention written only in words.
    """

    model: str
    provider: str
    check_abstentions: bool

    def context_size(self) -> int:
        """The window to work with: the configured one, capped by what the model supports."""
        ...

    def count_tokens(self, text: str) -> int:
        """Estimate a text's length with the model's own tokenizer."""
        ...

    def stream(self, messages: Sequence[Message], parameters: GenerationParameters) -> Iterator[TextDelta | Generation]:
        """Generate, yielding text as it arrives and a Generation at the end.

        Raises:
            ConfigurationError: the model does not support the configured settings.
            ModelNotFoundError: the model is not on the server.
            ServiceUnavailableError: the runtime failed or timed out.
            ModelFailedError: a cloud provider's failure of any kind, in place of the above.
        """
        ...

    def generate(self, messages: Sequence[Message], parameters: GenerationParameters) -> Generation:
        """Generate without streaming. Raises what stream() raises."""
        ...
