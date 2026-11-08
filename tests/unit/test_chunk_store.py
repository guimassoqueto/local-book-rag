import chromadb
import pytest
from llama_index.core.vector_stores import FilterOperator, MetadataFilter, MetadataFilters

from app.errors import EmbeddingDimensionError, ServiceUnavailableError
from app.ingestion.chunker import Chunk
from app.storage.chroma import ChromaServer, ChunkStore, revision_filter, revision_key
from tests.fakes import FakeEmbedder

COLLECTION = "book_chunks_v1"
embedder = FakeEmbedder()


@pytest.fixture
def server(tmp_path):
    return ChromaServer("embedded", 0, client=chromadb.PersistentClient(path=str(tmp_path / "chroma")))


@pytest.fixture
def store(server):
    server.create_collection(COLLECTION, {"embedding_model": "fake"})
    return ChunkStore(server, COLLECTION)


def chunk(book_id="book_001", index=0, text=None, chapter=1, page_start=3, section="Section", language="en"):
    return Chunk(
        chunk_id=f"{book_id}_chapter_{chapter:02d}_chunk_{index:04d}",
        book_id=book_id,
        book_title="Title",
        chapter_number=chapter,
        chapter_title="One",
        section_title=section,
        page_start=page_start,
        page_end=page_start,
        chunk_index=index,
        language=language,
        text=text or f"Text of {book_id} chunk {index}.",
    )


def add(store, chunks, revision=1):
    vectors = embedder.embed_documents([item.text for item in chunks])
    store.add(chunks, vectors, revision, "fake", 1)


def everything(*revisions):
    return revision_filter(list(revisions))


def test_a_chunk_comes_back_exactly_as_it_went_in(store):
    original = chunk()
    add(store, [original])

    [found] = store.query(embedder.embed_query(original.text), 1, everything(revision_key("book_001", 1)))

    assert found.chunk == original


def test_null_pages_and_sections_stay_null(store):
    original = chunk(page_start=None, section=None)
    add(store, [original])

    [found] = store.query(embedder.embed_query(original.text), 1, everything(revision_key("book_001", 1)))

    assert found.chunk.page_start is None
    assert found.chunk.page_end is None
    assert found.chunk.section_title is None


def test_the_nearest_chunk_comes_first(store):
    chunks = [chunk(index=index) for index in range(5)]
    add(store, chunks)

    results = store.query(embedder.embed_query(chunks[3].text), 5, everything(revision_key("book_001", 1)))

    assert results[0].chunk == chunks[3]
    assert [item.score for item in results] == sorted((item.score for item in results), reverse=True)


def test_books_are_isolated_by_their_filter(store):
    add(store, [chunk("book_001"), chunk("book_002")])

    results = store.query(embedder.embed_query("anything"), 10, everything(revision_key("book_002", 1)))

    assert {item.chunk.book_id for item in results} == {"book_002"}


def test_revisions_of_a_book_coexist_without_mixing(store):
    add(store, [chunk(text="Old text.")], revision=1)
    add(store, [chunk(text="New text.")], revision=2)

    query = embedder.embed_query("anything")

    assert [item.chunk.text for item in store.query(query, 10, everything(revision_key("book_001", 1)))] == [
        "Old text."
    ]
    assert [item.chunk.text for item in store.query(query, 10, everything(revision_key("book_001", 2)))] == [
        "New text."
    ]


def test_counting_a_revision(store):
    add(store, [chunk(index=0), chunk(index=1)], revision=1)
    add(store, [chunk(index=0)], revision=2)

    assert store.count_revision("book_001", 1) == 2
    assert store.count_revision("book_001", 2) == 1
    assert store.count_revision("book_002", 1) == 0


def test_deleting_a_book_leaves_the_others(store):
    add(store, [chunk("book_001"), chunk("book_002")])

    store.delete_book("book_001")

    assert store.count_revision("book_001", 1) == 0
    assert store.count_revision("book_002", 1) == 1


def test_deleting_a_revision_leaves_the_others(store):
    add(store, [chunk()], revision=1)
    add(store, [chunk()], revision=2)

    store.delete_revision("book_001", 1)

    assert store.count_revision("book_001", 1) == 0
    assert store.count_revision("book_001", 2) == 1


def test_large_books_are_written_in_batches(store, server, monkeypatch):
    monkeypatch.setattr(server, "max_write_batch", lambda: 3)
    chunks = [chunk(index=index) for index in range(10)]

    add(store, chunks)

    assert store.count() == 10


def test_metadata_filters_narrow_a_query(store):
    add(store, [chunk(index=0, chapter=1), chunk(index=1, chapter=2)])
    filters = MetadataFilters(
        filters=[
            *everything(revision_key("book_001", 1)).filters,
            MetadataFilter(key="chapter_number", value=2, operator=FilterOperator.EQ),
        ]
    )

    [found] = store.query(embedder.embed_query("anything"), 10, filters)

    assert found.chunk.chapter_number == 2


def test_a_page_range_never_matches_a_chunk_without_pages(store):
    add(store, [chunk(index=0, page_start=None), chunk(index=1, page_start=5)])
    filters = MetadataFilters(
        filters=[
            *everything(revision_key("book_001", 1)).filters,
            MetadataFilter(key="page_start", value=1, operator=FilterOperator.GTE),
        ]
    )

    [found] = store.query(embedder.embed_query("anything"), 10, filters)

    assert found.chunk.page_start == 5


def test_vectors_of_another_size_are_refused(store):
    add(store, [chunk(index=0)])
    other = FakeEmbedder(dimensions=16).embed_documents(["Longer vector."])

    with pytest.raises(EmbeddingDimensionError):
        store.add([chunk(index=1)], other, 1, "fake", 1)


def test_collections_are_created_once_and_deleted_on_request(server):
    server.create_collection("book_chunks_v7", {"embedding_model": "fake"})
    server.create_collection("book_chunks_v7", {"embedding_model": "fake"})

    assert server.collection_names() == ["book_chunks_v7"]

    server.delete_collection("book_chunks_v7")
    server.delete_collection("book_chunks_v7")

    assert server.collection_names() == []


def test_an_unreachable_server_is_reported():
    server = ChromaServer("127.0.0.1", 1)

    with pytest.raises(ServiceUnavailableError, match="not reachable"):
        server.version()
