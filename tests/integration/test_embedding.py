"""Runs each candidate embedding model on the real Ollama server, into a real collection."""

import os
import uuid

import chromadb
import pytest

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings
from app.embeddings.factory import create_embedding_provider
from app.errors import ServiceUnavailableError
from app.ingestion.chunker import Chunk
from app.storage.chroma import ChromaServer, ChunkStore, revision_filter, revision_key
from app.utils.ollama_runtime import OllamaRuntime

pytestmark = pytest.mark.integration

MODELS = ["qwen3-embedding:0.6b", "bge-m3"]
PASSAGES = [
    "Opportunity cost is the value of the best alternative given up when making a choice.",
    "Photosynthesis lets plants turn sunlight, water and carbon dioxide into sugar and oxygen.",
    "The Treaty of Tordesillas divided newly discovered lands between Portugal and Spain in 1494.",
    "A hash table stores values under keys, and finds them in constant time on average.",
]


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    settings = load_settings(EnvironmentSettings().config_dir)
    return OllamaRuntime(EnvironmentSettings().ollama_base_url, settings.ollama.request_timeout_seconds)


@pytest.fixture
def settings():
    return load_settings(EnvironmentSettings().config_dir)


@pytest.fixture
def store():
    server = ChromaServer("localhost", 8000, client=chromadb.HttpClient(host="localhost", port=8000))
    name = f"test_{uuid.uuid4().hex}"
    server.create_collection(name, {"purpose": "integration test"})
    yield ChunkStore(server, name)
    server.delete_collection(name)


def chunk(index, text):
    return Chunk(
        f"book_001_chapter_01_chunk_{index:04d}", "book_001", "T", 1, "One", None, None, None, index, "en", text
    )


@pytest.mark.parametrize("model", MODELS)
def test_the_model_reports_the_configured_size(settings, runtime, model):
    assert create_embedding_provider(settings, runtime, model).dimensions() == settings.embedding.dimensions


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What do you lose when you pick one option over another?", 0),
        ("Como as plantas produzem açúcar?", 1),
        ("Quem dividiu as terras descobertas com a Espanha?", 2),
        ("What data structure gives fast lookups by key?", 3),
    ],
)
def test_the_right_passage_comes_first(settings, runtime, store, model, question, expected):
    embedder = create_embedding_provider(settings, runtime, model)
    chunks = [chunk(index, text) for index, text in enumerate(PASSAGES)]
    store.add(chunks, embedder.embed_documents(PASSAGES), 1, model, 1)

    results = store.query(embedder.embed_query(question), 4, revision_filter([revision_key("book_001", 1)]))

    assert results[0].chunk.text == PASSAGES[expected]


def test_documents_reach_the_gpu_after_a_query_left_the_model_on_the_cpu(settings, runtime):
    embedder = create_embedding_provider(settings, runtime)
    embedder.embed_query("A question loads the model on the CPU.")

    def placement():
        return next(item for item in runtime.loaded_models() if item.name == settings.embedding.model)

    assert placement().vram_bytes == 0

    embedder.embed_documents(["Bulk embedding has to move it to the GPU."])

    assert placement().gpu_fraction == 1


def test_input_beyond_the_context_is_refused_not_truncated(settings, runtime):
    embedder = create_embedding_provider(settings, runtime)

    with pytest.raises(ServiceUnavailableError, match="context length"):
        embedder.embed_documents(["word " * 50000])
