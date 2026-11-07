"""A judge for RAGAS, served by this project's own provider.

Ollama's OpenAI-compatible endpoint can't set a context window: it runs at the server's default of
4096 tokens and silently cuts what doesn't fit, so RAGAS would score answers against part of their
sources. Imported only where RAGAS is needed: it pulls in LangChain.
"""

from typing import TypeVar

from pydantic import BaseModel, ValidationError
from ragas.llms.base import InstructorBaseRagasLLM

from app.errors import BenchmarkJudgeError
from app.evaluation.verdicts import JUDGE_ATTEMPTS, attempt_parameters, read_verdict
from app.generation.base import GenerationParameters, LLMProvider, Message

Verdict = TypeVar("Verdict", bound=BaseModel)


class ProviderLLM(InstructorBaseRagasLLM):
    def __init__(self, llm: LLMProvider, parameters: GenerationParameters) -> None:
        """Create a judge.

        Args:
            llm: the model that judges.
            parameters: how it generates. Reasoning counts against max_tokens.
        """
        self._llm = llm
        self._parameters = parameters

    def generate(self, prompt: str, response_model: type[Verdict]) -> Verdict:
        if self._llm.count_tokens(prompt) + self._parameters.max_tokens > self._llm.context_size():
            raise BenchmarkJudgeError("The prompt doesn't fit the judge's context window.")
        for attempt in range(JUDGE_ATTEMPTS):
            parameters = attempt_parameters(self._parameters, attempt)
            reply = self._llm.generate([Message("user", prompt)], parameters).text
            try:
                return response_model.model_validate(read_verdict(reply))
            except ValidationError:
                continue
        raise BenchmarkJudgeError(f"No valid {response_model.__name__} in {JUDGE_ATTEMPTS} attempts.")

    async def agenerate(self, prompt: str, response_model: type[Verdict]) -> Verdict:
        return self.generate(prompt, response_model)
