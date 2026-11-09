import json

import chromadb
import pytest

from app.errors import EmbeddingDimensionError, ReindexRequiredError
from app.services.index_service import IndexService
from app.storage.catalog import BookCatalog
from app.storage.chroma import ChromaServer
from tests.fakes import FakeRuntime


@pytest.fixture
def catalog(tmp_path):
    return BookCatalog(tmp_path / "catalog.db")


@pytest.fixture
def server(tmp_path):
    return ChromaServer("embedded", 0, client=chromadb.PersistentClient(path=str(tmp_path / "chroma")))


def indexes(settings, catalog, server, runtime=None):
    return IndexService(settings, catalog, server, runtime or FakeRuntime())


def changed(settings, section, **values):
    return settings.model_copy(update={section: getattr(settings, section).model_copy(update=values)})


def test_there_is_no_index_until_the_first_book(settings, catalog, server):
    service = indexes(settings, catalog, server)

    assert service.active() is None
    assert not service.needs_reindex()


def test_the_first_write_creates_the_recommended_collection(settings, catalog, server):
    record = indexes(settings, catalog, server).require_writable()

    assert record.collection == "book_chunks_v1"
    assert record.version == 1
    assert record.embedding_model == settings.embedding.model
    assert record.embedding_digest == "digest-1"
    assert record.dimensions == 1024
    assert server.collection_names() == ["book_chunks_v1"]


def test_the_collection_records_what_built_it(settings, catalog, server):
    indexes(settings, catalog, server).require_writable()

    metadata = server.collection("book_chunks_v1").metadata

    assert metadata["embedding_model"] == settings.embedding.model
    assert metadata["dimensions"] == 1024


def test_the_index_is_stored_with_its_configuration(settings, catalog, server):
    record = indexes(settings, catalog, server).require_writable()

    configuration = json.loads(record.configuration)

    assert configuration["chunking"]["target_size"] == settings.chunking.target_size
    assert configuration["embedding_digest"] == "digest-1"


def test_later_writes_reuse_the_same_index(settings, catalog, server):
    service = indexes(settings, catalog, server)

    assert service.require_writable() == service.require_writable()
    assert server.collection_names() == ["book_chunks_v1"]


@pytest.mark.parametrize(
    ("section", "values"),
    [
        ("chunking", {"target_size": 300}),
        ("chunking", {"overlap": 40}),
        ("chunking", {"strategy": "fixed"}),
        ("embedding", {"model": "bge-m3"}),
    ],
)
def test_a_changed_configuration_needs_an_explicit_reindex(settings, catalog, server, section, values):
    indexes(settings, catalog, server).require_writable()
    service = indexes(changed(settings, section, **values), catalog, server)

    assert service.needs_reindex()
    with pytest.raises(ReindexRequiredError, match="reindex-all"):
        service.require_writable()


def test_new_weights_under_the_same_tag_need_a_reindex(settings, catalog, server):
    indexes(settings, catalog, server, FakeRuntime(digest="old")).require_writable()
    service = indexes(settings, catalog, server, FakeRuntime(digest="new"))

    assert service.needs_reindex()


def test_the_query_template_can_change_without_a_reindex(settings, catalog, server):
    indexes(settings, catalog, server).require_writable()
    profile = settings.embedding_profile.model_copy(update={"query_template": "Search: {text}"})
    profiles = settings.embedding_profiles | {settings.embedding.model: profile}

    service = indexes(settings.model_copy(update={"embedding_profiles": profiles}), catalog, server)

    assert not service.needs_reindex()


def test_historical_spelling_can_change_without_a_reindex(settings, catalog, server):
    indexes(settings, catalog, server).require_writable()
    current = settings.retrieval.bm25
    bm25 = current.model_copy(update={"historical_spelling": not current.historical_spelling})

    service = indexes(changed(settings, "retrieval", bm25=bm25), catalog, server)

    assert not service.needs_reindex()


def test_a_size_that_contradicts_the_model_stops_everything(settings, catalog, server):
    with pytest.raises(EmbeddingDimensionError, match="produces 768"):
        indexes(settings, catalog, server, FakeRuntime(dimensions=768)).require_writable()


def test_queries_use_the_model_that_built_the_index(settings, catalog, server):
    record = indexes(settings, catalog, server).require_writable()

    service = indexes(changed(settings, "embedding", model="bge-m3"), catalog, server)

    assert service.query_embedder(record).model == settings.embedding.model


def test_questions_keep_the_dimensions_of_the_index_when_the_configuration_moves_on(settings, catalog, server):
    record = indexes(settings, catalog, server).require_writable()
    moved = settings.model_copy(
        update={"embedding": settings.embedding.model_copy(update={"model": "bge-m3", "dimensions": 768})}
    )

    embedder = indexes(moved, catalog, server).query_embedder(record)

    assert embedder.model == settings.embedding.model
    assert embedder._config.dimensions == 1024


def test_the_index_survives_reopening_the_catalog(settings, catalog, server, tmp_path):
    record = indexes(settings, catalog, server).require_writable()

    assert indexes(settings, BookCatalog(tmp_path / "catalog.db"), server).active() == record
