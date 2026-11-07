"""Answers questions from retrieved passages, with every claim traceable to its source."""

from collections.abc import Iterator
from dataclasses import dataclass
from time import perf_counter

from app.config.settings import RetrievalConfig, Settings
from app.errors import GenerationError
from app.generation.base import (
    FINISHED_BY_LENGTH,
    Generation,
    GenerationParameters,
    LLMProvider,
    Message,
    TextDelta,
)
from app.generation.citations import Citation, normalize_citations, resolve_citations
from app.generation.prompts import NO_EVIDENCE_MARKER, format_passage, question_answering_messages
from app.retrieval.base import Passage, RetrievalFilters
from app.retrieval.pipeline import RetrievalResult
from app.services.retrieval_service import RetrievalService

NOTHING_RETRIEVED = "The selected sources hold no passage that could answer this question."


@dataclass(frozen=True)
class Answer:
    """An answer and everything that explains it.

    Attributes:
        question: what was asked.
        text: the answer, without the model's reasoning.
        citations: the sources it relies on, the passages they point to being in `passages`.
        invented_citations: numbers it cited that match no passage.
        insufficient_evidence: the model said the sources can't answer the question.
        retrieval: the search behind it, with every candidate and score.
        passages: the passages that fit in the context, in the order they were numbered.
        messages: the exact prompt.
        thinking: the model's reasoning, for inspection.
        generation: the inference's statistics. None when no inference was needed.
        total_seconds: the whole operation.
    """

    question: str
    text: str
    citations: tuple[Citation, ...]
    invented_citations: tuple[int, ...]
    insufficient_evidence: bool
    retrieval: RetrievalResult
    passages: tuple[Passage, ...]
    messages: tuple[Message, ...]
    thinking: str
    generation: Generation | None
    total_seconds: float


class QuestionAnsweringService:
    def __init__(self, settings: Settings, retrieval: RetrievalService, llm: LLMProvider) -> None:
        self._settings = settings
        self._retrieval = retrieval
        self._llm = llm

    def answer(
        self,
        question: str,
        filters: RetrievalFilters,
        language: str | None = None,
        retrieval_config: RetrievalConfig | None = None,
    ) -> Answer:
        """Answer a question. See stream()."""
        for event in self.stream(question, filters, language, retrieval_config):
            if isinstance(event, Answer):
                return event
        raise AssertionError("stream() always ends with an Answer")

    def stream(
        self,
        question: str,
        filters: RetrievalFilters,
        language: str | None = None,
        retrieval_config: RetrievalConfig | None = None,
    ) -> Iterator[RetrievalResult | TextDelta | Answer]:
        """Answer a question, reporting progress as it happens.

        Args:
            question: what was asked.
            filters: where to look.
            language: the language to answer in. None means the question's.
            retrieval_config: a strategy other than the configured one, for experiments.

        Yields:
            The retrieval result, then the text as it arrives, then the Answer.

        Raises:
            GenerationError: the model produced no answer.
        """
        started = perf_counter()
        result = self._retrieval.search(question, filters, retrieval_config)
        yield result

        passages = self._fit_in_context(question, result.passages, language)
        if not passages:
            yield Answer(
                question=question,
                text=NOTHING_RETRIEVED,
                citations=(),
                invented_citations=(),
                insufficient_evidence=True,
                retrieval=result,
                passages=(),
                messages=(),
                thinking="",
                generation=None,
                total_seconds=perf_counter() - started,
            )
            return

        chunks = [passage.chunk for passage in passages]
        messages = question_answering_messages(question, chunks, language)
        generation: Generation | None = None
        marker = _MarkerFilter()
        for event in self._llm.stream(messages, self._parameters()):
            if isinstance(event, Generation):
                generation = event
            elif visible := marker.feed(event.text):
                yield TextDelta(visible)
        if leftover := marker.flush():
            yield TextDelta(leftover)

        text, insufficient = _read_marker(normalize_citations(_usable_text(generation)))
        citations, invented = resolve_citations(text, chunks)
        yield Answer(
            question=question,
            text=text,
            citations=tuple(citations),
            invented_citations=tuple(invented),
            insufficient_evidence=insufficient,
            retrieval=result,
            passages=tuple(passages),
            messages=tuple(messages),
            thinking=generation.thinking,
            generation=generation,
            total_seconds=perf_counter() - started,
        )

    def _parameters(self) -> GenerationParameters:
        task = self._settings.generation.question_answering
        llm = self._settings.llm
        return GenerationParameters(
            temperature=llm.temperature if task.temperature is None else task.temperature,
            max_tokens=task.max_tokens or llm.max_tokens,
        )

    def _fit_in_context(self, question: str, passages: tuple[Passage, ...], language: str | None) -> list[Passage]:
        """Keep the best passages that fit, since Ollama silently cuts a prompt that doesn't.

        A cut prompt would still get an answer, from whatever text happened to survive.
        """
        margin = self._settings.generation.context.safety_margin
        budget = int(self._llm.context_size() * (1 - margin)) - self._parameters().max_tokens
        frame = question_answering_messages(question, [], language)
        budget -= sum(self._llm.count_tokens(message.content) for message in frame)

        selected: list[Passage] = []
        for number, passage in enumerate(passages, start=1):
            cost = self._llm.count_tokens(format_passage(number, passage.chunk))
            if cost > budget:
                break
            budget -= cost
            selected.append(passage)
        return selected


class _MarkerFilter:
    """Holds a reply's first characters back until they can't be the no-evidence marker."""

    def __init__(self) -> None:
        self._held = ""
        self._decided = False

    def feed(self, text: str) -> str:
        if self._decided:
            return text
        self._held += text
        reply = self._held.lstrip()
        if reply.startswith(NO_EVIDENCE_MARKER):
            self._decided = True
            return reply.removeprefix(NO_EVIDENCE_MARKER).lstrip()
        if NO_EVIDENCE_MARKER.startswith(reply):
            return ""
        self._decided = True
        return self._held

    def flush(self) -> str:
        return "" if self._decided else self._held


def _usable_text(generation: Generation | None) -> str:
    if generation is None or not generation.text.strip():
        reason = generation.stats.finish_reason if generation else None
        if reason == FINISHED_BY_LENGTH:
            raise GenerationError(
                "The model used its whole token limit on reasoning, without reaching an answer. "
                "Raise max_tokens in config/generation.yaml."
            )
        raise GenerationError("The model finished without an answer.")
    return generation.text


def _read_marker(text: str) -> tuple[str, bool]:
    stripped = text.strip()
    if stripped.startswith(NO_EVIDENCE_MARKER):
        return stripped.removeprefix(NO_EVIDENCE_MARKER).strip(), True
    return stripped, False
