import json

import httpx
import pytest
import yaml

from app.errors import BenchmarkDatasetError
from app.evaluation.dataset import (
    BenchmarkDataset,
    BenchmarkQuestion,
    dataset_checksum,
    fetch_books,
    load_dataset,
    relevant_chunks,
    validate_against_book,
)
from tests.fakes import make_chunk

BOOK = {
    "key": "a_book",
    "role": "English book",
    "title": "A Book",
    "author": "Someone",
    "language": "en",
    "filename": "a.md",
    "url": "https://example.test/a.md",
    "sha256": "0" * 64,
    "license": "Public domain",
}


def question(identifier="q1", category="factual", evidence=("the exact words",), **overrides):
    values = {
        "id": identifier,
        "book": "a_book",
        "category": category,
        "question": "What?",
        "expected_answer": "That.",
        "chapter": None,
        "evidence": evidence,
        "answerable": True,
        "language": "en",
    }
    return BenchmarkQuestion(**(values | overrides))


def unanswerable(identifier="u1"):
    return question(identifier, "unanswerable", evidence=(), expected_answer=None, answerable=False)


def write_dataset(directory, questions, key_points=()):
    (directory / "books.yaml").write_text(yaml.safe_dump({"books": [BOOK]}), encoding="utf-8")
    (directory / "questions.jsonl").write_text("".join(json.dumps(item) + "\n" for item in questions), encoding="utf-8")
    (directory / "chapter_key_points.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in key_points), encoding="utf-8"
    )


def full_book_questions():
    counts = {"factual": 10, "conceptual": 5, "multi_section": 5, "chapter_specific": 5}
    questions = [
        question(f"{category}_{index}", category) for category, count in counts.items() for index in range(count)
    ]
    return [*questions, *(unanswerable(f"u{index}") for index in range(5))]


def test_an_answerable_question_needs_evidence():
    with pytest.raises(ValueError, match="evidence"):
        question(evidence=())


def test_an_unanswerable_question_cant_have_evidence():
    with pytest.raises(ValueError, match="evidence"):
        question(category="unanswerable", answerable=False, expected_answer=None)


def test_only_the_unanswerable_category_can_be_unanswerable():
    with pytest.raises(ValueError, match="unanswerable"):
        question(answerable=False)


def test_evidence_finds_its_chunks():
    chunks = [make_chunk("Holds The Exact   Words here.", index=0), make_chunk("Something else.", index=1)]

    assert relevant_chunks(question(), chunks) == [{chunks[0].chunk_id}]


def test_a_quote_in_two_chunks_finds_both():
    chunks = [make_chunk("the exact words", index=0), make_chunk("again the exact words", index=1)]

    assert relevant_chunks(question(), chunks) == [{chunks[0].chunk_id, chunks[1].chunk_id}]


def test_a_quote_cut_by_a_chunk_boundary_is_still_found():
    quote = "one two three four five six seven eight nine ten eleven twelve thirteen"
    chunks = [
        make_chunk("…one two three four five six", index=0),
        make_chunk("seven eight nine ten eleven twelve thirteen…", index=1),
    ]

    [found] = relevant_chunks(question(evidence=(quote,)), chunks)

    assert found == {chunks[0].chunk_id, chunks[1].chunk_id}


def test_a_short_quote_has_to_match_whole():
    assert relevant_chunks(question(evidence=("one two",)), [make_chunk("one only")]) == [set()]


def test_evidence_finds_its_chunk_under_any_chunking():
    small = [make_chunk("the exact words", index=0)]
    large = [make_chunk("Much more text around the exact words in a larger chunk.", index=7)]

    assert relevant_chunks(question(), small) == [{small[0].chunk_id}]
    assert relevant_chunks(question(), large) == [{large[0].chunk_id}]


def dataset_of(questions, key_points=()):
    return BenchmarkDataset(books=[BOOK], questions=questions, key_points=key_points)


def test_a_sound_book_has_no_problems():
    chunks = [make_chunk("Here are the exact words.")]

    assert validate_against_book(dataset_of(full_book_questions()), "a_book", chunks, []) == []


def test_a_quote_that_isnt_in_the_book_is_reported():
    problems = validate_against_book(dataset_of(full_book_questions()), "a_book", [make_chunk("Nothing.")], [])

    assert any("not found in the book" in problem for problem in problems)


def test_a_mistyped_quote_is_caught_even_if_half_of_it_matches():
    book = "one two three four five six seven eight; nine ten eleven twelve thirteen fourteen"
    typo = "one two three four five six seven eight: nine ten eleven twelve thirteen fourteen"
    questions = [*full_book_questions(), question("extra", evidence=(typo,))]

    problems = validate_against_book(dataset_of(questions), "a_book", [make_chunk(f"the exact words {book}")], [])

    assert any("extra: not found" in problem for problem in problems)


def test_a_quote_has_to_match_case_too():
    questions = [*full_book_questions(), question("extra", evidence=("THE EXACT WORDS",))]

    problems = validate_against_book(dataset_of(questions), "a_book", [make_chunk("the exact words")], [])

    assert any("extra: not found" in problem for problem in problems)


def test_a_quote_over_the_limit_is_reported():
    long_quote = " ".join(["word"] * 31)
    questions = [*full_book_questions(), question("extra", evidence=(long_quote,))]

    problems = validate_against_book(dataset_of(questions), "a_book", [make_chunk(f"the exact words {long_quote}")], [])

    assert any("over 30 words" in problem for problem in problems)


def test_the_distribution_of_categories_is_enforced():
    problems = validate_against_book(dataset_of([question()]), "a_book", [make_chunk("the exact words")], [])

    assert "a_book: 1 factual questions, expected 10" in problems


def test_an_unknown_chapter_is_reported():
    questions = [*full_book_questions(), question("extra", chapter="No Such Chapter")]

    problems = validate_against_book(dataset_of(questions), "a_book", [make_chunk("the exact words")], [])

    assert any("No Such Chapter" in problem for problem in problems)


def test_repeated_ids_are_reported():
    questions = [*full_book_questions(), question("factual_0")]

    problems = validate_against_book(dataset_of(questions), "a_book", [make_chunk("the exact words")], [])

    assert "repeated id: factual_0" in problems


def test_the_dataset_loads_from_its_files(tmp_path):
    write_dataset(
        tmp_path, [question().model_dump(mode="json")], [{"book": "a_book", "chapter": "One", "key_points": ["x"]}]
    )

    dataset = load_dataset(tmp_path)

    assert dataset.book("a_book").title == "A Book"
    assert len(dataset.questions) == 1
    assert dataset.key_points[0].key_points == ("x",)


def test_a_malformed_dataset_is_reported(tmp_path):
    write_dataset(tmp_path, [{"id": "only an id"}])

    with pytest.raises(BenchmarkDatasetError):
        load_dataset(tmp_path)


def test_the_checksum_identifies_the_exact_content(tmp_path):
    write_dataset(tmp_path, [question().model_dump(mode="json")])
    before = dataset_checksum(tmp_path)

    write_dataset(tmp_path, [question(expected_answer="Another.").model_dump(mode="json")])

    assert dataset_checksum(tmp_path) != before


def test_a_book_that_changed_is_refused(tmp_path):
    (tmp_path / "a.md").write_text("Different content", encoding="utf-8")

    with pytest.raises(BenchmarkDatasetError, match="differs"):
        fetch_books(dataset_of([question()]), tmp_path)


def test_a_download_that_differs_is_not_kept(tmp_path, monkeypatch):
    response = httpx.Response(200, content=b"Different content", request=httpx.Request("GET", BOOK["url"]))
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: response)

    with pytest.raises(BenchmarkDatasetError, match="differs"):
        fetch_books(dataset_of([question()]), tmp_path)

    assert not (tmp_path / "a.md").exists()
