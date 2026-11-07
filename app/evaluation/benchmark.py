"""Runs reproducible experiments and writes machine-readable results.

An experiment is a YAML file in benchmarks/experiments: a kind, and variants that are the normal
configuration plus overrides. Everything runs in benchmarks/workspace, on its own catalog, files
and ChromaDB collections, so the real library is never touched. Variants that index the same way
share a workspace, so a book is only ever indexed once for each way of indexing it.
"""

import csv
import hashlib
import json
import platform
import statistics
import subprocess
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from app.config.settings import EnvironmentSettings, JudgeConfig, Settings
from app.container import Container, assemble, build_pipeline
from app.errors import BookRagError, ConfigurationError
from app.evaluation.dataset import (
    BenchmarkQuestion,
    ChapterKeyPoints,
    dataset_checksum,
    load_dataset,
    relevant_chunks,
    validate_against_book,
)
from app.evaluation.extraction_metrics import extraction_scores
from app.evaluation.generation_metrics import (
    RagasJudge,
    abstention_is_correct,
    citation_accuracy,
    language_matches,
)
from app.evaluation.performance import measure
from app.evaluation.retrieval_metrics import (
    context_precision,
    context_recall,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.evaluation.summary_metrics import SummaryJudge
from app.generation.base import GenerationParameters, LLMProvider
from app.generation.factory import create_llm_provider
from app.generation.prompts import question_answering_messages
from app.generation.question_answering import read_reply
from app.ingestion.chunker import Chunk
from app.ingestion.validation import validate_upload
from app.retrieval.base import RetrievalFilters
from app.services.reset_service import CONFIRM_RESET_EVERYTHING
from app.storage.catalog import Book, BookStatus, utc_now
from app.utils.gpu import query_gpu
from app.utils.hashing import file_checksum
from app.utils.ollama_runtime import OllamaRuntime

_SEED = 0
_PERFORMANCE_CONTEXT_CHUNKS = 4
_TRACKED_PACKAGES = (
    "chromadb",
    "llama-index-core",
    "ollama",
    "ragas",
    "sentence-transformers",
    "torch",
    "transformers",
)

_RETRIEVAL_METRICS = ("recall_at_5", "recall_at_10", "mrr", "ndcg_at_10", "context_precision", "context_recall")
_GENERATION_METRICS = (
    "faithfulness",
    "answer_correctness",
    "answer_relevance",
    "citation_accuracy",
    "language_consistency",
    "abstention_quality",
)
_PERFORMANCE_METRICS = (
    "load_seconds",
    "time_to_first_token",
    "prompt_tokens_per_second",
    "generation_tokens_per_second",
    "total_seconds",
    "idle_vram_mb",
    "peak_vram_mb",
    "idle_ram_mb",
    "peak_ram_mb",
    "gpu_fraction",
)
_EXTRACTION_METRICS = ("toc_coverage", "chapters", "chunks", "pages_covered")
_SUMMARY_METRICS = (
    "argument_coverage",
    "concept_preservation",
    "factual_consistency",
    "coherence",
    "completeness",
    "citation_traceability",
    "chunks_covered_share",
)


class VariantConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class Experiment(BaseModel):
    """One experiment file.

    Attributes:
        name: names the results.
        kind: what it measures.
        description: why it exists.
        variants: the configurations it compares.
        judge: the model that scores generation and summaries.
        runs: measured runs per variant, for performance.
        max_tokens: tokens to generate per run, for performance.
        prompt_book: the dataset's book to take the prompt from, for performance. The first by default.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: Literal["retrieval", "generation", "summarization", "performance", "extraction"]
    description: str
    variants: tuple[VariantConfig, ...]
    judge: JudgeConfig | None = None
    runs: PositiveInt = 3
    max_tokens: PositiveInt = 256
    prompt_book: str | None = None

    @model_validator(mode="after")
    def distinct_variants(self) -> "Experiment":
        names = [variant.name for variant in self.variants]
        if len(set(names)) != len(names):
            raise ValueError("variant names have to differ: results are grouped by them")
        return self


def load_experiment(path: Path) -> Experiment:
    try:
        return Experiment.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"Invalid experiment {path}: {exc}") from exc


def apply_overrides(settings: Settings, overrides: Mapping[str, Any]) -> Settings:
    """Derive a variant's configuration. Validation is the same as for the files in config/."""
    return Settings.model_validate(_merged(settings.model_dump(), overrides))


def _merged(base: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in changes.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merged(result[key], value)
        else:
            result[key] = value
    return result


def index_key(settings: Settings) -> str:
    """Identify what shapes an index: variants with the same key can share one."""
    shape = {
        "embedding": settings.embedding.model,
        "profile": settings.embedding_profile.model_dump(),
        "chunking": settings.chunking.model_dump(),
        "extraction": {"pdf": settings.pdf.model_dump(), "normalization": settings.normalization.model_dump()},
    }
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()[:10]


@dataclass(frozen=True)
class Workspace:
    """A separate library for one way of indexing, holding the dataset's books."""

    container: Container
    settings: Settings
    books: Mapping[str, Book]
    chunks: Mapping[str, Sequence[Chunk]]

    def filters(self, question: BenchmarkQuestion) -> RetrievalFilters:
        """Search as a reader would: the question's book, and its chapter if it names one."""
        book = self.books[question.book]
        chapters: tuple[int, ...] = ()
        if question.category == "chapter_specific":
            numbers = {title: number for number, title in self.container.books.chapters(book.book_id)}
            chapters = (numbers[question.chapter],)
        return RetrievalFilters(book_ids=(book.book_id,), chapter_numbers=chapters)


class BenchmarkRunner:
    def __init__(
        self,
        settings: Settings,
        environment: EnvironmentSettings,
        say: Callable[[str], None] = print,
    ) -> None:
        self._settings = settings
        self._environment = environment
        self._root = environment.benchmarks_dir
        self._dataset_directory = self._root / "datasets"
        self._dataset = load_dataset(self._dataset_directory)
        self._say = say

    def run(self, experiment: Experiment, limit: int | None = None) -> Path:
        """Run an experiment and write its results.

        Args:
            experiment: what to run.
            limit: for a quick pass, how many questions to take per book and category, or
                chapters per book. A full run leaves it out.

        Returns:
            The directory holding the results.
        """
        environment = self._describe_environment(experiment)  # first: a run can take hours
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        directory = self._root / "results" / f"{experiment.name}_{stamp}"
        directory.mkdir(parents=True)
        rows = _Rows(directory / "rows.jsonl")

        metrics: Sequence[str] = ()
        match experiment.kind:
            case "retrieval":
                self._run_retrieval(experiment, limit, rows)
                metrics = _RETRIEVAL_METRICS
            case "generation":
                self._run_generation(experiment, limit, rows)
                metrics = _GENERATION_METRICS
            case "summarization":
                self._run_summarization(experiment, limit, rows)
                metrics = _SUMMARY_METRICS
            case "performance":
                self._run_performance(experiment, rows)
                metrics = _PERFORMANCE_METRICS
            case "extraction":
                self._run_extraction(experiment, rows)
                metrics = _EXTRACTION_METRICS
        self._write(directory, experiment, environment, rows.all, metrics, limit)
        return directory

    def validate(self) -> list[str]:
        """Check every question against the real text of its book, as the current code extracts it."""
        pipeline = build_pipeline(self._settings)
        problems: list[str] = []
        for entry in self._dataset.books:
            self._say(f"checking {entry.title}")
            path = self._root / "books" / entry.filename
            processed = pipeline.process(path, validate_upload(path, entry.filename, 2**30), "book", entry.title)
            chapters = [chapter.title for chapter in processed.structure.chapters]
            problems.extend(validate_against_book(self._dataset, entry.key, processed.chunks, chapters))
        return problems

    def _questions(self, limit: int | None, answerable_only: bool = False) -> list[BenchmarkQuestion]:
        taken: dict[tuple[str, str], int] = defaultdict(int)
        selected = []
        for question in self._dataset.questions:
            if answerable_only and not question.answerable:
                continue
            key = (question.book, question.category)
            if limit is None or taken[key] < limit:
                taken[key] += 1
                selected.append(question)
        return selected

    def _open(self, settings: Settings) -> Workspace:
        """Open a variant's workspace, indexing the dataset's books the first time.

        Changes to the ingestion code aren't detected: after one, delete benchmarks/workspace.
        """
        key = index_key(settings)
        directory = self._root / "workspace" / key
        new = not directory.exists()
        environment = self._environment.model_copy(update={"data_dir": directory})
        container = assemble(settings, environment, collection_prefix=f"bench_{key}_v")
        if new:  # a workspace deleted by hand leaves collections that its first index would fill again
            container.resets.reset_everything(CONFIRM_RESET_EVERYTHING)
        container.library.recover()
        if container.indexes.needs_reindex():  # the embedding model pulled again, say
            self._say(f"  rebuilding {key}, whose index no longer matches the configuration")
            container.library.reindex_all()

        books: dict[str, Book] = {}
        chunks: dict[str, Sequence[Chunk]] = {}
        known = {book.checksum: book for book in container.books.list_books()}
        for entry in self._dataset.books:
            path = self._root / "books" / entry.filename
            book = known.get(file_checksum(path))
            if book is None or book.status is not BookStatus.INDEXED:  # adding retries a failed book
                self._say(f"  indexing {entry.title} for {key}")
                book = container.books.add_book(path, entry.filename)
            books[entry.key] = book
            chunks[entry.key] = container.books.chunks(book.book_id)
        return Workspace(container, settings, books, chunks)

    def _run_retrieval(self, experiment: Experiment, limit: int | None, rows: "_Rows") -> None:
        questions = self._questions(limit, answerable_only=True)
        for variant in experiment.variants:
            self._say(f"{variant.name}: {len(questions)} questions")
            workspace = self._open(apply_overrides(self._settings, variant.overrides))
            for question in questions:
                evidence = relevant_chunks(question, workspace.chunks[question.book])
                result = workspace.container.retrieval.search(
                    question.question, workspace.filters(question), workspace.settings.retrieval
                )
                ranking = [passage.chunk.chunk_id for passage in result.candidates]
                context = [passage.chunk.chunk_id for passage in result.passages]
                rows.append(
                    {
                        "variant": variant.name,
                        "question": question.id,
                        "book": question.book,
                        "category": question.category,
                        **_relevant_places(evidence, workspace.chunks[question.book]),
                        "recall_at_5": recall_at_k(ranking, evidence, 5),
                        "recall_at_10": recall_at_k(ranking, evidence, 10),
                        "mrr": reciprocal_rank(ranking, evidence),
                        "ndcg_at_10": ndcg_at_k(ranking, evidence, 10),
                        "context_precision": context_precision(context, evidence),
                        "context_recall": context_recall(context, evidence),
                        "retrieval_seconds": result.retrieval_seconds,
                        "rerank_seconds": result.rerank_seconds,
                    }
                )

    def _run_generation(self, experiment: Experiment, limit: int | None, rows: "_Rows") -> None:
        """Compare LLMs on identical contexts: retrieval runs once, before any of them answers."""
        judge_config = _require_judge(experiment)
        workspace = self._open(self._settings)
        questions = self._questions(limit)
        self._say(f"retrieving contexts for {len(questions)} questions")
        contexts = {
            question.id: [
                passage.chunk
                for passage in workspace.container.retrieval.search(
                    question.question, workspace.filters(question), workspace.settings.retrieval
                ).passages
            ]
            for question in questions
        }

        judge = RagasJudge(
            self._judge_llm(judge_config, workspace.container.runtime),
            _judge_parameters(judge_config),
            judge_config,
            self._environment.ollama_base_url,
            self._settings.ollama.request_timeout_seconds,
        )
        for variant in experiment.variants:
            settings = apply_overrides(self._settings, variant.overrides)
            llm = create_llm_provider(settings, workspace.container.runtime)
            task = settings.generation.question_answering
            parameters = GenerationParameters(
                temperature=settings.llm.temperature if task.temperature is None else task.temperature,
                max_tokens=task.max_tokens or settings.llm.max_tokens,
                seed=_SEED,
            )
            answers = []
            for position, question in enumerate(questions, start=1):
                self._say(f"{variant.name}: answering {position} of {len(questions)}")
                chunks = contexts[question.id]
                messages = question_answering_messages(question.question, chunks, None)
                try:
                    generation = llm.generate(messages, parameters)
                    answers.append((question, generation, read_reply(generation, chunks)))
                except BookRagError as exc:
                    self._say(f"  {question.id}: {exc}")
                    answers.append((question, None, None))

            for position, (question, generation, reply) in enumerate(answers, start=1):
                self._say(f"{variant.name}: judging {position} of {len(answers)}")
                chunks = contexts[question.id]
                row = {
                    "variant": variant.name,
                    "question": question.id,
                    "book": question.book,
                    "category": question.category,
                    "model": settings.llm.model,
                    "failed": reply is None,
                }
                if reply is not None:
                    row |= self._judge_answer(question, reply, chunks, judge, workspace)
                    row["answer"] = reply.text
                    row["tokens_per_second"] = generation.stats.tokens_per_second
                    row["total_seconds"] = generation.stats.total_seconds
                rows.append(row)

    def _judge_llm(self, judge: JudgeConfig, runtime: OllamaRuntime) -> LLMProvider:
        """The judge at the widest window: it has to read an answer and its sources, and still reply."""
        window = self._settings.generation.context.max_size
        overrides: dict[str, Any] = {"llm": {"model": judge.model, "context_size": window}}
        if judge.reasoning is not None:
            overrides["llm_profiles"] = {judge.model: {"reasoning": judge.reasoning}}
        return create_llm_provider(apply_overrides(self._settings, overrides), runtime)

    def _judge_answer(
        self, question: BenchmarkQuestion, reply: Any, chunks: Sequence[Chunk], judge: RagasJudge, workspace: Workspace
    ) -> dict[str, Any]:
        scores: dict[str, Any] = {
            "abstained": reply.insufficient_evidence,
            "abstention_quality": float(abstention_is_correct(question.answerable, reply.insufficient_evidence)),
            "language_consistency": float(language_matches(reply.text, question.language)),
            "invented_citations": len(reply.invented_citations),
        }
        if not question.answerable:
            return scores
        evidence = relevant_chunks(question, workspace.chunks[question.book])
        # Abstaining is right when retrieval missed the evidence: this tells the two failures apart.
        scores["evidence_in_context"] = context_recall([chunk.chunk_id for chunk in chunks], evidence)
        if reply.insufficient_evidence:
            return scores
        cited = [citation.chunk_id for citation in reply.citations]
        scores["citation_accuracy"] = citation_accuracy(cited, evidence)
        scores |= asdict(
            judge.score(question.question, reply.text, [chunk.text for chunk in chunks], question.expected_answer)
        )
        return scores

    def _key_points(self, limit: int | None) -> list[ChapterKeyPoints]:
        taken: dict[str, int] = defaultdict(int)
        selected = []
        for points in self._dataset.key_points:
            if limit is None or taken[points.book] < limit:
                taken[points.book] += 1
                selected.append(points)
        return selected

    def _run_summarization(self, experiment: Experiment, limit: int | None, rows: "_Rows") -> None:
        judge_config = _require_judge(experiment)
        for variant in experiment.variants:
            settings = apply_overrides(self._settings, variant.overrides)
            workspace = self._open(settings)
            judge = SummaryJudge(
                self._judge_llm(judge_config, workspace.container.runtime), _judge_parameters(judge_config)
            )
            for points in self._key_points(limit):
                book = workspace.books[points.book]
                number = {title: number for number, title in workspace.container.books.chapters(book.book_id)}[
                    points.chapter
                ]
                self._say(f"{variant.name}: summarizing {points.chapter[:50]}")
                try:
                    summary = workspace.container.summaries.summarize(book.book_id, number, "standard")
                except BookRagError as exc:
                    self._say(f"  {exc}")
                    rows.append(
                        {"variant": variant.name, "book": points.book, "chapter": points.chapter, "failed": True}
                    )
                    continue
                sources = [chunk.text for chunk in workspace.chunks[points.book] if chunk.chapter_number == number]
                scores = judge.score(summary, points.key_points, sources)
                rows.append(
                    {
                        "variant": variant.name,
                        "book": points.book,
                        "chapter": points.chapter,
                        "failed": False,
                        "model": settings.llm.model,
                        "strategy": summary.strategy,
                        "steps": summary.steps,
                        "incomplete_steps": summary.incomplete_steps,
                        "chunks_covered_share": summary.chunks_covered / summary.chunks_total,
                        "total_seconds": summary.total_seconds,
                        **asdict(scores),
                        "summary": summary.text,
                    }
                )

    def _run_performance(self, experiment: Experiment, rows: "_Rows") -> None:
        workspace = self._open(self._settings)
        book = experiment.prompt_book or self._dataset.books[0].key
        passages = list(workspace.chunks[book])[:_PERFORMANCE_CONTEXT_CHUNKS]
        prompt = question_answering_messages("What is the main argument of this text?", passages, None)[-1].content
        runtime = workspace.container.runtime
        for variant in experiment.variants:
            settings = apply_overrides(self._settings, variant.overrides)
            self._say(f"{variant.name}: {settings.llm.model} at {settings.llm.context_size} tokens of context")
            llm = create_llm_provider(settings, runtime)
            result = measure(
                llm, runtime, prompt, experiment.runs, experiment.max_tokens, lambda step: self._say(f"  {step}")
            )
            info = runtime.model_info(settings.llm.model)
            rows.append(
                {
                    "variant": variant.name,
                    **asdict(result),
                    "digest": info.digest,
                    "quantization": info.quantization,
                    "parameters": info.parameter_size,
                }
            )

    def _run_extraction(self, experiment: Experiment, rows: "_Rows") -> None:
        for variant in experiment.variants:
            settings = apply_overrides(self._settings, variant.overrides)
            pipeline = build_pipeline(settings)
            for entry in self._dataset.books:
                self._say(f"{variant.name}: extracting {entry.title}")
                path = self._root / "books" / entry.filename
                processed = pipeline.process(path, validate_upload(path, entry.filename, 2**30), "book", entry.title)
                rows.append({"variant": variant.name, "book": entry.key, **asdict(extraction_scores(path, processed))})

    def _write(
        self,
        directory: Path,
        experiment: Experiment,
        environment: dict[str, Any],
        rows: list[dict[str, Any]],
        metrics: Sequence[str],
        limit: int | None,
    ) -> None:
        summary = summarize(rows, metrics)
        report = {
            "experiment": experiment.model_dump(),
            "complete": limit is None,
            "sample_limit": limit,
            "environment": environment,
            "summary": summary,
            "by_category": summarize(rows, metrics, "category") if rows and "category" in rows[0] else [],
            "by_book": summarize(rows, metrics, "book") if rows and "book" in rows[0] else [],
            "rows": rows,
        }
        (directory / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
        _write_csv(directory / "summary.csv", summary or rows)
        _write_csv(directory / "rows.csv", rows)

    def _describe_environment(self, experiment: Experiment) -> dict[str, Any]:
        """Say exactly what was measured: results mean nothing without it."""
        timeout = self._settings.ollama.request_timeout_seconds
        runtime = OllamaRuntime(self._environment.ollama_base_url, timeout)
        models = {self._settings.llm.model, self._settings.embedding.model}
        for variant in experiment.variants:
            settings = apply_overrides(self._settings, variant.overrides)
            models |= {settings.llm.model, settings.embedding.model}
        if experiment.judge is not None:
            models |= {experiment.judge.model, experiment.judge.embedding_model}
        gpu = query_gpu()
        return {
            "date": utc_now(),
            "dataset_sha256": dataset_checksum(self._dataset_directory),
            "configuration_sha256": hashlib.sha256(self._settings.model_dump_json().encode()).hexdigest(),
            "configuration": self._settings.model_dump(),
            "ollama_version": runtime.version(),
            "models": {model: asdict(runtime.model_info(model)) for model in sorted(models)},
            "hardware": {
                "cpu": _cpu_model(),
                "gpu": gpu.name if gpu else None,
                "gpu_memory_mb": gpu.memory_total_mb if gpu else None,
                "gpu_driver": _gpu_driver(),
            },
            "python": platform.python_version(),
            "packages": {name: _package_version(name) for name in _TRACKED_PACKAGES},
        }


def _relevant_places(evidence: Sequence[set[str]], chunks: Sequence[Chunk]) -> dict[str, str]:
    """Say where a question's evidence is under this chunking: the dataset only holds the quotes."""
    relevant = set().union(*evidence) if evidence else set()
    found = [chunk for chunk in chunks if chunk.chunk_id in relevant]
    pages = sorted({page for chunk in found for page in (chunk.page_start, chunk.page_end) if page is not None})
    return {
        "relevant_chapters": "; ".join(dict.fromkeys(chunk.chapter_title for chunk in found)),
        "relevant_pages": f"{pages[0]}-{pages[-1]}" if pages else "",
        "relevant_chunks": "; ".join(chunk.chunk_id for chunk in found),
    }


class _Rows:
    """Results as they come, kept on disk at once: a run can take hours, and fail near its end."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.all: list[dict[str, Any]] = []

    def append(self, row: dict[str, Any]) -> None:
        self.all.append(row)
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _judge_parameters(judge: JudgeConfig) -> GenerationParameters:
    return GenerationParameters(temperature=0.0, max_tokens=judge.max_tokens, seed=_SEED)


def _require_judge(experiment: Experiment) -> JudgeConfig:
    if experiment.judge is None:
        raise ConfigurationError(f"The experiment {experiment.name} needs a judge.")
    return experiment.judge


def summarize(
    rows: Iterable[Mapping[str, Any]], metrics: Sequence[str], group: str | None = None
) -> list[dict[str, Any]]:
    """Average each metric per variant, leaving out what a row doesn't have.

    Args:
        rows: the detailed results.
        metrics: the metrics to average.
        group: a field to split each variant by, such as the category.

    Returns:
        One row per variant, or per variant and group, with the number of samples of each metric.
    """
    groups: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["variant"], row[group]) if group else (row["variant"],)].append(row)

    result = []
    for key, members in groups.items():
        entry: dict[str, Any] = {"variant": key[0], "samples": len(members)}
        if group:
            entry[group] = key[1]
        for metric in metrics:
            values = [member[metric] for member in members if member.get(metric) is not None]
            entry[metric] = round(statistics.fmean(values), 4) if values else None
            entry[f"{metric}_samples"] = len(values)
        failed = sum(1 for member in members if member.get("failed"))
        if failed:
            entry["failed"] = failed
        result.append(entry)
    return result


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    columns: dict[str, None] = {}
    for row in rows:
        columns.update(dict.fromkeys(row))
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)


def _package_version(name: str) -> str | None:
    """None for a package left out with its extra, which an experiment may not need."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _cpu_model() -> str | None:
    for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return None


def _gpu_driver() -> str | None:
    command = ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
