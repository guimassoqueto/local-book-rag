"""Measure the progress of library operations on the four benchmark books (specs/004-library-progress).

It runs every library operation on the benchmark's books, three times, and records how long each
one takes and what it leaves behind, so that the feature's code can be compared with `main`'s
(research.md, R14). With the feature's code, it also samples what the progress reports, and reads
the stage lines from the log, for the spec's success criteria SC-002, SC-003, SC-004, SC-005 and
SC-009.

It never touches the library: it works in benchmarks/workspace/progress and the bench_progress_v
collections, which it empties before each run (principle II). It runs in the app container, where
the services are, from /app:

    stage=$(mktemp -d) && mkdir -p "$stage/benchmarks/results" && cp -r benchmarks/books "$stage/benchmarks/"
    docker compose cp -a "$stage/benchmarks" app:/app/   # /app is root's: -a keeps the files the app user's
    docker compose exec app mkdir -p /tmp/devtools
    docker compose cp devtools/measure_library_progress.py app:/tmp/devtools/
    docker compose exec -w /app app python -I /tmp/devtools/measure_library_progress.py --baseline --runs 3
    docker compose exec -w /app app python -I /tmp/devtools/measure_library_progress.py --runs 3 \\
        --baseline-results benchmarks/results/library_progress_<time>
    docker compose cp app:/app/benchmarks/results benchmarks/

`--baseline` calls only what `main` has: no `progress` argument, and no app.utils.progress.
"""

import argparse
import csv
import dataclasses
import hashlib
import json
import platform
import statistics
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BOOKS = ("think-python.pdf", "historia-economica-global.pdf", "on-liberty.epub", "quincas-borba.epub")
PROCESSED_FILES = ("extracted.json", "normalized.json", "chunks.jsonl")
WORKSPACE = Path("benchmarks/workspace/progress")
COLLECTION_PREFIX = "bench_progress_v"

SAMPLE_SECONDS = 0.25
PACE_SECONDS = 3.0  # FR-006: a stage has a pace once it has run 3 s
PACE_SHARE = 0.10  # ... and done 10% of its items
WITHIN = (0.5, 2.0)  # SC-003: within half and double the time actually left
ESTIMATE_SHARE = 0.90  # SC-003: for at least 90% of them
OVERHEAD_SHARE = 0.05  # SC-005: no more than 5% longer
OVERHEAD_SECONDS = 1.0  # ... or 1 s, whichever is larger
SUM_TOLERANCE = 1.0  # SC-009: the stages add up to the operation within 1 s
ADDING = "Adding a book"
SUMMARY_REINDEX = "reindex_all with summaries"


# What decides each criterion: pure functions, tested in tests/unit/test_progress_devtool.py.


def median_durations(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[int, str], float]:
    """The median duration of each step of the sequence, across runs."""
    durations: dict[tuple[int, str], list[float]] = {}
    for row in rows:
        durations.setdefault((int(row["step"]), str(row["operation"])), []).append(float(row["seconds"]))
    return {key: statistics.median(values) for key, values in durations.items()}


def overhead(baseline: Iterable[Mapping[str, Any]], feature: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """SC-005: each step's median against the baseline's, the reindex that writes summaries left out."""
    before, after = median_durations(baseline), median_durations(feature)
    rows = []
    for key in sorted(before.keys() & after.keys()):
        step, operation = key
        if operation == SUMMARY_REINDEX:
            continue
        limit = before[key] + max(before[key] * OVERHEAD_SHARE, OVERHEAD_SECONDS)
        rows.append(
            {
                "step": step,
                "operation": operation,
                "baseline": before[key],
                "feature": after[key],
                "limit": limit,
                "ok": after[key] <= limit,
            }
        )
    return rows


def digest_differences(baseline: Mapping[str, str], feature: Mapping[str, str]) -> list[str]:
    """SC-004: every file both runs wrote must have the same bytes."""
    missing = sorted(baseline.keys() ^ feature.keys())
    changed = sorted(key for key in baseline.keys() & feature.keys() if baseline[key] != feature[key])
    return [f"only in one run: {key}" for key in missing] + [f"different: {key}" for key in changed]


def _instance(sample: Mapping[str, Any]) -> tuple[Any, ...]:
    return (sample["run"], sample["step"], sample.get("stage"), sample.get("step_key"), sample.get("item"))


def counts_never_go_back(samples: Sequence[Mapping[str, Any]]) -> list[str]:
    """SC-002: within a stage, a count only grows."""
    problems = []
    last: dict[tuple[Any, ...], int] = {}
    for sample in samples:
        if sample.get("done") is None:
            continue
        key = _instance(sample)
        if key in last and sample["done"] < last[key]:
            problems.append(f"{key}: {last[key]} then {sample['done']}")
        last[key] = sample["done"]
    return problems


def counts_reach_totals(
    stage_lines: Iterable[Mapping[str, Any]], expected: Mapping[tuple[str, str | None], int | set[int]]
) -> list[str]:
    """SC-002: a counted stage that finishes ends at its total, which is what the book or library holds.

    Args:
        stage_lines: the "stage finished" and "stage failed" lines of the log.
        expected: the true total of a stage, by its key and the book it was about (None for the
            library's books and summaries). A book ID that held several books, across runs or after a
            replacement, has each of their totals.
    """
    problems = []
    for line in stage_lines:
        if line.get("message") != "stage finished" or line.get("total") is None:
            continue
        book = line.get("item") or line.get("book_id")
        where = " ".join(str(part) for part in (line.get("operation"), line["stage"], book) if part)
        if line["done"] != line["total"]:
            problems.append(f"{where}: ended at {line['done']} of {line['total']}")
        true_total = expected.get((line["stage"], book), expected.get((line["stage"], None)))
        allowed = true_total if isinstance(true_total, set) else {true_total}
        if true_total is not None and line["total"] not in allowed:
            problems.append(f"{where}: total {line['total']}, but there are {true_total}")
    return problems


def estimate_accuracy(samples: Sequence[Mapping[str, Any]], operation: str = ADDING) -> dict[str, Any]:
    """SC-003: the times left of an operation's samples, against the time each stage actually took.

    A stage ends halfway between its last sample and the next one, so the truth is known to within
    an eighth of a second. A time left is premature when it shows before the stage has run 3 s,
    give or take a sample, or done 10% of its items.
    """
    ordered = sorted(samples, key=lambda sample: (sample["run"], sample["step"], sample["t"]))
    first_seen: dict[tuple[Any, ...], float] = {}
    ends: dict[tuple[Any, ...], float] = {}
    for index, sample in enumerate(ordered):
        key = _instance(sample)
        first_seen.setdefault(key, sample["t"])
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        same_step = following is not None and (following["run"], following["step"]) == (sample["run"], sample["step"])
        if same_step and _instance(following) != key:
            ends[key] = (sample["t"] + following["t"]) / 2
        elif not same_step:
            ends[key] = sample.get("finished", sample["t"])

    shown = within = 0
    premature = []
    for sample in ordered:
        if sample["operation"] != operation or sample.get("time_left") is None:
            continue
        key = _instance(sample)
        shown += 1
        actual = ends[key] - sample["t"]
        if WITHIN[0] * actual <= sample["time_left"] <= WITHIN[1] * actual:
            within += 1
        ran = sample["t"] - first_seen[key]
        if ran < PACE_SECONDS - SAMPLE_SECONDS or sample["done"] < PACE_SHARE * sample["total"]:
            premature.append(f"{key} after {ran:.2f} s at {sample['done']} of {sample['total']}")
    share = within / shown if shown else None
    return {
        "shown": shown,
        "within": within,
        "share": share,
        "premature": premature,
        "ok": share is not None and share >= ESTIMATE_SHARE and not premature,
    }


def stage_sums(log_lines: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """SC-009: each operation's top-level stages, against its logged duration. Steps aren't summed."""
    operations: dict[str, dict[str, Any]] = {}
    for line in log_lines:
        execution = line.get("execution_id")
        if execution is None:
            continue
        entry = operations.setdefault(execution, {"operation": line.get("operation"), "stages": 0.0, "lines": 0})
        if line.get("message") in ("stage finished", "stage failed"):
            entry["lines"] += 1
            if line.get("within") is None:
                entry["stages"] += float(line["duration_seconds"])
        elif line.get("message") in ("operation finished", "operation failed"):
            entry["duration"] = float(line["duration_seconds"])
    rows = []
    for execution, entry in operations.items():
        if "duration" not in entry or entry["lines"] == 0:
            continue
        gap = entry["duration"] - entry["stages"]
        rows.append({"execution_id": execution, **entry, "gap": gap, "ok": abs(gap) <= SUM_TOLERANCE})
    return rows


# Running the operations


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Sampler:
    """Asks a Progress for its snapshot every quarter second, from a thread, while an operation runs."""

    def __init__(self, progress: Any, run: int, step: int, operation: str, sink: list[dict[str, Any]]) -> None:
        self._progress, self._run, self._step, self._operation = progress, run, step, operation
        self._sink, self._samples = sink, []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def __enter__(self) -> "Sampler":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        finished = time.monotonic()
        self._stop.set()
        self._thread.join()
        for sample in self._samples:
            sample["finished"] = finished
        self._sink.extend(self._samples)

    def _sample(self) -> None:
        while not self._stop.wait(SAMPLE_SECONDS):
            view = self._progress.snapshot()
            if view is None or view.stage is None:
                continue
            current = view.step or view.stage
            self._samples.append(
                {
                    "run": self._run,
                    "step": self._step,
                    "operation": view.operation,
                    "t": time.monotonic(),
                    "stage": view.stage.key,
                    "step_key": view.step.key if view.step else None,
                    "item": view.stage.note if view.step else None,
                    "done": current.done,
                    "total": current.total,
                    "time_left": current.time_left,
                }
            )


class Run:
    """One run of every operation, in the order R14 fixes, on an emptied workspace."""

    def __init__(self, container: Any, books: Path, baseline: bool, run: int, out: "Results") -> None:
        self._container, self._books, self._baseline, self._run, self._out = container, books, baseline, run, out
        self._step = 0
        self.book_ids: dict[str, str] = {}

    def call(self, operation: str, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        self._step += 1
        if self._baseline:
            started = time.perf_counter()
            result = function(*args, **kwargs)
            seconds = time.perf_counter() - started
        else:
            from app.utils.progress import Progress  # the feature's: absent from main

            progress = Progress()
            with Sampler(progress, self._run, self._step, operation, self._out.samples):
                started = time.perf_counter()
                result = function(*args, progress=progress, **kwargs)
                seconds = time.perf_counter() - started
        self._out.durations.append({"run": self._run, "step": self._step, "operation": operation, "seconds": seconds})
        return result

    def digest(self, book_id: str) -> None:
        container = self._container
        book = container.books.get_book(book_id)
        directory = container.environment.data_dir / "processed" / book_id / f"r{book.revision}"
        for name in PROCESSED_FILES:
            self._out.digests[f"run{self._run}/step{self._step}/{book_id}/{name}"] = _sha256(directory / name)
        self._out.chunk_counts.setdefault(book_id, set()).add(book.chunk_count)

    def run(self) -> None:
        from app.services.reset_service import CONFIRM_RESET_EVERYTHING, CONFIRM_RESET_INDEX

        container = self._container
        container.resets.reset_everything(CONFIRM_RESET_EVERYTHING)  # an empty workspace: the same IDs every run
        for name in BOOKS:
            book = self.call("add_book", container.books.add_book, self._books / name, name)
            self.book_ids[name] = book.book_id
            self.digest(book.book_id)
        for name in BOOKS:
            self.call("reindex_book", container.books.reindex_book, self.book_ids[name])
            self.digest(self.book_ids[name])
        quincas, liberty = self.book_ids["quincas-borba.epub"], self.book_ids["on-liberty.epub"]
        self.call("remove_book", container.books.remove_book, quincas, quincas)
        path = self._books / "quincas-borba.epub"
        self.call("replace_book", container.books.replace_book, liberty, path, path.name)
        self.digest(liberty)
        self.call("reindex_all", container.library.reindex_all)
        for book in container.books.list_books():
            self.digest(book.book_id)
        self.call("reset_index", container.resets.reset_index, CONFIRM_RESET_INDEX)
        self.call("reindex_all", container.library.reindex_all)
        for book in container.books.list_books():
            self.digest(book.book_id)
        self.call("reset_everything", container.resets.reset_everything, CONFIRM_RESET_EVERYTHING)


@dataclasses.dataclass
class Results:
    durations: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    digests: dict[str, str] = dataclasses.field(default_factory=dict)
    samples: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    chunk_counts: dict[str, set[int]] = dataclasses.field(default_factory=dict)
    summary_count: int | None = None


def _summary_reindex(container: Any, books: Path, out: Results, run: int) -> None:
    """Once: two saved summaries written again by a reindex, for SC-002's count of summaries."""
    from app.services.reset_service import CONFIRM_RESET_EVERYTHING
    from app.utils.progress import Progress

    container.resets.reset_everything(CONFIRM_RESET_EVERYTHING)
    book = container.books.add_book(books / "on-liberty.epub", "on-liberty.epub")
    out.chunk_counts.setdefault(book.book_id, set()).add(book.chunk_count)  # another book under a reused ID
    sizes: dict[int, int] = {}
    for chunk in container.books.chunks(book.book_id):
        sizes[chunk.chapter_number] = sizes.get(chunk.chapter_number, 0) + 1
    summary_type = container.summaries.summary_types()[0]
    for number in sorted(sizes, key=lambda chapter: (sizes[chapter], chapter))[:2]:
        container.summaries.save(container.summaries.summarize(book.book_id, number, summary_type))
    out.summary_count = 2
    progress = Progress()
    with Sampler(progress, run, 1, SUMMARY_REINDEX, out.samples):
        started = time.perf_counter()
        container.library.reindex_all(regenerate_summaries=True, progress=progress)
        out.durations.append(
            {"run": run, "step": 1, "operation": SUMMARY_REINDEX, "seconds": time.perf_counter() - started}
        )
    container.resets.reset_everything(CONFIRM_RESET_EVERYTHING)


def _environment(container: Any, books: Path, commit: str | None) -> dict[str, Any]:
    """What a benchmark run records (BenchmarkRunner._describe_environment), without the dataset's checksum."""
    from app.evaluation import benchmark
    from app.utils.gpu import query_gpu
    from app.utils.hashing import file_checksum

    settings = container.settings
    runtime = container.runtime
    gpu = query_gpu()
    models = sorted({settings.llm.model, settings.embedding.model})
    return {
        "date": _now(),
        "configuration_sha256": hashlib.sha256(settings.model_dump_json().encode()).hexdigest(),
        "configuration": settings.model_dump(),
        "ollama_version": runtime.version(),
        "models": {model: dataclasses.asdict(runtime.model_info(model)) for model in models},
        "hardware": {
            "cpu": benchmark._cpu_model(),
            "gpu": gpu.name if gpu else None,
            "gpu_memory_mb": gpu.memory_total_mb if gpu else None,
            "gpu_driver": benchmark._gpu_driver(),
        },
        "python": platform.python_version(),
        "packages": {name: benchmark._package_version(name) for name in benchmark._TRACKED_PACKAGES},
        "commit": commit,
        "book_sha256": {name: file_checksum(books / name) for name in BOOKS},
    }


def _expected_totals(
    books: Path, results: Results, book_ids: Mapping[str, str]
) -> dict[tuple[str, str | None], int | set[int]]:
    import pymupdf

    expected: dict[tuple[str, str | None], int] = {}
    for name, book_id in book_ids.items():
        if name.endswith(".pdf"):
            with pymupdf.open(books / name) as document:
                expected[("extract", book_id)] = document.page_count
    expected.update({("embed", book_id): counts for book_id, counts in results.chunk_counts.items()})
    if results.summary_count is not None:
        expected[("summaries", None)] = results.summary_count
    return expected


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _verdict(ok: bool) -> str:
    return "pass" if ok else "**fail**"


def _report(
    directory: Path,
    results: Results,
    log_lines: list[dict[str, Any]],
    expected: Mapping[tuple[str, str | None], int | set[int]],
    baseline: Path | None,
) -> str:
    lines = [f"# Library progress measurement, {directory.name}", ""]
    stage_lines = [line for line in log_lines if line.get("message") in ("stage finished", "stage failed")]
    if results.samples:
        problems = counts_never_go_back(results.samples) + counts_reach_totals(stage_lines, expected)
        lines += [f"- **SC-002**: {_verdict(not problems)}, {len(problems)} problems.", *[f"  - {p}" for p in problems]]
        accuracy = estimate_accuracy(results.samples)
        share = "none shown" if accuracy["share"] is None else f"{accuracy['share']:.3f}"
        lines.append(
            f"- **SC-003**: {_verdict(accuracy['ok'])}, {accuracy['within']} of {accuracy['shown']} times left "
            f"within half and double ({share}), {len(accuracy['premature'])} premature."
        )
        lines += [f"  - premature: {p}" for p in accuracy["premature"]]
        sums = stage_sums(log_lines)
        failed = [row for row in sums if not row["ok"]]
        widest = max((abs(row["gap"]) for row in sums), default=0.0)
        lines.append(
            f"- **SC-009**: {_verdict(bool(sums) and not failed)}, {len(sums)} operations with stage lines, "
            f"the widest gap {widest:.3f} s."
        )
        lines += [f"  - {row['operation']} {row['execution_id']}: gap {row['gap']:.3f} s" for row in failed]
    if baseline is not None:
        differences = digest_differences(json.loads((baseline / "digests.json").read_text()), results.digests)
        lines += [f"- **SC-004**: {_verdict(not differences)}, {len(differences)} files differ."]
        lines += [f"  - {d}" for d in differences]
        with (baseline / "durations.csv").open(encoding="utf-8") as file:
            rows = overhead(list(csv.DictReader(file)), results.durations)
        lines.append(f"- **SC-005**: {_verdict(all(row['ok'] for row in rows))}.")
        lines += [
            "",
            "| Step | Operation | Baseline (s) | Feature (s) | Limit (s) | |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {r['step']} | {r['operation']} | {r['baseline']:.2f} | {r['feature']:.2f} | {r['limit']:.2f} | "
            f"{'ok' if r['ok'] else 'over'} |"
            for r in rows
        ]
    medians = median_durations(results.durations)
    lines += ["", "| Step | Operation | Median (s) |", "| --- | --- | --- |"]
    lines += [f"| {step} | {operation} | {seconds:.2f} |" for (step, operation), seconds in sorted(medians.items())]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", action="store_true", help="call only the API main has")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--books", type=Path, default=Path("benchmarks/books"))
    parser.add_argument("--baseline-results", type=Path, default=None)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--report", type=Path, default=None, help="recompute a run's report from its files")
    arguments = parser.parse_args(argv)
    if arguments.report is not None:
        return _rewrite_report(arguments.report, arguments.books, arguments.baseline_results)

    from app.config.loader import load_settings
    from app.config.settings import EnvironmentSettings
    from app.container import assemble
    from app.utils.logging import configure_logging

    environment = EnvironmentSettings()
    settings = load_settings(environment.config_dir)
    workspace = environment.benchmarks_dir / WORKSPACE.relative_to("benchmarks")
    environment = environment.model_copy(update={"data_dir": workspace / "data", "logs_dir": workspace / "logs"})
    logs = workspace / "logs" / "app.jsonl"
    logs.unlink(missing_ok=True)
    configure_logging(environment.log_level, settings.logging.inference_level, environment.logs_dir, console=False)
    container = assemble(settings, environment, collection_prefix=COLLECTION_PREFIX)
    container.library.recover()

    results = Results()
    book_ids: dict[str, str] = {}
    for run in range(1, arguments.runs + 1):
        print(f"run {run} of {arguments.runs}", file=sys.stderr)
        sequence = Run(container, arguments.books, arguments.baseline, run, results)
        sequence.run()
        book_ids = sequence.book_ids
    if not arguments.baseline:
        print("the reindex that writes two saved summaries again", file=sys.stderr)
        _summary_reindex(container, arguments.books, results, arguments.runs + 1)

    name = f"library_progress_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    directory = environment.benchmarks_dir / "results" / name
    directory.mkdir(parents=True)
    (directory / "environment.json").write_text(
        json.dumps(_environment(container, arguments.books, arguments.commit), indent=2, default=str), encoding="utf-8"
    )
    _write_csv(directory / "durations.csv", results.durations)
    (directory / "digests.json").write_text(json.dumps(results.digests, indent=2, sort_keys=True), encoding="utf-8")
    counts = {book_id: sorted(values) for book_id, values in results.chunk_counts.items()}
    (directory / "chunk_counts.json").write_text(json.dumps(counts, indent=2, sort_keys=True), encoding="utf-8")
    (directory / "book_ids.json").write_text(json.dumps(book_ids, indent=2), encoding="utf-8")
    log_lines = _read_jsonl(logs)
    if results.samples:
        with (directory / "timeline.jsonl").open("w", encoding="utf-8") as file:
            for sample in results.samples:
                file.write(json.dumps(sample) + "\n")
        with (directory / "stage_lines.jsonl").open("w", encoding="utf-8") as file:
            for line in log_lines:
                if "stage" in line or line.get("message", "").startswith("operation "):
                    file.write(json.dumps(line, ensure_ascii=False) + "\n")
    expected = _expected_totals(arguments.books, results, book_ids)
    report = _report(directory, results, log_lines, expected, arguments.baseline_results)
    (directory / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(directory)
    return 0


def _rewrite_report(directory: Path, books: Path, baseline: Path | None) -> int:
    """Recompute a run's report from the files it wrote, without running anything."""
    results = Results(
        digests=json.loads((directory / "digests.json").read_text()),
        samples=_read_jsonl(directory / "timeline.jsonl"),
        chunk_counts={
            key: set(values) for key, values in json.loads((directory / "chunk_counts.json").read_text()).items()
        },
    )
    with (directory / "durations.csv").open(encoding="utf-8") as file:
        results.durations = list(csv.DictReader(file))
    if any(row["operation"] == SUMMARY_REINDEX for row in results.durations):
        results.summary_count = 2
    book_ids = json.loads((directory / "book_ids.json").read_text())
    expected = _expected_totals(books, results, book_ids)
    report = _report(directory, results, _read_jsonl(directory / "stage_lines.jsonl"), expected, baseline)
    (directory / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
