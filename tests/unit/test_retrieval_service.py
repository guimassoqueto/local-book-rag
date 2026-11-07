import pytest

from app.errors import NothingToSearchError
from app.retrieval.base import RetrievalFilters
from app.services.retrieval_service import RetrievalService
from app.storage.catalog import BookStatus
from tests.fakes import FakeReranker
from tests.library import MARKDOWN, TEXT, Library, upload


@pytest.fixture
def library(settings, tmp_path):
    return Library(settings, tmp_path / "data")


@pytest.fixture
def reranker():
    return FakeReranker()


@pytest.fixture
def retrieval(library, reranker):
    return RetrievalService(library.settings, library.catalog, library.indexes, library.processed, reranker)


def add(library, tmp_path, name="one.md", text=MARKDOWN):
    return library.books.add_book(upload(tmp_path, name, text), name)


def test_an_empty_library_says_so(retrieval):
    with pytest.raises(NothingToSearchError, match="empty"):
        retrieval.search("question", RetrievalFilters())


def test_finds_passages_with_their_sources(library, retrieval, tmp_path):
    book = add(library, tmp_path)

    result = retrieval.search("the lazy dog", RetrievalFilters())

    assert result.passages
    assert all(passage.chunk.book_id == book.book_id for passage in result.passages)
    assert result.passages[0].chunk.chapter_title in ("One", "Two")


def test_every_stage_ran(library, retrieval, reranker, tmp_path):
    add(library, tmp_path)

    [first, *_] = retrieval.search("the lazy dog", RetrievalFilters()).candidates

    assert first.fusion_score is not None
    assert first.rerank_score is not None
    assert reranker.calls == 1


def test_no_book_ids_searches_the_whole_library(library, retrieval, tmp_path):
    first = add(library, tmp_path, "one.md")
    second = add(library, tmp_path, "two.md", MARKDOWN + "\n\nOne more paragraph about dogs.")

    result = retrieval.search("dog", RetrievalFilters())

    assert {passage.chunk.book_id for passage in result.passages} == {first.book_id, second.book_id}


def test_a_book_filter_isolates_a_book(library, retrieval, tmp_path):
    add(library, tmp_path, "one.md")
    second = add(library, tmp_path, "two.md", MARKDOWN + "\n\nOne more paragraph about dogs.")

    result = retrieval.search("dog", RetrievalFilters(book_ids=(second.book_id,)))

    assert {passage.chunk.book_id for passage in result.candidates} == {second.book_id}


def test_a_chapter_filter_applies_to_every_strategy(library, retrieval, tmp_path):
    add(library, tmp_path)

    result = retrieval.search("the lazy dog", RetrievalFilters(chapter_numbers=(2,)))

    assert {passage.chunk.chapter_title for passage in result.candidates} == {"Two"}


def test_failed_books_are_not_searched(library, retrieval, tmp_path):
    book = add(library, tmp_path)
    library.catalog.update(book.book_id, status=BookStatus.FAILED)

    with pytest.raises(NothingToSearchError, match="None of the selected"):
        retrieval.search("dog", RetrievalFilters())


def test_a_book_being_reindexed_stays_searchable(library, retrieval, tmp_path):
    book = add(library, tmp_path)
    library.catalog.update(book.book_id, status=BookStatus.REINDEXING)

    assert retrieval.search("dog", RetrievalFilters()).passages


def test_a_book_outside_the_active_index_is_not_searched(library, retrieval, tmp_path):
    book = add(library, tmp_path)
    library.catalog.update(book.book_id, index_version=99)

    with pytest.raises(NothingToSearchError):
        retrieval.search("dog", RetrievalFilters())


def test_a_language_filter_selects_books(library, retrieval, tmp_path):
    add(library, tmp_path)

    with pytest.raises(NothingToSearchError):
        retrieval.search("dog", RetrievalFilters(languages=("pt",)))


@pytest.mark.parametrize("strategy", ["dense", "bm25", "hybrid"])
def test_a_strategy_can_be_chosen_per_search(library, retrieval, tmp_path, strategy):
    add(library, tmp_path)
    config = library.settings.retrieval.model_copy(update={"strategy": strategy})

    [first, *_] = retrieval.search("the lazy dog", RetrievalFilters(), config).candidates

    assert (first.dense_score is not None) is (strategy != "bm25")
    assert (first.bm25_score is not None) is (strategy != "dense")


def test_reranking_can_be_switched_off_per_search(library, retrieval, reranker, tmp_path):
    add(library, tmp_path)
    settings = library.settings.retrieval
    config = settings.model_copy(update={"reranker": settings.reranker.model_copy(update={"enabled": False})})

    retrieval.search("the lazy dog", RetrievalFilters(), config)

    assert reranker.calls == 0


def test_the_final_count_is_the_configured_one(library, retrieval, tmp_path):
    text = "\n\n".join(f"# Chapter {index}\n\n{TEXT}" for index in range(10))
    add(library, tmp_path, text=text)

    result = retrieval.search("the lazy dog", RetrievalFilters())

    assert len(result.passages) == library.settings.retrieval.reranker.top_k
