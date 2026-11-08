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
    make_chunk("One.", index=0, chapter=1, section="Intro", page_start=1, page_end=2, language="en"),
    make_chunk("Two.", index=1, chapter=1, section="Body", page_start=3, page_end=5, language="en"),
    make_chunk("Three.", index=2, chapter=2, section="Body", page_start=6, page_end=6, language="pt"),
    make_chunk("Four.", index=3, chapter=3, section=None, page_start=None, language="pt"),
]

CASES = [
    RetrievalFilters(),
    RetrievalFilters(chapter_numbers=(1,)),
    RetrievalFilters(chapter_numbers=(1, 3)),
    RetrievalFilters(section_titles=("Body",)),
    RetrievalFilters(languages=("pt",)),
    RetrievalFilters(page_start=3),
    RetrievalFilters(page_end=2),
    RetrievalFilters(page_start=2, page_end=4),
    RetrievalFilters(page_start=5, page_end=5),
    RetrievalFilters(page_start=100),
    RetrievalFilters(chapter_numbers=(1,), section_titles=("Body",), languages=("en",), page_start=4),
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


def test_a_page_range_means_overlap():
    filters = RetrievalFilters(page_start=2, page_end=4)

    assert [chunk.chunk_index for chunk in CHUNKS if filters.allows(chunk)] == [0, 1]


def test_chunks_without_pages_never_match_a_page_range():
    assert not RetrievalFilters(page_start=1).allows(CHUNKS[3])
    assert not RetrievalFilters(page_end=100).allows(CHUNKS[3])


def test_every_scope_is_limited_to_one_revision():
    conditions = metadata_filters(BookScope("book_001", 2, "en")).filters

    assert [(condition.key, condition.value) for condition in conditions] == [("book_revision", "book_001:r2")]
