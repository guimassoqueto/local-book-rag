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
from time import perf_counter
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
from app.evaluation.quiz_metrics import KnownCase, load_known_cases, summarize_check, write_reading
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
from app.generation.prompts import QUIZ_LETTERS, QuizSource, question_answering_messages
from app.generation.question_answering import check_abstention, read_reply
from app.generation.quiz import REFUSAL_KINDS, QuizWriter
from app.ingestion.chunker import Chunk
from app.ingestion.validation import validate_upload
from app.retrieval.base import RetrievalFilters
from app.services.quiz_service import QuestionReady, QuizReady
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
_QUIZ_ROW_METRICS = ("delivered_share", "seconds", "first_question_seconds")
_QUESTION_METRICS = ("key_is_longest", "key_is_shortest", "closed_book_correct")
QUIZ_METRICS = _QUIZ_ROW_METRICS + _QUESTION_METRICS
_WHOLE_BOOK = "(whole book)"
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


class LocalBook(BaseModel):
    """A book that isn't in the dataset, such as the owner's own copy of a book that isn't public.

    The owner copies its file into benchmarks/books: it is never fetched, and its checksum is
    checked before a run does anything.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    title: str
    language: str
    filename: str
    sha256: str


class QuizTarget(BaseModel):
    """What a quiz experiment prepares a quiz on.

    Attributes:
        book: a dataset or local book's key.
        chapter: a chapter's title, or None for the whole book.
        questions: how many questions. None for the application's default count.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    book: str
    chapter: str | None
    questions: PositiveInt | None = None


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
        local_books: books outside the dataset, indexed in the workspace beside its books.
        targets: the quizzes to prepare, for quiz.
        seed: fixes passages, letters, order and sampling, so variants pair up, for quiz.
        known_cases: the known cases file, relative to the experiment file, for quiz_check.
        case_set: which known cases to run on, for quiz_check.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: Literal["retrieval", "generation", "summarization", "performance", "extraction", "quiz", "quiz_check"]
    description: str
    variants: tuple[VariantConfig, ...]
    judge: JudgeConfig | None = None
    runs: PositiveInt = 3
    max_tokens: PositiveInt = 256
    prompt_book: str | None = None
    local_books: tuple[LocalBook, ...] = ()
    targets: tuple[QuizTarget, ...] = ()
    seed: int = 0
    known_cases: Path | None = None
    case_set: Literal["development", "test"] | None = None

    @model_validator(mode="after")
    def distinct_variants(self) -> "Experiment":
        names = [variant.name for variant in self.variants]
        if len(set(names)) != len(names):
            raise ValueError("variant names have to differ: results are grouped by them")
        return self

    @model_validator(mode="after")
    def check_needs_its_cases(self) -> "Experiment":
        if self.kind == "quiz_check" and (self.known_cases is None or self.case_set is None):
            raise ValueError("a quiz_check experiment needs known_cases and a case_set: development or test")
        return self


def load_experiment(path: Path) -> Experiment:
    """Read an experiment file. Its known cases, if any, are read from beside it."""
    try:
        experiment = Experiment.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"Invalid experiment {path}: {exc}") from exc
    if experiment.known_cases is not None and not experiment.known_cases.is_absolute():
        experiment = experiment.model_copy(update={"known_cases": path.parent / experiment.known_cases})
    return experiment


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

    def run(self, experiment: Experiment, limit: int | None = None, commit: str | None = None) -> Path:
        """Run an experiment and write its results.

        Args:
            experiment: what to run.
            limit: for a quick pass, how many questions to take per book and category, or
                chapters per book. A full run leaves it out.
            commit: the code's commit, recorded with the results: the container holds no .git.

        Returns:
            The directory holding the results.

        Raises:
            ConfigurationError: a local book's file is missing or isn't the expected one.
        """
        self._check_local_books(experiment)
        environment = self._describe_environment(experiment, commit)  # first: a run can take hours
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
            case "quiz":
                reading: list[dict[str, Any]] = []
                self._run_quiz(experiment, rows, reading)
                write_reading(directory / "reading.csv", reading)
                metrics = QUIZ_METRICS
            case "quiz_check":
                self._run_quiz_check(experiment, rows)
        self._write(directory, experiment, environment, rows.all, metrics, limit)
        return directory

    def _check_local_books(self, experiment: Experiment) -> None:
        """Stop before any work when a local book isn't the owner's copy the experiment names."""
        for book in experiment.local_books:
            path = self._root / "books" / book.filename
            if not path.is_file():
                raise ConfigurationError(f"{book.key}: {path} is missing. Copy the owner's file there first.")
            if (checksum := file_checksum(path)) != book.sha256:
                raise ConfigurationError(
                    f"{book.key}: {path} isn't the file the experiment names: its sha256 is {checksum}, "
                    f"not {book.sha256}."
                )

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

    def _open(self, settings: Settings, local_books: Sequence[LocalBook] = ()) -> Workspace:
        """Open a variant's workspace, indexing the dataset's books, and any local ones, the first time.

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
        entries: list[LocalBook | Any] = [*self._dataset.books, *local_books]
        for entry in entries:
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
                    reply = read_reply(generation, chunks)
                    reply = check_abstention(llm, settings, question.question, reply, parameters)
                    answers.append((question, generation, reply))
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

    def _run_quiz_check(self, experiment: Experiment, rows: "_Rows") -> None:
        """Run the key check, and the comparator, over the known cases of one set (FR-026, FR-027).

        The comparator is the shipped writer answering each case with its passage, so it is the
        same for every variant, and asked once per case.
        """
        assert experiment.known_cases is not None
        cases = [case for case in load_known_cases(experiment.known_cases) if case.case_set == experiment.case_set]
        self._say(f"{len(cases)} {experiment.case_set} cases")
        comparator_answers: dict[str, str | None] = {}
        for variant in experiment.variants:
            settings = apply_overrides(self._settings, variant.overrides)
            workspace = self._open(settings, experiment.local_books)
            runtime = workspace.container.runtime
            check = settings.generation.quiz.check
            checker = QuizWriter(
                settings.generation.quiz,
                settings.generation.context.safety_margin,
                create_llm_provider(settings, runtime),
                checker=create_llm_provider(
                    settings, runtime, model=check.model or settings.llm.model, reasoning=check.reasoning
                ),
            )
            comparator = QuizWriter(
                self._settings.generation.quiz,
                self._settings.generation.context.safety_margin,
                create_llm_provider(self._settings, runtime),
            )
            for position, case in enumerate(cases, start=1):
                self._say(f"{variant.name}: case {position} of {len(cases)}")
                row: dict[str, Any] = {
                    "variant": variant.name,
                    "row": "case",
                    "case": case.id,
                    "book": case.book,
                    "label": case.label,
                    "set": case.case_set,
                }
                passage = _locate(case, workspace)
                if passage is None:
                    self._say(f"  {case.id}: its quote is in no passage of {case.book}, {case.chapter}")
                    rows.append(row | {"located": False})
                    continue
                book = workspace.books[case.book]
                source = QuizSource(book.title, book.author, case.chapter)
                verdict = checker.check(case.question, case.lettered, case.key, passage, source, seed=_SEED)
                if case.id not in comparator_answers:
                    comparator_answers[case.id] = comparator.answer(
                        case.question, case.lettered, passage, source, seed=_SEED
                    )
                answer = comparator_answers[case.id]
                rows.append(
                    row
                    | {
                        "located": True,
                        "rejected": verdict.readable and not verdict.accepted,
                        "supported": "".join(verdict.supported),
                        "readable": verdict.readable,
                        "open_book_answer": answer,
                        "open_book_caught": None if answer is None else answer != case.key,
                    }
                )

    def _run_quiz(self, experiment: Experiment, rows: "_Rows", reading: list[dict[str, Any]]) -> None:
        """Prepare each target's quiz through the workspace's QuizService, as the tab does, and time it.

        The same seed gives every variant the same passages, letters and order, so their rows pair
        question by question. The writer then answers each question without its passage.
        """
        for variant in experiment.variants:
            settings = apply_overrides(self._settings, variant.overrides)
            workspace = self._open(settings, experiment.local_books)
            answerer = QuizWriter(
                settings.generation.quiz,
                settings.generation.context.safety_margin,
                create_llm_provider(settings, workspace.container.runtime),
            )
            for target in experiment.targets:
                self._run_target(variant.name, experiment.seed, target, workspace, answerer, rows, reading)

    def _run_target(
        self,
        variant: str,
        seed: int,
        target: QuizTarget,
        workspace: Workspace,
        answerer: QuizWriter,
        rows: "_Rows",
        reading: list[dict[str, Any]],
    ) -> None:
        book = workspace.books.get(target.book)
        if book is None:
            raise ConfigurationError(f"No book '{target.book}' in the dataset or the experiment's local_books.")
        quizzes = workspace.container.quizzes
        number = None
        if target.chapter is not None:
            numbers = {title: number for number, title in workspace.container.books.chapters(book.book_id)}
            if target.chapter not in numbers:
                raise ConfigurationError(f"{target.book} has no chapter '{target.chapter}'. It has: {list(numbers)}.")
            number = numbers[target.chapter]
        chapter = target.chapter or _WHOLE_BOOK
        count = target.questions or quizzes.default_count(book.book_id, number)
        self._say(f"{variant}: {count} questions on {target.book}, {chapter}")
        quiz_row: dict[str, Any] = {"variant": variant, "row": "quiz", "book": target.book, "chapter": chapter}

        started = last = perf_counter()
        first: float | None = None
        ready: list[tuple[QuestionReady, float]] = []
        final: QuizReady | None = None
        try:
            for event in quizzes.prepare(book.book_id, number, count, seed=seed):
                now = perf_counter()
                if isinstance(event, QuestionReady):
                    first = now - started if first is None else first
                    ready.append((event, now - last))
                    last = now
                elif isinstance(event, QuizReady):
                    final = event
        except BookRagError as exc:
            self._say(f"  {exc}")
            rows.append(quiz_row | {"asked": count, "failed": True, "error": str(exc)})
            return
        seconds = perf_counter() - started
        assert final is not None

        source = QuizSource(book.title, book.author, None)
        passages: dict[int, list[Chunk]] = defaultdict(list)
        for chunk in workspace.chunks[target.book]:
            passages[chunk.chapter_number].append(chunk)
        for event, question_seconds in ready:
            question = event.question
            chapter_passages = sorted(passages[question.passage.chapter_number], key=lambda chunk: chunk.chunk_index)
            place = [chunk.chunk_id for chunk in chapter_passages].index(question.passage.chunk_id)
            key_index = QUIZ_LETTERS.index(question.key)
            key = question.options[key_index]
            others = [option for index, option in enumerate(question.options) if index != key_index]
            answer = answerer.answer(question.text, question.options, None, source, seed=seed)
            identifier = f"{target.book}:{chapter}:{question.position}"
            rows.append(
                {
                    "variant": variant,
                    "row": "question",
                    "question": identifier,
                    "book": target.book,
                    "chapter": chapter,
                    "question_chapter": question.passage.chapter_title,
                    "relative_position": place / (len(chapter_passages) - 1) if len(chapter_passages) > 1 else 0.0,
                    "third": 3 * place // len(chapter_passages),
                    "letter": question.key,
                    # Length gives the answer away both ways: models were measured writing the key
                    # longest, or shortest (specs/003-chapter-quiz, SC-002).
                    "key_is_longest": len(key) > max(len(option) for option in others),
                    "key_is_shortest": len(key) < min(len(option) for option in others),
                    "closed_book_answer": answer,
                    "closed_book_correct": None if answer is None else answer == question.key,
                    "question_seconds": question_seconds,
                    "attempts": event.attempts,
                    "refusals": sum(event.refusals.values()),
                    **{f"refused_{kind}": event.refusals.get(kind, 0) for kind in REFUSAL_KINDS},
                    "checked": event.check is not None,
                    "check_accepted": None if event.check is None else event.check.accepted,
                }
            )
            passage = question.passage
            reading.append(
                {
                    "variant": variant,
                    "question": identifier,
                    "book": target.book,
                    "chapter": passage.chapter_title,
                    "pages": "" if passage.page_start is None else f"{passage.page_start}-{passage.page_end}",
                    "passage": passage.text,
                    "text": question.text,
                    **dict(zip(QUIZ_LETTERS, question.options, strict=True)),
                    "key": question.key,
                    "explanation": question.explanation,
                }
            )
        delivered = len(final.quiz.questions)
        rows.append(
            quiz_row
            | {
                "asked": count,
                "delivered": delivered,
                "delivered_share": delivered / count,
                "seconds": seconds,
                "first_question_seconds": first,
                "skipped_passages": final.skipped_passages,
                "passed_over_passages": final.passed_over_passages,
                "ruled_out_chapters": len(final.ruled_out_chapters),
                "check_unreadable": final.check_unreadable,
                "check_rejected": final.check_rejected,
                "failed": False,
            }
        )

    def _write(
        self,
        directory: Path,
        experiment: Experiment,
        environment: dict[str, Any],
        rows: list[dict[str, Any]],
        metrics: Sequence[str],
        limit: int | None,
    ) -> None:
        summarizer = summarize_quiz if experiment.kind == "quiz" else summarize
        if experiment.kind == "quiz_check":
            summary = summarize_check(rows, experiment.case_set)
        else:
            summary = summarizer(rows, metrics)
        report = {
            "experiment": experiment.model_dump(mode="json"),
            "complete": limit is None,
            "sample_limit": limit,
            "environment": environment,
            "summary": summary,
            "by_category": summarizer(rows, metrics, "category") if rows and "category" in rows[0] else [],
            "by_book": summarizer(rows, metrics, "book")
            if rows and "book" in rows[0] and experiment.kind != "quiz_check"
            else [],
            "rows": rows,
        }
        (directory / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
        _write_csv(directory / "summary.csv", summary or rows)
        _write_csv(directory / "rows.csv", rows)

    def _describe_environment(self, experiment: Experiment, commit: str | None = None) -> dict[str, Any]:
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
            "commit": commit,
            "book_sha256": {
                entry.key: file_checksum(path) if (path := self._root / "books" / entry.filename).is_file() else None
                for entry in [*self._dataset.books, *experiment.local_books]
            },
        }


def _locate(case: KnownCase, workspace: Workspace) -> Chunk | None:
    """The passage of the case's chapter that holds its quote, under this workspace's chunking."""
    quote = " ".join(case.quote.casefold().split())
    for chunk in workspace.chunks.get(case.book, ()):
        if chunk.chapter_title == case.chapter and quote in " ".join(chunk.text.casefold().split()):
            return chunk
    return None


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


def summarize_quiz(
    rows: Iterable[Mapping[str, Any]], metrics: Sequence[str], group: str | None = None
) -> list[dict[str, Any]]:
    """Average a quiz run's measures per variant: quiz measures over quizzes, the rest over questions.

    `samples` counts questions, and `quizzes` the quizzes. `closed_book_unreadable` counts the
    closed-book answers that couldn't be read, which closed_book_correct leaves out.
    """
    rows = list(rows)
    questions = [row for row in rows if row.get("row") == "question"]
    quizzes = [row for row in rows if row.get("row") == "quiz"]
    per_quiz = summarize(quizzes, [metric for metric in metrics if metric in _QUIZ_ROW_METRICS], group)
    per_question = summarize(questions, [metric for metric in metrics if metric in _QUESTION_METRICS], group)

    def key(entry: Mapping[str, Any]) -> tuple[Any, ...]:
        return (entry["variant"], entry[group]) if group else (entry["variant"],)

    question_entries = {key(entry): entry for entry in per_question}
    quiz_entries = {key(entry): entry for entry in per_quiz}
    result = []
    for entry_key in dict.fromkeys([*quiz_entries, *question_entries]):
        on_quizzes = quiz_entries.get(entry_key, {})
        on_questions = question_entries.get(entry_key, {})
        entry: dict[str, Any] = {"variant": entry_key[0]}
        if group:
            entry[group] = entry_key[1]
        entry["samples"] = on_questions.get("samples", 0)
        entry["quizzes"] = on_quizzes.get("samples", 0)
        for metric in metrics:
            source = on_quizzes if metric in _QUIZ_ROW_METRICS else on_questions
            entry[metric] = source.get(metric)
            entry[f"{metric}_samples"] = source.get(f"{metric}_samples", 0)
        entry["closed_book_unreadable"] = sum(
            1 for row in questions if key(row) == entry_key and row.get("closed_book_correct") is None
        )
        if failed := on_quizzes.get("failed"):
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
