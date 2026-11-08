import pytest

from app.errors import ConfigurationError
from app.evaluation.benchmark import summarize
from app.evaluation.report import paired_difference, render


def row(variant, question, recall, mrr=None):
    return {"variant": variant, "question": question, "category": "factual", "recall_at_5": recall, "mrr": mrr}


def scored(variant, recall, questions=20):
    return [row(variant, f"q{index}", recall) for index in range(questions)]


def results(rows, kind="retrieval", complete=True):
    metrics = ["recall_at_5", "mrr"]
    return {
        "experiment": {"name": "retrieval", "kind": kind, "description": "Compares retrieval."},
        "complete": complete,
        "sample_limit": None if complete else 2,
        "environment": {"date": "2026-11-07", "ollama_version": "0.40.15", "hardware": {"gpu": "RTX"}},
        "summary": summarize(rows, metrics),
        "by_category": summarize(rows, metrics, "category"),
        "rows": rows,
    }


def test_a_consistent_gain_is_real():
    rows = [*scored("base", 0.5), *scored("better", 0.6)]

    difference = paired_difference(rows, "base", "better", "recall_at_5")

    assert difference.mean == pytest.approx(0.1)
    assert difference.real
    assert difference.pairs == 20


def test_a_gain_on_some_questions_and_a_loss_on_others_is_noise():
    base = [row("base", f"q{index}", 0.5) for index in range(20)]
    other = [row("other", f"q{index}", 1.0 if index % 2 else 0.0) for index in range(20)]

    difference = paired_difference(base + other, "base", "other", "recall_at_5")

    assert not difference.real


def test_only_items_both_variants_scored_are_paired():
    rows = [row("base", "q1", 0.5), row("base", "q2", 0.5), row("other", "q1", 0.7), row("other", "q2", None)]

    assert paired_difference(rows, "base", "other", "recall_at_5").pairs == 1
    assert paired_difference(rows, "base", "other", "mrr") is None


def test_the_report_shows_each_variant_and_marks_real_differences():
    rows = [*scored("base", 0.5), *scored("better", 0.6)]

    report = render(results(rows), baseline="base")

    assert "| better | 0.600 | – |" in report
    assert "## By category" in report
    assert "| better | **+0.100 (+0.100 to +0.100)** | – |" in report


def test_a_sample_says_so():
    assert "A sample of 2" in render(results([row("base", "q1", 0.5)], complete=False))


def test_an_unknown_baseline_is_refused():
    with pytest.raises(ConfigurationError, match="no variant named nope"):
        render(results([row("base", "q1", 0.5)]), baseline="nope")


def test_performance_runs_have_nothing_to_pair():
    with pytest.raises(ConfigurationError, match="nothing to pair"):
        render(results([row("base", "q1", 0.5)], kind="performance"), baseline="base")
