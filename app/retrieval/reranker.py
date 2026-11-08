"""Reranking inside the application, through Hugging Face models.

Installing a model in Ollama does not make it a reranker: Ollama has no reranking API. Both
candidates load through sentence-transformers' CrossEncoder, which reads from each model's
own configuration how to score. Qwen3-Reranker compares its "yes" and "no" logits, and the
sigmoid turns that into the same probability its model card computes.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cached_property
from typing import Any

from app.config.settings import RerankerModelConfig
from app.utils.huggingface import local_snapshot


class CrossEncoderReranker:
    """Loads on first use. On the GPU, the model only stays in VRAM while it is scoring."""

    def __init__(self, config: RerankerModelConfig) -> None:
        self.model = config.model
        self._config = config

    @cached_property
    def _encoder(self) -> Any:
        # Imported here: torch takes seconds to load, and most commands never rerank.
        import torch
        from sentence_transformers import CrossEncoder

        # It warns that the CPU default of bfloat16 may be slow. Here it is three times
        # faster than float32, thanks to the 9950X3D's AVX-512.
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        half_precision = {"dtype": torch.float16} if self._config.device == "cuda" else {}
        return CrossEncoder(local_snapshot(self.model), device=self._config.device, model_kwargs=half_precision)

    def score(self, query: str, texts: list[str]) -> list[float]:
        import torch

        if not texts:
            return []
        with self._on_device():
            scores = self._encoder.predict(
                [(query, text) for text in texts],
                batch_size=self._config.batch_size,
                activation_fn=torch.nn.Sigmoid(),
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return [float(score) for score in scores]

    @contextmanager
    def _on_device(self) -> Iterator[None]:
        import torch

        self._encoder.to(self._config.device)
        try:
            yield
        finally:
            if self._config.device == "cuda":
                self._encoder.to("cpu")
                torch.cuda.empty_cache()
