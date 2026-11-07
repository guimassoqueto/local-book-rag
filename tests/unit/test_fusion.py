import pytest

from app.config.settings import FusionConfig
from app.retrieval.base import Passage
from app.retrieval.fusion import create_fusion, reciprocal_rank_fusion, weighted_fusion
from tests.fakes import make_chunk


def dense(*indexes):
    return [Passage(make_chunk(index=i), dense_score=1 - position / 10) for position, i in enumerate(indexes)]


def bm25(*indexes):
    return [Passage(make_chunk(index=i), bm25_score=10 - position) for position, i in enumerate(indexes)]


def order(passages):
    return [passage.chunk.chunk_index for passage in passages]


def test_rrf_follows_the_formula():
    merged = reciprocal_rank_fusion(dense(0, 1), bm25(1), k=60)

    assert order(merged) == [1, 0]
    assert merged[0].fusion_score == pytest.approx(1 / 62 + 1 / 61)
    assert merged[1].fusion_score == pytest.approx(1 / 61)


def test_rrf_rewards_agreement_over_a_single_first_place():
    merged = reciprocal_rank_fusion(dense(0, 1, 2), bm25(3, 1, 2), k=60)

    assert order(merged)[0] == 1


def test_a_passage_found_by_both_keeps_both_scores():
    [merged] = reciprocal_rank_fusion(dense(0), bm25(0), k=60)

    assert merged.dense_score == 1.0
    assert merged.bm25_score == 10


def test_a_passage_found_by_one_keeps_the_other_score_empty():
    merged = {p.chunk.chunk_index: p for p in reciprocal_rank_fusion(dense(0), bm25(1), k=60)}

    assert merged[0].bm25_score is None
    assert merged[1].dense_score is None


def test_one_empty_list_leaves_the_other():
    assert order(reciprocal_rank_fusion(dense(0, 1), [], k=60)) == [0, 1]
    assert order(reciprocal_rank_fusion([], bm25(0, 1), k=60)) == [0, 1]


def test_weighted_fusion_can_favor_either_side():
    assert order(weighted_fusion(dense(0, 1), bm25(1, 0), dense_weight=0.9))[0] == 0
    assert order(weighted_fusion(dense(0, 1), bm25(1, 0), dense_weight=0.1))[0] == 1


def test_weighted_fusion_normalizes_each_list():
    merged = weighted_fusion(dense(0, 1), bm25(0, 1), dense_weight=0.5)

    assert merged[0].fusion_score == pytest.approx(1.0)
    assert merged[1].fusion_score == pytest.approx(0.0)


def test_weighted_fusion_survives_equal_scores():
    merged = weighted_fusion([Passage(make_chunk(), dense_score=0.5)], [], dense_weight=0.5)

    assert merged[0].fusion_score == pytest.approx(0.5)


@pytest.mark.parametrize("method", ["rrf", "weighted"])
def test_the_configuration_selects_the_method(method):
    fusion = create_fusion(FusionConfig(method=method, rrf_k=60, dense_weight=0.5))

    assert order(fusion(dense(0), bm25(0))) == [0]
