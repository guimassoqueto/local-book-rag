"""Filters exist twice: as a ChromaDB query for dense search, and in Python for BM25.

If the two ever disagreed, retrieval strategies would search different parts of a book, and
comparing them would be meaningless. So both run on the same cases here.
"""

import chromadb
import pytest

from app.retrieval.base import BookScope, RetrievalFilters
from app.retrieval.dense import DenseRetriever, metadata_filters
from app.storage.chroma import ChromaServer, ChunkStore
from tests.fakes import FakeEmbedder, make_chunk

CHUNKS = [
    make_chunk("One.", index=0, chapter=1, section="Intro", language="en"),
    make_chunk("Two.", index=1, chapter=1, section="Body", language="en"),
    make_chunk("Three.", index=2, chapter=2, section="Body", language="pt"),
    make_chunk("Four.", index=3, chapter=3, section=None, language="pt"),
]

CASES = [
    RetrievalFilters(),
    RetrievalFilters(chapter_numbers=(1,)),
    RetrievalFilters(chapter_numbers=(1, 3)),
    RetrievalFilters(section_titles=("Body",)),
    RetrievalFilters(languages=("pt",)),
    RetrievalFilters(chapter_numbers=(1,), section_titles=("Body",), languages=("en",)),
    RetrievalFilters(chapter_numbers=(3,), languages=("en",)),
]


@pytest.fixture(scope="module")
def dense(tmp_path_factory):
    client = chromadb.PersistentClient(path=str(tmp_path_factory.mktemp("chroma")))
    server = ChromaServer("embedded", 0, client=client)
    server.create_collection("chunks", {"purpose": "test"})
    store = ChunkStore(server, "chunks")
    embedder = FakeEmbedder()
    store.add(CHUNKS, embedder.embed_documents([chunk.text for chunk in CHUNKS]), 1, "fake", 1)
    return DenseRetriever(embedder, store, top_k=10)


@pytest.mark.parametrize("filters", CASES, ids=str)
def test_chromadb_and_python_agree(dense, filters):
    found = dense.retrieve("anything", BookScope("book_001", 1, "en", filters))

    assert {p.chunk.chunk_index for p in found} == {c.chunk_index for c in CHUNKS if filters.allows(c)}


def test_filters_have_no_page_range():
    assert {"page_start", "page_end"}.isdisjoint(RetrievalFilters.__dataclass_fields__)


def test_every_scope_is_limited_to_one_revision():
    conditions = metadata_filters(BookScope("book_001", 2, "en")).filters

    assert [(condition.key, condition.value) for condition in conditions] == [("book_revision", "book_001:r2")]
