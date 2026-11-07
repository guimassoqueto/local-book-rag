"""Stand-ins for the services that need a running server."""

import hashlib
import math

from app.ingestion.chunker import Chunk
from app.utils.ollama_runtime import ModelInfo


def make_chunk(
    text="Some text.",
    book_id="book_001",
    index=0,
    chapter=1,
    section="Section",
    page_start=None,
    page_end=None,
    language="en",
):
    return Chunk(
        chunk_id=f"{book_id}_chapter_{chapter:02d}_chunk_{index:04d}",
        book_id=book_id,
        book_title="Title",
        chapter_number=chapter,
        chapter_title=f"Chapter {chapter}",
        section_title=section,
        page_start=page_start,
        page_end=page_end if page_end is not None else page_start,
        chunk_index=index,
        language=language,
        text=text,
    )


class WordCounter:
    def count(self, text):
        return len(text.split())


class FakeChunks:
    """A chunk source that counts how often it is read."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.loads = 0

    def load_chunks(self, book_id, revision):
        self.loads += 1
        return [chunk for chunk in self.chunks if chunk.book_id == book_id]


class FakeReranker:
    """Scores a text by how often the query's words appear in it."""

    model = "fake-reranker"

    def __init__(self):
        self.calls = 0

    def score(self, query, texts):
        self.calls += 1
        words = query.casefold().split()
        return [min(1.0, sum(text.casefold().count(word) for word in words) / 10) for text in texts]


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
