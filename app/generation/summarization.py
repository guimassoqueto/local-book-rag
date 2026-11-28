"""Chapter summaries, by map-reduce over the whole chapter.

Retrieval doesn't pick what gets summarized: the top passages for "summarize this" are whatever
happens to resemble that phrase, and they leave out most of a chapter. Every chunk goes through
here.

Citations are computed, not claimed. Models don't carry source tags through several rounds of
summarizing: the ones tested count upward, or drop them. So each statement of the finished
summary is looked up among the chapter's chunks, and cites the passage it actually resembles.
This works the same for every model.
"""

import logging
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any, Protocol

from app.config.settings import Settings, SummaryTypeConfig
from app.errors import BookRagError, ChapterNotFoundError, ConfigurationError, GenerationError
from app.generation.base import (
    FINISHED_BY_LENGTH,
    Attempt,
    Generation,
    GenerationParameters,
    LLMProvider,
    Message,
)
from app.generation.choices import ModelChoices, failed_attempt, moves_on
from app.generation.citations import Citation, citation_for
from app.generation.prompts import (
    collapse_messages,
    final_summary_messages,
    map_messages,
    verification_messages,
)
from app.ingestion.chunker import Chunk, split_sentences
from app.retrieval.bm25 import ChunkSource
from app.storage.catalog import Book, BookCatalog
from app.storage.repositories import SummaryDocuments
from app.utils.logging import get_logger, log_event, operation

logger = get_logger("generation.summaries")

_BOLD_HEADING = re.compile(r"^\s*\*\*\s*(#{1,6}\s[^*\n]+?)\s*\*\*[ \t]*(.*)$", re.MULTILINE)
_REFERENCES = "\n\n## References\n\n"
_COLLAPSE_FAN_IN = 3  # merging everything at once would squeeze a long chapter into one reply
_PARTS_SEPARATOR = "\n\n---\n\n"
_MAP_INPUT_RATIO = 4  # how many tokens of text a reply of one token can do justice to
_WORDS_PER_TOKEN = 0.6  # leaves part of the limit to reasoning, and stays well within the rest
_MIN_PARTIAL_WORDS = 150  # below this, a part can't say anything: better to combine partials later
_MERGE_LIMIT_RATIO = 2  # models overrun word targets, and a merge cut off at the limit gains nothing
_MIN_ROUND_SHRINK = 0.9  # what a round of merges has to leave, at most, of what it was given
_MIN_STATEMENT_WORDS = 5  # shorter lines are labels, with nothing to look up
# A downloaded summary's name leaves room for its folder: Windows' paths stop at 260 characters by
# default, and most file systems take 255 bytes for a name.
_FILE_NAME_LIMIT = 100


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
        model: the model that wrote it, alone (FR-019), as its provider reported it.
        total_seconds: the whole operation.
        provider: the model's provider.
        attempts: the models that failed before it, each with the tokens of the steps it finished.
        prompt_tokens: the tokens its steps read, added up.
        completion_tokens: the tokens its steps generated, reasoning included, added up.
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
    provider: str
    attempts: tuple[Attempt, ...] = ()
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class SummaryFile:
    """A summary as a Markdown file of its own, which the Summarization tab downloads.

    Attributes:
        name: the file's name, with `.md`: the book, the chapter, the type and the language asked for.
        text: a title naming the book and the chapter, a line naming the type, the summary as the tab
            shows it, and a closing note naming the model that wrote it.
    """

    name: str
    text: str


class ChapterSummarizer:
    def __init__(
        self,
        settings: Settings,
        models: ModelChoices,
        catalog: BookCatalog,
        chunks: ChunkSource,
        documents: SummaryDocuments,
        locator: SourceLocator,
    ) -> None:
        self._config = settings.generation.summarization
        self._llm_defaults = settings.llm
        self._safety_margin = settings.generation.context.safety_margin
        self._models = models
        self._catalog = catalog
        self._chunks = chunks
        self._documents = documents
        self._locator = locator

    def summary_types(self) -> list[str]:
        return list(self._config.types)

    def cloud_written(self, provider: str | None) -> bool:
        """Whether a saved summary's provider is a cloud one, configured now or not."""
        return self._models.is_cloud_provider(provider)

    def label_of(self, provider: str) -> str:
        return self._models.label_of(provider)

    def summarize(
        self,
        book_id: str,
        chapter_number: int,
        summary_type: str,
        language: str | None = None,
        on_progress: Callable[[str], None] | None = None,
        model: str | None = None,
        fallbacks: Sequence[str] = (),
    ) -> ChapterSummary:
        """Summarize a chapter.

        Each model of the sequence makes the whole summary, until one finishes: when a step
        fails, the summary starts again from its first step with the next model (FR-019).

        Args:
            book_id: the book.
            chapter_number: the chapter, as a position in the book.
            summary_type: one of summary_types().
            language: the language to write in. None means the book's.
            on_progress: told what is happening, for long chapters, failures included.
            model: the model picked for the summary. None means the local model.
            fallbacks: the cloud models to ask, in order, if it fails, before the local model.

        Raises:
            ModelChoiceError: the sequence is refused, before the chapter is read.
            ChapterNotFoundError: the book has no such chapter.
            ConfigurationError: the summary type doesn't exist.
            AllModelsFailedError: the local model failed after other models did.
            GenerationError: the local model, asked alone, produced no text at some step.
        """
        sequence = self._models.sequence(model, fallbacks)
        with operation(logger, "summarize_chapter", book_id=book_id, chapter=chapter_number, model=sequence[0].model):
            return self._summarize(book_id, chapter_number, summary_type, language, on_progress, sequence)

    def _summarize(
        self,
        book_id: str,
        chapter_number: int,
        summary_type: str,
        language: str | None,
        on_progress: Callable[[str], None] | None,
        sequence: Sequence[LLMProvider],
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

        attempts: list[Attempt] = []
        for position, llm in enumerate(sequence, start=1):
            run = _Run(llm, book.language, language, chunks[0].chapter_title)
            try:
                summary = self._write(run, book, chunks, summary_type, style, report)
            except BookRagError as exc:
                last = position == len(sequence)
                if (last and not attempts) or not (last or moves_on(exc)):
                    raise
                attempt = failed_attempt(llm, exc, run.steps, run.prompt_tokens, run.completion_tokens)
                attempts.append(attempt)
                log_event(
                    logger,
                    "model failed",
                    logging.WARNING,
                    provider=attempt.provider,
                    model=attempt.model,
                    reason=attempt.reason.value,
                    position=position,
                )
                if last:
                    raise self._models.all_failed(attempts, exc) from exc
                described = attempt.describe(self._models.label_of(attempt.provider))
                report(f"{described} Starting again with {sequence[position].model}.")
                continue

            tokens: dict[str, Any] = {}
            if self._models.is_cloud_provider(llm.provider):
                tokens = {"prompt_tokens": run.prompt_tokens, "completion_tokens": run.completion_tokens}
            log_event(
                logger,
                "chapter summarized",
                chunks=len(chunks),
                lost_chunks=run.lost_sources,
                strategy=summary.strategy,
                steps=run.steps,
                citations=len(summary.citations),
                # The operation's own model is the first one asked, which a fallback may have replaced.
                model=summary.model,
                provider=llm.provider,
                failed_attempts=len(attempts),
                **tokens,
            )
            return replace(summary, attempts=tuple(attempts), total_seconds=perf_counter() - started)
        raise AssertionError("a sequence always ends with the local model")

    def _write(
        self,
        run: "_Run",
        book: Book,
        chunks: list[Chunk],
        summary_type: str,
        style: SummaryTypeConfig,
        report: Callable[[str], None],
    ) -> ChapterSummary:
        """One model's whole summary: its budgets, counts and steps are the run's model's."""
        book_id, chapter_number, language = book.book_id, chunks[0].chapter_number, run.language
        sources = [chunk.text for chunk in chunks]
        final_tokens = style.max_tokens or self._config.max_tokens or self._llm_defaults.max_tokens

        def final_messages(material: str) -> list[Message]:
            return final_summary_messages(
                book.title, run.chapter, material, style.target_words, style.style, language, book.language
            )

        final_budget = self._budget(run, final_tokens) - self._frame_tokens(run, final_messages(""))
        whole = _PARTS_SEPARATOR.join(sources)
        if run.llm.count_tokens(whole) <= final_budget:
            strategy, material = "direct", whole
        else:
            strategy = "map_reduce"
            batches = self._batches(run, sources)
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
            model=final.stats.model,
            total_seconds=0.0,
            provider=run.llm.provider,
            prompt_tokens=run.prompt_tokens,
            completion_tokens=run.completion_tokens,
        )

    def save(self, summary: ChapterSummary) -> str:
        """Keep a summary with the book's other derived data, and return where it went.

        Its JSON file records the provider and the failed attempts always, and the tokens of a
        cloud model's attempts, which were billed (FR-022).
        """
        name = f"chapter_{summary.chapter_number:02d}_{summary.summary_type}"
        metadata: dict[str, Any] = {
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
            "provider": summary.provider,
            "failed_attempts": [self._attempt_record(attempt) for attempt in summary.attempts],
        }
        if self._models.is_cloud_provider(summary.provider):
            metadata["tokens"] = {"read": summary.prompt_tokens, "generated": summary.completion_tokens}
        return str(self._documents.save(summary.book_id, name, summary.text, metadata))

    def _attempt_record(self, attempt: Attempt) -> dict[str, Any]:
        record: dict[str, Any] = {
            "model": attempt.model,
            "provider": attempt.provider,
            "reason": attempt.reason.value,
            "detail": attempt.detail,
            "step": attempt.step,
        }
        if self._models.is_cloud_provider(attempt.provider):
            record["tokens"] = {"read": attempt.prompt_tokens, "generated": attempt.completion_tokens}
        return record

    def summary_file(self, summary: ChapterSummary) -> SummaryFile:
        """The summary as a Markdown file to download, made from the summary alone.

        It reads no book, no chunk and no model, and writes nothing. Once downloaded, the file has
        left the tab's report behind, so its closing note names the model that wrote it, after a
        rule, which reads as a footnote in every viewer. It names only that model: a summary is
        written by one model, which starts again from the first step when another fails.
        """
        if self._models.is_cloud_provider(summary.provider):
            origin = f"a cloud model from {self._models.label_of(summary.provider)}"
        else:
            origin = "a local model"
        blocks = (
            _file_title(summary),
            _type_line(summary),
            summary.text.strip(),
            "---",
            f"Written by `{summary.model}`, {origin}.",
        )
        return SummaryFile(_file_name(summary), "\n\n".join(blocks) + "\n")

    def _budget(self, run: "_Run", max_tokens: int) -> int:
        """How many tokens a prompt may take in the run's model, after reserving the reply and a margin."""
        return int(run.llm.context_size() * (1 - self._safety_margin)) - max_tokens

    def _frame_tokens(self, run: "_Run", messages: Sequence[Message]) -> int:
        return sum(run.llm.count_tokens(message.content) for message in messages)

    def _parameters(self, max_tokens: int) -> GenerationParameters:
        temperature = self._config.temperature
        return GenerationParameters(
            temperature=self._llm_defaults.temperature if temperature is None else temperature,
            max_tokens=max_tokens,
        )

    def _batches(self, run: "_Run", sources: list[str]) -> list[list[str]]:
        """Group consecutive sources into batches that a reply can do justice to.

        The context window would hold far more, but the reply is what has to carry it all.
        """
        frame = self._frame_tokens(run, map_messages("", "", 0, None, None))
        available = self._budget(run, self._config.map_max_tokens) - frame
        budget = min(available, self._config.map_max_tokens * _MAP_INPUT_RATIO)
        batches: list[list[str]] = []
        current: list[str] = []
        tokens = 0
        for source in sources:
            cost = run.llm.count_tokens(source)
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
        """Merge partial summaries until they fit in the final prompt.

        A model can merge three parts into a text as long as all three, so progress is measured in
        tokens, and a part left on its own is condensed. A round that doesn't take a tenth off what
        is left halves the length the next one asks for: models overrun it, some by twice. When
        rounds at the shortest length stop condensing too, the summary ends: more would only take time.
        """
        material = _PARTS_SEPARATOR.join(partials)
        size = run.llm.count_tokens(material)
        share = 1.0  # of the length the parts could have, what the merges ask for
        while size > budget:
            report(f"Combining {len(partials)} partial summaries")
            groups = self._groups(run, partials)
            words = max(_MIN_PARTIAL_WORDS, int(self._partial_words(budget, len(groups)) * share))
            partials = [merged for group in groups for merged in self._merge(run, group, words)]
            material = _PARTS_SEPARATOR.join(partials)
            previous, size = size, run.llm.count_tokens(material)
            if size > budget and size > previous * _MIN_ROUND_SHRINK:
                if words <= _MIN_PARTIAL_WORDS:
                    raise GenerationError("The partial summaries are too long to combine in this context window.")
                share /= 2
        return material

    def _groups(self, run: "_Run", partials: list[str]) -> list[list[str]]:
        """Consecutive partials, a few at a time, as many as one prompt holds with room for the reply."""
        frame = self._frame_tokens(run, collapse_messages("", "", 0, None, None))
        budget = self._budget(run, self._merge_limit()) - frame
        groups: list[list[str]] = []
        tokens = 0
        for partial in partials:
            cost = run.llm.count_tokens(partial)
            if groups and len(groups[-1]) < _COLLAPSE_FAN_IN and tokens + cost <= budget:
                groups[-1].append(partial)
                tokens += cost
            else:
                groups.append([partial])
                tokens = cost
        return groups

    def _merge(self, run: "_Run", partials: list[str], words: int) -> list[str]:
        """Merge a few partials, or condense one. A reply cut off at its limit would lose their end.

        A reply no shorter than what it was given gains nothing, and only rewords: the parts stay.
        """
        merged = _PARTS_SEPARATOR.join(partials)
        messages = collapse_messages(run.chapter, merged, words, run.language, run.book_language)
        generation = run.step(messages, self._parameters(self._merge_limit()), retried_if_cut_off=True)
        if generation.stats.finish_reason != FINISHED_BY_LENGTH:
            if run.llm.count_tokens(generation.text) >= run.llm.count_tokens(merged):
                return partials
            return [generation.text]
        if len(partials) == 1:
            return partials
        middle = len(partials) // 2
        return self._merge(run, partials[:middle], words) + self._merge(run, partials[middle:], words)

    def _merge_limit(self) -> int:
        return self._config.map_max_tokens * _MERGE_LIMIT_RATIO

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
        budget = self._budget(run, max_tokens) - self._frame_tokens(run, verification_messages(summary, ""))
        cited: list[str] = []
        for citation in citations:
            source = chunks[citation.number - 1].text
            budget -= run.llm.count_tokens(source)
            if budget < 0:
                break
            cited.append(source)
        return run.step(verification_messages(summary, "\n\n".join(cited)), self._parameters(max_tokens)).text


class _Run:
    """What one model's summary needs at every step, and the counts of how they went.

    Attributes:
        llm: the model that makes the whole summary; its window sets every budget.
        steps: the steps begun, the failing one included.
        prompt_tokens: what the steps that returned read, added up, since they were billed.
        completion_tokens: what they generated.
    """

    def __init__(self, llm: LLMProvider, book_language: str | None, language: str | None, chapter: str) -> None:
        self.llm = llm
        self.book_language = book_language
        self.language = language
        self.chapter = chapter
        self.steps = 0
        self.incomplete_steps = 0
        self.lost_sources = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def step(
        self, messages: Sequence[Message], parameters: GenerationParameters, retried_if_cut_off: bool = False
    ) -> Generation:
        """Run one inference.

        Args:
            messages: the prompt.
            parameters: temperature and limit.
            retried_if_cut_off: the caller redoes this step if the reply hits the limit.
        """
        self.steps += 1
        generation = self.llm.generate(messages, parameters)
        self.prompt_tokens += generation.stats.prompt_tokens
        self.completion_tokens += generation.stats.completion_tokens
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
        place = f"{citation.section_title}: " if citation.section_title else ""
        lines.append(f"- [{citation.number}] {place}“{citation.excerpt}”")
    return f"{text.rstrip()}{_REFERENCES}" + "\n".join(lines)


def without_references(text: str) -> str:
    """A summary as the model wrote it. The references quote the book, which the model didn't write."""
    return text.split(_REFERENCES)[0]


def _file_title(summary: ChapterSummary) -> str:
    """The titles go in as the catalog holds them: a title made from a file name, such as
    `02_a_era_das_revolucoes`, renders as written, since an underscore between letters isn't
    emphasis."""
    title = f"# {summary.book_title}, chapter {summary.chapter_number}"
    return f"{title}: {summary.chapter_title}" if summary.chapter_title else title


def _type_line(summary: ChapterSummary) -> str:
    kind = f"{summary.summary_type[:1].upper()}{summary.summary_type[1:]} summary"
    return f"{kind}, in {summary.language}." if summary.language else f"{kind}."


def _file_name(summary: ChapterSummary) -> str:
    """`<book>_chapter_<NN>_<type>[_<language>].md`, a name every system takes.

    Underscores separate the parts and hyphens the words. A name over the limit loses the end of
    its book part, at a word when it can: the chapter, the type and the language are what tell one
    book's summaries apart.
    """
    parts = [f"chapter_{summary.chapter_number:02d}", _safe_name_part(summary.summary_type)]
    if summary.language:
        parts.append(_safe_name_part(summary.language))
    rest = "_" + "_".join(parts) + ".md"
    book = _safe_name_part(summary.book_title) or _safe_name_part(summary.book_id)
    room = max(_FILE_NAME_LIMIT - len(rest), 1)
    if len(book) > room:
        cut = book[:room]
        if book[room] != "-" and "-" in cut:
            cut = cut[: cut.rindex("-")]
        book = cut.rstrip("-")
    return book + rest


def _safe_name_part(text: str) -> str:
    """Lowercase words of letters and digits in any script, and the marks that combine with them,
    joined by hyphens. NFC keeps an accented letter one character, however its title was typed."""
    text = unicodedata.normalize("NFC", text.lower())
    kept = "".join(c if c.isalnum() or unicodedata.category(c).startswith("M") else " " for c in text)
    return "-".join(kept.split())
