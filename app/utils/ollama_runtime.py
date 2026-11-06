"""Model management on the Ollama server, shared by the embedding and generation providers."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import httpx
import ollama

from app.errors import ModelNotFoundError, ServiceUnavailableError


@dataclass(frozen=True)
class ModelInfo:
    """What the server reports about a model: benchmarks record this, not the config."""

    name: str
    digest: str | None
    family: str | None
    parameter_size: str | None
    quantization: str | None
    context_length: int | None
    embedding_length: int | None
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class LoadedModel:
    name: str
    size_bytes: int
    vram_bytes: int
    context_length: int | None

    @property
    def gpu_fraction(self) -> float:
        return self.vram_bytes / self.size_bytes if self.size_bytes else 0.0


@dataclass(frozen=True)
class PullProgress:
    status: str
    completed: int | None
    total: int | None


def qualified_name(model: str) -> str:
    """Ollama lists an untagged model under its implicit :latest tag."""
    return model if ":" in model else f"{model}:latest"


class OllamaRuntime:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url
        self.client = ollama.Client(host=base_url, timeout=timeout)
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    @contextmanager
    def translate_errors(self, model: str | None = None) -> Iterator[None]:
        """Turn the client's exceptions into the application's own."""
        try:
            yield
        except ollama.ResponseError as exc:
            if exc.status_code == 404 and model:
                raise ModelNotFoundError(
                    f"Model '{model}' is not on the Ollama server. Download it with `book-rag pull-models`."
                ) from exc
            raise ServiceUnavailableError(f"Ollama answered with an error: {exc.error}") from exc
        except (ConnectionError, httpx.HTTPError) as exc:
            raise ServiceUnavailableError(f"Ollama is not reachable at {self.base_url}: {exc}") from exc

    def version(self) -> str:
        with self.translate_errors():
            response = self._http.get("/api/version")
            response.raise_for_status()
        return response.json()["version"]

    def model_info(self, model: str) -> ModelInfo:
        with self.translate_errors(model):
            shown = self.client.show(model)
            listed = self.client.list()

        wanted = qualified_name(model)
        digest = next((entry.digest for entry in listed.models if entry.model == wanted), None)
        info = shown.modelinfo or {}
        architecture = info.get("general.architecture")
        details = shown.details
        return ModelInfo(
            name=model,
            digest=digest,
            family=details.family if details else None,
            parameter_size=details.parameter_size if details else None,
            quantization=details.quantization_level if details else None,
            context_length=info.get(f"{architecture}.context_length"),
            embedding_length=info.get(f"{architecture}.embedding_length"),
            capabilities=tuple(shown.capabilities or ()),
        )

    def loaded_models(self) -> list[LoadedModel]:
        with self.translate_errors():
            running = self.client.ps()
        return [
            LoadedModel(
                name=entry.model or "",
                size_bytes=entry.size or 0,
                vram_bytes=entry.size_vram or 0,
                context_length=entry.context_length,
            )
            for entry in running.models
        ]

    def pull(self, model: str) -> Iterator[PullProgress]:
        with self.translate_errors(model):
            for update in self.client.pull(model, stream=True):
                yield PullProgress(status=update.status or "", completed=update.completed, total=update.total)
