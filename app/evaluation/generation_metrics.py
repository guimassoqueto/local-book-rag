"""Answer quality: what can be checked exactly, and RAGAS for what takes judgment.

RAGAS needs a model as a judge. The same one judges every candidate, so that the scores compare
candidates with each other. They are a first signal, not a verdict.
"""

import asyncio
import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any

import py3langid

from app.config.settings import JudgeConfig
from app.evaluation.retrieval_metrics import Evidence
from app.generation.base import GenerationParameters, LLMProvider
from app.utils.logging import get_logger, log_event

logger = get_logger("evaluation.generation")

_MIN_CHARACTERS_FOR_LANGUAGE = 20


def citation_accuracy(cited: Sequence[str], evidence: Evidence) -> float:
    """1 if the answer cites a passage holding the evidence, and 0 if it cites none that does.

    A passage without the gold quote can still support a claim, so a share of "correct" citations
    would punish correct answers. Reaching the evidence at all is what can be verified.
    """
    return 1.0 if set(cited) & (set().union(*evidence) if evidence else set()) else 0.0


def language_matches(text: str, expected: str) -> bool:
    """Whether an answer is in the expected language. Very short texts can't be told, so they pass."""
    return len(text) < _MIN_CHARACTERS_FOR_LANGUAGE or py3langid.classify(text)[0] == expected


def abstention_is_correct(answerable: bool, abstained: bool) -> bool:
    """A model should abstain exactly when the source can't answer."""
    return abstained is not answerable


@dataclass(frozen=True)
class JudgeScores:
    faithfulness: float | None
    answer_correctness: float | None
    answer_relevance: float | None


class RagasJudge:
    """Runs the RAGAS metrics locally. Only the embeddings go through Ollama's OpenAI-compatible endpoint."""

    def __init__(
        self,
        llm: LLMProvider,
        parameters: GenerationParameters,
        config: JudgeConfig,
        ollama_base_url: str,
        timeout: float,
    ) -> None:
        """Create a judge.

        Args:
            llm: the model that judges.
            parameters: how it generates.
            config: the experiment's judge, for its embedding model.
            ollama_base_url: where the embeddings are.
            timeout: how long to wait for them, in seconds.
        """
        self._llm = llm
        self._parameters = parameters
        self._config = config
        self._base_url = f"{ollama_base_url}/v1"
        self._timeout = timeout

    @cached_property
    def _metrics(self) -> dict[str, Any]:
        # Imported here: ragas pulls in LangChain, which only benchmarks need.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from openai import AsyncOpenAI
            from ragas.embeddings.base import embedding_factory
            from ragas.metrics.collections import AnswerCorrectness, AnswerRelevancy, Faithfulness

            from app.evaluation.ragas_llm import ProviderLLM

            client = AsyncOpenAI(base_url=self._base_url, api_key="local", timeout=self._timeout)
            llm = ProviderLLM(self._llm, self._parameters)
            embeddings = embedding_factory("openai", model=self._config.embedding_model, client=client)
            return {
                "faithfulness": Faithfulness(llm=llm),
                "relevance": AnswerRelevancy(llm=llm, embeddings=embeddings),
                "correctness": AnswerCorrectness(llm=llm, embeddings=embeddings),
            }

    def score(self, question: str, answer: str, contexts: Sequence[str], reference: str) -> JudgeScores:
        """Judge one answer. A metric that fails gives None instead of stopping a long run."""
        metrics = self._metrics

        def run(name: str, **inputs: Any) -> float | None:
            try:
                value = float(asyncio.run(metrics[name].ascore(**inputs)).value)
            except Exception as exc:  # judges fail on malformed replies: one sample must not end the run
                log_event(logger, "judge failed", metric=name, error=str(exc)[:200])
                return None
            return None if math.isnan(value) else value  # RAGAS's way of finding nothing to score

        return JudgeScores(
            faithfulness=run("faithfulness", user_input=question, response=answer, retrieved_contexts=list(contexts)),
            answer_correctness=run("correctness", user_input=question, response=answer, reference=reference),
            answer_relevance=run("relevance", user_input=question, response=answer),
        )
