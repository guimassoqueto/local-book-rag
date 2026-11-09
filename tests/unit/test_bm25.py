import pytest

from app.config.settings import BM25Config
from app.retrieval.base import BookScope, RetrievalFilters
from app.retrieval.bm25 import BM25Retriever, Tokenizer
from tests.fakes import FakeChunks, make_chunk
from tests.historical_spelling import COLLISIONS, PAIRS

CONFIG = BM25Config(top_k=5, k1=1.5, b=0.75, stemming=True, historical_spelling=False)
HISTORICAL = CONFIG.model_copy(update={"historical_spelling": True})


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


def folding():
    return Tokenizer("pt", stemming=True, historical_spelling=True)


def portuguese(*texts):
    return [make_chunk(text, index=index, language="pt") for index, text in enumerate(texts)]


@pytest.mark.parametrize(("modern", "old"), PAIRS, ids=[f"{modern}-{old}" for modern, old in PAIRS])
def test_an_old_spelling_matches_the_modern_one(modern, old):
    assert folding().tokenize(modern) == folding().tokenize(old)


@pytest.mark.parametrize(("first", "second"), COLLISIONS, ids=[f"{a}-{b}" for a, b in COLLISIONS])
def test_different_modern_words_stay_apart(first, second):
    assert folding().tokenize(first) != folding().tokenize(second)


def test_a_modern_spelling_finds_the_old_one_and_the_text_is_left_as_printed():
    chunks = portuguese("Sophia sorriu para Rubião.", "O Palha fechou a porta.")

    results = retriever(chunks, HISTORICAL).retrieve("Sofia", scope("pt"))

    assert texts(results) == ["Sophia sorriu para Rubião."]


def test_the_books_own_spelling_still_finds_the_passage():
    chunks = portuguese("Sophia sorriu para Rubião.", "O Palha fechou a porta.")

    assert texts(retriever(chunks, HISTORICAL).retrieve("Sophia", scope("pt"))) == ["Sophia sorriu para Rubião."]


@pytest.mark.parametrize(
    ("query", "text"),
    [
        ("filósofo", "O philosopho de Barbacena."),
        ("Teresa", "Thereza chegou cedo."),
        ("aparecer", "Rubião não apparecia."),
        ("Sofia", "As Sophias da côrte."),
    ],
)
def test_other_old_spellings_and_word_forms_are_found(query, text):
    chunks = portuguese(text, "O Palha fechou a porta.")

    assert texts(retriever(chunks, HISTORICAL).retrieve(query, scope("pt"))) == [text]


@pytest.mark.parametrize(
    ("query", "text"),
    [("Theophilo", "Teófilo saiu cedo."), ("philosopho", "O filósofo de Barbacena.")],
)
def test_an_old_spelling_finds_a_modern_edition(query, text):
    chunks = portuguese(text, "O Palha fechou a porta.")

    assert texts(retriever(chunks, HISTORICAL).retrieve(query, scope("pt"))) == [text]


OLD_SPELLINGS = "Sophia elle anno philosopho typo apparecer Thereza scena"


@pytest.mark.parametrize(
    ("language", "stemming", "historical_spelling"),
    [("en", True, True), (None, True, True), ("pt", True, False), ("pt", False, True)],
    ids=["english", "no-language", "portuguese-off", "portuguese-unstemmed"],
)
def test_tokens_are_unchanged_where_historical_spelling_does_not_apply(language, stemming, historical_spelling):
    plain = Tokenizer(language, stemming).tokenize(OLD_SPELLINGS)

    assert Tokenizer(language, stemming, historical_spelling).tokenize(OLD_SPELLINGS) == plain


def test_unstemmed_search_ignores_historical_spelling_even_past_the_validator():
    chunks = portuguese("Sophia sorriu para Rubião.")
    config = HISTORICAL.model_copy(update={"stemming": False})  # model_copy skips the validator

    assert retriever(chunks, config).retrieve("Sofia", scope("pt")) == []
