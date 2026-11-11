"""The quiz measurement's own figures, and its reading (specs/003-chapter-quiz, FR-019 and FR-020).

Scores are a first signal: a question's key is judged sound or flawed by reading it against its
passage, in reading.csv, which the run writes with empty marks. The file holds the passages, so it
stays with the results, out of the repository.
"""

import csv
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.errors import ConfigurationError
from app.generation.quiz import REFUSAL_KINDS

LETTERS = "ABCDE"
READING_FIELDS = (
    "variant",
    "question",
    "book",
    "chapter",
    "pages",
    "passage",
    "text",
    "A",
    "B",
    "C",
    "D",
    "E",
    "key",
    "explanation",
    "mark",
    "reasons",
    "note",
)
MARKS = ("sound", "flawed")
FLAW_REASONS = (
    "wrong_key",
    "key_not_stated",
    "two_defensible",
    "explanation_beyond_passage",
    "option_depends_on_others",
    "nothing_to_ask",
)
REFERS_TO_PASSAGE = "refers_to_passage"  # a note on a question that points to where its answer is (SC-015)

_REASON_SEPARATOR = re.compile(r"[;,\s]+")


def _questions(rows: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    return [row for row in rows if row.get("row") == "question"]


def letter_spread(rows: Iterable[Mapping[str, object]]) -> dict[str, float]:
    """The share of keys on each letter (SC-001). Balanced by construction, and checked here."""
    letters = Counter(str(row["letter"]) for row in _questions(rows))
    total = sum(letters.values())
    return {letter: letters[letter] / total for letter in LETTERS} if total else {}


def thirds(rows: Iterable[Mapping[str, object]]) -> tuple[float, float, float] | None:
    """The share of questions from the start, middle and end of their chapter (SC-005)."""
    counts = Counter(int(str(row["third"])) for row in _questions(rows))
    total = sum(counts.values())
    if not total:
        return None
    start, middle, end = (counts[third] / total for third in range(3))
    return start, middle, end


def refusal_counts(rows: Iterable[Mapping[str, object]]) -> dict[str, int]:
    """Refused attempts by FR-010's kinds, over every question."""
    questions = _questions(rows)
    return {kind: sum(int(str(row.get(f"refused_{kind}") or 0)) for row in questions) for kind in REFUSAL_KINDS}


def write_reading(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    """Write the reading, one question per row, with empty marks, reasons and notes."""
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=READING_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            values = {field: row.get(field, "") for field in READING_FIELDS}
            writer.writerow(values | {"mark": "", "reasons": "", "note": ""})


def read_reading(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return [dict(row) for row in csv.DictReader(file)]


@dataclass(frozen=True)
class ReadingSummary:
    """What the marks of one variant's questions say (FR-020, SC-003, SC-015).

    Attributes:
        marked: questions marked sound or flawed.
        unmarked: questions not marked yet, which count as neither.
        sound: questions whose key is sound.
        flawed: questions with a flaw.
        reasons: the flawed ones, by reason. One question can have several.
        refers_to_passage: questions noted as pointing to where their answer is.
    """

    marked: int
    unmarked: int
    sound: int
    flawed: int
    reasons: dict[str, int]
    refers_to_passage: int

    @property
    def sound_share(self) -> float | None:
        """The share of sound keys among the marked questions. None before any mark."""
        return self.sound / self.marked if self.marked else None


def summarize_reading(rows: Iterable[Mapping[str, str]], variant: str | None = None) -> ReadingSummary:
    """Count the marks, for one variant or all.

    Raises:
        ConfigurationError: a mark or reason outside FR-020's rubric, or a flawed mark without a
            reason: a typo would otherwise count as no mark at all.
    """
    sound = flawed = unmarked = passage_notes = 0
    reasons: Counter[str] = Counter()
    for row in rows:
        if variant is not None and row.get("variant") != variant:
            continue
        mark = (row.get("mark") or "").strip().lower()
        given = [reason for reason in _REASON_SEPARATOR.split((row.get("reasons") or "").strip().lower()) if reason]
        question = row.get("question", "?")
        if mark and mark not in MARKS:
            raise ConfigurationError(f"{question}: '{mark}' isn't a mark. Use one of: {', '.join(MARKS)}.")
        if unknown := [reason for reason in given if reason not in FLAW_REASONS]:
            raise ConfigurationError(f"{question}: unknown reasons {unknown}. Use: {', '.join(FLAW_REASONS)}.")
        if mark == "flawed" and not given:
            raise ConfigurationError(f"{question}: a flawed mark needs a reason: {', '.join(FLAW_REASONS)}.")
        if mark != "flawed" and given:
            raise ConfigurationError(f"{question}: reasons go with a flawed mark only.")
        if REFERS_TO_PASSAGE in (row.get("note") or ""):
            passage_notes += 1
        if mark == "sound":
            sound += 1
        elif mark == "flawed":
            flawed += 1
            reasons.update(given)
        else:
            unmarked += 1
    return ReadingSummary(sound + flawed, unmarked, sound, flawed, dict(reasons), passage_notes)


# The key check's proof (FR-026, FR-027)

MAX_QUOTE_WORDS = 30
MIN_FLAWED_TEST_CASES = 10
MIN_SOUND_TEST_CASES = 30
MAX_SOUND_REJECTED = 0.10
Letter = Literal["A", "B", "C", "D", "E"]


class KnownCase(BaseModel):
    """A question whose key is known sound or flawed, by reading it against its passage.

    The passage is located by a verbatim quote of at most 30 words: no passage text is stored, as
    some books aren't public.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str
    source: str
    book: str
    chapter: str
    quote: str
    question: str
    options: dict[Letter, str]
    key: Letter
    label: Literal["sound", "flawed"]
    reasons: tuple[str, ...] = ()
    note: str | None = None
    case_set: Literal["development", "test"] = Field(alias="set")

    @model_validator(mode="after")
    def check_rules(self) -> "KnownCase":
        if len(self.quote.split()) > MAX_QUOTE_WORDS:
            raise ValueError(f"the quote has more than {MAX_QUOTE_WORDS} words")
        if sorted(self.options) != list(LETTERS):
            raise ValueError("the options are A to E, all five")
        if unknown := [reason for reason in self.reasons if reason not in FLAW_REASONS]:
            raise ValueError(f"unknown reasons {unknown}")
        if self.label == "flawed" and not self.reasons:
            raise ValueError("a flawed case needs its reasons")
        if self.label == "sound" and self.reasons:
            raise ValueError("a sound case has no reasons")
        return self

    @property
    def lettered(self) -> tuple[str, ...]:
        return tuple(self.options[letter] for letter in LETTERS)  # type: ignore[index]


def load_known_cases(path: Path) -> list[KnownCase]:
    """Read the known cases file.

    Raises:
        ConfigurationError: the file can't be read, or a case breaks a rule.
    """
    try:
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Cannot read the known cases in {path}: {exc}") from exc
    cases = []
    for entry in entries:
        try:
            cases.append(KnownCase.model_validate(entry))
        except ValidationError as exc:
            raise ConfigurationError(f"{path}: case {entry.get('id', '?')}: {exc}") from exc
    if repeated := [key for key, count in Counter(case.id for case in cases).items() if count > 1]:
        raise ConfigurationError(f"{path}: case IDs repeat: {repeated}")
    return cases


def summarize_check(rows: Iterable[Mapping[str, Any]], case_set: str | None) -> list[dict[str, Any]]:
    """Each variant's catches and rejections, the comparator's, and FR-027's verdict on the test set."""
    rows = list(rows)
    result = []
    for variant in dict.fromkeys(row["variant"] for row in rows):
        own = [row for row in rows if row["variant"] == variant]
        located = [row for row in own if row.get("located", True)]
        flawed = [row for row in located if row["label"] == "flawed"]
        sound = [row for row in located if row["label"] == "sound"]
        passes, reason, difference = check_rule(flawed, sound, case_set)
        result.append(
            {
                "variant": variant,
                "samples": len(located),
                "missing_quotes": len(own) - len(located),
                "flawed_cases": len(flawed),
                "flawed_caught": sum(bool(row["rejected"]) for row in flawed),
                "sound_cases": len(sound),
                "sound_rejected": sum(bool(row["rejected"]) for row in sound),
                "unreadable": sum(not row["readable"] for row in located),
                "comparator_flawed_caught": sum(bool(row["open_book_caught"]) for row in flawed),
                "comparator_unreadable": sum(row["open_book_answer"] is None for row in located),
                "difference": difference,
                "rule_passes": passes,
                "rule_reason": reason,
            }
        )
    return result


def check_rule(
    flawed: Sequence[Mapping[str, Any]], sound: Sequence[Mapping[str, Any]], case_set: str | None
) -> tuple[bool | None, str, dict[str, Any] | None]:
    """FR-027: the check catches more flawed cases than the comparator, and rejects at most a tenth of sound ones.

    Condition (a) pairs the two case by case over the flawed cases whose comparator answer could be
    read, with the paired bootstrap of every other comparison (constitution VI). A tie fails.

    Returns:
        Whether the rule passes, None when this run can't decide; why; and condition (a)'s difference.
    """
    from app.evaluation.report import paired_difference  # the report reads this module

    if case_set != "test":
        return None, "Development cases choose a wording, and decide nothing (FR-026).", None
    if len(flawed) < MIN_FLAWED_TEST_CASES or len(sound) < MIN_SOUND_TEST_CASES:
        return (
            None,
            f"The test set has {len(flawed)} flawed and {len(sound)} sound cases located: FR-026 asks for at "
            f"least {MIN_FLAWED_TEST_CASES} and {MIN_SOUND_TEST_CASES}.",
            None,
        )
    paired = []
    for row in flawed:
        if row["open_book_caught"] is not None:
            paired.append({"variant": "check", "question": row["case"], "caught": int(bool(row["rejected"]))})
            paired.append({"variant": "comparator", "question": row["case"], "caught": int(row["open_book_caught"])})
    difference = paired_difference(paired, "comparator", "check", "caught")
    catches_more = difference is not None and difference.low > 0
    rejected_share = sum(bool(row["rejected"]) for row in sound) / len(sound)
    rejects_few = rejected_share <= MAX_SOUND_REJECTED
    reason = (
        f"(a) the check catches {'more' if catches_more else 'no more'} flawed cases than the comparator; "
        f"(b) it rejects {rejected_share:.0%} of sound cases, "
        f"{'within' if rejects_few else 'over'} {MAX_SOUND_REJECTED:.0%}."
    )
    summary = asdict(difference) if difference is not None else None
    return catches_more and rejects_few, reason, summary
