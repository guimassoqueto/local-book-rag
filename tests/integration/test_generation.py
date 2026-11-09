"""Runs the configured LLM for real, and every model whose profile checks for abstentions."""

import os
from pathlib import Path

import pytest
import yaml

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings
from app.errors import ModelNotFoundError
from app.evaluation.benchmark import apply_overrides
from app.generation.base import GenerationParameters, Message
from app.generation.factory import create_llm_provider
from app.generation.question_answering import Reply, check_abstention
from app.utils.ollama_runtime import OllamaRuntime

pytestmark = pytest.mark.integration


@pytest.fixture
def settings():
    return load_settings(EnvironmentSettings().config_dir)


@pytest.fixture
def llm(settings, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    runtime = OllamaRuntime(EnvironmentSettings().ollama_base_url, settings.ollama.request_timeout_seconds)
    return create_llm_provider(settings, runtime)


def test_the_token_estimate_matches_the_runtime_count(llm):
    text = "Opportunity cost is the value of the best alternative given up when making a choice. " * 20
    parameters = GenerationParameters(temperature=0, max_tokens=5)

    baseline = llm.generate([Message("user", "x")], parameters).stats.prompt_tokens
    measured = llm.generate([Message("user", text)], parameters).stats.prompt_tokens

    assert measured - baseline == pytest.approx(llm.count_tokens(text) - llm.count_tokens("x"), abs=2)


def test_a_reply_reports_its_statistics(llm):
    generation = llm.generate(
        [Message("user", "Reply with one word: hello")], GenerationParameters(temperature=0, max_tokens=200)
    )

    assert generation.text.strip()
    assert generation.stats.prompt_tokens > 0
    assert generation.stats.completion_tokens > 0
    assert generation.stats.tokens_per_second > 0
    assert generation.stats.time_to_first_token > 0
    assert generation.stats.finish_reason == "stop"


# The abstention check's proof (constitution VI, .specify/bugs/unmarked-abstentions). It reads
# known replies, labeled by reading them in abstention_cases.yaml: abstentions written without
# the no-evidence marker, and answers that look like them. A check that reads an answer as an
# abstention hides it from the reader, so every case has to come out as labeled. Each model reads
# only its own replies, as it does in use; read by another model, a few came out otherwise, and
# the fix report records which.

CHECKED = {
    model
    for model, profile in load_settings(EnvironmentSettings().config_dir).llm_profiles.items()
    if profile.check_abstentions
}
CASES = [
    case
    for case in yaml.safe_load((Path(__file__).parent / "abstention_cases.yaml").read_text(encoding="utf-8"))
    if case["label"] != "ambiguous" and case["model"] in CHECKED
]


@pytest.fixture
def runtime(settings, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    return OllamaRuntime(EnvironmentSettings().ollama_base_url, settings.ollama.request_timeout_seconds)


# gemma4 reads this partial answer of its own as an abstention under some loads of the model, and
# as an answer under others. The reader still sees the answer, under the note that the model
# found none. Kept on by the owner's decision, since the check ends gemma4's unmarked abstentions.
_KNOWN_MISREADS = {("gemma4:12b", "generation_20261108T175100527075Z, think_python_multi_section_05")}


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, marks=pytest.mark.xfail(reason="a known misread, see above"))
        if (case["model"], case["source"]) in _KNOWN_MISREADS
        else case
        for case in CASES
    ],
    ids=[f"{case['model']}-{case['label']}-{number}" for number, case in enumerate(CASES, 1)],
)
def test_the_check_reads_known_replies_as_they_were_labeled(settings, runtime, case):
    model = case["model"]
    try:
        runtime.model_info(model)
    except ModelNotFoundError:
        pytest.skip(f"{model} isn't pulled")
    settings = apply_overrides(settings, {"llm": {"model": model}})
    task = settings.generation.question_answering
    parameters = GenerationParameters(
        temperature=settings.llm.temperature if task.temperature is None else task.temperature,
        max_tokens=task.max_tokens or settings.llm.max_tokens,
    )
    reply = Reply(case["reply"], (), (), insufficient_evidence=False)

    checked = check_abstention(create_llm_provider(settings, runtime), settings, case["question"], reply, parameters)

    assert checked.insufficient_evidence == (case["label"] == "abstention"), case["source"]
