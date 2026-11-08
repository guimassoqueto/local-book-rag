from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.errors import ModelNotFoundError, ServiceUnavailableError
from app.services.health_service import HealthService
from app.utils.gpu import GpuStatus
from app.utils.ollama_runtime import LoadedModel, ModelInfo


def model_info(name, embedding_length=None, capabilities=("completion", "thinking"), context_length=131072):
    return ModelInfo(name, "digest", "family", "20B", "Q4", context_length, embedding_length, capabilities)


class FakeRuntime:
    base_url = "http://ollama.test"

    def __init__(self, settings, **overrides):
        self.models = {
            settings.llm.model: model_info(settings.llm.model),
            settings.embedding.model: model_info(settings.embedding.model, embedding_length=1024),
        }
        self.models.update(overrides)
        self.client = SimpleNamespace(
            embed=lambda **kwargs: SimpleNamespace(embeddings=[[0.0] * 1024]),
            chat=lambda **kwargs: SimpleNamespace(message=SimpleNamespace(content="ready")),
        )

    def version(self):
        return "0.40.15"

    def model_info(self, name):
        if self.models[name] is None:
            raise ModelNotFoundError(f"{name} is missing")
        return self.models[name]

    def loaded_models(self):
        return [LoadedModel("gpt-oss:20b", 100, 100, 8192)]

    def translate_errors(self, model=None):
        return nullcontext()


class FakeChroma:
    address = "chroma.test:8000"

    def __init__(self, available=True):
        self.available = available

    def version(self):
        if not self.available:
            raise ServiceUnavailableError("ChromaDB is not reachable")
        return "1.5.9"


GPU = GpuStatus("NVIDIA GeForce RTX 5060 Ti", 500, 16311)


class FakeIndexes:
    def __init__(self, record=None, stale=False):
        self.record = record
        self.stale = stale

    def active(self):
        return self.record

    def needs_reindex(self):
        return self.stale


def run_checks(settings, runtime=None, chroma=None, gpu=GPU, inference=False, indexes=None):
    service = HealthService(
        settings, runtime or FakeRuntime(settings), chroma or FakeChroma(), indexes or FakeIndexes(), lambda: gpu
    )
    return {result.name: result for result in service.run(inference=inference)}


@pytest.mark.parametrize("inference", [False, True])
def test_a_healthy_deployment_passes_everything(settings, inference):
    results = run_checks(settings, inference=inference)

    assert all(result.ok for result in results.values())
    assert ("llm inference" in results) is inference


def test_inference_reports_the_gpu_placement(settings):
    results = run_checks(settings, inference=True)

    assert "100% of 0.0 GB on GPU" in results["llm inference"].detail


def test_a_failed_service_does_not_stop_the_other_checks(settings):
    results = run_checks(settings, chroma=FakeChroma(available=False))

    assert not results["chromadb"].ok
    assert results["ollama"].ok
    assert results["gpu"].ok


def test_a_missing_model_is_a_failed_check(settings):
    results = run_checks(settings, runtime=FakeRuntime(settings, **{settings.llm.model: None}))

    assert not results["llm model"].ok


def test_reasoning_needs_a_model_that_supports_it(settings):
    plain = model_info(settings.llm.model, capabilities=("completion",))

    results = run_checks(settings, runtime=FakeRuntime(settings, **{settings.llm.model: plain}))

    assert not results["llm model"].ok
    assert "reasoning" in results["llm model"].detail


def test_context_size_cannot_exceed_the_model(settings):
    small = model_info(settings.llm.model, context_length=4096)

    results = run_checks(settings, runtime=FakeRuntime(settings, **{settings.llm.model: small}))

    assert not results["llm model"].ok
    assert "4096" in results["llm model"].detail


def test_embedding_dimensions_are_verified_against_the_model(settings):
    wrong = model_info(settings.embedding.model, embedding_length=768)

    results = run_checks(settings, runtime=FakeRuntime(settings, **{settings.embedding.model: wrong}))

    assert not results["embedding model"].ok
    assert "768" in results["embedding model"].detail


def test_a_library_without_an_index_is_fine(settings):
    assert run_checks(settings)["index"].ok


def test_a_stale_index_is_reported(settings):
    record = SimpleNamespace(version=3, collection="book_chunks_v3", embedding_model="old-model")

    result = run_checks(settings, indexes=FakeIndexes(record, stale=True))["index"]

    assert not result.ok
    assert "reindex-all" in result.detail


def test_a_missing_gpu_is_reported(settings):
    results = run_checks(settings, gpu=None)

    assert not results["gpu"].ok
