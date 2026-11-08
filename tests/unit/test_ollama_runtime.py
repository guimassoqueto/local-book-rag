import httpx
import pytest
import respx

from app.errors import ModelNotFoundError, ServiceUnavailableError
from app.utils.ollama_runtime import OllamaRuntime, qualified_name

BASE_URL = "http://ollama.test:11434"

SHOW_RESPONSE = {
    "details": {"family": "gptoss", "parameter_size": "20.9B", "quantization_level": "MXFP4"},
    "model_info": {"general.architecture": "gptoss", "gptoss.context_length": 131072},
    "capabilities": ["completion", "thinking"],
}


@pytest.fixture
def runtime():
    return OllamaRuntime(BASE_URL, timeout=5)


@respx.mock
def test_version(runtime):
    respx.get(f"{BASE_URL}/api/version").respond(json={"version": "0.40.15"})

    assert runtime.version() == "0.40.15"


@respx.mock
def test_model_info_combines_show_and_list(runtime):
    respx.post(f"{BASE_URL}/api/show").respond(json=SHOW_RESPONSE)
    respx.get(f"{BASE_URL}/api/tags").respond(
        json={"models": [{"model": "gpt-oss:20b", "digest": "abc123", "size": 1}]}
    )

    info = runtime.model_info("gpt-oss:20b")

    assert info.digest == "abc123"
    assert info.quantization == "MXFP4"
    assert info.context_length == 131072
    assert "thinking" in info.capabilities


@respx.mock
def test_missing_model_says_how_to_get_it(runtime):
    respx.post(f"{BASE_URL}/api/show").respond(404, json={"error": "model not found"})

    with pytest.raises(ModelNotFoundError, match="pull-models"):
        runtime.model_info("absent:1b")


@respx.mock
def test_unreachable_server_is_reported(runtime):
    respx.get(f"{BASE_URL}/api/version").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ServiceUnavailableError, match="not reachable"):
        runtime.version()


@respx.mock
def test_loaded_models_report_their_gpu_share(runtime):
    respx.get(f"{BASE_URL}/api/ps").respond(
        json={"models": [{"model": "gpt-oss:20b", "size": 100, "size_vram": 75, "context_length": 8192}]}
    )

    [loaded] = runtime.loaded_models()

    assert loaded.gpu_fraction == 0.75
    assert loaded.context_length == 8192


def test_untagged_models_resolve_to_latest():
    assert qualified_name("bge-m3") == "bge-m3:latest"
    assert qualified_name("gpt-oss:20b") == "gpt-oss:20b"
