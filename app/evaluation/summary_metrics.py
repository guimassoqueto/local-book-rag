"""Summary quality, judged by a model against the chapter's key points and sources."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.errors import BookRagError
from app.evaluation.verdicts import JUDGE_ATTEMPTS, attempt_parameters, read_verdict
from app.generation.base import GenerationParameters, LLMProvider, Message
from app.generation.summarization import ChapterSummary
from app.utils.logging import get_logger, log_event

logger = get_logger("evaluation.summaries")

_RATING_SCALE = 5
_RATINGS = ("concept_preservation", "factual_consistency", "coherence", "completeness")
_PROMPT_SHARE = 0.8  # of the context window, leaving a margin for an approximate tokenizer

# Neither prompt shows a sample rating: at low reasoning, gpt-oss copies it without reading the
# summary. Key points are written in detail, so a point counts once its main idea is there.
_COVERAGE_PROMPT = """Does the summary below convey the main idea of this point? Paraphrases count, the idea can be spread across several sentences, and secondary details may be missing.

Point: {point}

Summary:

{summary}

Reply with JSON only: {{"covered": true}} or {{"covered": false}}"""  # noqa: E501

_RATING_PROMPT = """Review this summary of a book chapter. Compare its claims with the passages from the chapter, one by one, before giving any rating.

Rate each criterion with an integer from 1 (poor) to 5 (excellent):

- concept_preservation: the chapter's concepts are stated without distorting them.
- factual_consistency: nothing in it contradicts or goes beyond the passages.
- coherence: it reads as an organized whole, not a list of fragments.
- completeness: it covers the chapter from beginning to end.

Summary:

{summary}

Passages:

{sources}

Reply with JSON only, with exactly these keys: concept_preservation, factual_consistency, coherence, completeness."""  # noqa: E501


@dataclass(frozen=True)
class SummaryScores:
    """Each from 0 to 1. A rating the judge failed to give is None."""

    argument_coverage: float | None
    concept_preservation: float | None
    factual_consistency: float | None
    coherence: float | None
    completeness: float | None
    citation_traceability: float


def citation_traceability(summary: ChapterSummary) -> float:
    """The share of statements that resemble a passage of the chapter closely enough to cite it."""
    if not summary.statements:
        return 0.0
    return 1 - summary.statements_without_source / summary.statements


class SummaryJudge:
    def __init__(self, llm: LLMProvider, parameters: GenerationParameters) -> None:
        """Create a judge.

        Args:
            llm: the model that judges.
            parameters: how it generates. Reasoning counts against max_tokens.
        """
        self._llm = llm
        self._parameters = parameters

    def score(self, summary: ChapterSummary, key_points: Sequence[str], sources: Sequence[str]) -> SummaryScores:
        """Judge a summary.

        Args:
            summary: the summary.
            key_points: what it has to cover.
            sources: passages of the chapter to check it against.
        """
        ratings = self._rate(summary.text, sources)
        return SummaryScores(
            argument_coverage=self._coverage(summary.text, key_points),
            citation_traceability=citation_traceability(summary),
            **{name: ratings.get(name) for name in _RATINGS},
        )

    def _coverage(self, summary: str, key_points: Sequence[str]) -> float | None:
        verdicts = [self._ask(_COVERAGE_PROMPT.format(point=point, summary=summary)) for point in key_points]
        known = [verdict["covered"] for verdict in verdicts if isinstance(verdict.get("covered"), bool)]
        return sum(known) / len(known) if known else None

    def _rate(self, summary: str, sources: Sequence[str]) -> dict[str, float]:
        reply = self._ask(_RATING_PROMPT.format(summary=summary, sources=self._fit(summary, sources)))
        ratings = {}
        for name in _RATINGS:
            value = reply.get(name)
            if isinstance(value, int | float) and 1 <= value <= _RATING_SCALE:
                ratings[name] = (value - 1) / (_RATING_SCALE - 1)
        return ratings

    def _fit(self, summary: str, sources: Sequence[str]) -> str:
        """Take as many passages as the context holds, spread evenly over the chapter."""
        window = int(self._llm.context_size() * _PROMPT_SHARE)
        budget = window - self._parameters.max_tokens - self._llm.count_tokens(summary)
        cost = max(1, max((self._llm.count_tokens(source) for source in sources), default=1))
        room = max(1, budget // cost)
        step = max(1, len(sources) / room)
        chosen = [sources[int(position * step)] for position in range(min(room, len(sources)))]
        return "\n\n".join(chosen)

    def _ask(self, prompt: str) -> dict[str, object]:
        """Ask the judge. A failure gives no verdict, instead of stopping a long run."""
        for attempt in range(JUDGE_ATTEMPTS):
            parameters = attempt_parameters(self._parameters, attempt)
            try:
                verdict = read_verdict(self._llm.generate([Message("user", prompt)], parameters).text)
            except BookRagError as exc:
                log_event(logger, "judge failed", error=str(exc)[:200])
                return {}
            if verdict:
                return verdict
        log_event(logger, "judge failed", error=f"no verdict in {JUDGE_ATTEMPTS} attempts")
        return {}
