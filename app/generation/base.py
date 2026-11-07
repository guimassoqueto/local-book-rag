"""The generation layer's interface. Nothing above it knows which runtime serves the model."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

FINISHED_BY_LENGTH = "length"


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class GenerationParameters:
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class GenerationStats:
    """What an inference cost, as the runtime reported it.

    Attributes:
        model: the model that ran.
        prompt_tokens: tokens read.
        completion_tokens: tokens produced, reasoning included.
        time_to_first_token: seconds until anything came back, reasoning included.
        load_seconds: seconds spent loading the model.
        prompt_seconds: seconds spent reading the prompt.
        generation_seconds: seconds spent producing tokens.
        total_seconds: wall-clock seconds.
        finish_reason: why it stopped, in the runtime's words.
    """

    model: str
    prompt_tokens: int
    completion_tokens: int
    time_to_first_token: float
    load_seconds: float
    prompt_seconds: float
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
    """A finished inference. `thinking` is the model's reasoning, kept apart from its answer."""

    text: str
    thinking: str
    stats: GenerationStats


class LLMProvider(Protocol):
    model: str

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
        """
        ...

    def generate(self, messages: Sequence[Message], parameters: GenerationParameters) -> Generation:
        """Generate without streaming. Raises what stream() raises."""
        ...
