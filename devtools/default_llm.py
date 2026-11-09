"""Choose the default LLM by the rule in specs/002-gemma4-default-llm, and record how.

The spec fixed a rule before any run: the default switches from gpt-oss:20b to gemma4:12b only if a
confirmation shows nothing gated worse, the wins that motivated it again, no systematic weakness in
the outputs read, nothing blocking in a probe of what the benchmarks don't cover, and the real-model
checks passing. This script runs that confirmation and applies the rule. It stays after the
decision, either way, as the record of how the numbers were made (FR-016).

Four subcommands need the stack, and run in the app container, where the benchmarks ran. The
container mounts benchmarks/ but not devtools/, so the script is piped to its Python:

    docker compose exec -T app python - preflight … < devtools/default_llm.py
    docker compose exec -T app python - summarize … < devtools/default_llm.py
    docker compose exec -T app python - probe … < devtools/default_llm.py
    docker compose exec -T app python - packets … < devtools/default_llm.py

The fifth only reads files, and runs on the host:

    uv run python devtools/default_llm.py verdict …

specs/002-gemma4-default-llm/contracts/devtool.md describes every subcommand, and quickstart.md the
order to run them in. Being piped, the script can import nothing that sits next to it: only app, the
packages the application depends on, and the standard library.
"""

import argparse
import contextlib
import hashlib
import json
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml

from app.evaluation.report import Difference, paired_difference
from app.generation.base import Generation, GenerationParameters, Message

BASELINE = "gpt_oss_20b"
CANDIDATE = "gemma4_12b"

# Condition (a): the metrics the first version's spec compares candidates on (§ 15.3), and
# correctness on the category where gemma4 leaned lower in both earlier runs.
GENERATION_METRICS = (
    "faithfulness",
    "answer_correctness",
    "answer_relevance",
    "citation_accuracy",
    "language_consistency",
    "abstention_quality",
)
SUMMARY_METRICS = (
    "argument_coverage",
    "concept_preservation",
    "factual_consistency",
    "coherence",
    "completeness",
    "citation_traceability",
)
MULTI_SECTION = "multi_section_answer_correctness"

# Condition (b): the book whose coverage motivated the switch.
NOVEL = "quincas_borba"

# Condition (c), FR-006: what the reading records, and when a kind of error is systematic.
ERROR_KINDS = frozenset(
    {"unsupported_claim", "misattribution", "unanswered_part", "abstention_with_evidence", "false_citation"}
)
ENTRY_KINDS = frozenset({"answer", "summary", "probe_reply", "probe_summary"})
LABELS = frozenset({"abstains", "answers"})
SYSTEMATIC_ANSWERS = 3
SYSTEMATIC_SUMMARIES = 2
LOW_CONSISTENCY = 0.5

# Condition (d), FR-008: the probe.
TRAP = "quincas_borba_unanswerable_04"
WHOLE_LIBRARY = (TRAP, "think_python_multi_section_04")
RUNS = 3
MARKER_LANGUAGES = ("Spanish", "French", "German", "Italian")
LONG_SUMMARY_BOOK, LONG_SUMMARY_CHAPTER, LONG_SUMMARY_TYPE = "think_python", "Inheritance", "analytical"
MAX_EXTRA_WAIT_SECONDS = 1.0

# The experiment whose variants name the two models the probe compares.
MODELS_FROM = Path("experiments/default_llm_generation.yaml")


class CheckFailed(Exception):
    """A check refused to go on. main() prints it and exits with 1."""


# The recorder (research R5)

Label = Callable[[], tuple[str | None, str | None] | None]


class RecordingLLM:
    """An LLM provider that passes every call through, and records each prompt's size two ways.

    The estimate is what the application fits prompts by, the sum of `count_tokens` over the
    messages. The other is Ollama's own count of what it read. When the label is None, nothing is
    recorded.
    """

    def __init__(self, inner: Any, sink: list[dict[str, Any]], label: Label) -> None:
        self._inner = inner
        self._sink = sink
        self._label = label

    @property
    def model(self) -> str:
        return self._inner.model

    def context_size(self) -> int:
        return self._inner.context_size()

    def count_tokens(self, text: str) -> int:
        return self._inner.count_tokens(text)

    def stream(self, messages: Sequence[Message], parameters: GenerationParameters) -> Iterator[Any]:
        for event in self._inner.stream(messages, parameters):
            if isinstance(event, Generation):
                self._record(messages, parameters, event)
            yield event

    def generate(self, messages: Sequence[Message], parameters: GenerationParameters) -> Generation:
        for event in self.stream(messages, parameters):
            if isinstance(event, Generation):
                return event
        raise AssertionError("stream() always ends with a Generation")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _record(self, messages: Sequence[Message], parameters: GenerationParameters, generation: Generation) -> None:
        label = self._label()
        if label is None:
            return
        variant, chapter = label
        self._sink.append(
            {
                "variant": variant,
                "chapter": chapter,
                "model": self._inner.model,
                "estimate_tokens": sum(self._inner.count_tokens(message.content) for message in messages),
                "prompt_tokens": generation.stats.prompt_tokens,
                "window": self._inner.context_size(),
                "max_tokens": parameters.max_tokens,
                "finish_reason": generation.stats.finish_reason,
            }
        )


@contextlib.contextmanager
def recording_llms(sink: list[dict[str, Any]], label: Label) -> Iterator[None]:
    """Wrap every LLM provider that app.container.assemble builds, while the block runs.

    The benchmark runner builds its judge through its own import of create_llm_provider, which
    this leaves alone: the judge isn't recorded.
    """
    import app.container as container_module

    original = container_module.create_llm_provider

    def wrapped(settings: Any, runtime: Any) -> RecordingLLM:
        return RecordingLLM(original(settings, runtime), sink, label)

    container_module.create_llm_provider = wrapped
    try:
        yield
    finally:
        container_module.create_llm_provider = original


# Preflight (research R4)


@dataclass(frozen=True)
class Check:
    name: str
    expected: Any
    actual: Any

    @property
    def ok(self) -> bool:
        return self.expected is not None and self.expected == self.actual


def compare_environment(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    models: Iterable[str],
    dataset_expected: str | None,
    dataset_actual: str | None,
) -> list[Check]:
    """Compare a live environment with an earlier run's: Ollama, each model's digest, the dataset."""
    checks = [Check("ollama", expected.get("ollama_version"), actual.get("ollama_version"))]
    for model in sorted(models):
        checks.append(Check(f"digest {model}", _digest(expected, model), _digest(actual, model)))
    checks.append(Check("dataset", dataset_expected, dataset_actual))
    return checks


def _digest(environment: Mapping[str, Any], model: str) -> str | None:
    return (environment.get("models", {}).get(model) or {}).get("digest")


def _preflight(arguments: argparse.Namespace) -> int:
    from app.config.loader import load_settings
    from app.config.settings import EnvironmentSettings
    from app.errors import BookRagError
    from app.evaluation.benchmark import load_experiment
    from app.evaluation.dataset import dataset_checksum
    from app.utils.ollama_runtime import OllamaRuntime

    environment = EnvironmentSettings()
    settings = load_settings(environment.config_dir)
    models = _experiment_models(settings, load_experiment(arguments.experiment))
    runtime = OllamaRuntime(environment.ollama_base_url, settings.ollama.request_timeout_seconds)
    actual: dict[str, Any] = {"ollama_version": runtime.version(), "models": {}}
    for model in models:
        try:
            actual["models"][model] = {"digest": runtime.model_info(model).digest}
        except BookRagError:
            actual["models"][model] = {"digest": None}

    checks = compare_environment(
        _results(arguments.like)["environment"],
        actual,
        models,
        _results(arguments.dataset_like)["environment"].get("dataset_sha256"),
        dataset_checksum(environment.benchmarks_dir / "datasets"),
    )
    for check in checks:
        print(f"[{'  ok  ' if check.ok else 'DIFFERS'}] {check.name:<32} {check.expected} → {check.actual}")
    return 0 if all(check.ok for check in checks) else 1


def _experiment_models(settings: Any, experiment: Any) -> set[str]:
    """Every model an experiment uses: its variants', their embedding model's, and its judge's."""
    from app.evaluation.benchmark import apply_overrides

    models: set[str] = set()
    for variant in experiment.variants:
        derived = apply_overrides(settings, variant.overrides)
        models |= {derived.llm.model, derived.embedding.model}
    if experiment.judge is not None:
        models |= {experiment.judge.model, experiment.judge.embedding_model}
    return models


# Summarize (research R5)


def _summarize(arguments: argparse.Namespace) -> int:
    from app.container import build_container
    from app.evaluation.benchmark import BenchmarkRunner, load_experiment

    experiment = load_experiment(arguments.experiment)
    if experiment.kind != "summarization":
        raise CheckFailed(f"{arguments.experiment} is a {experiment.kind} experiment, not a summarization one")

    container = build_container()  # before recording: the library's own provider isn't the benchmark's
    prompts: list[dict[str, Any]] = []
    current: dict[str, str | None] = {"variant": None, "chapter": None}

    def say(message: str) -> None:
        print(message, flush=True)
        variant, summarizing, chapter = message.partition(": summarizing ")
        if summarizing:
            current.update(variant=variant, chapter=chapter)

    runner = BenchmarkRunner(container.settings, container.environment, say=say)
    with recording_llms(prompts, lambda: (current["variant"], current["chapter"])):
        directory = runner.run(experiment, arguments.limit)
    _write_jsonl(directory / "prompts.jsonl", prompts)
    print(f"Results: {directory}")
    return 0


# Probe (research R6)


def _probe(arguments: argparse.Namespace) -> int:
    from app.errors import BookRagError
    from app.evaluation.benchmark import Workspace, load_experiment
    from app.evaluation.dataset import load_dataset
    from app.generation.summarization import without_references
    from app.ingestion.language import detect_language, normalize_language
    from app.retrieval.base import RetrievalFilters
    from app.storage.catalog import utc_now

    settings, environment = _workspace_settings(arguments.workspace)
    dataset = load_dataset(environment.benchmarks_dir / "datasets")
    models = _variant_models(settings, load_experiment(environment.benchmarks_dir / MODELS_FROM))
    missing = set(MARKER_LANGUAGES) - set(settings.generation.response_languages)
    if missing:
        raise CheckFailed(f"generation.response_languages doesn't offer {', '.join(sorted(missing))}")

    questions = {question.id: question for question in dataset.questions}
    warmup = next(question for question in dataset.questions if question.answerable)
    unanswerable = [question for question in dataset.questions if not question.answerable]
    if arguments.smoke:
        unanswerable = unanswerable[:1]
    runs = 1 if arguments.smoke else RUNS

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = (
        environment.benchmarks_dir / "results" / f"default_llm_probe{'_smoke' if arguments.smoke else ''}_{stamp}"
    )
    directory.mkdir(parents=True)
    records = directory / "probe.jsonl"
    prompts: list[dict[str, Any]] = []
    summarizing: dict[str, str | None] = {"item": None}
    runtime = None

    for variant in (BASELINE, CANDIDATE):
        model = models[variant]
        with recording_llms(prompts, lambda: None if summarizing["item"] is None else (None, summarizing["item"])):
            container, variant_settings = _open_workspace(settings, environment, arguments.workspace, model)
        runtime = container.runtime
        books = _workspace_books(container, dataset)
        workspace = Workspace(container, variant_settings, books, {})

        _ask(records, container, "warmup", warmup, workspace.filters(warmup))
        for run in range(1, runs + 1):
            for question_id in WHOLE_LIBRARY:
                _ask(records, container, "whole_library", questions[question_id], RetrievalFilters(), run=run)
        for question in unanswerable:
            for language in MARKER_LANGUAGES:
                _ask(records, container, "marker", question, workspace.filters(question), language)

        if not arguments.smoke:
            print(f"{model}: {LONG_SUMMARY_TYPE} summary of {LONG_SUMMARY_CHAPTER}", flush=True)
            book = books[LONG_SUMMARY_BOOK]
            number = {title: number for number, title in container.books.chapters(book.book_id)}[LONG_SUMMARY_CHAPTER]
            record = {
                "kind": "analytical",
                "model": model,
                "item": LONG_SUMMARY_CHAPTER,
                "book_language": normalize_language(dataset.book(LONG_SUMMARY_BOOK).language),
            }
            summarizing["item"] = LONG_SUMMARY_CHAPTER
            try:
                summary = container.summaries.summarize(book.book_id, number, LONG_SUMMARY_TYPE)
            except BookRagError as exc:
                record |= {"text": None, "steps": None, "incomplete_steps": None, "detected_language": None}
                record["error"] = str(exc)
            else:
                record |= {
                    "text": summary.text,
                    "steps": summary.steps,
                    "incomplete_steps": summary.incomplete_steps,
                    "detected_language": detect_language(without_references(summary.text)),
                    "error": None,
                }
            finally:
                summarizing["item"] = None
            _append_jsonl(records, record)

    _write_jsonl(directory / "prompts.jsonl", prompts)
    used = sorted({*models.values(), settings.embedding.model})
    (directory / "environment.json").write_text(
        json.dumps(
            {
                "date": utc_now(),
                "ollama_version": runtime.version(),
                "models": {model: runtime.model_info(model).digest for model in used},
                "workspace": arguments.workspace,
                "complete": not arguments.smoke,
            },
            indent=1,
        )
    )
    print(f"Probe: {directory}")
    return 0


def _ask(
    records: Path,
    container: Any,
    kind: str,
    question: Any,
    filters: Any,
    language: str | None = None,
    run: int | None = None,
) -> None:
    """Ask through the service, and record what it showed and how long the first text took.

    The wait runs from retrieval's end, through fitting the passages, to the first text the reader
    sees, after any reasoning and after the marker and citation filters.
    """
    from app.errors import BookRagError
    from app.generation.base import TextDelta
    from app.generation.question_answering import Answer
    from app.retrieval.pipeline import RetrievalResult

    model = container.settings.llm.model
    print(f"{model}: {kind} {question.id}{f' in {language}' if language else ''}", flush=True)
    record: dict[str, Any] = {"kind": kind, "model": model, "item": question.id, "language": language, "run": run}
    retrieved: float | None = None
    wait: float | None = None
    answer = None
    try:
        for event in container.questions.stream(question.question, filters, language):
            if isinstance(event, RetrievalResult):
                retrieved = perf_counter()
            elif isinstance(event, TextDelta):
                if wait is None and retrieved is not None:
                    wait = perf_counter() - retrieved
            elif isinstance(event, Answer):
                answer = event
    except BookRagError as exc:
        record |= {"insufficient_evidence": None, "text": None, "citations": [], "invented_citations": []}
        record |= {"wait_seconds": None, "error": str(exc)}
    else:
        record |= {
            "insufficient_evidence": answer.insufficient_evidence,
            "text": answer.text,
            "citations": [citation.number for citation in answer.citations],
            "invented_citations": list(answer.invented_citations),
            "wait_seconds": None if kind == "warmup" else wait,
            "error": None,
        }
    _append_jsonl(records, record)


# The benchmark workspace, read and never changed


def _workspace_settings(key: str) -> tuple[Any, Any]:
    from app.config.loader import load_settings
    from app.config.settings import EnvironmentSettings
    from app.evaluation.benchmark import index_key

    environment = EnvironmentSettings()
    settings = load_settings(environment.config_dir)
    if key != index_key(settings):
        raise CheckFailed(f"workspace {key} isn't the default configuration's, which is {index_key(settings)}")
    if not (environment.benchmarks_dir / "workspace" / key).is_dir():
        raise CheckFailed(f"there is no workspace {key}: run the generation benchmark first")
    return settings, environment


def _open_workspace(settings: Any, environment: Any, key: str, model: str | None) -> tuple[Any, Any]:
    """The workspace's container, for a model chosen in memory. Nothing is reset, recovered or added."""
    from app.container import assemble
    from app.evaluation.benchmark import apply_overrides

    if model is not None:
        settings = apply_overrides(settings, {"llm": {"model": model}})
    workspace = environment.model_copy(update={"data_dir": environment.benchmarks_dir / "workspace" / key})
    return assemble(settings, workspace, collection_prefix=f"bench_{key}_v"), settings


def _workspace_books(container: Any, dataset: Any) -> dict[str, Any]:
    from app.storage.catalog import BookStatus

    known = {book.checksum: book for book in container.books.list_books()}
    books = {}
    for entry in dataset.books:
        book = known.get(entry.sha256)
        if book is None or book.status is not BookStatus.INDEXED:
            raise CheckFailed(f"the workspace doesn't hold {entry.title}, indexed")
        books[entry.key] = book
    return books


def _variant_models(settings: Any, experiment: Any) -> dict[str, str]:
    from app.evaluation.benchmark import apply_overrides

    models = {variant.name: apply_overrides(settings, variant.overrides).llm.model for variant in experiment.variants}
    if set(models) != {BASELINE, CANDIDATE}:
        raise CheckFailed(f"expected the variants {BASELINE} and {CANDIDATE}, found {', '.join(sorted(models))}")
    return models


# Packets (research R7)


def _packets(arguments: argparse.Namespace) -> int:
    from app.evaluation.benchmark import Workspace
    from app.evaluation.dataset import load_dataset, relevant_chunks
    from app.evaluation.retrieval_metrics import context_recall

    generation = _results(arguments.generation)
    summary_runs = _summary_runs(arguments.summarization, arguments.earlier)
    probe = _read_jsonl(arguments.probe / "probe.jsonl")
    models = _models(generation["rows"])

    key = _workspace_key(arguments.probe)
    settings, environment = _workspace_settings(key)
    dataset = load_dataset(environment.benchmarks_dir / "datasets")
    container, settings = _open_workspace(settings, environment, key, None)
    books = _workspace_books(container, dataset)
    workspace = Workspace(container, settings, books, {})
    chunks = {book_key: container.books.chunks(book.book_id) for book_key, book in books.items()}

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = environment.benchmarks_dir / "results" / f"default_llm_reading_{stamp}"
    (directory / "multi_section").mkdir(parents=True)
    (directory / "summaries").mkdir()
    index = ["# Reading packets", "", f"Generation: `{arguments.generation.name}`", ""]

    rows = _by_item(generation["rows"])
    index += ["## Multi-section answers", ""]
    for question in (question for question in dataset.questions if question.category == "multi_section"):
        passages = [
            passage.chunk
            for passage in container.retrieval.search(
                question.question, workspace.filters(question), settings.retrieval
            ).passages
        ]
        recall = context_recall(
            [chunk.chunk_id for chunk in passages], relevant_chunks(question, chunks[question.book])
        )
        pair = rows.get(question.id, {})
        recorded = {row.get("evidence_in_context") for row in pair.values()} - {None}
        lines = [f"# {question.id}", ""]
        if recorded and recorded != {recall}:
            lines += [
                f"> **The passages differ from the run's**: evidence in context {recall:.3f} rebuilt, "
                f"{', '.join(f'{value:.3f}' for value in sorted(recorded))} in the run.",
                "",
            ]
        lines += [f"**Question**: {question.question}", "", f"**Expected answer**: {question.expected_answer}", ""]
        lines += ["**Evidence**:", "", *(f"- {quote}" for quote in question.evidence), "", "## Passages", ""]
        for number, chunk in enumerate(passages, start=1):
            section = f", {chunk.section_title}" if chunk.section_title else ""
            lines += [f"### [{number}] {chunk.chapter_title}{section} (`{chunk.chunk_id}`)", "", chunk.text, ""]
        for variant in (BASELINE, CANDIDATE):
            row = pair.get(variant, {})
            lines += [f"## {models.get(variant, variant)}", "", _scores(row, (*GENERATION_METRICS, "abstained")), ""]
            lines += [row.get("answer") or "_No answer: the reply failed._", ""]
        (directory / "multi_section" / f"{question.id}.md").write_text("\n".join(lines))
        index.append(f"- [{question.id}](multi_section/{question.id}.md)")

    index += ["", "## Summaries", ""]
    for run_name, run_rows in summary_runs.items():
        by_chapter = _by_item(run_rows)
        for book_key, chapter in _summaries_to_read(run_rows):
            pair = by_chapter[(book_key, chapter)]
            book = books[book_key]
            number = {title: number for number, title in container.books.chapters(book.book_id)}[chapter]
            lines = [f"# {chapter} ({run_name})", ""]
            for variant in (BASELINE, CANDIDATE):
                row = pair.get(variant, {})
                lines += [f"## {models.get(variant, variant)}", "", _scores(row, SUMMARY_METRICS), ""]
                lines += [row.get("summary") or "_No summary: it failed._", ""]
            lines += ["## The chapter's chunks", ""]
            for chunk in chunks[book_key]:
                if chunk.chapter_number == number:
                    lines += [f"### `{chunk.chunk_id}`", "", chunk.text, ""]
            name = f"{_slug(chapter)}__{run_name}.md"
            (directory / "summaries" / name).write_text("\n".join(lines))
            index.append(f"- [{chapter}, {run_name}](summaries/{name})")

    lines = ["# The probe's outputs to read", "", "## Marker replies not shown as abstentions", ""]
    for record in probe:
        if record["kind"] == "marker" and record.get("insufficient_evidence") is False:
            question = next(question for question in dataset.questions if question.id == record["item"])
            lines += [f"### {record['item']} in {record['language']}, {record['model']}", ""]
            lines += [f"**Question**: {question.question}", "", record.get("text") or "", ""]
    lines += [
        "## The analytical summaries",
        "",
        f"The chapter's chunks are in `summaries/{_slug(LONG_SUMMARY_CHAPTER)}__*.md`.",
        "",
    ]
    for record in probe:
        if record["kind"] == "analytical":
            lines += [f"### {record['model']}", "", _scores(record, ("steps", "incomplete_steps", "error")), ""]
            lines += [f"Language: {record.get('detected_language')}, the book's: {record.get('book_language')}", ""]
            lines += [record.get("text") or "_No summary: it failed._", ""]
    (directory / "probe.md").write_text("\n".join(lines))
    index += ["", "## The probe", "", "- [Marker replies and analytical summaries](probe.md)"]

    skeleton = []
    for item, kind, model in required_entries(generation["rows"], summary_runs, probe, models):
        entry: dict[str, Any] = {"item": item, "kind": kind, "model": model}
        if kind == "probe_reply":
            entry["label"] = None
        skeleton.append(entry | {"errors": [], "note": ""})
    (directory / "reading.skeleton.yaml").write_text(yaml.safe_dump(skeleton, sort_keys=False, allow_unicode=True))
    (directory / "index.md").write_text("\n".join(index) + "\n")
    print(f"Packets: {directory}")
    return 0


def _workspace_key(probe: Path) -> str:
    return json.loads((probe / "environment.json").read_text())["workspace"]


def _scores(row: Mapping[str, Any], fields: Sequence[str]) -> str:
    def value(name: str) -> str:
        number = row.get(name)
        return f"{number:.3f}" if isinstance(number, float) else str(number)

    return ", ".join(f"{name} {value(name)}" for name in fields)


def _slug(text: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in text).strip("_")[:60]


def _summaries_to_read(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """The chapters whose candidate summary scored LOW_CONSISTENCY or lower, in the run's order (FR-006)."""
    chapters = []
    for row in rows:
        score = row.get("factual_consistency")
        if row["variant"] == CANDIDATE and score is not None and score <= LOW_CONSISTENCY:
            chapters.append((row["book"], row["chapter"]))
    return chapters


def required_entries(
    generation_rows: Sequence[Mapping[str, Any]],
    summary_runs: Mapping[str, Sequence[Mapping[str, Any]]],
    probe: Sequence[Mapping[str, Any]],
    models: Mapping[str, str],
) -> list[tuple[str, str, str]]:
    """Every (item, kind, model) a complete reading holds (contracts/records.md)."""
    required = []
    for question in sorted({row["question"] for row in generation_rows if row["category"] == "multi_section"}):
        required += [(question, "answer", models[variant]) for variant in (BASELINE, CANDIDATE)]
    for run_name, rows in summary_runs.items():
        for _, chapter in _summaries_to_read(rows):
            required += [(f"{chapter}@{run_name}", "summary", models[variant]) for variant in (BASELINE, CANDIDATE)]
    required += [
        (f"{LONG_SUMMARY_CHAPTER}@probe", "probe_summary", models[variant]) for variant in (BASELINE, CANDIDATE)
    ]
    for record in probe:
        if record["kind"] == "marker" and record.get("insufficient_evidence") is False:
            required.append((f"{record['item']}@{record['language']}", "probe_reply", record["model"]))
    return required


# The reading record (contracts/records.md)


class ReadingError(ValueError):
    """reading.yaml doesn't follow its contract."""


@dataclass(frozen=True)
class ReadingEntry:
    item: str
    kind: str
    model: str
    errors: tuple[str, ...]
    label: str | None
    note: str


_ENTRY_FIELDS = frozenset({"item", "kind", "model", "errors", "label", "note"})


def load_reading(path: Path) -> list[ReadingEntry]:
    """Load reading.yaml, refusing anything outside its contract."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ReadingError(f"{path} has to hold a list of entries")
    entries: list[ReadingEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for position, raw in enumerate(data, start=1):
        where = f"{path}, entry {position}"
        if not isinstance(raw, dict):
            raise ReadingError(f"{where} isn't a mapping")
        if unknown := set(raw) - _ENTRY_FIELDS:
            raise ReadingError(f"{where} has unknown fields: {', '.join(sorted(unknown))}")
        item, kind, model = raw.get("item"), raw.get("kind"), raw.get("model")
        if not all(isinstance(value, str) and value for value in (item, kind, model)):
            raise ReadingError(f"{where} needs an item, a kind and a model")
        if kind not in ENTRY_KINDS:
            raise ReadingError(f"{where} has an unknown kind {kind!r}")
        errors = raw.get("errors") or []
        if not isinstance(errors, list) or not set(errors) <= ERROR_KINDS:
            raise ReadingError(f"{where} has errors outside {', '.join(sorted(ERROR_KINDS))}")
        label = raw.get("label")
        if kind == "probe_reply" and label not in LABELS:
            raise ReadingError(f"{where} is a probe reply, and needs a label: abstains or answers")
        if kind != "probe_reply" and label is not None:
            raise ReadingError(f"{where} has a label, which only a probe reply takes")
        note = raw.get("note") or ""
        if errors and not note.strip():
            raise ReadingError(f"{where} lists errors, and needs a note saying where they are")
        if (item, kind, model) in seen:
            raise ReadingError(f"{where} repeats {item} ({kind}, {model})")
        seen.add((item, kind, model))
        entries.append(ReadingEntry(item, kind, model, tuple(errors), label, note))
    return entries


def missing_entries(
    entries: Sequence[ReadingEntry], required: Sequence[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    present = {(entry.item, entry.kind, entry.model) for entry in entries}
    return [entry for entry in dict.fromkeys(required) if entry not in present]


# The rule (spec FR-002, research R12)


@dataclass(frozen=True)
class Condition:
    passed: bool
    failures: tuple[str, ...]
    lines: tuple[str, ...]
    differences: Mapping[str, Difference | None] = field(default_factory=dict)


@dataclass(frozen=True)
class Verdict:
    """outcome is switch, keep or pending: pending until the real-model checks have run."""

    outcome: str
    conditions: Mapping[str, Condition]
    models: Mapping[str, str]


def decide(
    generation_rows: Sequence[Mapping[str, Any]],
    summarization_rows: Sequence[Mapping[str, Any]],
    prompts: Sequence[Mapping[str, Any]],
    probe: Sequence[Mapping[str, Any]],
    reading: Sequence[ReadingEntry],
    safety_margin: float,
    integration: str,
) -> Verdict:
    """Apply the rule. Each condition passes or fails on the numbers and the reading alone."""
    models = _models(generation_rows)
    conditions = {
        "a": _nothing_worse(generation_rows, summarization_rows, models),
        "b": _wins_repeat(generation_rows, summarization_rows),
        "c": _no_systematic_weakness(reading, models),
        "d": _nothing_blocks(prompts, probe, reading, models, safety_margin),
        "e": Condition(integration == "passed", () if integration == "passed" else (integration,), (integration,)),
    }
    if not all(conditions[name].passed for name in "abcd"):
        outcome = "keep"
    elif integration == "pending":
        outcome = "pending"
    else:
        outcome = "switch" if integration == "passed" else "keep"
    return Verdict(outcome, conditions, models)


def _models(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {row["variant"]: row["model"] for row in rows if row.get("model")}


def _mean(rows: Iterable[Mapping[str, Any]], variant: str, metric: str) -> float | None:
    values = [row[metric] for row in rows if row["variant"] == variant and row.get(metric) is not None]
    return statistics.fmean(values) if values else None


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _interval(difference: Difference | None) -> str:
    if difference is None:
        return "no pairs"
    return f"{difference.mean:+.3f} ({difference.low:+.3f} to {difference.high:+.3f})"


def _nothing_worse(
    generation_rows: Sequence[Mapping[str, Any]],
    summarization_rows: Sequence[Mapping[str, Any]],
    models: Mapping[str, str],
) -> Condition:
    multi_section = [row for row in generation_rows if row.get("category") == "multi_section"]
    gated = [
        *((metric, metric, generation_rows) for metric in GENERATION_METRICS),
        (MULTI_SECTION, "answer_correctness", multi_section),
        *((metric, metric, summarization_rows) for metric in SUMMARY_METRICS),
    ]
    baseline, candidate = models.get(BASELINE, BASELINE), models.get(CANDIDATE, CANDIDATE)
    lines = [
        f"| Metric | {baseline} | {candidate} | Difference (95%) | Pairs | |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    differences: dict[str, Difference | None] = {}
    failures = []
    for name, metric, rows in gated:
        difference = paired_difference(rows, BASELINE, CANDIDATE, metric)
        differences[name] = difference
        worse = difference is None or difference.high < 0
        if worse:
            failures.append(name)
        pairs = difference.pairs if difference else 0
        lines.append(
            f"| {name} | {_number(_mean(rows, BASELINE, metric))} | {_number(_mean(rows, CANDIDATE, metric))} "
            f"| {_interval(difference)} | {pairs} | {'**worse**' if worse else '—'} |"
        )
    return Condition(not failures, tuple(failures), tuple(lines), differences)


def _wins_repeat(
    generation_rows: Sequence[Mapping[str, Any]], summarization_rows: Sequence[Mapping[str, Any]]
) -> Condition:
    failures = []
    wrong = {
        variant: sum(
            1
            for row in generation_rows
            if row["variant"] == variant and row.get("abstained") and row.get("category") != "unanswerable"
        )
        for variant in (BASELINE, CANDIDATE)
    }
    if not wrong[CANDIDATE] < wrong[BASELINE]:
        failures.append("wrong_abstentions")
    lines = [f"- **Wrong abstentions**: {wrong[BASELINE]} for the baseline, {wrong[CANDIDATE]} for the candidate"]

    differences: dict[str, Difference | None] = {}
    for metric, name in (("total_seconds", "Seconds per summary"), ("steps", "Steps per summary")):
        difference = paired_difference(summarization_rows, BASELINE, CANDIDATE, metric)
        differences[metric] = difference
        if difference is None or not difference.high < 0:
            failures.append(metric)
        lines.append(
            f"- **{name}**: {_number(_mean(summarization_rows, BASELINE, metric))} and "
            f"{_number(_mean(summarization_rows, CANDIDATE, metric))}, a difference of {_interval(difference)}"
        )

    novel_rows = [row for row in summarization_rows if row.get("book") == NOVEL]
    novel = {variant: _mean(novel_rows, variant, "argument_coverage") for variant in (BASELINE, CANDIDATE)}
    if novel[BASELINE] is None or novel[CANDIDATE] is None or not novel[CANDIDATE] > novel[BASELINE]:
        failures.append("novel_coverage")
    lines.append(
        f"- **The novel's coverage**, over {len(novel_rows) // 2} chapters, direction only: "
        f"{_number(novel[BASELINE])} and {_number(novel[CANDIDATE])}"
    )
    return Condition(not failures, tuple(failures), tuple(lines), differences)


def _no_systematic_weakness(reading: Sequence[ReadingEntry], models: Mapping[str, str]) -> Condition:
    entries = {(entry.item, entry.kind, entry.model): entry for entry in reading}
    answers: Counter[str] = Counter()
    summaries: Counter[str] = Counter()
    for item, kind in dict.fromkeys((entry.item, entry.kind) for entry in reading):
        candidate = entries.get((item, kind, models.get(CANDIDATE, "")))
        if candidate is None:
            continue
        baseline = entries.get((item, kind, models.get(BASELINE, "")))
        only = set(candidate.errors) - set(baseline.errors if baseline else ())
        if kind == "answer":
            answers.update(only)
        elif kind in ("summary", "probe_summary"):
            summaries.update(only)
    failures = sorted(
        {kind for kind, count in answers.items() if count >= SYSTEMATIC_ANSWERS}
        | {kind for kind, count in summaries.items() if count >= SYSTEMATIC_SUMMARIES}
    )
    lines = ["| Error kind | Multi-section answers | Summaries |", "| --- | --- | --- |"]
    for kind in sorted(ERROR_KINDS):
        lines.append(
            f"| {kind} | {answers[kind]} of {SYSTEMATIC_ANSWERS} | {summaries[kind]} of {SYSTEMATIC_SUMMARIES} |"
        )
    lines.append("")
    lines.append("Counted where the candidate's entry has the kind and the baseline's, for the same item, doesn't.")
    return Condition(not failures, tuple(failures), tuple(lines))


def _nothing_blocks(
    prompts: Sequence[Mapping[str, Any]],
    probe: Sequence[Mapping[str, Any]],
    reading: Sequence[ReadingEntry],
    models: Mapping[str, str],
    safety_margin: float,
) -> Condition:
    baseline, candidate = models.get(BASELINE, ""), models.get(CANDIDATE, "")
    failures = []
    lines = []

    trap = {
        model: sum(
            1
            for record in probe
            if record["kind"] == "whole_library"
            and record["model"] == model
            and record["item"] == TRAP
            and record.get("insufficient_evidence") is False
        )
        for model in (baseline, candidate)
    }
    if trap[candidate] > trap[baseline]:
        failures.append("trap")
    lines.append(f"- **The trap answered**: {trap[baseline]} of {RUNS} and {trap[candidate]} of {RUNS}")

    labels = {(entry.item, entry.model): entry.label for entry in reading if entry.kind == "probe_reply"}
    unrecognized: dict[str, Counter[str]] = {baseline: Counter(), candidate: Counter()}
    for record in probe:
        if (
            record["kind"] == "marker"
            and record["model"] in unrecognized
            and record.get("insufficient_evidence") is False
            and labels.get((f"{record['item']}@{record['language']}", record["model"])) == "abstains"
        ):
            unrecognized[record["model"]][record["language"]] += 1
    totals = {model: sum(counts.values()) for model, counts in unrecognized.items()}
    if totals[candidate] > totals[baseline]:
        failures.append("unrecognized_abstentions")
    by_language = "; ".join(
        f"{language} {unrecognized[baseline][language]} and {unrecognized[candidate][language]}"
        for language in MARKER_LANGUAGES
    )
    lines.append(f"- **Unrecognized abstentions**: {totals[baseline]} and {totals[candidate]} ({by_language})")

    analytical = {record["model"]: record for record in probe if record["kind"] == "analytical"}

    def failed(record: Mapping[str, Any] | None) -> bool:
        return (
            record is None
            or record.get("error") is not None
            or record.get("detected_language") != record.get("book_language")
        )

    if failed(analytical.get(candidate)) and not failed(analytical.get(baseline)):
        failures.append("analytical")
    for model in (baseline, candidate):
        record = analytical.get(model) or {}
        lines.append(
            f"- **The {LONG_SUMMARY_TYPE} summary, {model}**: "
            + (
                "missing"
                if not record
                else f"error {record.get('error')}, language {record.get('detected_language')} "
                f"of {record.get('book_language')}, {record.get('incomplete_steps')} incomplete steps"
            )
        )

    candidate_prompts = [prompt for prompt in prompts if prompt["model"] == candidate]
    over = [
        prompt
        for prompt in candidate_prompts
        if prompt["prompt_tokens"] - prompt["estimate_tokens"] > safety_margin * prompt["window"]
    ]
    if over or not candidate_prompts:
        failures.append("undercount")
    if candidate_prompts:
        worst = max(candidate_prompts, key=lambda prompt: prompt["prompt_tokens"] - prompt["estimate_tokens"])
        lines.append(
            f"- **The largest undercount**, of {len(candidate_prompts)} prompts: "
            f"{worst['prompt_tokens'] - worst['estimate_tokens']} tokens, against "
            f"{safety_margin * worst['window']:.0f} ({safety_margin} of {worst['window']}); {len(over)} over it"
        )
    else:
        lines.append("- **The largest undercount**: no prompt recorded for the candidate")

    waits = {
        model: [
            record["wait_seconds"]
            for record in probe
            if record["kind"] == "whole_library" and record["model"] == model and record.get("wait_seconds") is not None
        ]
        for model in (baseline, candidate)
    }
    if not waits[baseline] or not waits[candidate]:
        failures.append("wait")
        lines.append("- **The median wait**: not measured for both models")
    else:
        medians = {model: statistics.median(values) for model, values in waits.items()}
        if medians[candidate] - medians[baseline] > MAX_EXTRA_WAIT_SECONDS:
            failures.append("wait")
        lines.append(
            f"- **The median wait for the first visible word**: {medians[baseline]:.2f} s and "
            f"{medians[candidate]:.2f} s, at most {MAX_EXTRA_WAIT_SECONDS:.0f} s more"
        )
    return Condition(not failures, tuple(failures), tuple(lines))


_TITLES = {
    "a": "(a) Nothing gated is worse",
    "b": "(b) The wins repeat",
    "c": "(c) The reading finds no systematic weakness",
    "d": "(d) The probe finds nothing that blocks",
    "e": "(e) The real-model checks pass",
}


def render_verdict(verdict: Verdict, inputs: Mapping[str, Any]) -> str:
    """Write the verdict in the order of contracts/records.md."""
    baseline, candidate = verdict.models.get(BASELINE, BASELINE), verdict.models.get(CANDIDATE, CANDIDATE)
    lines = [
        "# Verdict: the default LLM",
        "",
        "Written by `devtools/default_llm.py verdict`, applying the rule of",
        "[spec.md](spec.md) FR-002. The baseline is first in every comparison, the candidate second.",
        "",
        "## Inputs",
        "",
        *(f"- **{name}**: {value}" for name, value in inputs.items()),
    ]
    for name in "abcde":
        condition = verdict.conditions[name]
        status = "Passed" if condition.passed else f"Failed: {', '.join(condition.failures)}"
        lines += ["", f"## {_TITLES[name]}", "", *condition.lines, "", f"**{status}**"]
    failed = [name for name in "abcde" if not verdict.conditions[name].passed]
    match verdict.outcome:
        case "switch":
            outcome = f"**Switch to {candidate}.** Every condition passed."
        case "keep":
            outcome = f"**Keep {baseline}.** Failed: {', '.join(f'({name})' for name in failed)}."
        case _:
            outcome = "**Pending.** (a) to (d) passed; the real-model checks of (e) haven't run with the candidate."
    lines += ["", "## Verdict", "", outcome, "", "## Follow-ups", "", "_Added by hand after the verdict._", ""]
    return "\n".join(lines)


def _verdict(arguments: argparse.Namespace) -> int:
    from app.config.loader import load_settings

    generation = _results(arguments.generation)
    summarization = _results(arguments.summarization)
    for directory, results in ((arguments.generation, generation), (arguments.summarization, summarization)):
        if not results.get("complete"):
            raise CheckFailed(f"{directory} isn't a complete run, so it decides nothing")
        variants = {row["variant"] for row in results["rows"]}
        if variants != {BASELINE, CANDIDATE}:
            raise CheckFailed(f"{directory} has the variants {', '.join(sorted(variants))}")
    probe_environment = json.loads((arguments.probe / "environment.json").read_text())
    if not probe_environment.get("complete"):
        raise CheckFailed(f"{arguments.probe} is a smoke pass, so it decides nothing")

    probe = _read_jsonl(arguments.probe / "probe.jsonl")
    prompts = _read_jsonl(arguments.summarization / "prompts.jsonl") + _read_jsonl(arguments.probe / "prompts.jsonl")
    reading = load_reading(arguments.reading)
    models = _models(generation["rows"])
    summary_runs = _summary_runs(arguments.summarization, arguments.earlier)
    missing = missing_entries(reading, required_entries(generation["rows"], summary_runs, probe, models))
    if missing:
        listed = "; ".join(f"{item} ({kind}, {model})" for item, kind, model in missing[:10])
        raise CheckFailed(f"{arguments.reading} is missing {len(missing)} entries: {listed}")

    margin = load_settings(Path("config")).generation.context.safety_margin
    verdict = decide(generation["rows"], summarization["rows"], prompts, probe, reading, margin, arguments.integration)
    inputs = {
        "Commit the runs started from": f"`{arguments.commit}`",
        "Generation run": _describe_run(arguments.generation, generation),
        "Summarization run": _describe_run(arguments.summarization, summarization),
        "Probe": f"`{arguments.probe.name}`, {probe_environment['date']}",
        "Earlier summarization runs": ", ".join(f"`{run.name}`" for run in arguments.earlier),
        "Reading": f"`{arguments.reading}`, SHA-256 `{hashlib.sha256(arguments.reading.read_bytes()).hexdigest()}`",
    }
    text = render_verdict(verdict, inputs)
    arguments.output.write_text(text)
    print(text)
    return 0


def _describe_run(directory: Path, results: Mapping[str, Any]) -> str:
    environment = results["environment"]
    digests = ", ".join(f"{model} `{(info.get('digest') or '')[:12]}`" for model, info in environment["models"].items())
    return (
        f"`{directory.name}`, {environment['date']}, Ollama {environment['ollama_version']}, "
        f"dataset `{environment['dataset_sha256'][:12]}`, {digests}"
    )


# Files


def _results(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "results.json").read_text())


def _summary_runs(confirmation: Path, earlier: Sequence[Path]) -> dict[str, list[dict[str, Any]]]:
    return {directory.name: _results(directory)["rows"] for directory in (confirmation, *earlier)}


def _by_item(rows: Sequence[Mapping[str, Any]]) -> dict[Any, dict[str, Mapping[str, Any]]]:
    paired: dict[Any, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        item = row.get("question") or (row.get("book"), row.get("chapter"))
        paired.setdefault(item, {})[row["variant"]] = row
    return paired


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records))


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


# The command line


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="default_llm", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    preflight = commands.add_parser("preflight", help="check the versions against an earlier run")
    preflight.add_argument("experiment", type=Path)
    preflight.add_argument("--like", type=Path, required=True, help="the run whose models and Ollama to match")
    preflight.add_argument("--dataset-like", type=Path, required=True, help="the run whose dataset to match")
    preflight.set_defaults(handler=_preflight)

    summarize = commands.add_parser("summarize", help="the summarization run, recording every prompt")
    summarize.add_argument("experiment", type=Path)
    summarize.add_argument("--limit", type=int, help="chapters per book, for a smoke pass that decides nothing")
    summarize.set_defaults(handler=_summarize)

    probe = commands.add_parser("probe", help="what the benchmarks don't cover")
    probe.add_argument("--workspace", required=True, help="the benchmark workspace's key")
    probe.add_argument("--smoke", action="store_true", help="a few of each, deciding nothing")
    probe.set_defaults(handler=_probe)

    packets = commands.add_parser("packets", help="the material for the reading")
    packets.add_argument("--generation", type=Path, required=True)
    packets.add_argument("--summarization", type=Path, required=True)
    packets.add_argument("--probe", type=Path, required=True)
    packets.add_argument("--earlier", type=Path, nargs="+", required=True, help="earlier summarization runs")
    packets.set_defaults(handler=_packets)

    verdict = commands.add_parser("verdict", help="apply the rule")
    verdict.add_argument("--generation", type=Path, required=True)
    verdict.add_argument("--summarization", type=Path, required=True)
    verdict.add_argument("--probe", type=Path, required=True)
    verdict.add_argument("--earlier", type=Path, nargs="+", required=True, help="earlier summarization runs")
    verdict.add_argument("--reading", type=Path, required=True)
    verdict.add_argument("--integration", choices=("passed", "failed", "pending"), required=True)
    verdict.add_argument("--commit", required=True, help="the commit the runs started from")
    verdict.add_argument("--output", type=Path, default=Path("specs/002-gemma4-default-llm/verdict.md"))
    verdict.set_defaults(handler=_verdict)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a subcommand. 0 is success, 1 a failed check, and 2 bad arguments (argparse's own)."""
    arguments = _parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except CheckFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
