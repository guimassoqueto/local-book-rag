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


def render(results: Mapping[str, Any], baseline: str | None = None) -> str:
    """Write a run's results as Markdown.

    Args:
        results: the contents of a run's results.json.
        baseline: a variant to compare the others with.

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
    lines += ["", _table(["variant"], summary, metrics)]
    for group in ("category", "book"):
        if entries := results.get(f"by_{group}"):
            lines += ["", f"## By {group}", "", _table(["variant", group], entries, metrics)]
    if baseline is not None:
        lines += ["", *_comparisons(results, baseline, metrics)]
    return "\n".join(lines) + "\n"


def _comparisons(results: Mapping[str, Any], baseline: str, metrics: Sequence[str]) -> list[str]:
    variants = [entry["variant"] for entry in results["summary"]]
    if baseline not in variants:
        raise ConfigurationError(f"There is no variant named {baseline}. This run has: {', '.join(variants)}.")
    if results["experiment"]["kind"] == "performance":
        raise ConfigurationError("A performance run has one row per variant, so there is nothing to pair.")
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
