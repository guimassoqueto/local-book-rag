import pytest

from app.errors import ConfigurationError
from app.evaluation.quiz_metrics import (
    READING_FIELDS,
    letter_spread,
    read_reading,
    refusal_counts,
    summarize_reading,
    thirds,
    write_reading,
)


def question(letter="A", third=0, variant="v", **fields):
    return {"variant": variant, "row": "question", "letter": letter, "third": third, **fields}


def reading_row(mark="", reasons="", note="", variant="v", question="b:One:1"):
    return {"variant": variant, "question": question, "mark": mark, "reasons": reasons, "note": note}


def test_the_letter_spread_is_the_share_of_keys_on_each_letter():
    rows = [question("A"), question("A"), question("C"), question("E"), {"variant": "v", "row": "quiz"}]

    assert letter_spread(rows) == {"A": 0.5, "B": 0.0, "C": 0.25, "D": 0.0, "E": 0.25}


def test_the_letter_spread_of_no_questions_is_empty():
    assert letter_spread([]) == {}


def test_thirds_are_the_share_of_questions_from_each_third_of_their_chapter():
    rows = [question(third=0), question(third=1), question(third=1), question(third=2)]

    assert thirds(rows) == (0.25, 0.5, 0.25)


def test_refusals_are_summed_by_kind():
    rows = [question(refused_unreadable=1, refused_cut_off=0), question(refused_unreadable=2, refused_cut_off=1)]

    counts = refusal_counts(rows)

    assert counts["unreadable"] == 3
    assert counts["cut_off"] == 1
    assert counts["wrong_language"] == 0


def test_the_reading_is_written_with_empty_marks_and_read_back(tmp_path):
    path = tmp_path / "reading.csv"
    entry = {field: f"{field} value" for field in READING_FIELDS if field not in ("mark", "reasons", "note")}

    write_reading(path, [entry])
    [row] = read_reading(path)

    assert list(row) == list(READING_FIELDS)
    assert row["text"] == "text value"
    assert (row["mark"], row["reasons"], row["note"]) == ("", "", "")


def test_the_reading_keeps_line_breaks_and_commas(tmp_path):
    path = tmp_path / "reading.csv"
    passage = 'A passage, with commas;\nand "quotes" over\n\ntwo paragraphs.'

    write_reading(path, [{"question": "q", "passage": passage}])

    assert read_reading(path)[0]["passage"] == passage


def test_the_share_of_sound_keys_counts_marked_rows_only():
    rows = [
        reading_row("sound"),
        reading_row("sound"),
        reading_row("sound"),
        reading_row("flawed", "wrong_key"),
        reading_row(""),
        reading_row(""),
    ]

    summary = summarize_reading(rows)

    assert (summary.marked, summary.unmarked, summary.sound, summary.flawed) == (4, 2, 3, 1)
    assert summary.sound_share == 0.75


def test_an_unmarked_reading_has_no_share():
    assert summarize_reading([reading_row(""), reading_row("")]).sound_share is None


def test_flawed_rows_are_counted_by_reason():
    rows = [
        reading_row("flawed", "wrong_key"),
        reading_row("flawed", "two_defensible; explanation_beyond_passage"),
        reading_row("flawed", "two_defensible,nothing_to_ask"),
    ]

    reasons = summarize_reading(rows).reasons

    assert reasons == {"wrong_key": 1, "two_defensible": 2, "explanation_beyond_passage": 1, "nothing_to_ask": 1}


def test_questions_that_refer_to_their_passage_are_counted():
    rows = [
        reading_row("sound", note="refers_to_passage"),
        reading_row("flawed", "wrong_key", note="weak wording; refers_to_passage"),
        reading_row("sound", note="weak wording"),
    ]

    assert summarize_reading(rows).refers_to_passage == 2


def test_the_reading_is_summarized_per_variant():
    rows = [reading_row("sound", variant="one"), reading_row("flawed", "wrong_key", variant="two")]

    assert summarize_reading(rows, "one").sound_share == 1.0
    assert summarize_reading(rows, "two").sound_share == 0.0


@pytest.mark.parametrize(
    "row",
    [reading_row("good"), reading_row("flawed", "wrong"), reading_row("flawed", ""), reading_row("sound", "wrong_key")],
)
def test_a_mark_or_reason_outside_the_rubric_is_reported(row):
    with pytest.raises(ConfigurationError, match="b:One:1"):
        summarize_reading([row])
