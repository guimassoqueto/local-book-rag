"""The benchmark dataset: its books, its questions, and what a correct answer rests on.

Relevance is stored as evidence, verbatim quotes from the book, and not as chunk IDs. IDs change
with every chunk size and comparing chunk sizes is one of the experiments, while a quote finds
its chunks under any configuration.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.errors import BenchmarkDatasetError
from app.ingestion.chunker import Chunk
from app.utils.hashing import file_checksum

Category = Literal["factual", "conceptual", "multi_section", "chapter_specific", "unanswerable"]

CATEGORY_COUNTS: dict[str, int] = {
    "factual": 10,
    "conceptual": 5,
    "multi_section": 5,
    "chapter_specific": 5,
    "unanswerable": 5,
}
_BOOKS_FILE = "books.yaml"
_QUESTIONS_FILE = "questions.jsonl"
_KEY_POINTS_FILE = "chapter_key_points.jsonl"
_MIN_FRAGMENT_WORDS = 6  # shorter than this, half a quote could match anywhere
_MAX_QUOTE_WORDS = 30


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BenchmarkBook(_Model):
    key: str
    role: str
    title: str
    author: str
    language: str
    filename: str
    url: str
    sha256: str
    license: str


class BenchmarkQuestion(_Model):
    """One question.

    Attributes:
        id: unique in the dataset.
        book: the key of its book.
        category: one of the categories the spec distributes questions into.
        question: the question.
        expected_answer: what a correct answer says. None for an unanswerable one.
        chapter: the title of the chapter it concerns, when it has one in particular.
        evidence: verbatim quotes that hold the answer.
        answerable: whether the book holds the answer.
        language: the language of the question, which is the one an answer should be in.
    """

    id: str
    book: str
    category: Category
    question: str
    expected_answer: str | None
    chapter: str | None
    evidence: tuple[str, ...]
    answerable: bool
    language: str

    @model_validator(mode="after")
    def consistent(self) -> "BenchmarkQuestion":
        if self.answerable != (self.category != "unanswerable"):
            raise ValueError("only the unanswerable category can have answerable=false")
        if self.answerable and not (self.evidence and self.expected_answer):
            raise ValueError("an answerable question needs evidence and an expected answer")
        if not self.answerable and self.evidence:
            raise ValueError("an unanswerable question can't have evidence")
        if self.category == "chapter_specific" and not self.chapter:
            raise ValueError("a question about one chapter has to name it")
        return self


class ChapterKeyPoints(_Model):
    """What a summary of a chapter has to cover, to measure argument coverage."""

    book: str
    chapter: str
    key_points: tuple[str, ...]


class BenchmarkDataset(_Model):
    books: tuple[BenchmarkBook, ...]
    questions: tuple[BenchmarkQuestion, ...]
    key_points: tuple[ChapterKeyPoints, ...]

    def book(self, key: str) -> BenchmarkBook:
        return next(book for book in self.books if book.key == key)


def load_dataset(directory: Path) -> BenchmarkDataset:
    """Load and validate the dataset's files.

    Raises:
        BenchmarkDatasetError: a file is missing or malformed.
    """
    try:
        books = yaml.safe_load((directory / _BOOKS_FILE).read_text(encoding="utf-8"))["books"]
        return BenchmarkDataset(
            books=books,
            questions=_read_lines(directory / _QUESTIONS_FILE),
            key_points=_read_lines(directory / _KEY_POINTS_FILE),
        )
    except (OSError, KeyError, ValueError, ValidationError) as exc:
        raise BenchmarkDatasetError(f"Invalid benchmark dataset in {directory}: {exc}") from exc


def _read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dataset_checksum(directory: Path) -> str:
    """Identify the dataset's exact content, for a result to say what it was measured on."""
    digest = hashlib.sha256()
    for name in (_BOOKS_FILE, _QUESTIONS_FILE, _KEY_POINTS_FILE):
        digest.update((directory / name).read_bytes())
    return digest.hexdigest()


def fetch_books(dataset: BenchmarkDataset, directory: Path) -> list[str]:
    """Download the dataset's books, checking that each is the file the dataset was written against.

    Returns:
        A line about each book.

    Raises:
        BenchmarkDatasetError: a book differs from its checksum.
    """
    directory.mkdir(parents=True, exist_ok=True)
    report = []
    for book in dataset.books:
        path = directory / book.filename
        if path.exists():
            checksum = file_checksum(path)
        else:
            response = httpx.get(book.url, follow_redirects=True, timeout=120)
            response.raise_for_status()
            checksum = hashlib.sha256(response.content).hexdigest()
            if checksum == book.sha256:  # a wrong download kept on disk would fail every later run
                path.write_bytes(response.content)
        if checksum != book.sha256:
            raise BenchmarkDatasetError(
                f"{book.filename} differs from the file this dataset was written against. "
                "Its evidence quotes may no longer be found in it."
            )
        report.append(f"{book.key}: {path}")
    return report


def _comparable(text: str) -> str:
    return " ".join(text.casefold().split())


def _holds(quote: str, text: str) -> bool:
    """Whether a text holds a quote, or the half of it that a chunk boundary left there."""
    if quote in text:
        return True
    words = quote.split()
    middle = len(words) // 2
    if middle < _MIN_FRAGMENT_WORDS:
        return False
    return " ".join(words[:middle]) in text or " ".join(words[middle:]) in text


def relevant_chunks(question: BenchmarkQuestion, chunks: Sequence[Chunk]) -> list[set[str]]:
    """Find, for each piece of a question's evidence, the chunks that hold it.

    Overlap can put one quote in two chunks, and those count as one piece of evidence: finding
    either is finding it.

    Returns:
        One set of chunk IDs per quote.
    """
    texts = [(chunk.chunk_id, _comparable(chunk.text)) for chunk in chunks]
    return [{chunk_id for chunk_id, text in texts if _holds(_comparable(quote), text)} for quote in question.evidence]


def validate_against_book(
    dataset: BenchmarkDataset, book_key: str, chunks: Sequence[Chunk], chapters: Sequence[str]
) -> list[str]:
    """Check a book's questions against its real text.

    Args:
        dataset: the dataset.
        book_key: the book to check.
        chunks: the book's chunks.
        chapters: the book's chapter titles.

    Returns:
        Every problem found. None means the book's questions are sound.
    """
    questions = [question for question in dataset.questions if question.book == book_key]
    book_text = " ".join(" ".join(chunk.text.split()) for chunk in chunks)
    problems = []
    counts = Counter(question.category for question in questions)
    for category, expected in CATEGORY_COUNTS.items():
        if counts[category] != expected:
            problems.append(f"{book_key}: {counts[category]} {category} questions, expected {expected}")
    repeated = [key for key, count in Counter(question.id for question in dataset.questions).items() if count > 1]
    problems.extend(f"repeated id: {key}" for key in repeated)

    titles = Counter(chapters)
    for question in questions:
        if question.chapter is not None and question.chapter not in chapters:
            problems.append(f"{question.id}: there is no chapter titled {question.chapter!r}")
        if titles[question.chapter] > 1:
            problems.append(f"{question.id}: {titles[question.chapter]} chapters are titled {question.chapter!r}")
        for quote in question.evidence:
            # Exact here, unlike when resolving evidence: half of a mistyped quote still matches.
            if " ".join(quote.split()) not in book_text:
                problems.append(f"{question.id}: not found in the book: {quote!r}")
            if len(quote.split()) > _MAX_QUOTE_WORDS:
                problems.append(f"{question.id}: over {_MAX_QUOTE_WORDS} words: {quote!r}")
    for points in dataset.key_points:
        if points.book == book_key and points.chapter not in chapters:
            problems.append(f"key points: there is no chapter titled {points.chapter!r}")
    return problems
