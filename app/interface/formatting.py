"""Turns results into what the interface shows. Nothing here touches Gradio or a service."""

from collections.abc import Sequence

from app.generation.base import GenerationStats, Message
from app.generation.citations import Citation
from app.generation.question_answering import Answer
from app.generation.summarization import ChapterSummary
from app.retrieval.base import Passage
from app.storage.catalog import Book, IndexRecord
from app.utils.gpu import GpuStatus
from app.utils.ollama_runtime import LoadedModel

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
SCORE_COLUMNS = ["In context", "Chunk", "Chapter", "Pages", "Dense", "BM25", "Fusion", "Reranker"]


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


def pages_of(passage: Passage) -> str:
    chunk = passage.chunk
    if chunk.page_start is None:
        return ""
    return str(chunk.page_start) if chunk.page_start == chunk.page_end else f"{chunk.page_start}-{chunk.page_end}"


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
        pages = pages_of(passage)
        if pages:
            place.append(f"p. {pages}")
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
            pages_of(passage),
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
