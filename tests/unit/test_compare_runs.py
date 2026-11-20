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
ABOVE = "\n## What ranked above the evidence\n"  # the section after "Questions that moved"


def row(question, value, chunks="c1", book="a_book", category="factual", ranking=None):
    fields = {
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
    if ranking is not None:  # without one, a row as written before the rows recorded their rankings
        fields |= {"ranking": ranking, "context": ranking[:5]}
    return fields


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

    [line] = [line for line in text.split(ABOVE)[0].splitlines() if line.startswith("| q2 |")]
    assert "0.500" in line and "1.000" in line and "c1" in line
    assert not any(line.startswith("| q1 |") for line in text.splitlines())


def test_the_header_says_what_each_run_was_and_what_was_left_out():
    text = compare_runs.render_comparison(BASELINE, CHANGED, LABELS)

    assert "originals: commit main" in text and "markdown: commit branch" in text
    assert "q3 (no evidence found in originals)" in text and "q4 (no evidence found in markdown)" in text


@pytest.mark.parametrize(
    ("ranking", "evidence_at", "ranked_above"),
    [
        (["e1", "e2", "c1"], "1, 2", "none"),
        (
            ["c7", "c9", "e1", "c2", "c4", "c5", "e2", "c8", "c3", "c6", "e3"],
            "3, 7",
            "1: c7; 2: c9; 4: c2; 5: c4; 6: c5",
        ),
        (["e1", "c1", "c2", "e2", "c3"], "1, 4", "2: c1; 3: c2"),
        ([*(f"c{n}" for n in range(1, 13)), "e1", "c13"], "13", "; ".join(f"{n}: c{n}" for n in range(1, 13))),
        ([f"c{n}" for n in range(1, 31)], "not retrieved", "; ".join(f"{n}: c{n}" for n in range(1, 11))),
        (["c1", "c2", "c3"], "not retrieved", "1: c1; 2: c2; 3: c3"),
        ([], "not retrieved", "none"),
        (["c1", "e1", "c2"], "2", "1: c1"),
        (None, "not recorded", "not recorded"),
    ],
    ids=[
        "evidence first",
        "evidence below other chunks, the eleventh rank unread",
        "several quotes, one lower within the first ten",
        "none within the first ten",
        "none retrieved",
        "none retrieved, in a short ranking",
        "nothing retrieved",
        "a ranking shorter than ten",
        "a row without its ranking",
    ],
)
def test_a_run_shows_what_ranked_above_the_evidence(ranking, evidence_at, ranked_above):
    reading = compare_runs.ranked_above(row("q1", 1.0, chunks="e1; e2; e3", ranking=ranking))

    assert reading == (evidence_at, ranked_above)


def test_each_question_that_moved_shows_each_runs_reading_after_the_table():
    baseline = results([row("q1", 1.0, ranking=["c1", "x1"]), row("q2", 0.5, ranking=["x1", "c1", "x2"])])
    changed = results([row("q1", 1.0, ranking=["c1", "y1"]), row("q2", 1.0, ranking=["c1", "x1"])])

    before, section = compare_runs.render_comparison(baseline, changed, LABELS).split(ABOVE)

    assert "## Questions that moved" in before
    assert section.splitlines()[1:] == [
        "| question | run | evidence at | ranked above it |",
        "| --- | --- | --- | --- |",
        "| q2 | originals | 2 | 1: x1 |",  # x1 is shown where this run put it above the evidence
        "| q2 | markdown | 1 | none |",  # and not where the other run did, below it
    ]


def with_rankings(run):
    recorded = copy.deepcopy(run)
    for item in recorded["rows"]:
        item |= {"ranking": ["x1", "c1"], "context": ["x1", "c1"]}
    return recorded


def test_what_the_comparison_showed_before_stays_as_it_was():
    without = compare_runs.render_comparison(BASELINE, CHANGED, LABELS)

    recorded = compare_runs.render_comparison(with_rankings(BASELINE), with_rankings(CHANGED), LABELS)

    assert recorded.split(ABOVE)[0] == without.split(ABOVE)[0]


def test_nothing_is_shown_above_the_evidence_when_no_question_moved():
    run = results([row("q1", 1.0, ranking=["c1"]), row("q2", 0.5, ranking=["x1", "c1"])])

    text = compare_runs.render_comparison(run, copy.deepcopy(run), LABELS)

    assert text.rstrip().endswith("None.")
    assert ABOVE.strip() not in text


def section_rows(text):
    """The rows of "What ranked above the evidence", past its empty line, header and separator."""
    return text.split(ABOVE)[1].splitlines()[3:]


def test_runs_written_before_say_that_they_didnt_record_their_rankings():
    text = compare_runs.render_comparison(BASELINE, CHANGED, LABELS)

    assert section_rows(text) == [
        "| q2 | originals | not recorded | not recorded |",
        "| q2 | markdown | not recorded | not recorded |",
    ]


@pytest.mark.parametrize(
    ("baseline", "changed", "old", "new"),
    [
        (BASELINE, with_rankings(CHANGED), "originals", "markdown"),
        (with_rankings(BASELINE), CHANGED, "markdown", "originals"),
    ],
    ids=["the old run first", "the new run first"],
)
def test_a_run_written_before_pairs_with_one_written_after(baseline, changed, old, new):
    rows = section_rows(compare_runs.render_comparison(baseline, changed, LABELS))

    assert f"| q2 | {old} | not recorded | not recorded |" in rows
    assert f"| q2 | {new} | 2 | 1: x1 |" in rows


def test_the_runs_compared_are_left_as_they_were():
    baseline, changed = with_rankings(BASELINE), CHANGED
    before = copy.deepcopy((baseline, changed))

    compare_runs.render_comparison(baseline, changed, LABELS)

    assert (baseline, changed) == before


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
