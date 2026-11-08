"""Embeddings through Ollama, with LlamaIndex's integration underneath."""

from collections.abc import Callable, Sequence
from typing import Any

from llama_index.embeddings.ollama import OllamaEmbedding
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config.settings import EmbeddingConfig, EmbeddingProfile
from app.errors import EmbeddingDimensionError, ServiceUnavailableError
from app.utils.ollama_runtime import OllamaRuntime

# Ollama reuses a loaded runner unless a request names a device, so both have to be explicit:
# without it, a model that a query loaded on the CPU would stay there for a whole book.
_DEVICE_OPTIONS = {"cpu": {"num_gpu": 0}, "gpu": {"num_gpu": 999}}
_MAX_ATTEMPTS = 3


class _StrictOllamaEmbedding(OllamaEmbedding):
    """Fails on input longer than the model's context.

    Ollama truncates it silently by default, and LlamaIndex has no way to ask otherwise.
    A truncated chunk would be indexed as if it were whole.
    """

    def get_general_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts).embeddings

    def get_general_text_embedding(self, texts: str) -> list[float]:
        return self._embed(texts).embeddings[0]

    def _embed(self, texts: str | list[str]) -> Any:
        return self._client.embed(
            model=self.model_name,
            input=texts,
            options=self.ollama_additional_kwargs,
            keep_alive=self.keep_alive,
            truncate=False,
        )


class OllamaEmbeddingProvider:
    """Document and query embedding, which can run on different devices.

    Ollama normalizes the vectors it returns, so nothing here has to.
    """

    def __init__(
        self, config: EmbeddingConfig, profile: EmbeddingProfile, runtime: OllamaRuntime, timeout: float
    ) -> None:
        self.model = config.model
        self._config = config
        self._profile = profile
        self._runtime = runtime

        def embedding(device: str) -> _StrictOllamaEmbedding:
            return _StrictOllamaEmbedding(
                model_name=config.model,
                base_url=runtime.base_url,
                embed_batch_size=config.batch_size,
                ollama_additional_kwargs=_DEVICE_OPTIONS[device],
                client_kwargs={"timeout": timeout},
            )

        self._documents = embedding(config.document_device)
        self._queries = embedding(config.query_device)

    def dimensions(self) -> int:
        size = self._runtime.model_info(self.model).embedding_length
        if size is None:
            raise EmbeddingDimensionError(f"Ollama does not report the embedding size of {self.model}.")
        return size

    def embed_documents(self, texts: Sequence[str], on_batch: Callable[[int], None] | None = None) -> list[list[float]]:
        vectors: list[list[float]] = []
        size = self._config.batch_size
        for start in range(0, len(texts), size):
            batch = [self._profile.document_template.format(text=text) for text in texts[start : start + size]]
            vectors.extend(self._embed_batch(batch))
            if on_batch is not None:
                on_batch(len(batch))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_query(self._profile.query_template.format(text=text))

    @retry(
        retry=retry_if_exception_type(ServiceUnavailableError),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, max=8),
        reraise=True,
    )
    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        with self._runtime.translate_errors(self.model):
            vectors = self._documents.get_text_embedding_batch(batch)
        return [self._checked(vector) for vector in vectors]

    @retry(
        retry=retry_if_exception_type(ServiceUnavailableError),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, max=8),
        reraise=True,
    )
    def _embed_query(self, text: str) -> list[float]:
        with self._runtime.translate_errors(self.model):
            return self._checked(self._queries.get_query_embedding(text))

    def _checked(self, vector: list[float]) -> list[float]:
        if len(vector) != self._config.dimensions:
            raise EmbeddingDimensionError(
                f"{self.model} produced {len(vector)} dimensions, but embedding.dimensions says "
                f"{self._config.dimensions}."
            )
        return vector
