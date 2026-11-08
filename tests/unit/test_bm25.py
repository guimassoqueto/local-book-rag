import pytest

from app.config.settings import BM25Config
from app.retrieval.base import BookScope, RetrievalFilters
from app.retrieval.bm25 import BM25Retriever, Tokenizer
from tests.fakes import FakeChunks, make_chunk

CONFIG = BM25Config(top_k=5, k1=1.5, b=0.75, stemming=True)


def retriever(chunks, config=CONFIG):
    return BM25Retriever(config, FakeChunks(chunks))


def scope(language="en", **filters):
    return BookScope("book_001", 1, language, RetrievalFilters(**filters))


def corpus():
    return [
        make_chunk("Opportunity cost is the value of the next best alternative.", index=0, chapter=1, page_start=1),
        make_chunk("Supply and demand set the price in a free market.", index=1, chapter=1, page_start=2),
        make_chunk("Comparative advantage explains why nations trade.", index=2, chapter=2, page_start=3),
        make_chunk(
            "Inflation erodes the purchasing power of money.", index=3, chapter=2, section="Money", page_start=4
        ),
    ]


def texts(passages):
    return [passage.chunk.text for passage in passages]


def test_the_matching_passage_comes_first():
    results = retriever(corpus()).retrieve("what is opportunity cost", scope())

    assert results[0].chunk.chunk_index == 0
    assert results[0].bm25_score > 0


def test_stemming_matches_other_forms_of_a_word():
    results = retriever(corpus()).retrieve("nations trading advantages", scope())

    assert results[0].chunk.chunk_index == 2


def test_stemming_can_be_switched_off():
    config = CONFIG.model_copy(update={"stemming": False})

    assert retriever(corpus(), config).retrieve("trading advantages", scope()) == []


def test_portuguese_is_stemmed_and_accents_do_not_matter():
    chunks = [
        make_chunk("A divisão do trabalho aumenta a produtividade.", index=0, language="pt"),
        make_chunk("O preço depende da oferta e da procura.", index=1, language="pt"),
    ]

    results = retriever(chunks).retrieve("divisao dos trabalhos", scope("pt"))

    assert results[0].chunk.chunk_index == 0


def test_unknown_terms_find_nothing():
    assert retriever(corpus()).retrieve("zzzznotaword", scope()) == []


def test_a_query_without_words_finds_nothing():
    assert retriever(corpus()).retrieve("?!", scope()) == []


def test_top_k_can_exceed_the_corpus():
    chunks = [make_chunk("A single chunk about money.")]

    assert len(retriever(chunks).retrieve("money", scope())) == 1


def test_results_are_limited_to_top_k():
    chunks = [make_chunk(f"Money and more money {index}.", index=index) for index in range(10)]

    assert len(retriever(chunks).retrieve("money", scope())) == CONFIG.top_k


def test_filters_narrow_the_corpus():
    results = retriever(corpus()).retrieve("money price trade", scope(chapter_numbers=(2,)))

    assert {passage.chunk.chapter_number for passage in results} == {2}


def test_a_filter_that_excludes_everything_finds_nothing():
    assert retriever(corpus()).retrieve("money", scope(chapter_numbers=(9,))) == []


def test_other_books_are_never_searched():
    chunks = [make_chunk("Money in book one."), make_chunk("Money in book two.", book_id="book_002")]

    assert texts(retriever(chunks).retrieve("money", scope())) == ["Money in book one."]


def test_a_book_is_read_from_disk_once():
    source = FakeChunks(corpus())
    bm25 = BM25Retriever(CONFIG, source)

    bm25.retrieve("money", scope())
    bm25.retrieve("price", scope())
    bm25.retrieve("trade", scope(chapter_numbers=(2,)))

    assert source.loads == 1


def test_a_new_revision_is_read_afresh():
    source = FakeChunks(corpus())
    bm25 = BM25Retriever(CONFIG, source)

    bm25.retrieve("money", scope())
    bm25.retrieve("money", BookScope("book_001", 2, "en"))

    assert source.loads == 2


@pytest.mark.parametrize(
    ("language", "text", "expected"),
    [
        ("en", "Running Economies", ["run", "economi"]),
        ("pt", "CORAÇÕES", ["coraco"]),
        (None, "Unstemmed Words", ["unstemmed", "words"]),
        ("xx", "Unknown Language", ["unknown", "language"]),
    ],
)
def test_tokenizer(language, text, expected):
    assert Tokenizer(language, stemming=True).tokenize(text) == expected
