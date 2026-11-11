"""A run's results as Markdown, with paired comparisons that tell real differences from noise.

The dataset is small, so most differences between variants are noise. A paired bootstrap over the
items both variants scored, questions or chapters, says which ones aren't.
"""

import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.errors import ConfigurationError
from app.evaluation.quiz_metrics import (
    FLAW_REASONS,
    REFERS_TO_PASSAGE,
    letter_spread,
    refusal_counts,
    summarize_reading,
    thirds,
)
from app.generation.quiz import REFUSAL_KINDS

_DRAWS = 4000
_SEED = 0
_SAMPLES = "_samples"


@dataclass(frozen=True)
class Difference:
    """How much higher a metric is for a variant than for the baseline.

    Attributes:
        mean: the average difference, over the items both have a value for.
        low: the bottom of its 95% interval.
        high: the top of its 95% interval.
        pairs: how many items it was measured on.
    """

    mean: float
    low: float
    high: float
    pairs: int

    @property
    def real(self) -> bool:
        """Whether the interval leaves zero out."""
        return self.low > 0 or self.high < 0


def paired_difference(
    rows: Sequence[Mapping[str, Any]], baseline: str, variant: str, metric: str, draws: int = _DRAWS
) -> Difference | None:
    """Bootstrap a variant's difference from the baseline, item by item. None if they share none."""
    values: dict[Any, dict[str, float]] = {}
    for row in rows:
        if row["variant"] in (baseline, variant) and row.get(metric) is not None:
            values.setdefault(_item(row), {})[row["variant"]] = row[metric]
    differences = [pair[variant] - pair[baseline] for pair in values.values() if len(pair) == 2]
    if not differences:
        return None
    sampler = random.Random(_SEED)
    means = sorted(statistics.fmean(sampler.choices(differences, k=len(differences))) for _ in range(draws))
    return Difference(
        statistics.fmean(differences), means[int(draws * 0.025)], means[int(draws * 0.975)], len(differences)
    )


def render(
    results: Mapping[str, Any], baseline: str | None = None, reading: Sequence[Mapping[str, str]] | None = None
) -> str:
    """Write a run's results as Markdown.

    Args:
        results: the contents of a run's results.json.
        baseline: a variant to compare the others with.
        reading: a quiz run's reading.csv, with whatever marks it holds.

    Raises:
        ConfigurationError: there is no variant by that name, or nothing to pair in this kind of run.
    """
    experiment = results["experiment"]
    environment = results["environment"]
    summary = results["summary"]
    metrics = _metrics(summary)
    lines = [
        f"# {experiment['name']}",
        "",
        experiment["description"].strip(),
        "",
        f"Run on {environment['date']} with Ollama {environment['ollama_version']}, "
        f"on {environment['hardware']['gpu'] or 'no GPU'}.",
    ]
    if not results["complete"]:
        lines.append(f"A sample of {results['sample_limit']} per book and category, not the whole dataset.")
    if experiment["kind"] == "quiz_check":
        lines += ["", *_check_section(summary)]
    else:
        lines += ["", _table(["variant"], summary, metrics)]
    for group in ("category", "book"):
        if entries := results.get(f"by_{group}"):
            lines += ["", f"## By {group}", "", _table(["variant", group], entries, metrics)]
    if experiment["kind"] == "quiz":
        lines += _quiz_sections(results, reading)
    if baseline is not None:
        lines += ["", *_comparisons(results, baseline, metrics)]
    return "\n".join(lines) + "\n"


def _quiz_sections(results: Mapping[str, Any], reading: Sequence[Mapping[str, str]] | None) -> list[str]:
    """FR-019's measures that aren't averages, and the reading's marks (FR-020)."""
    variants = [entry["variant"] for entry in results["summary"]]
    rows = {variant: [row for row in results["rows"] if row["variant"] == variant] for variant in variants}
    letters, places, refusals, closed = [], [], [], []
    for variant, own in rows.items():
        spread = letter_spread(own)
        letters.append([variant, *(_number(spread[letter]) if spread else "–" for letter in "ABCDE")])
        shares = thirds(own)
        places.append([variant, *(_number(share) for share in shares)] if shares else [variant, "–", "–", "–"])
        quizzes = [row for row in own if row.get("row") == "quiz" and not row.get("failed")]
        counts = refusal_counts(own)
        extra = [sum(row.get(field) or 0 for row in quizzes) for field in ("skipped_passages", "passed_over_passages")]
        unreadable_checks = sum(row.get("check_unreadable") or 0 for row in quizzes)
        refusals.append([variant, *(counts[kind] for kind in REFUSAL_KINDS), *extra, unreadable_checks])
        answers = [row for row in own if row.get("row") == "question"]
        read = [row["closed_book_correct"] for row in answers if row.get("closed_book_correct") is not None]
        share = _number(sum(read) / len(read)) if read else "–"
        closed.append([variant, share, len(read), len(answers) - len(read)])
    lines = [
        "",
        "## Letters",
        "",
        "The share of keys on each letter, balanced by construction (SC-001).",
        "",
        _markdown(["variant", *"ABCDE"], letters),
        "",
        "## Where questions come from",
        "",
        "The share of questions from each third of their chapter (SC-005).",
        "",
        _markdown(["variant", "start", "middle", "end"], places),
        "",
        "## Refusals and skips",
        "",
        "Attempts refused, by kind (FR-010); passages skipped as having nothing to ask about; passages "
        "too long to send (FR-011); and check verdicts that couldn't be read, even asked again.",
        "",
        _markdown(["variant", *REFUSAL_KINDS, "skipped", "passed_over", "check_unreadable"], refusals),
        "",
        "## Closed-book answers",
        "",
        "The writer answering each question without its passage. There is no target: a high share means "
        "questions can be answered without reading, which the reading weighs.",
        "",
        _markdown(["variant", "closed_book_correct", "answered", "closed_book_unreadable"], closed),
    ]
    if reading is not None:
        lines += ["", *_reading_section(variants, reading)]
    return lines


def _check_section(summary: Sequence[Mapping[str, Any]]) -> list[str]:
    """The key check against the comparator, and FR-027's verdict on the test set."""
    rows = []
    for entry in summary:
        caught = entry["flawed_caught"] / entry["flawed_cases"] if entry["flawed_cases"] else None
        rejected = entry["sound_rejected"] / entry["sound_cases"] if entry["sound_cases"] else None
        compared = entry["comparator_flawed_caught"] / entry["flawed_cases"] if entry["flawed_cases"] else None
        verdict = {True: "passes", False: "fails", None: "–"}[entry["rule_passes"]]
        rows.append(
            [
                entry["variant"],
                f"{entry['flawed_caught']} of {entry['flawed_cases']}",
                "–" if caught is None else _number(caught),
                f"{entry['sound_rejected']} of {entry['sound_cases']}",
                "–" if rejected is None else _number(rejected),
                "–" if compared is None else _number(compared),
                entry["comparator_unreadable"],
                entry["unreadable"],
                entry["missing_quotes"],
                verdict,
            ]
        )
    headers = [
        "variant",
        "flawed caught",
        "share",
        "sound rejected",
        "share",
        "comparator caught",
        "comparator_unreadable",
        "unreadable",
        "missing_quotes",
        "FR-027",
    ]
    lines = [
        "The check's catches among flawed cases and rejections among sound ones; the comparator is the "
        "shipped writer answering each case with its passage (FR-027).",
        "",
        _markdown(headers, rows),
    ]
    for entry in summary:
        lines += ["", f"**{entry['variant']}**: {entry['rule_reason']}"]
        if difference := entry.get("difference"):
            lines.append(
                f"Check minus comparator, over {difference['pairs']} flawed cases: {difference['mean']:+.3f} "
                f"({difference['low']:+.3f} to {difference['high']:+.3f})."
            )
    return lines


def _reading_section(variants: Sequence[str], reading: Sequence[Mapping[str, str]]) -> list[str]:
    summaries = {variant: summarize_reading(reading, variant) for variant in variants}
    lines = ["## The reading", ""]
    if not any(summary.marked for summary in summaries.values()):
        return [*lines, "No question is marked yet: mark reading.csv by FR-020's rubric, then run this again."]
    rows = [
        [
            variant,
            summary.marked,
            summary.sound,
            summary.flawed,
            summary.unmarked,
            "–" if summary.sound_share is None else _number(summary.sound_share),
            summary.refers_to_passage,
        ]
        for variant, summary in summaries.items()
    ]
    lines += [
        f"The share of sound keys among the marked questions (SC-003), and those noted {REFERS_TO_PASSAGE} "
        "(SC-015). Unmarked questions count as neither.",
        "",
        _markdown(["variant", "marked", "sound", "flawed", "unmarked", "sound_share", REFERS_TO_PASSAGE], rows),
    ]
    for variant, summary in summaries.items():
        if summary.reasons:
            counted = [reason for reason in FLAW_REASONS if reason in summary.reasons]
            reasons = ", ".join(f"{reason}: {summary.reasons[reason]}" for reason in counted)
            lines += ["", f"Flawed by reason, {variant}: {reasons}."]
    return lines


def _comparisons(results: Mapping[str, Any], baseline: str, metrics: Sequence[str]) -> list[str]:
    variants = [entry["variant"] for entry in results["summary"]]
    if baseline not in variants:
        raise ConfigurationError(f"There is no variant named {baseline}. This run has: {', '.join(variants)}.")
    if results["experiment"]["kind"] == "performance":
        raise ConfigurationError("A performance run has one row per variant, so there is nothing to pair.")
    if results["experiment"]["kind"] == "quiz_check":
        raise ConfigurationError("A quiz_check run compares each variant with the comparator: see its verdict.")
    rows = []
    for variant in variants:
        if variant != baseline:
            differences = [paired_difference(results["rows"], baseline, variant, metric) for metric in metrics]
            rows.append([variant, *(_difference(difference) for difference in differences)])
    return [
        f"## Compared with {baseline}",
        "",
        f"The difference from {baseline}, with its 95% interval. Bold where the interval leaves zero out.",
        "",
        _markdown(["variant", *metrics], rows),
    ]


def _metrics(summary: Sequence[Mapping[str, Any]]) -> list[str]:
    """The metrics of a summary, in its order: every field with a sample count next to it."""
    fields = summary[0] if summary else {}
    return [field for field in fields if f"{field}{_SAMPLES}" in fields]


def _table(keys: Sequence[str], entries: Sequence[Mapping[str, Any]], metrics: Sequence[str]) -> str:
    rows = [[*(entry[key] for key in keys), *(_value(entry, metric) for metric in metrics)] for entry in entries]
    return _markdown([*keys, *metrics], rows)


def _value(entry: Mapping[str, Any], metric: str) -> str:
    """The value, and how many it averages when that's fewer than the variant's samples."""
    value = entry.get(metric)
    if value is None:
        return "–"
    text = _number(value) if isinstance(value, float) else str(value)
    count = entry.get(f"{metric}{_SAMPLES}")
    return f"{text} ({count})" if count is not None and count < entry["samples"] else text


def _number(value: float) -> str:
    """Three decimals for scores, fewer for speeds and megabytes."""
    size = abs(value)
    return f"{value:.3f}" if size < 10 else f"{value:.1f}" if size < 1000 else f"{value:.0f}"


def _difference(difference: Difference | None) -> str:
    if difference is None:
        return "–"
    text = f"{difference.mean:+.3f} ({difference.low:+.3f} to {difference.high:+.3f})"
    return f"**{text}**" if difference.real else text


def _markdown(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def _item(row: Mapping[str, Any]) -> Any:
    """What a row is about, to pair it with another variant's row about the same thing."""
    return row.get("question") or (row.get("book"), row.get("chapter"))
