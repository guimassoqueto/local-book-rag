"""Chapter summaries, by map-reduce over the whole chapter.

Retrieval doesn't pick what gets summarized: the top passages for "summarize this" are whatever
happens to resemble that phrase, and they leave out most of a chapter. Every chunk goes through
here.

Citations are computed, not claimed. Models don't carry source tags through several rounds of
summarizing: the ones tested count upward, or drop them. So each statement of the finished
summary is looked up among the chapter's chunks, and cites the passage it actually resembles.
This works the same for every model.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from app.config.settings import Settings
from app.errors import ChapterNotFoundError, ConfigurationError, GenerationError
from app.generation.base import FINISHED_BY_LENGTH, Generation, GenerationParameters, LLMProvider, Message
from app.generation.citations import Citation, citation_for
from app.generation.prompts import (
    collapse_messages,
    final_summary_messages,
    map_messages,
    verification_messages,
)
from app.ingestion.chunker import Chunk, split_sentences
from app.retrieval.bm25 import ChunkSource
from app.storage.catalog import BookCatalog
from app.storage.repositories import SummaryDocuments
from app.utils.logging import get_logger, log_event, operation

logger = get_logger("generation.summaries")

_BOLD_HEADING = re.compile(r"^\s*\*\*\s*(#{1,6}\s[^*\n]+?)\s*\*\*[ \t]*(.*)$", re.MULTILINE)
_COLLAPSE_FAN_IN = 3  # merging everything at once would squeeze a long chapter into one reply
_PARTS_SEPARATOR = "\n\n---\n\n"
_MAP_INPUT_RATIO = 4  # how many tokens of text a reply of one token can do justice to
_WORDS_PER_TOKEN = 0.6  # leaves part of the limit to reasoning, and stays well within the rest
_MIN_PARTIAL_WORDS = 150  # below this, a part can't say anything: better to combine partials later
_MERGE_LIMIT_RATIO = 2  # models overrun word targets, and a merge cut off at the limit gains nothing
_MIN_STATEMENT_WORDS = 5  # shorter lines are labels, with nothing to look up


class SourceLocator(Protocol):
    def closest_chunk(self, statement: str, book_id: str, chapter_number: int) -> Chunk | None:
        """Find the chapter's passage nearest to a statement, or None if none is close enough."""
        ...


@dataclass(frozen=True)
class ChapterSummary:
    """A summary, and how it was made.

    Attributes:
        book_id: the book.
        book_title: its title.
        chapter_number: the chapter.
        chapter_title: its title.
        summary_type: brief, standard or any other type in the configuration.
        language: the language asked for, if any.
        text: the summary, with a references section built from what it cites.
        citations: the sources it cites.
        chunks_total: the chunks in the chapter.
        chunks_covered: the chunks in steps that finished, rather than being cut off by their
            token limit and losing the end of what they were given.
        strategy: direct, when the chapter fit in the context, or map_reduce.
        statements: the statements looked up.
        statements_without_source: those close to no passage of the chapter, which is where to
            look first for anything the model added.
        steps: how many inferences it took.
        incomplete_steps: steps cut off by their token limit, which may have lost content.
        verification: the verification step's report, if enabled.
        model: the model that wrote it.
        total_seconds: the whole operation.
    """

    book_id: str
    book_title: str
    chapter_number: int
    chapter_title: str
    summary_type: str
    language: str | None
    text: str
    citations: tuple[Citation, ...]
    chunks_total: int
    chunks_covered: int
    strategy: str
    statements: int
    statements_without_source: int
    steps: int
    incomplete_steps: int
    verification: str | None
    model: str
    total_seconds: float


class ChapterSummarizer:
    def __init__(
        self,
        settings: Settings,
        llm: LLMProvider,
        catalog: BookCatalog,
        chunks: ChunkSource,
        documents: SummaryDocuments,
        locator: SourceLocator,
    ) -> None:
        self._config = settings.generation.summarization
        self._llm_defaults = settings.llm
        self._safety_margin = settings.generation.context.safety_margin
        self._llm = llm
        self._catalog = catalog
        self._chunks = chunks
        self._documents = documents
        self._locator = locator

    def summary_types(self) -> list[str]:
        return list(self._config.types)

    def summarize(
        self,
        book_id: str,
        chapter_number: int,
        summary_type: str,
        language: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> ChapterSummary:
        """Summarize a chapter.

        Args:
            book_id: the book.
            chapter_number: the chapter, as a position in the book.
            summary_type: one of summary_types().
            language: the language to write in. None means the book's.
            on_progress: told what is happening, for long chapters.

        Raises:
            ChapterNotFoundError: the book has no such chapter.
            ConfigurationError: the summary type doesn't exist.
            GenerationError: the model produced no text at some step.
        """
        with operation(logger, "summarize_chapter", book_id=book_id, chapter=chapter_number, model=self._llm.model):
            return self._summarize(book_id, chapter_number, summary_type, language, on_progress)

    def _summarize(
        self,
        book_id: str,
        chapter_number: int,
        summary_type: str,
        language: str | None,
        on_progress: Callable[[str], None] | None,
    ) -> ChapterSummary:
        started = perf_counter()
        report = on_progress or (lambda message: None)
        style = self._config.types.get(summary_type)
        if style is None:
            raise ConfigurationError(f"There is no summary type '{summary_type}'. Options: {self.summary_types()}.")

        book = self._catalog.get(book_id)
        chunks = sorted(
            (
                chunk
                for chunk in self._chunks.load_chunks(book_id, book.revision)
                if chunk.chapter_number == chapter_number
            ),
            key=lambda chunk: chunk.chunk_index,
        )
        if not chunks:
            raise ChapterNotFoundError(f"{book_id} has no chapter {chapter_number}.")

        run = _Run(self._llm, book.language, language, chunks[0].chapter_title)
        sources = [chunk.text for chunk in chunks]
        final_tokens = style.max_tokens or self._config.max_tokens or self._llm_defaults.max_tokens

        def final_messages(material: str) -> list[Message]:
            return final_summary_messages(
                book.title, run.chapter, material, style.target_words, style.style, language, book.language
            )

        final_budget = self._budget(final_tokens) - self._frame_tokens(final_messages(""))
        whole = _PARTS_SEPARATOR.join(sources)
        if self._llm.count_tokens(whole) <= final_budget:
            strategy, material = "direct", whole
        else:
            strategy = "map_reduce"
            batches = self._batches(sources)
            max_words = self._partial_words(final_budget, len(batches))
            partials: list[str] = []
            for position, batch in enumerate(batches, start=1):
                report(f"Reading part {position} of {len(batches)}")
                partials.extend(self._map(run, batch, max_words))
            material = self._collapse(run, partials, final_budget, report)

        report("Writing the final summary")
        final = run.step(final_messages(material), self._parameters(final_tokens))

        report("Finding the sources of each statement")
        text = _clean_headings(final.text)
        cited_text, citations, statements, unsourced = self._cite(text, book_id, chapter_number, chunks)

        verification = None
        if self._config.verify_claims and citations:
            report("Checking the claims against the sources")
            verification = self._verify(run, final.text, citations, chunks)

        log_event(
            logger,
            "chapter summarized",
            chunks=len(chunks),
            lost_chunks=run.lost_sources,
            strategy=strategy,
            steps=run.steps,
            citations=len(citations),
        )
        return ChapterSummary(
            book_id=book_id,
            book_title=book.title,
            chapter_number=chapter_number,
            chapter_title=run.chapter,
            summary_type=summary_type,
            language=language,
            text=_with_references(cited_text, citations),
            citations=tuple(citations),
            chunks_total=len(chunks),
            chunks_covered=len(chunks) - run.lost_sources,
            strategy=strategy,
            statements=statements,
            statements_without_source=unsourced,
            steps=run.steps,
            incomplete_steps=run.incomplete_steps,
            verification=verification,
            model=self._llm.model,
            total_seconds=perf_counter() - started,
        )

    def save(self, summary: ChapterSummary) -> str:
        """Keep a summary with the book's other derived data, and return where it went."""
        name = f"chapter_{summary.chapter_number:02d}_{summary.summary_type}"
        metadata = {
            "book_title": summary.book_title,
            "chapter_title": summary.chapter_title,
            "summary_type": summary.summary_type,
            "language": summary.language,
            "model": summary.model,
            "strategy": summary.strategy,
            "statements": summary.statements,
            "statements_without_source": summary.statements_without_source,
            "chunks_total": summary.chunks_total,
            "chunks_covered": summary.chunks_covered,
            "steps": summary.steps,
            "incomplete_steps": summary.incomplete_steps,
            "verification": summary.verification,
        }
        return str(self._documents.save(summary.book_id, name, summary.text, metadata))

    def _budget(self, max_tokens: int) -> int:
        """How many tokens a prompt may take, after reserving the reply and a margin."""
        return int(self._llm.context_size() * (1 - self._safety_margin)) - max_tokens

    def _frame_tokens(self, messages: Sequence[Message]) -> int:
        return sum(self._llm.count_tokens(message.content) for message in messages)

    def _parameters(self, max_tokens: int) -> GenerationParameters:
        temperature = self._config.temperature
        return GenerationParameters(
            temperature=self._llm_defaults.temperature if temperature is None else temperature,
            max_tokens=max_tokens,
        )

    def _batches(self, sources: list[str]) -> list[list[str]]:
        """Group consecutive sources into batches that a reply can do justice to.

        The context window would hold far more, but the reply is what has to carry it all.
        """
        frame = self._frame_tokens(map_messages("", "", 0, None, None))
        available = self._budget(self._config.map_max_tokens) - frame
        budget = min(available, self._config.map_max_tokens * _MAP_INPUT_RATIO)
        batches: list[list[str]] = []
        current: list[str] = []
        tokens = 0
        for source in sources:
            cost = self._llm.count_tokens(source)
            if current and tokens + cost > budget:
                batches.append(current)
                current, tokens = [], 0
            current.append(source)
            tokens += cost
        if current:
            batches.append(current)
        return batches

    def _partial_words(self, final_budget: int, parts: int) -> int:
        """Size each part so that together they fit the final prompt, which spares a merging stage."""
        limit = int(self._config.map_max_tokens * _WORDS_PER_TOKEN)
        return max(_MIN_PARTIAL_WORDS, min(limit, int(final_budget / parts * _WORDS_PER_TOKEN)))

    def _map(self, run: "_Run", batch: list[str], max_words: int) -> list[str]:
        """Summarize a batch. A reply cut off by its limit lost the end of it, so it is redone in halves."""
        messages = map_messages(run.chapter, _PARTS_SEPARATOR.join(batch), max_words, run.language, run.book_language)
        parameters = self._parameters(self._config.map_max_tokens)
        generation = run.step(messages, parameters, retried_if_cut_off=len(batch) > 1)
        if generation.stats.finish_reason != FINISHED_BY_LENGTH:
            return [generation.text]
        if len(batch) == 1:
            run.lost_sources += 1
            return [generation.text]
        middle = len(batch) // 2
        return self._map(run, batch[:middle], max_words) + self._map(run, batch[middle:], max_words)

    def _collapse(self, run: "_Run", partials: list[str], budget: int, report: Callable[[str], None]) -> str:
        """Merge partial summaries until they fit in the final prompt."""
        material = _PARTS_SEPARATOR.join(partials)
        while self._llm.count_tokens(material) > budget:
            report(f"Combining {len(partials)} partial summaries")
            merged: list[str] = []
            for start in range(0, len(partials), _COLLAPSE_FAN_IN):
                merged.extend(self._merge(run, partials[start : start + _COLLAPSE_FAN_IN]))
            if len(merged) >= len(partials):
                raise GenerationError("The partial summaries are too long to combine in this context window.")
            partials = merged
            material = _PARTS_SEPARATOR.join(partials)
        return material

    def _merge(self, run: "_Run", partials: list[str]) -> list[str]:
        """Merge a few partial summaries. A reply that gets cut off would lose the last of them."""
        if len(partials) == 1:
            return partials
        max_tokens = self._config.map_max_tokens
        messages = collapse_messages(
            run.chapter,
            _PARTS_SEPARATOR.join(partials),
            int(max_tokens * _WORDS_PER_TOKEN),
            run.language,
            run.book_language,
        )
        parameters = self._parameters(max_tokens * _MERGE_LIMIT_RATIO)
        generation = run.step(messages, parameters, retried_if_cut_off=True)
        if generation.stats.finish_reason != FINISHED_BY_LENGTH:
            return [generation.text]
        middle = len(partials) // 2
        return self._merge(run, partials[:middle]) + self._merge(run, partials[middle:])

    def _cite(
        self, summary: str, book_id: str, chapter_number: int, chunks: list[Chunk]
    ) -> tuple[str, list[Citation], int, int]:
        """Look each statement up among the chapter's chunks, and cite the passage it resembles.

        Returns:
            The text with its citations, the sources cited, how many statements were looked
            up, and how many of them have no source.
        """
        numbers = {chunk.chunk_id: number for number, chunk in enumerate(chunks, start=1)}
        cited: dict[int, Citation] = {}
        statements = 0
        unsourced = 0

        def cite(statement: str) -> str:
            nonlocal statements, unsourced
            if len(statement.split()) < _MIN_STATEMENT_WORDS:
                return statement
            statements += 1
            chunk = self._locator.closest_chunk(statement, book_id, chapter_number)
            if chunk is None:
                unsourced += 1
                return statement
            number = numbers[chunk.chunk_id]
            cited.setdefault(number, citation_for(number, chunk))
            return f"{statement} [{number}]"

        lines = [_cite_line(line, cite) for line in summary.splitlines()]
        return "\n".join(lines), [cited[number] for number in sorted(cited)], statements, unsourced

    def _verify(self, run: "_Run", summary: str, citations: list[Citation], chunks: list[Chunk]) -> str:
        """Check the summary against the passages it cites, as many of them as fit."""
        max_tokens = self._config.map_max_tokens
        budget = self._budget(max_tokens) - self._frame_tokens(verification_messages(summary, ""))
        cited: list[str] = []
        for citation in citations:
            source = chunks[citation.number - 1].text
            budget -= self._llm.count_tokens(source)
            if budget < 0:
                break
            cited.append(source)
        return run.step(verification_messages(summary, "\n\n".join(cited)), self._parameters(max_tokens)).text


class _Run:
    """What one summary needs at every step, and the counts of how they went."""

    def __init__(self, llm: LLMProvider, book_language: str | None, language: str | None, chapter: str) -> None:
        self._llm = llm
        self.book_language = book_language
        self.language = language
        self.chapter = chapter
        self.steps = 0
        self.incomplete_steps = 0
        self.lost_sources = 0

    def step(
        self, messages: Sequence[Message], parameters: GenerationParameters, retried_if_cut_off: bool = False
    ) -> Generation:
        """Run one inference.

        Args:
            messages: the prompt.
            parameters: temperature and limit.
            retried_if_cut_off: the caller redoes this step if the reply hits the limit.
        """
        generation = self._llm.generate(messages, parameters)
        self.steps += 1
        cut_off = generation.stats.finish_reason == FINISHED_BY_LENGTH
        if cut_off and retried_if_cut_off:
            return generation
        if cut_off:
            self.incomplete_steps += 1
        if not generation.text.strip():
            raise GenerationError(
                "The model produced no text for a step of the summary. Its token limit may have gone "
                "to reasoning: raise the limits in config/generation.yaml."
            )
        return generation


def _clean_headings(text: str) -> str:
    """Undo the bold that some replies wrap around a heading, which shows its # marks as text."""
    return _BOLD_HEADING.sub(lambda match: f"{match.group(1).strip()}\n\n{match.group(2).strip()}".strip(), text)


def _cite_line(line: str, cite: Callable[[str], str]) -> str:
    """Add citations to one line of Markdown, leaving its headings and list markers alone."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return line
    indent = line[: len(line) - len(line.lstrip())]
    marker, body = _split_list_marker(stripped)
    return indent + marker + " ".join(cite(sentence) for sentence in split_sentences(body))


def _split_list_marker(text: str) -> tuple[str, str]:
    head, _, rest = text.partition(" ")
    if rest and (head in ("-", "*", "+") or (head.endswith(".") and head[:-1].isdigit())):
        return f"{head} ", rest
    return "", text


def _with_references(text: str, citations: Sequence[Citation]) -> str:
    if not citations:
        return text
    lines = []
    for citation in citations:
        place = ", ".join(part for part in (citation.section_title, citation.pages) if part)
        lines.append(f"- [{citation.number}] " + (f"{place}: " if place else "") + f"“{citation.excerpt}”")
    return f"{text.rstrip()}\n\n## References\n\n" + "\n".join(lines)
