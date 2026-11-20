"""Turns results into what the interface shows. Nothing here touches Gradio or a service."""

import html
import math
from collections.abc import Sequence

from app.generation.base import GenerationStats, Message
from app.generation.citations import Citation
from app.generation.question_answering import Answer
from app.generation.summarization import ChapterSummary
from app.retrieval.base import Passage
from app.services.library_service import ReindexReport
from app.storage.catalog import Book, IndexRecord
from app.utils.gpu import GpuStatus
from app.utils.ollama_runtime import LoadedModel
from app.utils.progress import ProgressView, StageView

ALL_CHAPTERS = -1

BOOK_COLUMNS = [
    "ID",
    "Title",
    "Author",
    "Format",
    "Lang",
    "Chapters",
    "Chunks",
    "Status",
    "Embedding model",
    "Index",
    "Added",
    "Indexed",
    "Details",
]
BOOK_COLUMN_WIDTHS = [90, 260, 170, 90, 60, 90, 80, 110, 190, 70, 150, 150, 300]
SCORE_COLUMNS = ["In context", "Chunk", "Chapter", "Dense", "BM25", "Fusion", "Reranker"]


def book_rows(books: Sequence[Book]) -> list[list[object]]:
    return [
        [
            book.book_id,
            book.title,
            book.author or "",
            book.format,
            book.language or "",
            book.chapter_count,
            book.chunk_count,
            book.status.value,
            book.embedding_model or "",
            f"v{book.index_version}" if book.index_version else "",
            _minutes(book.created_at),
            _minutes(book.indexed_at),
            book.status_detail or "",
        ]
        for book in books
    ]


def _minutes(timestamp: str | None) -> str:
    return timestamp[:16].replace("T", " ") if timestamp else ""


def book_choices(books: Sequence[Book]) -> list[tuple[str, str]]:
    return [(f"{book.book_id} · {book.title}", book.book_id) for book in books]


def chapter_choices(chapters: Sequence[tuple[int, str]], include_all: bool = True) -> list[tuple[str, int]]:
    choices = [(title, number) for number, title in chapters]
    return [("All chapters", ALL_CHAPTERS), *choices] if include_all else choices


def index_status(active: IndexRecord | None, needs_reindex: bool) -> str:
    if active is None:
        return "No index yet: the first book creates it."
    description = f"Index **v{active.version}** in `{active.collection}`, built with `{active.embedding_model}`."
    if needs_reindex:
        return (
            f"⚠️ {description} The embedding or chunking configuration no longer matches it. New books are "
            "refused until you run **Reindex the library**. Questions keep working on the current index."
        )
    return description


def sources_markdown(answer: Answer) -> str:
    """List the sources an answer cites, and what the reader should distrust about it."""
    lines = [f"- **[{citation.number}]** {citation.reference}" for citation in answer.citations]
    notes = []
    if answer.insufficient_evidence:
        notes.append("The model found no answer in the selected books.")
    elif not answer.citations:
        notes.append("⚠️ This answer cites no source.")
    if answer.invented_citations:
        numbers = ", ".join(str(number) for number in answer.invented_citations)
        notes.append(f"⚠️ The model cited sources that don't exist: {numbers}.")
    return "\n".join([*lines, *(f"\n{note}" for note in notes)])


def passages_markdown(passages: Sequence[Passage], citations: Sequence[Citation]) -> str:
    """Show the original text of each passage the model was given."""
    cited = {citation.number for citation in citations}
    sections = []
    for number, passage in enumerate(passages, start=1):
        chunk = passage.chunk
        place = [chunk.book_title, chunk.chapter_title, chunk.section_title]
        mark = " · cited" if number in cited else ""
        quoted = "\n".join(f"> {line}" if line else ">" for line in chunk.text.splitlines())
        title = ", ".join(part for part in place if part)
        sections.append(f"**[{number}]** {title}{mark}\n\n{quoted}")
    return "\n\n".join(sections) if sections else "No passages."


def timing_markdown(answer: Answer) -> str:
    timing = f"Answered in **{answer.total_seconds:.1f} s**"
    if answer.generation is None:
        return timing
    stats = answer.generation.stats
    return f"{timing} · {stats.completion_tokens} tokens at {stats.tokens_per_second:.0f} tokens/s"


def score_rows(answer: Answer) -> list[list[object]]:
    """List every candidate the search considered, best first, with the score of each stage."""
    in_context = {passage.chunk.chunk_id: number for number, passage in enumerate(answer.passages, start=1)}
    return [
        [
            f"[{in_context[passage.chunk.chunk_id]}]" if passage.chunk.chunk_id in in_context else "",
            passage.chunk.chunk_id,
            passage.chunk.chapter_title,
            _score(passage.dense_score),
            _score(passage.bm25_score),
            _score(passage.fusion_score),
            _score(passage.rerank_score),
        ]
        for passage in sorted(answer.retrieval.candidates, key=_rank, reverse=True)
    ]


def _rank(passage: Passage) -> float:
    for score in (passage.rerank_score, passage.fusion_score, passage.dense_score, passage.bm25_score):
        if score is not None:
            return score
    return 0.0


def _score(value: float | None) -> str:
    return "" if value is None else f"{value:.3f}"


def run_markdown(answer: Answer, llm: str, embedding: str, reranker: str) -> str:
    """Report a question's models, counts and timings."""
    retrieval = answer.retrieval
    lines = [
        "| Measure | Value |",
        "| --- | --- |",
        f"| LLM | `{llm}` |",
        f"| Embedding model | `{embedding}` |",
        f"| Reranker | `{reranker}` |",
        f"| Candidates retrieved | {len(retrieval.candidates)} |",
        f"| Passages in the context | {len(answer.passages)} of {len(retrieval.passages)} selected |",
        f"| Retrieval | {retrieval.retrieval_seconds:.2f} s |",
        f"| Reranking | {retrieval.rerank_seconds:.2f} s |",
    ]
    if answer.generation is not None:
        lines.extend(_generation_rows(answer.generation.stats))
    lines.append(f"| Total | {answer.total_seconds:.2f} s |")
    return "\n".join(lines)


def _generation_rows(stats: GenerationStats) -> list[str]:
    return [
        f"| Prompt tokens | {stats.prompt_tokens} |",
        f"| Generated tokens | {stats.completion_tokens} |",
        f"| Time to first token | {stats.time_to_first_token:.2f} s |",
        f"| Generation speed | {stats.tokens_per_second:.1f} tokens/s |",
        f"| Model loading | {stats.load_seconds:.2f} s |",
        f"| Prompt processing | {stats.prompt_seconds:.2f} s |",
        f"| Generation | {stats.generation_seconds:.2f} s |",
        f"| Finished because | {stats.finish_reason} |",
    ]


def gpu_markdown(gpu: GpuStatus | None, loaded: Sequence[LoadedModel]) -> str:
    if gpu is None:
        return "No GPU is visible to the application."
    lines = [f"**{gpu.name}**: {gpu.memory_used_mb} of {gpu.memory_total_mb} MiB in use."]
    for model in loaded:
        size = f"{model.size_bytes / 1e9:.1f} GB"
        lines.append(f"- `{model.name}`: {size}, {model.gpu_fraction:.0%} on the GPU, context {model.context_length}")
    if not loaded:
        lines.append("No model is loaded in Ollama.")
    return "\n".join(lines)


def prompt_text(messages: Sequence[Message]) -> str:
    return "\n\n".join(f"=== {message.role} ===\n{message.content}" for message in messages)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def summary_report(summary: ChapterSummary) -> str:
    """Say how a summary was made, and what the reader should distrust about it."""
    lines = [
        f"Read **{summary.chunks_covered} of {summary.chunks_total}** chunks of the chapter, "
        f"in {_count(summary.steps, 'step')} and {summary.total_seconds:.0f} s "
        f"({summary.strategy}, `{summary.model}`). Cites {_count(len(summary.citations), 'passage')}."
    ]
    lost = summary.chunks_total - summary.chunks_covered
    if lost:
        lines.append(f"⚠️ {_count(lost, 'chunk')} cut off by the token limit.")
    if summary.incomplete_steps:
        steps = _count(summary.incomplete_steps, "step")
        lines.append(f"⚠️ {steps} hit the token limit: raise it in the configuration.")
    if summary.statements_without_source:
        statements = _count(summary.statements_without_source, "statement")
        lines.append(f"⚠️ {statements} resembling no passage of the chapter: check those first.")
    if summary.verification:
        lines.append(f"**Claim check:** {summary.verification}")
    return "\n\n".join(lines)


# The progress of library operations (specs/004-library-progress). The services report the stages,
# counts and times left; these only write them in the forms of FR-002.

# Scoped to the progress area by Gradio. A JavaScript template string: no dollar-brace in here.
PROGRESS_CSS = """
.progress { display: flex; flex-direction: column; gap: 4px; padding: 8px 0; }
.progress .head { display: flex; justify-content: space-between; gap: 12px; }
.progress .elapsed { font-variant-numeric: tabular-nums; opacity: 0.8; }
.progress .detail, .progress .meanwhile { opacity: 0.8; font-size: 0.95em; }
.progress progress { width: 100%; height: 10px; }
.progress.failed { color: var(--error-text-color, #b91c1c); }
"""


def elapsed_text(seconds: float) -> str:
    """0:38, or 1:02:05 past an hour."""
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def time_left_text(seconds: float) -> str:
    """Under a minute, rounded up to 5 s; from a minute on, to the nearest minute; "almost done" at zero."""
    if seconds <= 0:
        return "almost done"
    if seconds < 60:
        return f"about {max(5, math.ceil(seconds / 5) * 5)} s left"
    return f"about {round(seconds / 60)} min left"


def _position(stage: StageView, kind: str) -> str | None:
    return f"{kind} {stage.position} of {stage.stages}" if stage.position is not None else None


def _count_text(stage: StageView) -> str | None:
    if stage.total is None or stage.done is None:
        return None
    return f"{stage.done} of {stage.total} {stage.unit}" if stage.unit else f"{stage.done} of {stage.total}"


def _stage_parts(stage: StageView, kind: str) -> list[str]:
    """The stage as the commands write it: position, label, count, time left, note."""
    parts = [part for part in (_position(stage, kind), stage.label, _count_text(stage)) if part]
    if stage.time_left is not None:
        parts.append(time_left_text(stage.time_left))
    if stage.note:
        parts.append(stage.note)
    return parts


def _head(view: ProgressView) -> str:
    return f"{view.operation}, {view.subject}" if view.subject else view.operation


def _lower_first(label: str) -> str:
    return label[:1].lower() + label[1:]


def progress_text(view: ProgressView) -> str:
    """One line for the commands' error stream."""
    prefix = f"[{elapsed_text(view.elapsed)}] {_head(view)}"
    if view.outcome is not None:
        if view.outcome.succeeded:
            return f"{prefix}: done"
        return f"{prefix}: failed{_where(view)}"
    if view.stage is None:
        return f"{prefix}: starting"
    line = f"{prefix}: " + ", ".join(_stage_parts(view.stage, "stage"))
    if view.step is not None:
        line += ": " + ", ".join(_stage_parts(view.step, "step"))
    return line


def _where(view: ProgressView) -> str:
    """Where a failed operation stopped: " while embedding the chunks", and the book of a reindex."""
    outcome = view.outcome
    if outcome is None or outcome.stage is None:
        return ""
    where = f" while {_lower_first(outcome.stage)}"
    if outcome.item:
        where += f", at {outcome.item}"
    if outcome.step:
        where += f", while {_lower_first(outcome.step)}"
    return where


def failed_line(view: ProgressView) -> str:
    """Failed after 0:15, while embedding the chunks: Ollama is down."""
    where = _where(view)
    error = view.outcome.error if view.outcome else None
    return f"Failed after {elapsed_text(view.elapsed)}{',' + where if where else ''}: {error}"


def _bar(stage: StageView) -> str:
    if stage.total is None or stage.done is None:
        return "<progress></progress>"
    if stage.total == 0:
        return '<progress value="1" max="1"></progress>'
    return f'<progress value="{stage.done}" max="{stage.total}"></progress>'


def _stage_html(stage: StageView, kind: str) -> str:
    """A stage, or a step: its name and position, its bar, and its count, time left and note."""
    title = " — ".join(part for part in (stage.label, _position(stage, kind)) if part)
    detail = [part for part in (_count_text(stage),) if part]
    if stage.time_left is not None:
        detail.append(time_left_text(stage.time_left))
    if stage.note:
        detail.append(stage.note)
    lines = [f'<div class="line">{html.escape(title)}</div>', _bar(stage)]
    if detail:
        lines.append(f'<div class="detail">{html.escape(" · ".join(detail))}</div>')
    return "".join(lines)


def progress_html(view: ProgressView | None) -> str:
    """The progress area while an operation runs, or its failure once it has failed. Empty before it begins."""
    if view is None:
        return ""
    if view.outcome is not None and not view.outcome.succeeded:
        return outcome_html(failed_line(view), succeeded=False)
    head = html.escape(view.operation) + (f" · {html.escape(view.subject)}" if view.subject else "")
    parts = [
        f'<div class="head"><strong>{head}</strong><span class="elapsed">{elapsed_text(view.elapsed)}</span></div>'
    ]
    if view.stage is not None:
        parts.append(_stage_html(view.stage, "stage"))
    if view.step is not None:
        parts.append(_stage_html(view.step, "step"))
    if view.stage is None:
        parts.append("<progress></progress>")
    if view.meanwhile:
        parts.append(f'<div class="meanwhile">{html.escape(view.meanwhile)}</div>')
    return f'<div class="progress">{"".join(parts)}</div>'


def starting_html(label: str) -> str:
    """What the area shows from the click until the operation's progress begins."""
    return f'<div class="progress"><div class="line">{html.escape(label)}: starting</div><progress></progress></div>'


def outcome_html(line: str, succeeded: bool) -> str:
    """The line the area keeps once the operation has ended."""
    classes = "progress" if succeeded else "progress failed"
    return f'<div class="{classes}"><div class="line">{html.escape(line)}</div></div>'


def added_line(book: Book, elapsed: float) -> str:
    return (
        f"Added in {elapsed_text(elapsed)}. {book.book_id}: {book.title}, "
        f"with {book.chapter_count} chapters and {book.chunk_count} chunks."
    )


def replaced_line(book: Book, elapsed: float) -> str:
    return f"Replaced in {elapsed_text(elapsed)}. {book.book_id} is now {book.title}, with {book.chunk_count} chunks."


def reprocessed_line(book: Book, elapsed: float) -> str:
    return f"Processed again in {elapsed_text(elapsed)}. {book.book_id}: {book.chunk_count} chunks."


def removed_line(book_id: str, archived: bool, elapsed: float) -> str:
    original = "its original is in the archive" if archived else "its original was deleted"
    return f"Removed in {elapsed_text(elapsed)}. {book_id} is gone; {original}."


def reindexed_line(report: ReindexReport, elapsed: float) -> str:
    notes = [
        f"Reindexed in {elapsed_text(elapsed)}.",
        f"Index v{report.index_version} is active: {report.books} books, {report.chunks} chunks.",
    ]
    if report.adopted:
        notes.append(f"Brought back from their originals: {', '.join(report.adopted)}.")
    if report.failed:
        notes.append(f"Still failing: {', '.join(report.failed)}.")
    if report.summaries_failed:
        failed = len(report.summaries_failed)
        notes.append(f"{failed} {'summary' if failed == 1 else 'summaries'} not written.")
    return " ".join(notes)


def index_reset_line(elapsed: float) -> str:
    return (
        f"Reset in {elapsed_text(elapsed)}. The index is gone and the originals are kept. "
        "Reindex the library to rebuild it."
    )


def everything_reset_line(elapsed: float) -> str:
    return f"Reset in {elapsed_text(elapsed)}. The library is empty."
