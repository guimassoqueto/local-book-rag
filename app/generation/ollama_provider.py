"""Generation through Ollama, with LlamaIndex's integration underneath."""

import logging
from collections.abc import Iterator, Sequence
from functools import cached_property
from time import perf_counter
from typing import Any

from llama_index.core.llms import ChatMessage
from llama_index.llms.ollama import Ollama

from app.config.settings import LLMConfig, LLMProfile
from app.errors import ConfigurationError
from app.generation.base import Generation, GenerationParameters, GenerationStats, Message, TextDelta
from app.utils.logging import INFERENCE_LOGGER, log_event
from app.utils.ollama_runtime import ModelInfo, OllamaRuntime
from app.utils.tokenization import TokenCounter

_NANOSECONDS = 1e9
_THINKING_CAPABILITY = "thinking"

inference_logger = logging.getLogger(INFERENCE_LOGGER)


class OllamaLLMProvider:
    def __init__(
        self,
        config: LLMConfig,
        profile: LLMProfile,
        runtime: OllamaRuntime,
        counter: TokenCounter,
        timeout: float,
    ) -> None:
        self.model = config.model
        self._config = config
        self._profile = profile
        self._runtime = runtime
        self._counter = counter
        self._timeout = timeout

    @cached_property
    def _info(self) -> ModelInfo:
        """Read once, and checked before the first inference: models differ in what they accept."""
        info = self._runtime.model_info(self.model)
        if self._profile.reasoning is not None and _THINKING_CAPABILITY not in info.capabilities:
            raise ConfigurationError(f"{self.model} has no reasoning mode, but its profile sets one.")
        return info

    def context_size(self) -> int:
        limit = self._info.context_length
        return min(self._config.context_size, limit) if limit else self._config.context_size

    def count_tokens(self, text: str) -> int:
        return self._counter.count(text)

    def stream(self, messages: Sequence[Message], parameters: GenerationParameters) -> Iterator[TextDelta | Generation]:
        llm = self._llm(parameters)
        started = perf_counter()
        first_token: float | None = None
        text: list[str] = []
        thinking: list[str] = []
        final: dict[str, Any] = {}

        with self._runtime.translate_errors(self.model):
            for part in llm.stream_chat([ChatMessage(role=m.role, content=m.content) for m in messages]):
                delta = part.delta or ""
                thought = part.additional_kwargs.get("thinking_delta") or ""
                if first_token is None and (delta or thought):
                    first_token = perf_counter() - started
                thinking.append(thought)
                if delta:
                    text.append(delta)
                    yield TextDelta(delta)
                final = dict(part.raw or {})

        stats = _stats(self.model, final, first_token or 0.0, perf_counter() - started)
        log_event(
            inference_logger,
            "generation finished",
            model=self.model,
            prompt_tokens=stats.prompt_tokens,
            completion_tokens=stats.completion_tokens,
            tokens_per_second=stats.tokens_per_second,
            time_to_first_token=stats.time_to_first_token,
            total_seconds=stats.total_seconds,
            finish_reason=stats.finish_reason,
        )
        yield Generation("".join(text), "".join(thinking), stats)

    def generate(self, messages: Sequence[Message], parameters: GenerationParameters) -> Generation:
        for event in self.stream(messages, parameters):
            if isinstance(event, Generation):
                return event
        raise AssertionError("stream() always ends with a Generation")

    def _llm(self, parameters: GenerationParameters) -> Ollama:
        options: dict[str, Any] = {"num_predict": parameters.max_tokens}
        if parameters.seed is not None:
            options["seed"] = parameters.seed
        return Ollama(
            model=self.model,
            base_url=self._runtime.base_url,
            temperature=parameters.temperature,
            context_window=self.context_size(),
            request_timeout=self._timeout,
            thinking=self._profile.reasoning,
            additional_kwargs=options,
        )


def _stats(model: str, final: dict[str, Any], first_token: float, total: float) -> GenerationStats:
    def seconds(name: str) -> float:
        return (final.get(name) or 0) / _NANOSECONDS

    return GenerationStats(
        model=model,
        prompt_tokens=final.get("prompt_eval_count") or 0,
        completion_tokens=final.get("eval_count") or 0,
        time_to_first_token=first_token,
        load_seconds=seconds("load_duration"),
        prompt_seconds=seconds("prompt_eval_duration"),
        generation_seconds=seconds("eval_duration"),
        total_seconds=total,
        finish_reason=final.get("done_reason"),
    )
