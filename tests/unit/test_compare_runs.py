"""devtools/compare_runs.py: two retrieval runs, paired question by question (specs/005-markdown-only, FR-020).

The script isn't a package, so it is loaded here by path. What it computes is checked on made-up
results; the pairing itself is app.evaluation.report's.
"""

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

from app.evaluation.report import paired_difference

PROJECT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("compare_runs", PROJECT / "devtools" / "compare_runs.py")
compare_runs = importlib.util.module_from_spec(_spec)
sys.modules["compare_runs"] = compare_runs
_spec.loader.exec_module(compare_runs)

LABELS = ("originals", "markdown")
METRICS = ("recall_at_5", "recall_at_10", "mrr", "ndcg_at_10", "context_precision", "context_recall")


def row(question, value, chunks="c1", book="a_book", category="factual"):
    return {
        "variant": "default",
        "question": question,
        "book": book,
        "category": category,
        "relevant_chapters": "One",
        "relevant_chunks": chunks,
        **dict.fromkeys(METRICS, value),
        "retrieval_seconds": 0.1,
        "rerank_seconds": 0.2,
    }


def results(rows, commit="abc", dataset="d" * 64, kind="retrieval"):
    return {
        "experiment": {"name": "markdown_books", "kind": kind, "description": "The default, twice."},
        "complete": True,
        "sample_limit": None,
        "environment": {
            "date": "2026-11-19T00:00:00+00:00",
            "ollama_version": "0.40.15",
            "hardware": {"gpu": "A GPU"},
            "commit": commit,
            "dataset_sha256": dataset,
            "book_sha256": {"a_book": "b" * 64},
        },
        "summary": [],
        "by_category": [],
        "by_book": [],
        "rows": rows,
    }


BASELINE = results([row("q1", 1.0), row("q2", 0.5), row("q3", 0.0, chunks=""), row("q4", 1.0)], commit="main")
CHANGED = results([row("q1", 1.0), row("q2", 1.0), row("q3", 1.0), row("q4", 0.0, chunks="")], commit="branch")


def test_each_runs_variant_takes_its_label():
    merged = compare_runs.merge(BASELINE, CHANGED, LABELS)

    assert {item["variant"] for item in merged.results["rows"]} == set(LABELS)
    assert {item["variant"] for item in merged.results["summary"]} == set(LABELS)


def test_a_question_whose_evidence_resolved_nowhere_in_either_run_is_left_out_and_counted():
    merged = compare_runs.merge(BASELINE, CHANGED, LABELS)

    assert merged.left_out == [("q3", "originals"), ("q4", "markdown")]
    assert {item["question"] for item in merged.results["rows"]} == {"q1", "q2"}


def test_the_differences_are_the_projects_paired_bootstrap():
    merged = compare_runs.merge(BASELINE, CHANGED, LABELS)
    text = compare_runs.render_comparison(BASELINE, CHANGED, LABELS)

    difference = paired_difference(merged.results["rows"], "originals", "markdown", "recall_at_5")
    assert difference.pairs == 2
    assert f"{difference.mean:+.3f}" in text


def test_the_questions_that_moved_are_listed_with_both_runs():
    text = compare_runs.render_comparison(BASELINE, CHANGED, LABELS)

    [line] = [line for line in text.splitlines() if line.startswith("| q2 |")]
    assert "0.500" in line and "1.000" in line and "c1" in line
    assert not any(line.startswith("| q1 |") for line in text.splitlines())


def test_the_header_says_what_each_run_was_and_what_was_left_out():
    text = compare_runs.render_comparison(BASELINE, CHANGED, LABELS)

    assert "originals: commit main" in text and "markdown: commit branch" in text
    assert "q3 (no evidence found in originals)" in text and "q4 (no evidence found in markdown)" in text


def two_variants():
    second = copy.deepcopy(BASELINE)
    second["rows"].append(row("q1", 1.0) | {"variant": "other"})
    return second


@pytest.mark.parametrize(
    ("baseline", "changed", "problem"),
    [
        (results([row("x1", 1.0)]), CHANGED, "share no question"),
        (two_variants(), CHANGED, "one variant"),
        (results([row("q1", 1.0)], kind="generation"), CHANGED, "retrieval"),
    ],
    ids=["nothing shared", "two variants", "not retrieval"],
)
def test_runs_that_cant_be_paired_are_refused(baseline, changed, problem):
    with pytest.raises(compare_runs.ComparisonError, match=problem):
        compare_runs.render_comparison(baseline, changed, LABELS)
