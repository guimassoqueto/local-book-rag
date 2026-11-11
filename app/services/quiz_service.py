"""Quizzes on one chapter or a whole book (specs/003-chapter-quiz).

The model writes one question from one passage, and never sees a letter (app/generation/quiz.py).
Everything the assessment's probe saw it do badly is decided here instead:
- which passages questions come from: spread over the chapter, or over the book by its chapters'
  length (research R6);
- which letter is right: a balanced set, so every letter is the key as often as any other (R7);
- the order: random, and never the text's (R7);
- what happens to a reply that can't be used: written again, then replaced, and counted (R4, R5);
- the score, by counting (FR-014).

The Quiz tab and the `quiz` experiment call this service, and nothing else holds a quiz rule
(constitution IV). Nothing is kept: a quiz lives in the caller's memory, and the one file written
is the current result's download, in a directory this service empties (FR-018).
"""

import logging
import math
import random
import shutil
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Literal

from app.config.settings import QuizConfig
from app.errors import (
    ChapterNotFoundError,
    ConfigurationError,
    GenerationError,
    NothingToAskError,
    NothingToSearchError,
    QuizAlreadyGradedError,
)
from app.generation.prompts import QUIZ_LETTERS, QuizSource
from app.generation.quiz import CheckVerdict, Draft, PassedOver, QuizWriter, Refusal, Skip
from app.ingestion.chunker import Chunk
from app.ingestion.language import language_name
from app.retrieval.bm25 import ChunkSource
from app.storage.catalog import Book, BookCatalog, BookStatus
from app.utils.logging import get_logger, log_event, new_execution_id

logger = get_logger("services.quizzes")

_QUIZZABLE = (BookStatus.INDEXED, BookStatus.REINDEXING)  # as for searches: the old index serves meanwhile
_THIRDS = 3


class QuizState(StrEnum):
    """A Quiz exists once prepared. Preparing, stopped and failed are states of the preparation."""

    READY = "ready"
    GRADED = "graded"


@dataclass(frozen=True)
class Scope:
    """What a quiz is about: a book, and one of its chapters, or None for the whole book."""

    book_id: str
    chapter_number: int | None


@dataclass(frozen=True)
class Question:
    """A question in its place in the quiz.

    Attributes:
        position: its place, from 1.
        text: the question.
        options: the five options, shown as A to E.
        key: the right option's letter.
        explanation: why it is right, from the passage.
        passage: the one passage it was written from, whole.
    """

    position: int
    text: str
    options: tuple[str, ...]
    key: str
    explanation: str
    passage: Chunk


@dataclass(frozen=True)
class Quiz:
    """A prepared quiz.

    Attributes:
        scope: the book and chapter.
        book_title: the book's title.
        chapter_title: the chapter's, or None for a whole-book quiz.
        language: the language the questions were written in, by name.
        writer: the model that wrote them.
        checker: the model that checked them, when the check was on.
        asked: how many questions were asked for.
        questions: the questions, in position order. Fewer than asked only with a shortfall.
        prepared_at: when it was ready.
        state: ready, then graded.
    """

    scope: Scope
    book_title: str
    chapter_title: str | None
    language: str
    writer: str
    checker: str | None
    asked: int
    questions: tuple[Question, ...]
    prepared_at: datetime
    state: QuizState


@dataclass(frozen=True)
class QuizStarted:
    """Preparation has begun."""

    asked: int
    limit: int
    book_title: str
    chapter_title: str | None


@dataclass(frozen=True)
class QuestionReady:
    """A question is final: written, read, in form, and checked when the check is on.

    Attributes:
        question: the question.
        ready: how many questions are ready, this one included.
        attempts: the writer's calls for this position, replaced passages included.
        refusals: the attempts refused, by kind.
        check: the key check's verdict, when the check is on.
    """

    question: Question
    ready: int
    attempts: int
    refusals: dict[str, int]
    check: CheckVerdict | None


@dataclass(frozen=True)
class QuizReady:
    """Preparation has finished.

    Attributes:
        quiz: the quiz.
        shortfall: how many questions are missing, because passages ran out.
        skipped_passages: passages the writer found nothing to ask about in.
        passed_over_passages: passages too long to send with their instructions (FR-011).
        ruled_out_chapters: chapters whose first two passages tried were both skipped.
        check_unreadable: verdicts that couldn't be read, even asked again.
        check_rejected: questions the check rejected, which were replaced.
    """

    quiz: Quiz
    shortfall: int
    skipped_passages: int
    passed_over_passages: int
    ruled_out_chapters: tuple[int, ...]
    check_unreadable: int
    check_rejected: int


QuizEvent = QuizStarted | QuestionReady | QuizReady


@dataclass(frozen=True)
class ChapterTally:
    chapter_number: int
    chapter_title: str
    questions: int
    missed: int


@dataclass(frozen=True)
class Result:
    """A graded quiz.

    Attributes:
        quiz: the quiz, in state graded.
        answers: the reader's letters, or None for a question not answered, in position order.
        right: whether each answer is right. An unanswered question is wrong.
        score: right answers over questions, as a percentage.
        ranking: for a whole-book quiz, the chapters by questions missed, most first.
        submitted_at: when it was graded.
    """

    quiz: Quiz
    answers: tuple[str | None, ...]
    right: tuple[bool, ...]
    score: float
    ranking: tuple[ChapterTally, ...]
    submitted_at: datetime


@dataclass
class _Slot:
    """A place in the quiz waiting for its question, with the letter its key will have.

    Attributes:
        letter: the key's letter, fixed in advance (R7).
        chapter: the chapter its passages come from.
        stratum: the passages of its stratum, which replacements are drawn from first.
        first: the passage drawn for it, tried first.
        queue: the replacements, nearest first, built when the first one is needed.
    """

    letter: str
    chapter: int
    stratum: list[Chunk]
    first: Chunk | None
    queue: list[Chunk] | None = None


@dataclass
class _Chapter:
    """A chapter during preparation, for the rule of R5."""

    number: int
    title: str
    passages: list[Chunk]
    words: int
    outcomes: list[str] = field(default_factory=list)  # of the passages tried, in order
    ready: int = 0
    ruled_out: bool = False


@dataclass
class _Counts:
    calls: int = 0
    skipped: int = 0
    passed_over: int = 0
    check_unreadable: int = 0
    check_rejected: int = 0


Outcome = Literal["ready", "skip", "refused", "rejected", "passed_over"]


class QuizService:
    """Prepares and grades quizzes.

    Args:
        config: generation.quiz.
        languages: generation.response_languages, the languages a quiz can be written in.
        catalog: the books.
        chunks: their passages, as indexed.
        writer: the models' side of a quiz.
        downloads: the directory for the current result's download, which this service empties.
    """

    def __init__(
        self,
        config: QuizConfig,
        languages: Sequence[str],
        catalog: BookCatalog,
        chunks: ChunkSource,
        writer: QuizWriter,
        downloads: Path,
    ) -> None:
        self._config = config
        self._languages = tuple(languages)
        self._catalog = catalog
        self._chunks = chunks
        self._writer = writer
        self._downloads = downloads
        self._empty_downloads()

    @property
    def max_questions(self) -> int:
        return self._config.max_questions

    def limit(self, book_id: str, chapter: int | None) -> int:
        """The most questions the text can hold: its passages, capped at max_questions (FR-002).

        Raises:
            BookNotFoundError: no such book.
            ChapterNotFoundError: no such chapter in the book.
            NothingToSearchError: the book isn't indexed.
        """
        _, passages = self._read(book_id, chapter)
        return min(len(passages), self._config.max_questions)

    def default_count(self, book_id: str, chapter: int | None) -> int:
        """One question per words_per_question words, rounded half up, between 1 and default_max (R8).

        Raises what limit() raises.
        """
        _, passages = self._read(book_id, chapter)
        return self._default_count(passages)

    def prepare(
        self,
        book_id: str,
        chapter: int | None,
        count: int,
        language: str | None = None,
        seed: int | None = None,
    ) -> Iterator[QuizEvent]:
        """Prepare a quiz, yielding each question as soon as it is ready (contracts/quiz-service.md).

        Closing the generator, as Gradio does on Stop, ends the preparation at once.

        Args:
            book_id: the book.
            chapter: one of its chapters, or None for the whole book.
            count: how many questions, from 1 to limit().
            language: the language to write in, from generation.response_languages. None means
                the book's.
            seed: fixes the passages, letters, order and the models' sampling, for the
                measurement. None in use.

        Raises:
            ConfigurationError: the count is out of bounds, or the language can't be used.
            NothingToAskError: a one-chapter quiz whose chapter has nothing to ask about.
            GenerationError: no question at all could be written.
            ServiceUnavailableError, ModelNotFoundError: from the model.
        """
        book, passages = self._read(book_id, chapter)
        limit = min(len(passages), self._config.max_questions)
        if not 1 <= count <= limit:
            raise ConfigurationError(f"A quiz on this text can have between 1 and {limit} questions, not {count}.")
        named_language = self._language(book, language)
        self._empty_downloads()

        # operation() keeps its fields in a context variable, which Gradio's worker threads, each
        # running one step of this generator in a context of its own, couldn't reset afterwards.
        fields = {
            "execution_id": new_execution_id(),
            "operation": "prepare_quiz",
            "book_id": book_id,
            "chapter": chapter,
            "model": self._writer.model,
        }
        started = perf_counter()
        log_event(logger, "operation started", **fields)
        try:
            yield from self._prepare(book, passages, chapter, count, limit, named_language, seed)
        except GeneratorExit:
            log_event(logger, "operation stopped", duration_seconds=perf_counter() - started, **fields)
            raise
        except Exception:
            duration = perf_counter() - started
            logger.exception("operation failed", extra={"fields": fields | {"duration_seconds": duration}})
            raise
        log_event(logger, "operation finished", duration_seconds=perf_counter() - started, **fields)

    def grade(self, quiz: Quiz, answers: Sequence[str | None]) -> Result:
        """Score a quiz, and rank a whole book's chapters by questions missed (FR-014, FR-016).

        Raises:
            QuizAlreadyGradedError: the quiz was graded already.
            ConfigurationError: the answers don't match the questions one for one.
        """
        if quiz.state != QuizState.READY:
            raise QuizAlreadyGradedError("This quiz has been graded. Prepare a new quiz to practice again.")
        if len(answers) != len(quiz.questions):
            raise ConfigurationError(f"The quiz has {len(quiz.questions)} questions, but {len(answers)} answers came.")
        right = tuple(answer == question.key for question, answer in zip(quiz.questions, answers, strict=True))
        ranking = _ranking(quiz.questions, right) if quiz.scope.chapter_number is None else ()
        return Result(
            quiz=replace(quiz, state=QuizState.GRADED),
            answers=tuple(answers),
            right=right,
            score=100 * sum(right) / len(quiz.questions),
            ranking=ranking,
            submitted_at=datetime.now(UTC),
        )

    def result_document(self, result: Result) -> tuple[str, str]:
        """The result as Markdown, the reader's only record (FR-017, contracts/quiz-tab.md § Download).

        Each question gets its passage's reference, not its text: the document records the quiz,
        not the book. It writes nothing.

        Returns:
            The file name, quiz-<book_id>[-ch<NN>]-<YYYYMMDDTHHMMSSZ>.md, and the Markdown.
        """
        quiz = result.quiz
        chapter = f"-ch{quiz.scope.chapter_number:02d}" if quiz.scope.chapter_number is not None else ""
        name = f"quiz-{quiz.scope.book_id}{chapter}-{result.submitted_at:%Y%m%dT%H%M%SZ}.md"
        title = f"{quiz.book_title}, {quiz.chapter_title}" if quiz.chapter_title else quiz.book_title
        writers = f"{quiz.writer}; **checked by**: {quiz.checker}" if quiz.checker else quiz.writer
        lines = [
            f"# Quiz: {title}",
            "",
            f"- **Taken**: {result.submitted_at:%Y-%m-%d %H:%M} UTC",
            f"- **Book**: {quiz.book_title} ({quiz.scope.book_id})",
            *([f"- **Chapter**: {quiz.chapter_title}"] if quiz.chapter_title else []),
            f"- **Language**: {quiz.language}",
            f"- **Written by**: {writers}",
            f"- **Score**: {sum(result.right)} of {len(quiz.questions)} ({result.score:.0f}%)",
        ]
        if result.ranking:
            lines += ["", "## Chapters to reread", "", "| Chapter | Questions | Missed |"]
            lines.append("| ------- | --------- | ------ |")
            lines += [f"| {tally.chapter_title} | {tally.questions} | {tally.missed} |" for tally in result.ranking]
        lines += ["", "## Questions"]
        for question, answer, right in zip(quiz.questions, result.answers, result.right, strict=True):
            lines += [
                "",
                f"### {question.position}. {question.text}",
                "",
                *(f"- {letter}) {option}" for letter, option in zip(QUIZ_LETTERS, question.options, strict=True)),
                "",
                f"**Your answer**: {answer or 'not answered'} · **Right answer**: {question.key} {_mark(right)}",
                "",
                question.explanation,
                "",
                f"*Source*: {_reference(question.passage)}",
            ]
        return name, "\n".join(lines) + "\n"

    def export(self, result: Result) -> Path:
        """Write the result's document for the tab to offer, and return where it is.

        The directory holds at most this file: it is emptied first, whenever a quiz is prepared,
        and when the application starts (FR-018). The tab writes nothing (constitution IV).
        """
        name, document = self.result_document(result)
        self._empty_downloads()
        path = self._downloads / name
        path.write_text(document, encoding="utf-8")
        return path

    # Reading the book

    def _read(self, book_id: str, chapter: int | None) -> tuple[Book, list[Chunk]]:
        book = self._catalog.get(book_id)
        if book.status not in _QUIZZABLE:
            raise NothingToSearchError(
                f"'{book.title}' ({book_id}) is {book.status.value}, so it can't be quizzed. Wait until it is "
                "indexed, or reindex it in the Library tab."
            )
        passages = sorted(self._chunks.load_chunks(book_id, book.revision), key=lambda chunk: chunk.chunk_index)
        if chapter is not None:
            passages = [passage for passage in passages if passage.chapter_number == chapter]
            if not passages:
                raise ChapterNotFoundError(f"{book_id} has no chapter {chapter}.")
        elif not passages:
            raise NothingToAskError(f"'{book.title}' has no passages to ask about.")
        return book, passages

    def _default_count(self, passages: Sequence[Chunk]) -> int:
        words = sum(len(passage.text.split()) for passage in passages)
        count = math.floor(words / self._config.words_per_question + 0.5)  # round() rounds half to even
        limit = min(len(passages), self._config.max_questions)
        return max(1, min(count, self._config.default_max, limit))

    def _language(self, book: Book, language: str | None) -> str:
        if language is not None:
            if language not in self._languages:
                raise ConfigurationError(
                    f"Questions can't be written in {language}. Choose one of: {', '.join(self._languages)}."
                )
            return language
        named = language_name(book.language) if book.language else None
        if named is None:
            raise ConfigurationError(
                f"The language of '{book.title}' isn't known. Choose a language to write the questions in."
            )
        return named

    def _empty_downloads(self) -> None:
        if self._downloads.exists():
            shutil.rmtree(self._downloads)
        self._downloads.mkdir(parents=True, exist_ok=True)

    # Preparing

    def _prepare(
        self,
        book: Book,
        passages: list[Chunk],
        chapter: int | None,
        count: int,
        limit: int,
        language: str,
        seed: int | None,
    ) -> Iterator[QuizEvent]:
        rng = random.Random(seed)
        whole_book = chapter is None
        chapters = _chapters(passages)
        slots = _plan(chapters, count, rng)
        chapter_title = None if whole_book else passages[0].chapter_title
        yield QuizStarted(asked=count, limit=limit, book_title=book.title, chapter_title=chapter_title)

        source = QuizSource(book.title, book.author, chapter_title)
        checking = self._config.check.enabled and self._writer.checker_model is not None
        counts = _Counts()
        used: set[str] = set()
        questions: list[Question] = []
        for index, slot in enumerate(slots):
            pending = slots[index + 1 :]
            attempts = 0
            refusals: Counter[str] = Counter()
            while True:
                passage = _next_passage(slot, chapters[slot.chapter], used, pending, rng)
                if passage is None:
                    if whole_book and _move(slot, chapters, slots, questions, used, count, rng):
                        continue
                    break
                used.add(passage.chunk_id)
                state = chapters[slot.chapter]
                forbidden = (passage.chapter_title,) if whole_book else ()
                outcome, written, verdict, calls = self._try(
                    passage, source, language, forbidden, slot.letter, counts, refusals, seed, rng, checking
                )
                attempts += calls
                if outcome != "passed_over":
                    state.outcomes.append(outcome)
                if outcome == "ready" and written is not None:
                    state.ready += 1
                    question = replace(written, position=len(questions) + 1)
                    questions.append(question)
                    yield QuestionReady(question, len(questions), attempts, dict(refusals), verdict)
                    break
                if outcome == "skip" and state.ready == 0 and state.outcomes[:2] == ["skip", "skip"]:
                    state.ruled_out = True
                    log_event(logger, "quiz chapter ruled out", chapter=state.number, title=state.title)
                    if not whole_book:
                        raise NothingToAskError(
                            f"'{state.title}' seems to hold nothing to ask about: its first passages are "
                            "references, lists or captions. Choose another chapter."
                        )
                    if not _move(slot, chapters, slots, questions, used, count, rng):
                        break

        if not questions:
            raise GenerationError(
                f"The model wrote no question that could be used, from any passage tried: {counts.skipped} "
                f"skipped, {counts.passed_over} too long, the rest refused. Try again, or another chapter."
            )
        quiz = Quiz(
            scope=Scope(book.book_id, chapter),
            book_title=book.title,
            chapter_title=chapter_title,
            language=language,
            writer=self._writer.model,
            checker=self._writer.checker_model if checking else None,
            asked=count,
            questions=tuple(questions),
            prepared_at=datetime.now(UTC),
            state=QuizState.READY,
        )
        log_event(
            logger,
            "quiz prepared",
            asked=count,
            questions=len(questions),
            calls=counts.calls,
            skipped=counts.skipped,
            passed_over=counts.passed_over,
            check_unreadable=counts.check_unreadable,
            check_rejected=counts.check_rejected,
        )
        yield QuizReady(
            quiz=quiz,
            shortfall=count - len(questions),
            skipped_passages=counts.skipped,
            passed_over_passages=counts.passed_over,
            ruled_out_chapters=tuple(sorted(number for number, state in chapters.items() if state.ruled_out)),
            check_unreadable=counts.check_unreadable,
            check_rejected=counts.check_rejected,
        )

    def _try(
        self,
        passage: Chunk,
        source: QuizSource,
        language: str,
        forbidden: Sequence[str],
        letter: str,
        counts: _Counts,
        refusals: Counter[str],
        seed: int | None,
        rng: random.Random,
        checking: bool,
    ) -> tuple[Outcome, Question | None, CheckVerdict | None, int]:
        """Write from one passage, up to attempts_per_passage times.

        Returns:
            What came of it, the question if one is ready, the check's verdict, and the calls made.
        """
        calls = 0
        for _ in range(self._config.attempts_per_passage):
            result = self._writer.write(passage, source, language, forbidden, _call_seed(seed, counts.calls))
            if isinstance(result, PassedOver):
                counts.passed_over += 1
                log_event(logger, "quiz passage passed over", chunk_id=passage.chunk_id, tokens=result.tokens)
                return "passed_over", None, None, calls
            counts.calls += 1
            calls += 1
            if isinstance(result, Skip):
                counts.skipped += 1
                return "skip", None, None, calls
            if isinstance(result, Refusal):
                refusals[result.kind] += 1
                continue
            question = _place(result, letter, passage, rng)
            verdict = None
            if checking:
                verdict = self._writer.check(
                    question.text, question.options, question.key, passage, source, _call_seed(seed, counts.calls)
                )
                if not verdict.readable:
                    counts.check_unreadable += 1
                    log_event(logger, "quiz check unreadable", chunk_id=passage.chunk_id, level=logging.WARNING)
                elif not verdict.accepted:
                    counts.check_rejected += 1
                    return "rejected", None, verdict, calls
            return "ready", question, verdict, calls
        return "refused", None, None, calls


def _call_seed(seed: int | None, calls: int) -> int | None:
    """Each call gets its own seed, so a measurement repeats call by call (contracts/model-replies.md)."""
    return None if seed is None else seed + calls


def _place(draft: Draft, letter: str, passage: Chunk, rng: random.Random) -> Question:
    """Put the right answer on its letter, and the wrong ones, shuffled, on the rest (R7)."""
    wrong = list(draft.wrong)
    rng.shuffle(wrong)
    key_index = QUIZ_LETTERS.index(letter)
    options = [*wrong[:key_index], draft.correct, *wrong[key_index:]]
    return Question(
        position=0,
        text=draft.question,
        options=tuple(options),
        key=letter,
        explanation=draft.explanation,
        passage=passage,
    )


# Choosing passages, letters and order (R6, R7)


def _chapters(passages: Sequence[Chunk]) -> dict[int, _Chapter]:
    chapters: dict[int, _Chapter] = {}
    for passage in passages:
        state = chapters.setdefault(
            passage.chapter_number, _Chapter(passage.chapter_number, passage.chapter_title, [], 0)
        )
        state.passages.append(passage)
        state.words += len(passage.text.split())
    return chapters


def allocate(count: int, weights: dict[int, int], capacity: dict[int, int], rng: random.Random) -> dict[int, int]:
    """Divide `count` among chapters by their weights, by largest remainder (R6).

    Each part is within one of its share. A chapter gets no more than its capacity: what it can't
    take is divided among the others the same way.
    """
    shares = dict.fromkeys(weights, 0)
    open_chapters = {number for number in weights if capacity[number] > 0 and weights[number] > 0}
    left = count
    while left > 0 and open_chapters:
        total = sum(weights[number] for number in open_chapters)
        quotas = {number: left * weights[number] / total for number in open_chapters}
        parts = {number: math.floor(quota) for number, quota in quotas.items()}
        remainder = left - sum(parts.values())
        order = sorted(open_chapters, key=lambda number: (-(quotas[number] - parts[number]), rng.random()))
        for number in order[:remainder]:
            parts[number] += 1
        left = 0
        for number in sorted(open_chapters):
            room = capacity[number] - shares[number]
            taken = min(parts[number], room)
            shares[number] += taken
            left += parts[number] - taken
            if shares[number] >= capacity[number]:
                open_chapters.discard(number)
    return shares


def strata(passages: Sequence[Chunk], count: int) -> list[list[Chunk]]:
    """Cut passages, in book order, into `count` contiguous strata of nearly equal size.

    The bounds round up, as the thirds do, so that with three strata they are the thirds.
    """
    total = len(passages)
    bounds = [-(-index * total // count) for index in range(count + 1)]
    return [list(passages[bounds[index] : bounds[index + 1]]) for index in range(count)]


def _third(position: int, total: int) -> int:
    return _THIRDS * position // total


def _draw(passages: list[Chunk], count: int, rng: random.Random) -> list[tuple[list[Chunk], Chunk]]:
    """One passage from each stratum. With three or more, every third of the text gets one (SC-005)."""
    layers = strata(passages, count)
    places = {passage.chunk_id: index for index, passage in enumerate(passages)}
    while True:
        drawn = [(layer, rng.choice(layer)) for layer in layers]
        thirds = {_third(places[passage.chunk_id], len(passages)) for _, passage in drawn}
        if count < _THIRDS or len(thirds) == _THIRDS:
            return drawn


def _plan(chapters: dict[int, _Chapter], count: int, rng: random.Random) -> list[_Slot]:
    """The quiz's slots in position order: chapter, stratum, first passage and letter of each."""
    weights = {number: state.words for number, state in chapters.items()}
    capacity = {number: len(state.passages) for number, state in chapters.items()}
    shares = allocate(count, weights, capacity, rng)
    drawn = [
        (number, layer, passage)
        for number, share in shares.items()
        if share
        for layer, passage in _draw(chapters[number].passages, share, rng)
    ]
    drawn.sort(key=lambda entry: entry[2].chunk_index)
    order = list(range(len(drawn)))
    while True:
        rng.shuffle(order)
        if len(order) < 2 or order != sorted(order):
            break
    letters = [letter for letter in QUIZ_LETTERS for _ in range(count // len(QUIZ_LETTERS))]
    letters += rng.sample(QUIZ_LETTERS, count % len(QUIZ_LETTERS))
    rng.shuffle(letters)
    return [
        _Slot(letter=letter, chapter=drawn[index][0], stratum=drawn[index][1], first=drawn[index][2])
        for letter, index in zip(letters, order, strict=True)
    ]


def _next_passage(
    slot: _Slot, chapter: _Chapter, used: set[str], pending: Sequence[_Slot], rng: random.Random
) -> Chunk | None:
    """The slot's next passage: its own, then its stratum's, then the nearest in its chapter (R6).

    A passage drawn for a later slot stays that slot's.
    """
    if chapter.ruled_out:
        return None
    if slot.first is not None and slot.first.chunk_id not in used:
        first, slot.first = slot.first, None
        return first
    reserved = {other.first.chunk_id for other in pending if other.first is not None}
    if slot.queue is None:
        stratum = {passage.chunk_id for passage in slot.stratum}
        places = {passage.chunk_id: index for index, passage in enumerate(chapter.passages)}
        own = [places[chunk_id] for chunk_id in stratum if chunk_id in places]
        low, high = (min(own), max(own)) if own else (0, len(chapter.passages) - 1)

        def distance(passage: Chunk) -> tuple[int, float]:
            place = places[passage.chunk_id]
            gap = 0 if passage.chunk_id in stratum else max(low - place, place - high)
            return gap, rng.random()

        slot.queue = sorted(chapter.passages, key=distance)
    while slot.queue:
        passage = slot.queue.pop(0)
        if passage.chunk_id not in used and passage.chunk_id not in reserved:
            return passage
    return None


def _move(
    slot: _Slot,
    chapters: dict[int, _Chapter],
    slots: Sequence[_Slot],
    questions: Sequence[Question],
    used: set[str],
    count: int,
    rng: random.Random,
) -> bool:
    """Give a whole-book slot whose chapter can't serve it to another chapter, by the chapters' shares.

    The shares are among the chapters still in play (FR-006). Returns False when none can take it.
    """
    reserved = {other.first.chunk_id for other in slots if other.first is not None and other is not slot}
    available = {
        number: [p for p in state.passages if p.chunk_id not in used and p.chunk_id not in reserved]
        for number, state in chapters.items()
        if not state.ruled_out
    }
    in_play = {number: passages for number, passages in available.items() if passages}
    if not in_play:
        return False
    weights = {number: chapters[number].words for number in in_play}
    capacity = {number: len(chapters[number].passages) for number in in_play}
    targets = allocate(count, weights, capacity, rng)
    current = Counter(question.passage.chapter_number for question in questions)
    current.update(other.chapter for other in slots if other.first is not None and other is not slot)
    number = max(in_play, key=lambda number: (targets[number] - current[number], rng.random()))
    passage = _widest_gap(chapters[number].passages, in_play[number], rng)
    slot.chapter = number
    slot.stratum = [passage]
    slot.first = passage
    slot.queue = None
    return True


def _widest_gap(passages: list[Chunk], free: list[Chunk], rng: random.Random) -> Chunk:
    """A free passage from the longest run of free ones, so a chapter's questions stay spread out."""
    runs: list[list[Chunk]] = [[]]
    free_ids = {passage.chunk_id for passage in free}
    for passage in passages:
        if passage.chunk_id in free_ids:
            runs[-1].append(passage)
        elif runs[-1]:
            runs.append([])
    longest = max(runs, key=len)
    return rng.choice(longest) if longest else rng.choice(free)


def _mark(right: bool) -> str:
    return "✓" if right else "✗"


def _reference(passage: Chunk) -> str:
    """Where a passage is: chapter, section and pages."""
    if passage.page_start is None:
        pages = ""
    elif passage.page_end is None or passage.page_end == passage.page_start:
        pages = f"p. {passage.page_start}"
    else:
        pages = f"pp. {passage.page_start}–{passage.page_end}"
    return ", ".join(part for part in (passage.chapter_title, passage.section_title, pages) if part)


def _ranking(questions: Sequence[Question], right: Sequence[bool]) -> tuple[ChapterTally, ...]:
    """Chapters by questions missed, then by the share missed, then in book order (FR-016)."""
    asked: Counter[int] = Counter()
    missed: Counter[int] = Counter()
    titles: dict[int, str] = {}
    for question, correct in zip(questions, right, strict=True):
        number = question.passage.chapter_number
        titles[number] = question.passage.chapter_title
        asked[number] += 1
        missed[number] += not correct
    tallies = [ChapterTally(number, titles[number], asked[number], missed[number]) for number in asked]
    return tuple(
        sorted(tallies, key=lambda tally: (-tally.missed, -tally.missed / tally.questions, tally.chapter_number))
    )
