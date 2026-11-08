"""The embedding layer's interface. Nothing outside app/embeddings knows which runtime serves it."""

from collections.abc import Callable, Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    model: str

    def dimensions(self) -> int:
        """Read the vector size from the model itself."""
        ...

    def embed_documents(self, texts: Sequence[str], on_batch: Callable[[int], None] | None = None) -> list[list[float]]:
        """Embed passages for indexing, in batches.

        Args:
            texts: the passages.
            on_batch: told how many texts each finished batch held.

        Raises:
            EmbeddingDimensionError: a vector has the wrong size.
            ServiceUnavailableError: the runtime failed.
        """
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a question for retrieval, which models treat differently from a passage."""
        ...
