r"""Compare two retrieval runs question by question, with the project's paired bootstrap.

`book-rag benchmark-report --baseline` pairs the variants of one run, and one run can't hold two
versions of the code. This script pairs two runs of one variant each instead: the default retrieval
configuration on main's code with the original books, and on the Markdown-only branch with
their conversions (specs/005-markdown-only, FR-020, research.md R13).

It merges both runs' rows under the labels given, leaving out each question whose evidence
resolved to no chunk in one of the runs (its metrics would measure the chunking, not the
retrieval), and renders them with app.evaluation.report: each metric's difference, with its 95%
interval from 4,000 resamples. Then it lists the questions whose Recall@5, MRR or nDCG@10 moved,
and shows what each run retrieved for them: the ranks the evidence took, and the chunks that ranked
above it, down to the lowest-ranked evidence among the first ten (specs/007-retrieval-rows). A run
written before the rows recorded their rankings says so. Each run's chunk IDs are its own, since
another chunking or ingestion numbers the chunks differently. It runs on the host, from the
repository's root:

    uv run python devtools/compare_runs.py benchmarks/results/markdown_books_<main> \
        benchmarks/results/markdown_books_<branch> --labels originals markdown
"""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evaluation.benchmark import _RETRIEVAL_METRICS, summarize
from app.evaluation.report import render

_MOVING = ("recall_at_5", "mrr", "ndcg_at_10")
_DEEPEST = 10  # Recall@10 and nDCG@10 read no deeper, and MRR only down to the first evidence


class ComparisonError(Exception):
    """The two runs can't be paired."""


@dataclass(frozen=True)
class Merged:
    """Both runs as one, for app.evaluation.report.

    Attributes:
        results: a results.json's shape, holding both runs' rows under their labels.
        left_out: the questions left out, each with the run where its evidence resolved nowhere.
    """

    results: dict[str, Any]
    left_out: list[tuple[str, str]]


def merge(baseline: Mapping[str, Any], changed: Mapping[str, Any], labels: Sequence[str]) -> Merged:
    """Pair two runs' rows by question.

    Raises:
        ComparisonError: a run isn't a retrieval run, holds more than one variant, or the two share
            no question.
    """
    runs = (baseline, changed)
    for label, run in zip(labels, runs, strict=True):
        if run["experiment"]["kind"] != "retrieval":
            raise ComparisonError(f"{label} is a {run['experiment']['kind']} run, not a retrieval run.")
        variants = {row["variant"] for row in run["rows"]}
        if len(variants) != 1:
            raise ComparisonError(f"{label} holds {len(variants)} variants: a comparison needs one variant per run.")
    shared = {row["question"] for row in baseline["rows"]} & {row["question"] for row in changed["rows"]}
    if not shared:
        raise ComparisonError("The two runs share no question.")

    left_out = [
        (row["question"], label)
        for label, run in zip(labels, runs, strict=True)
        for row in run["rows"]
        if row["question"] in shared and not row["relevant_chunks"]
    ]
    excluded = {question for question, _ in left_out}
    rows = [
        {**row, "variant": label}
        for label, run in zip(labels, runs, strict=True)
        for row in run["rows"]
        if row["question"] in shared and row["question"] not in excluded
    ]
    name = changed["experiment"]["name"]
    results = {
        "experiment": {
            "name": f"{name}: {labels[0]} vs {labels[1]}",
            "kind": "retrieval",
            "description": changed["experiment"]["description"],
        },
        "complete": changed["complete"],
        "sample_limit": changed["sample_limit"],
        "environment": changed["environment"],
        "summary": summarize(rows, _RETRIEVAL_METRICS),
        "by_category": summarize(rows, _RETRIEVAL_METRICS, "category"),
        "by_book": summarize(rows, _RETRIEVAL_METRICS, "book"),
        "rows": rows,
    }
    return Merged(results, left_out)


def moved(rows: Sequence[Mapping[str, Any]], labels: Sequence[str]) -> list[list[str]]:
    """The questions whose Recall@5, MRR or nDCG@10 differ between the runs, with both runs' values."""
    by_question: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        by_question.setdefault(row["question"], {})[row["variant"]] = row
    table = []
    for question, pair in by_question.items():
        before, after = pair.get(labels[0]), pair.get(labels[1])
        if before is None or after is None or all(before[metric] == after[metric] for metric in _MOVING):
            continue
        values = [f"{before[metric]:.3f} → {after[metric]:.3f}" for metric in _MOVING]
        table.append(
            [question, after["book"], after["category"], *values, before["relevant_chunks"], after["relevant_chunks"]]
        )
    return table


def ranked_above(row: Mapping[str, Any]) -> tuple[str, str]:
    """What ranked above a question's evidence in one run: the ranks its evidence took, and the others.

    The reading goes down to the lowest-ranked evidence among the first ten, as deep as the scores
    that decide whether a question moved read. When none of the evidence is there, it goes down to
    the first piece of evidence, which MRR reads however deep. The evidence is the run's own
    relevant_chunks: a chunk ID holds within its run only (specs/007-retrieval-rows, FR-009 to FR-011).

    Returns:
        The cells "evidence at" and "ranked above it".
    """
    ranking = row.get("ranking")
    if ranking is None:  # written before the rows recorded their rankings
        return "not recorded", "not recorded"
    evidence = {chunk_id for chunk_id in row["relevant_chunks"].split("; ") if chunk_id}
    ranks = [rank for rank, chunk_id in enumerate(ranking, start=1) if chunk_id in evidence]
    if not ranks:  # the chunks that took the evidence's places
        return "not retrieved", _ranked(enumerate(ranking[:_DEEPEST], start=1))
    within = [rank for rank in ranks if rank <= _DEEPEST]
    depth = within[-1] if within else ranks[0]
    above = [(rank, chunk_id) for rank, chunk_id in enumerate(ranking[: depth - 1], start=1) if chunk_id not in evidence]
    return ", ".join(str(rank) for rank in ranks if rank <= depth), _ranked(above)


def _ranked(chunks: Iterable[tuple[int, str]]) -> str:
    return "; ".join(f"{rank}: {chunk_id}" for rank, chunk_id in chunks) or "none"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(" --- " for _ in headers) + "|",
        *("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows),
    ]


def render_comparison(baseline: Mapping[str, Any], changed: Mapping[str, Any], labels: Sequence[str]) -> str:
    """The comparison as Markdown: what each run was, what was left out, the pairing and what moved."""
    merged = merge(baseline, changed, labels)
    lines = ["# Two runs, paired by question", ""]
    for label, run in zip(labels, (baseline, changed), strict=True):
        environment = run["environment"]
        books = ", ".join(f"{key} {checksum[:8]}" for key, checksum in environment["book_sha256"].items() if checksum)
        lines.append(
            f"- {label}: commit {environment['commit']}, dataset {environment['dataset_sha256'][:12]}, "
            f"books {books}, run on {environment['date']}"
        )
    left_out = ", ".join(f"{question} (no evidence found in {label})" for question, label in merged.left_out)
    lines += ["", f"Left out of the pairing, {len(merged.left_out)}: {left_out or 'none'}.", ""]
    lines.append(render(merged.results, baseline=labels[0]).rstrip("\n"))
    headers = [
        "question",
        "book",
        "category",
        *_MOVING,
        f"relevant_chunks ({labels[0]})",
        f"relevant_chunks ({labels[1]})",
    ]
    table = moved(merged.results["rows"], labels)
    lines += ["", "## Questions that moved", ""]
    lines += _table(headers, table) if table else ["None."]
    if table:
        rows = {(row["question"], row["variant"]): row for row in merged.results["rows"]}
        readings = [[entry[0], label, *ranked_above(rows[entry[0], label])] for entry in table for label in labels]
        lines += ["", "## What ranked above the evidence", ""]
        lines += _table(["question", "run", "evidence at", "ranked above it"], readings)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("baseline", type=Path, help="the first run's results directory")
    parser.add_argument("changed", type=Path, help="the second run's results directory")
    parser.add_argument("--labels", nargs=2, default=("originals", "markdown"), metavar=("BASELINE", "CHANGED"))
    arguments = parser.parse_args()
    runs = [
        json.loads((directory / "results.json").read_text(encoding="utf-8"))
        for directory in (arguments.baseline, arguments.changed)
    ]
    try:
        print(render_comparison(*runs, arguments.labels), end="")
    except ComparisonError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
