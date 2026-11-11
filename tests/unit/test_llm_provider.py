import json

import httpx
import pytest
import respx

from app.config.settings import LLMConfig, LLMProfile, TokenizerConfig
from app.errors import ConfigurationError, ModelNotFoundError, ServiceUnavailableError
from app.generation.base import Generation, GenerationParameters, Message, TextDelta
from app.generation.factory import create_llm_provider
from app.generation.ollama_provider import OllamaLLMProvider
from app.utils.ollama_runtime import OllamaRuntime
from tests.fakes import WordCounter

BASE_URL = "http://ollama.test:11434"
CHAT = f"{BASE_URL}/api/chat"
PARAMETERS = GenerationParameters(temperature=0.2, max_tokens=500)
MESSAGES = [Message("system", "Be brief."), Message("user", "Hello?")]


def line(**fields):
    return json.dumps({"model": "m", "created_at": "2026-11-06T00:00:00Z", "done": False, **fields}) + "\n"


def reply(*parts, **final):
    body = "".join(line(message=part) for part in parts)
    last = {
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 87,
        "eval_count": 33,
        "load_duration": 3_000_000_000,
        "prompt_eval_duration": 500_000_000,
        "eval_duration": 2_000_000_000,
    } | final
    return httpx.Response(200, content=body + line(message={"role": "assistant", "content": ""}, **last))


def mock_model(capabilities=("completion", "thinking"), context_length=131072):
    respx.post(f"{BASE_URL}/api/show").respond(
        json={
            "model_info": {"general.architecture": "gpt-oss", "gpt-oss.context_length": context_length},
            "capabilities": list(capabilities),
        }
    )
    respx.get(f"{BASE_URL}/api/tags").respond(json={"models": []})


def provider(reasoning="low", context_size=8192):
    config = LLMConfig(
        provider="ollama", model="gpt-oss:20b", context_size=context_size, temperature=0.2, max_tokens=99
    )
    profile = LLMProfile(tokenizer=TokenizerConfig(kind="tiktoken", name="o200k_base"), reasoning=reasoning)
    return OllamaLLMProvider(config, profile, OllamaRuntime(BASE_URL, timeout=5), WordCounter(), timeout=5)


def assistant(content="", thinking=None):
    message = {"role": "assistant", "content": content}
    return message | ({"thinking": thinking} if thinking else {})


@respx.mock
def test_text_arrives_as_it_is_generated():
    mock_model()
    respx.post(CHAT).mock(return_value=reply(assistant("Hel"), assistant("lo.")))

    events = list(provider().stream(MESSAGES, PARAMETERS))

    assert [event.text for event in events if isinstance(event, TextDelta)] == ["Hel", "lo."]
    assert isinstance(events[-1], Generation)
    assert events[-1].text == "Hello."


@respx.mock
def test_reasoning_stays_out_of_the_answer():
    mock_model()
    respx.post(CHAT).mock(return_value=reply(assistant(thinking="Let me think."), assistant("Answer.")))

    generation = provider().generate(MESSAGES, PARAMETERS)

    assert generation.text == "Answer."
    assert generation.thinking == "Let me think."


@respx.mock
def test_the_runtime_statistics_are_reported():
    mock_model()
    respx.post(CHAT).mock(return_value=reply(assistant("Answer.")))

    stats = provider().generate(MESSAGES, PARAMETERS).stats

    assert stats.model == "gpt-oss:20b"
    assert stats.prompt_tokens == 87
    assert stats.completion_tokens == 33
    assert stats.load_seconds == 3
    assert stats.prompt_seconds == 0.5
    assert stats.generation_seconds == 2
    assert stats.tokens_per_second == 16.5
    assert stats.finish_reason == "stop"
    assert stats.time_to_first_token > 0
    assert stats.total_seconds >= stats.time_to_first_token


@respx.mock
def test_parameters_reach_ollama():
    mock_model()
    route = respx.post(CHAT).mock(return_value=reply(assistant("Answer.")))

    provider().generate(MESSAGES, PARAMETERS)

    payload = json.loads(route.calls[0].request.content)
    assert payload["options"]["temperature"] == 0.2
    assert payload["options"]["num_predict"] == 500
    assert payload["options"]["num_ctx"] == 8192
    assert payload["think"] == "low"
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]


@respx.mock
def test_models_without_a_reasoning_setting_are_not_sent_one():
    mock_model()
    route = respx.post(CHAT).mock(return_value=reply(assistant("Answer.")))

    provider(reasoning=None).generate(MESSAGES, PARAMETERS)

    assert json.loads(route.calls[0].request.content).get("think") is None


@respx.mock
def test_a_reasoning_setting_needs_a_model_that_has_it():
    mock_model(capabilities=("completion",))

    with pytest.raises(ConfigurationError, match="no reasoning mode"):
        provider().generate(MESSAGES, PARAMETERS)


@respx.mock
def test_the_window_is_capped_by_the_model():
    mock_model(context_length=4096)

    assert provider(context_size=8192).context_size() == 4096


@respx.mock
def test_the_configured_window_is_used_when_the_model_allows_it():
    mock_model()

    assert provider(context_size=8192).context_size() == 8192


@respx.mock
def test_a_missing_model_is_reported():
    respx.post(f"{BASE_URL}/api/show").respond(404, json={"error": "model not found"})

    with pytest.raises(ModelNotFoundError):
        provider().generate(MESSAGES, PARAMETERS)


@respx.mock
def test_an_unreachable_server_is_reported():
    mock_model()
    respx.post(CHAT).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ServiceUnavailableError, match="not reachable"):
        provider().generate(MESSAGES, PARAMETERS)


@respx.mock
def test_a_timeout_is_reported_as_one():
    mock_model()
    respx.post(CHAT).mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(ServiceUnavailableError, match="in time"):
        provider().generate(MESSAGES, PARAMETERS)


@respx.mock
def test_running_out_of_memory_reaches_the_user():
    mock_model()
    respx.post(CHAT).respond(500, json={"error": "model requires more system memory (14 GiB) than is available"})

    with pytest.raises(ServiceUnavailableError, match="more system memory"):
        provider().generate(MESSAGES, PARAMETERS)


# create_llm_provider: a model other than llm.model, and a reasoning of its own (generation.quiz.check)


def sent_reasoning(llm):
    route = respx.post(f"{BASE_URL}/api/chat").mock(return_value=reply(assistant("Answer.")))
    llm.generate(MESSAGES, PARAMETERS)
    return json.loads(route.calls[-1].request.content).get("think")


@respx.mock
def test_the_factory_builds_a_named_model_from_its_own_profile(settings):
    mock_model()
    runtime = OllamaRuntime(BASE_URL, timeout=5)

    llm = create_llm_provider(settings, runtime, model="gemma4:12b")

    assert llm.model == "gemma4:12b"
    assert sent_reasoning(llm) is False  # gemma4's profile, not gpt-oss's "low"
    assert llm._counter._name == "o200k_base"  # gemma4's tokenizer, not gpt-oss's o200k_harmony


@respx.mock
def test_a_reasoning_level_replaces_the_profiles_for_that_provider_only(settings):
    mock_model()
    runtime = OllamaRuntime(BASE_URL, timeout=5)

    checker = create_llm_provider(settings, runtime, model=settings.llm.model, reasoning="medium")
    writer = create_llm_provider(settings, runtime)

    assert sent_reasoning(checker) == "medium"
    assert sent_reasoning(writer) == "low"


def test_a_model_without_a_profile_is_refused(settings):
    with pytest.raises(ConfigurationError, match="unknown-model"):
        create_llm_provider(settings, OllamaRuntime(BASE_URL, timeout=5), model="unknown-model")
