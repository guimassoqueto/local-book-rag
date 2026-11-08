import json

import httpx
import pytest
import respx

from app.embeddings.factory import create_embedding_provider
from app.embeddings.ollama_provider import OllamaEmbeddingProvider
from app.errors import ConfigurationError, EmbeddingDimensionError, ModelNotFoundError, ServiceUnavailableError
from app.utils.ollama_runtime import OllamaRuntime

BASE_URL = "http://ollama.test:11434"
EMBED = f"{BASE_URL}/api/embed"
VECTOR = [0.5] * 4


@pytest.fixture
def runtime():
    return OllamaRuntime(BASE_URL, timeout=5)


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def provider(settings, runtime, **overrides):
    values = {"dimensions": 4, "batch_size": 2} | overrides
    embedding = settings.embedding.model_copy(update=values)
    return OllamaEmbeddingProvider(embedding, settings.embedding_profile, runtime, timeout=5)


def echo_vectors(request):
    texts = json.loads(request.content)["input"]
    count = 1 if isinstance(texts, str) else len(texts)
    return httpx.Response(200, json={"model": "m", "embeddings": [VECTOR] * count})


def payloads(route):
    return [json.loads(call.request.content) for call in route.calls]


@respx.mock
def test_documents_are_sent_without_the_query_instruction(settings, runtime):
    route = respx.post(EMBED).mock(side_effect=echo_vectors)

    provider(settings, runtime).embed_documents(["A passage."])

    assert payloads(route)[0]["input"] == ["A passage."]


@respx.mock
def test_queries_follow_the_model_card_template(settings, runtime):
    route = respx.post(EMBED).mock(side_effect=echo_vectors)

    provider(settings, runtime).embed_query("What is a cost?")

    assert payloads(route)[0]["input"] == (
        "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:What is a cost?"
    )


@respx.mock
def test_long_input_is_never_truncated_silently(settings, runtime):
    route = respx.post(EMBED).mock(side_effect=echo_vectors)
    embedder = provider(settings, runtime)

    embedder.embed_documents(["passage"])
    embedder.embed_query("question")

    assert [payload["truncate"] for payload in payloads(route)] == [False, False]


@respx.mock
def test_each_device_setting_reaches_ollama(settings, runtime):
    route = respx.post(EMBED).mock(side_effect=echo_vectors)
    embedder = provider(settings, runtime, document_device="gpu", query_device="cpu")

    embedder.embed_documents(["passage"])
    embedder.embed_query("question")

    document, query = payloads(route)
    assert document["options"]["num_gpu"] > 0  # left unset, Ollama keeps whatever runner is loaded
    assert query["options"]["num_gpu"] == 0


@respx.mock
def test_documents_go_in_batches_of_the_configured_size(settings, runtime):
    route = respx.post(EMBED).mock(side_effect=echo_vectors)
    finished = []

    vectors = provider(settings, runtime, batch_size=2).embed_documents(["a", "b", "c"], on_batch=finished.append)

    assert [len(payload["input"]) for payload in payloads(route)] == [2, 1]
    assert finished == [2, 1]
    assert len(vectors) == 3


@respx.mock
def test_vectors_of_the_wrong_size_are_rejected(settings, runtime):
    respx.post(EMBED).respond(json={"model": "m", "embeddings": [[0.1, 0.2]]})

    with pytest.raises(EmbeddingDimensionError, match="produced 2 dimensions"):
        provider(settings, runtime).embed_query("question")


@respx.mock
def test_a_missing_model_is_reported_and_not_retried(settings, runtime):
    route = respx.post(EMBED).respond(404, json={"error": "model not found"})

    with pytest.raises(ModelNotFoundError):
        provider(settings, runtime).embed_query("question")

    assert route.call_count == 1


@respx.mock
def test_transient_failures_are_retried(settings, runtime):
    route = respx.post(EMBED).mock(
        side_effect=[httpx.Response(500, json={"error": "loading"}), httpx.Response(200, json={"embeddings": [VECTOR]})]
    )

    assert provider(settings, runtime).embed_query("question") == VECTOR
    assert route.call_count == 2


@respx.mock
def test_persistent_failures_surface(settings, runtime):
    route = respx.post(EMBED).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ServiceUnavailableError):
        provider(settings, runtime).embed_documents(["passage"])

    assert route.call_count == 3


@respx.mock
def test_dimensions_are_read_from_the_model(settings, runtime):
    respx.post(f"{BASE_URL}/api/show").respond(
        json={"model_info": {"general.architecture": "qwen3", "qwen3.embedding_length": 1024}}
    )
    respx.get(f"{BASE_URL}/api/tags").respond(json={"models": []})

    assert provider(settings, runtime).dimensions() == 1024


def test_the_factory_uses_the_configured_model(settings, runtime):
    assert create_embedding_provider(settings, runtime).model == settings.embedding.model


def test_the_factory_can_build_the_model_an_index_was_made_with(settings, runtime):
    assert create_embedding_provider(settings, runtime, "bge-m3").model == "bge-m3"


def test_a_model_without_a_profile_is_a_configuration_error(settings, runtime):
    with pytest.raises(ConfigurationError, match="no-such-model"):
        create_embedding_provider(settings, runtime, "no-such-model")
