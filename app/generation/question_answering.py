"""Answers questions from retrieved passages, with every claim traceable to its source."""

import logging
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from time import perf_counter

from app.config.settings import RetrievalConfig, Settings
from app.errors import BookRagError, GenerationError
from app.generation.base import (
    FINISHED_BY_LENGTH,
    Generation,
    GenerationParameters,
    LLMProvider,
    Message,
    TextDelta,
)
from app.generation.citations import Citation, normalize_citations, resolve_citations
from app.generation.prompts import (
    NO_EVIDENCE_MARKER,
    abstention_check_messages,
    format_passage,
    question_answering_messages,
)
from app.ingestion.chunker import Chunk
from app.retrieval.base import Passage, RetrievalFilters
from app.retrieval.pipeline import RetrievalResult
from app.services.retrieval_service import RetrievalService
from app.utils.logging import get_logger, log_event, new_execution_id

logger = get_logger("generation.questions")

NOTHING_RETRIEVED = "The selected sources hold no passage that could answer this question."

# gpt-oss can write the marker's hyphen as a non-breaking one (U+2011), or as another dash, and
# gemma4 translated the marker itself, as [NO-EVIDÊNCIA]. Both read as the marker.
_DASHES = str.maketrans(dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2212", "-"))
_MARKER_START = NO_EVIDENCE_MARKER[: NO_EVIDENCE_MARKER.index("EVID") + len("EVID")]
_MARKER = re.compile(re.escape(_MARKER_START) + r"\w{0,12}\]", re.IGNORECASE)
_MAX_MARKER_LENGTH = 30  # held back no longer than this while it could still be the marker

# The check's verdict is its first word, whatever surrounds it: **No**, "YES." and the like. NO
# means the reply gives nothing that was asked: an abstention. Matching the word anywhere would
# misread an explanation, where "no" is a common word.
_VERDICT = re.compile(r"\W*(YES|NO)\b", re.IGNORECASE)

_OPENING_BRACKETS = "【［〔"
_CLOSING_BRACKETS = "】］〕"
_MAX_CITATION_LENGTH = 40  # a bracket still open after this many characters isn't a citation


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


@dataclass(frozen=True)
class Reply:
    """What a model's reply says, whichever way that model writes it."""

    text: str
    citations: tuple[Citation, ...]
    invented_citations: tuple[int, ...]
    insufficient_evidence: bool


def read_reply(generation: Generation | None, chunks: Sequence[Chunk]) -> Reply:
    """Read a finished generation against the passages it was given.

    Raises:
        GenerationError: the model produced no answer.
    """
    text, insufficient = _read_marker(normalize_citations(_usable_text(generation)))
    citations, invented = resolve_citations(text, chunks)
    return Reply(text, tuple(citations), tuple(invented), insufficient)


def check_abstention(
    llm: LLMProvider, settings: Settings, question: str, reply: Reply, parameters: GenerationParameters
) -> Reply:
    """Read a reply without the marker again for an abstention in words, if the model's profile asks.

    gemma4 and qwen3.5 sometimes abstain without the no-evidence marker: asked who did something,
    they reply that the passages say only "someone". Rewording the prompt made gpt-oss abstain on
    questions its passages answer (.specify/bugs/unmarked-abstentions), so the model that wrote the
    reply reads it again instead, without the passages. The application shows an abstention only
    once the reply is finished, so one recognized here is shown as any other.

    A verdict that can't be read, a failed call, or a check too long for the context leaves the
    reply an answer, and is logged: a check must never cost the reader an answer.

    Args:
        llm: the model that wrote the reply.
        settings: its settings, whose profile says whether to check.
        question: what was asked.
        reply: the reply, as read_reply() read it.
        parameters: the reply's parameters. The check keeps its token limit, at temperature 0.
    """
    if reply.insufficient_evidence or not settings.llm_profile.check_abstentions:
        return reply
    messages = abstention_check_messages(question, reply.text)
    needed = sum(llm.count_tokens(message.content) for message in messages) + parameters.max_tokens
    if needed > llm.context_size():
        log_event(logger, "abstention check skipped", logging.WARNING, model=llm.model, reason="context")
        return reply
    try:
        verdict = _VERDICT.match(llm.generate(messages, replace(parameters, temperature=0)).text)
    except BookRagError as exc:
        log_event(logger, "abstention check skipped", logging.WARNING, model=llm.model, reason=type(exc).__name__)
        return reply
    if verdict is None:
        log_event(logger, "abstention check skipped", logging.WARNING, model=llm.model, reason="unreadable")
        return reply
    return replace(reply, insufficient_evidence=verdict.group(1).upper() == "NO")


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
        citations = _CitationFilter()
        for event in self._llm.stream(messages, self._parameters()):
            if isinstance(event, Generation):
                generation = event
            elif visible := citations.feed(marker.feed(event.text)):
                yield TextDelta(visible)
        if leftover := citations.feed(marker.flush()) + citations.flush():
            yield TextDelta(leftover)

        reply = read_reply(generation, chunks)
        reply = check_abstention(self._llm, self._settings, question, reply, self._parameters())
        # One event at the end: Gradio resumes this generator from different contexts, which rules
        # out the `operation` context manager. It never carries the text of a book or a question.
        log_event(
            logger,
            "question answered",
            execution_id=new_execution_id(),
            operation="answer_question",
            books=sorted({chunk.book_id for chunk in chunks}),
            model=self._llm.model,
            retrieved_passages=len(result.candidates),
            context_passages=len(passages),
            prompt_tokens=generation.stats.prompt_tokens,
            completion_tokens=generation.stats.completion_tokens,
            insufficient_evidence=reply.insufficient_evidence,
            duration_seconds=perf_counter() - started,
        )
        yield Answer(
            question=question,
            text=reply.text,
            citations=reply.citations,
            invented_citations=reply.invented_citations,
            insufficient_evidence=reply.insufficient_evidence,
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
        if length := _marker_length(reply):
            self._decided = True
            return reply[length:].lstrip()
        if _could_become_marker(reply):
            return ""
        self._decided = True
        return self._held

    def flush(self) -> str:
        return "" if self._decided else self._held


class _CitationFilter:
    """Normalizes citations as they stream, holding one back until it closes.

    `gpt-oss` cites as `【3】`, and the parts can arrive in separate pieces. Without this, the text
    streamed to a reader would cite differently from the finished answer and its list of sources.
    """

    def __init__(self) -> None:
        self._held = ""

    def feed(self, text: str) -> str:
        self._held += text
        opening = max(self._held.rfind(bracket) for bracket in _OPENING_BRACKETS)
        unclosed = opening >= 0 and not any(bracket in self._held[opening:] for bracket in _CLOSING_BRACKETS)
        if unclosed and len(self._held) - opening < _MAX_CITATION_LENGTH:
            ready, self._held = self._held[:opening], self._held[opening:]
        else:
            ready, self._held = self._held, ""
        return normalize_citations(ready)

    def flush(self) -> str:
        held, self._held = self._held, ""
        return normalize_citations(held)


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
    if length := _marker_length(stripped):
        return stripped[length:].strip(), True
    return stripped, False


def _marker_length(reply: str) -> int:
    """How long the marker that opens a reply is, or 0 if none does. Dashes map one to one."""
    match = _MARKER.match(reply.translate(_DASHES))
    return match.end() if match else 0


def _could_become_marker(reply: str) -> bool:
    """Whether more text could still make this the marker: the start of it, or its bracket still open."""
    start = reply.translate(_DASHES).upper()
    if len(start) <= len(_MARKER_START):
        return _MARKER_START.startswith(start)
    return start.startswith(_MARKER_START) and "]" not in start and len(start) < _MAX_MARKER_LENGTH
