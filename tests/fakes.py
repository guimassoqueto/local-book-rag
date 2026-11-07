"""Stand-ins for the services that need a running server."""

import hashlib
import math

from app.utils.ollama_runtime import ModelInfo


class WordCounter:
    def count(self, text):
        return len(text.split())


class FakeEmbedder:
    """Deterministic unit vectors: the same text always gets the same vector."""

    def __init__(self, model="fake-embedding", dimensions=8, failure=None):
        self.model = model
        self._dimensions = dimensions
        self.failure = failure

    def dimensions(self):
        return self._dimensions

    def embed_documents(self, texts, on_batch=None):
        if self.failure:
            raise self.failure
        vectors = [self._vector(text) for text in texts]
        if on_batch:
            on_batch(len(texts))
        return vectors

    def embed_query(self, text):
        return self._vector(text)

    def _vector(self, text):
        digest = hashlib.sha256(text.encode()).digest()
        values = [value - 127.5 for value in digest[: self._dimensions]]
        norm = math.sqrt(sum(value * value for value in values))
        return [value / norm for value in values]


class FakeRuntime:
    base_url = "http://ollama.test"

    def __init__(self, dimensions=1024, digest="digest-1"):
        self.dimensions = dimensions
        self.digest = digest
        self.unloaded = []

    def model_info(self, name):
        return ModelInfo(name, self.digest, "family", "1B", "Q8", 32768, self.dimensions, ("embedding",))

    def unload(self, model):
        self.unloaded.append(model)
