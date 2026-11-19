"""devtools/measure_library_progress.py: the measurement of the library's progress (specs/004-library-progress).

The script runs in the app container, so it isn't a package: it is loaded here by path. What it does
against the stack is checked by running it. What decides each success criterion is checked here, on
made-up records.
"""

import importlib.util
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "measure_library_progress", PROJECT / "devtools" / "measure_library_progress.py"
)
measure = importlib.util.module_from_spec(_spec)
sys.modules["measure_library_progress"] = measure
_spec.loader.exec_module(measure)


def sample(t, done, total, time_left=None, stage="embed", step=1, run=1, operation="Adding a book", **extra):
    return {
        "run": run,
        "step": step,
        "operation": operation,
        "t": t,
        "stage": stage,
        "step_key": None,
        "item": None,
        "done": done,
        "total": total,
        "time_left": time_left,
        **extra,
    }


# SC-002


def test_a_count_that_only_grows_passes():
    samples = [sample(0.25, 0, 10), sample(0.5, 4, 10), sample(0.75, 10, 10)]

    assert measure.counts_never_go_back(samples) == []


def test_a_count_that_goes_back_fails():
    samples = [sample(0.25, 5, 10), sample(0.5, 3, 10)]

    assert len(measure.counts_never_go_back(samples)) == 1


def test_a_new_stage_starts_its_own_count():
    samples = [sample(0.25, 10, 10, stage="extract"), sample(0.5, 0, 20, stage="embed")]

    assert measure.counts_never_go_back(samples) == []


def line(stage, done, total, book="book_001", message="stage finished", **extra):
    return {"message": message, "stage": stage, "done": done, "total": total, "book_id": book, **extra}


def test_a_stage_that_ends_at_the_true_total_passes():
    lines = [line("extract", 244, 244), line("embed", 425, 425)]

    assert measure.counts_reach_totals(lines, {("extract", "book_001"): 244, ("embed", "book_001"): {425}}) == []


def test_a_stage_that_stops_short_fails():
    assert measure.counts_reach_totals([line("embed", 400, 425)], {}) == ["embed book_001: ended at 400 of 425"]


def test_a_total_that_isnt_what_the_book_holds_fails():
    problems = measure.counts_reach_totals([line("extract", 240, 240)], {("extract", "book_001"): 244})

    assert problems == ["extract book_001: total 240, but there are 244"]


def test_a_reindex_step_is_matched_by_its_item():
    lines = [line("embed", 176, 176, book=None, item="book_003", within="books")]

    assert measure.counts_reach_totals(lines, {("embed", "book_003"): {176, 454}}) == []


def test_the_librarys_counts_are_matched_without_a_book():
    assert measure.counts_reach_totals([line("summaries", 2, 2, book=None)], {("summaries", None): 2}) == []


def test_a_failed_stage_isnt_held_to_its_total():
    assert measure.counts_reach_totals([line("embed", 100, 425, message="stage failed")], {}) == []


# SC-003


def stage_samples(times, total=100, pace=0.1, **extra):
    """A stage that does an item every `pace` seconds from t=0, sampled at `times`, ending at total × pace."""
    rows = []
    for t in times:
        done = min(int(t / pace), total)
        rows.append(sample(t, done, total, **extra))
    return rows


def test_times_left_within_half_and_double_pass():
    rows = stage_samples([0.25 * i for i in range(1, 40)])
    for row in rows:
        if row["t"] >= 3.25:
            row["time_left"] = 10.0 - row["t"]  # the truth
    rows.append(sample(10.0, 0, 0, stage="save"))  # the next stage: the embedding ends between them

    result = measure.estimate_accuracy(rows)

    assert result["shown"] > 0 and result["share"] == 1.0 and result["premature"] == [] and result["ok"]


def test_times_left_three_times_too_long_fail():
    rows = stage_samples([0.25 * i for i in range(1, 40)])
    for row in rows:
        if row["t"] >= 3.25:
            row["time_left"] = 3 * (10.0 - row["t"])
    rows.append(sample(10.0, 0, 0, stage="save"))

    result = measure.estimate_accuracy(rows)

    assert result["share"] == 0.0 and not result["ok"]


def test_a_time_left_before_three_seconds_is_premature():
    rows = stage_samples([0.25 * i for i in range(1, 40)])
    rows[3]["time_left"] = 10.0 - rows[3]["t"]  # at 1 s
    rows.append(sample(10.0, 0, 0, stage="save"))

    result = measure.estimate_accuracy(rows)

    assert len(result["premature"]) == 1 and not result["ok"]


def test_a_time_left_before_a_tenth_of_the_items_is_premature():
    rows = stage_samples([0.25 * i for i in range(1, 40)], pace=1.0, total=100)  # 4 items done at 4 s
    rows[15]["time_left"] = 96.0
    rows.append(sample(10.0, 0, 0, stage="save"))

    assert len(measure.estimate_accuracy(rows)["premature"]) == 1


def test_only_the_additions_count():
    rows = stage_samples([0.25 * i for i in range(1, 40)], operation="Reindexing the library")
    for row in rows:
        row["time_left"] = 100.0

    result = measure.estimate_accuracy(rows)

    assert result["shown"] == 0 and result["share"] is None and not result["ok"]


def test_the_last_stage_ends_when_the_operation_does():
    rows = stage_samples([0.25 * i for i in range(1, 40)], finished=10.0)
    for row in rows:
        if row["t"] >= 3.25:
            row["time_left"] = 10.0 - row["t"]

    assert measure.estimate_accuracy(rows)["share"] == 1.0


# SC-004


def test_equal_digests_pass():
    assert measure.digest_differences({"a": "1", "b": "2"}, {"a": "1", "b": "2"}) == []


def test_a_differing_byte_fails():
    assert measure.digest_differences({"a": "1"}, {"a": "2"}) == ["different: a"]


def test_a_file_only_one_run_wrote_fails():
    assert measure.digest_differences({"a": "1"}, {"a": "1", "b": "2"}) == ["only in one run: b"]


# SC-005


def durations(step, operation, *seconds):
    return [{"run": run, "step": step, "operation": operation, "seconds": value} for run, value in enumerate(seconds)]


def test_the_medians_are_compared():
    baseline = durations(1, "add_book", 20.0, 22.0, 21.0)
    feature = durations(1, "add_book", 25.0, 21.9, 22.0)

    [row] = measure.overhead(baseline, feature)

    assert (row["baseline"], row["feature"], row["limit"], row["ok"]) == (21.0, 22.0, 22.05, True)


def test_more_than_five_percent_longer_fails():
    [row] = measure.overhead(durations(1, "add_book", 40.0, 40.0, 40.0), durations(1, "add_book", 42.5, 42.5, 42.5))

    assert row["limit"] == 42.0 and not row["ok"]


def test_a_second_is_allowed_on_a_short_operation():
    [row] = measure.overhead(durations(9, "remove_book", 0.1, 0.1, 0.1), durations(9, "remove_book", 1.0, 1.0, 1.0))

    assert row["ok"]


def test_the_reindex_with_summaries_is_left_out():
    baseline = durations(1, measure.SUMMARY_REINDEX, 100.0)
    feature = durations(1, measure.SUMMARY_REINDEX, 300.0)

    assert measure.overhead(baseline, feature) == []


def test_durations_read_back_from_csv_are_compared_as_numbers():
    baseline = [{"run": "1", "step": "1", "operation": "add_book", "seconds": "10.0"}]

    [row] = measure.overhead(baseline, durations(1, "add_book", 10.4))

    assert row["ok"]


# SC-009


def log(execution, message, seconds=None, within=None, operation="add_book"):
    entry = {"execution_id": execution, "operation": operation, "message": message}
    if seconds is not None:
        entry["duration_seconds"] = seconds
    if within is not None:
        entry["within"] = within
    return entry


def test_top_level_stages_that_add_up_pass():
    lines = [
        log("e1", "operation started"),
        log("e1", "stage finished", 1.0),
        log("e1", "stage finished", 2.0),
        log("e1", "operation finished", 3.4),
    ]

    [row] = measure.stage_sums(lines)

    assert row["ok"] and round(row["gap"], 3) == 0.4


def test_steps_arent_summed():
    lines = [
        log("e1", "stage finished", 5.0),
        log("e1", "stage finished", 4.0, within="books"),
        log("e1", "operation finished", 5.2),
    ]

    [row] = measure.stage_sums(lines)

    assert row["ok"]


def test_a_gap_over_a_second_fails():
    lines = [log("e1", "stage finished", 1.0), log("e1", "operation failed", 2.5)]

    [row] = measure.stage_sums(lines)

    assert not row["ok"]


def test_an_operation_without_stage_lines_isnt_judged():
    assert measure.stage_sums([log("e1", "operation finished", 2.0)]) == []
