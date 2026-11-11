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


# The quiz sections (specs/003-chapter-quiz, contracts/quiz-experiments.md)


def quiz_results(variants=("writer",)):
    from app.evaluation.benchmark import QUIZ_METRICS, summarize_quiz

    rows = []
    for variant in variants:
        for position, (letter, third, closed) in enumerate(
            [("A", 0, True), ("B", 1, False), ("C", 2, None), ("D", 1, True), ("E", 0, False)], start=1
        ):
            rows.append(
                {
                    "variant": variant,
                    "row": "question",
                    "question": f"b:One:{position}",
                    "book": "b",
                    "chapter": "One",
                    "letter": letter,
                    "third": third,
                    "key_is_longest": position == 1,
                    "key_is_shortest": position == 2,
                    "closed_book_correct": closed,
                    "refused_unreadable": 1 if position == 2 else 0,
                    "refused_passage_reference": 2 if position == 3 else 0,
                }
            )
        rows.append(
            {
                "variant": variant,
                "row": "quiz",
                "book": "b",
                "chapter": "One",
                "asked": 6,
                "delivered": 5,
                "delivered_share": 5 / 6,
                "seconds": 20.0,
                "first_question_seconds": 3.0,
                "skipped_passages": 2,
                "passed_over_passages": 1,
                "ruled_out_chapters": 0,
                "check_unreadable": 1,
            }
        )
    return {
        "experiment": {"name": "quiz", "kind": "quiz", "description": "Measures questions."},
        "complete": True,
        "sample_limit": None,
        "environment": {"date": "2026-11-11", "ollama_version": "0.40.15", "hardware": {"gpu": "RTX"}},
        "summary": summarize_quiz(rows, QUIZ_METRICS),
        "by_book": summarize_quiz(rows, QUIZ_METRICS, "book"),
        "rows": rows,
    }


def test_the_quiz_report_shows_every_measure():
    report = render(quiz_results())

    assert "## Letters" in report
    assert "| writer | 0.200 | 0.200 | 0.200 | 0.200 | 0.200 |" in report
    assert "## Where questions come from" in report
    assert "| writer | 0.400 | 0.400 | 0.200 |" in report
    assert "## Refusals and skips" in report
    assert "| writer | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 2 | 1 | 1 |" in report
    assert "key_is_longest" in report
    assert "key_is_shortest" in report
    assert "delivered_share" in report
    assert "first_question_seconds" in report
    assert "closed_book_unreadable" in report


def test_closed_book_correct_is_shown_without_a_target():
    report = render(quiz_results())

    assert "closed_book_correct" in report
    assert "target" not in report.split("closed_book_correct")[1].split("\n")[0]


def test_the_quiz_report_reads_the_marks_when_there_are_some():
    reading = [
        {"variant": "writer", "question": "b:One:1", "mark": "sound", "reasons": "", "note": ""},
        {"variant": "writer", "question": "b:One:2", "mark": "sound", "reasons": "", "note": "refers_to_passage"},
        {"variant": "writer", "question": "b:One:3", "mark": "flawed", "reasons": "wrong_key", "note": ""},
        {"variant": "writer", "question": "b:One:4", "mark": "", "reasons": "", "note": ""},
    ]

    report = render(quiz_results(), reading=reading)

    assert "## The reading" in report
    assert "| writer | 3 | 2 | 1 | 1 | 0.667 | 1 |" in report
    assert "wrong_key: 1" in report


def test_the_quiz_report_says_when_nothing_is_marked():
    unmarked = [{"variant": "writer", "question": "q", "mark": "", "reasons": "", "note": ""}]

    report = render(quiz_results(), reading=unmarked)

    assert "No question is marked yet" in report


def test_quiz_variants_pair_question_by_question():
    results = quiz_results(("one", "two"))

    report = render(results, baseline="one")

    assert "## Compared with one" in report
    assert "key_is_longest" in report.split("## Compared with one")[1]


def test_a_check_run_shows_its_catches_and_its_verdict():
    summary = [
        {
            "variant": "medium",
            "samples": 40,
            "missing_quotes": 1,
            "flawed_cases": 10,
            "flawed_caught": 8,
            "sound_cases": 30,
            "sound_rejected": 2,
            "unreadable": 1,
            "comparator_flawed_caught": 3,
            "comparator_unreadable": 0,
            "difference": {"mean": 0.5, "low": 0.2, "high": 0.8, "pairs": 10},
            "rule_passes": True,
            "rule_reason": "(a) the check catches more flawed cases than the comparator; (b) ...",
        }
    ]
    results = {
        "experiment": {"name": "quiz_check", "kind": "quiz_check", "description": "Proves the check."},
        "complete": True,
        "sample_limit": None,
        "environment": {"date": "2026-11-11", "ollama_version": "0.40.15", "hardware": {"gpu": "RTX"}},
        "summary": summary,
        "rows": [],
    }

    report = render(results)

    assert "| medium | 8 of 10 | 0.800 | 2 of 30 | 0.067 | 0.300 | 0 | 1 | 1 | passes |" in report
    assert "over 10 flawed cases: +0.500 (+0.200 to +0.800)" in report
    with pytest.raises(ConfigurationError, match="comparator"):
        render(results, baseline="medium")
