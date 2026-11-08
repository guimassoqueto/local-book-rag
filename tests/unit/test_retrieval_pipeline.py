import pytest

from app.retrieval.base import BookScope, Passage
from app.retrieval.pipeline import RetrievalPipeline
from tests.fakes import FakeReranker, make_chunk


class FakeRetriever:
    def __init__(self, results):
        self.results = results

    def retrieve(self, query, scope):
        return self.results.get(scope.book_id, [])


def passages(book_id, *texts):
    return [
        Passage(make_chunk(text, book_id=book_id, index=index), fusion_score=1 / (index + 1))
        for index, text in enumerate(texts)
    ]


def scopes(*book_ids):
    return [BookScope(book_id, 1, "en") for book_id in book_ids]


def test_without_a_reranker_the_retriever_order_stands():
    retriever = FakeRetriever({"book_001": passages("book_001", "a", "b", "c")})

    result = RetrievalPipeline(retriever, None, top_k=2).run("query", scopes("book_001"))

    assert [passage.chunk.text for passage in result.passages] == ["a", "b"]
    assert all(passage.rerank_score is None for passage in result.passages)
    assert result.rerank_seconds == pytest.approx(0, abs=0.01)


def test_the_reranker_decides_the_final_order():
    retriever = FakeRetriever({"book_001": passages("book_001", "nothing here", "money", "money money")})

    result = RetrievalPipeline(retriever, FakeReranker(), top_k=2).run("money", scopes("book_001"))

    assert [passage.chunk.text for passage in result.passages] == ["money money", "money"]
    assert result.passages[0].rerank_score == pytest.approx(0.2)


def test_earlier_scores_survive_reranking():
    retriever = FakeRetriever({"book_001": passages("book_001", "money")})

    [passage] = RetrievalPipeline(retriever, FakeReranker(), top_k=1).run("money", scopes("book_001")).passages

    assert passage.fusion_score == 1
    assert passage.rerank_score is not None


def test_candidates_keep_everything_the_final_cut_drops():
    retriever = FakeRetriever({"book_001": passages("book_001", "a", "b", "c")})

    result = RetrievalPipeline(retriever, None, top_k=1).run("query", scopes("book_001"))

    assert len(result.passages) == 1
    assert len(result.candidates) == 3


def test_books_take_turns_so_that_none_is_crowded_out():
    retriever = FakeRetriever(
        {
            "book_001": passages("book_001", "a1", "a2", "a3", "a4"),
            "book_002": passages("book_002", "b1", "b2", "b3", "b4"),
        }
    )

    result = RetrievalPipeline(retriever, None, top_k=4).run("query", scopes("book_001", "book_002"))

    assert [passage.chunk.text for passage in result.passages] == ["a1", "b1", "a2", "b2"]


def test_a_stronger_book_cannot_take_a_weaker_books_share():
    retriever = FakeRetriever(
        {
            "book_001": passages("book_001", "money", "money", "money", "money"),
            "book_002": passages("book_002", "nothing relevant"),
        }
    )

    result = RetrievalPipeline(retriever, FakeReranker(), top_k=2).run("money", scopes("book_001", "book_002"))

    assert {passage.chunk.book_id for passage in result.passages} == {"book_001", "book_002"}


def test_an_odd_limit_is_respected():
    retriever = FakeRetriever(
        {"book_001": passages("book_001", "a1", "a2"), "book_002": passages("book_002", "b1", "b2")}
    )

    result = RetrievalPipeline(retriever, None, top_k=3).run("query", scopes("book_001", "book_002"))

    assert [passage.chunk.text for passage in result.passages] == ["a1", "b1", "a2"]


def test_a_book_without_results_does_not_block_the_others():
    retriever = FakeRetriever({"book_001": passages("book_001", "a1", "a2")})

    result = RetrievalPipeline(retriever, None, top_k=2).run("query", scopes("book_001", "book_002"))

    assert [passage.chunk.text for passage in result.passages] == ["a1"]


def test_timings_are_reported():
    retriever = FakeRetriever({"book_001": passages("book_001", "a")})

    result = RetrievalPipeline(retriever, FakeReranker(), top_k=1).run("query", scopes("book_001"))

    assert result.retrieval_seconds >= 0
    assert result.rerank_seconds >= 0
