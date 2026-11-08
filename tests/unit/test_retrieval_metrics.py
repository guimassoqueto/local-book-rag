import pytest

from app.evaluation.retrieval_metrics import (
    context_precision,
    context_recall,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)

TWO_QUOTES = [{"a"}, {"b"}]


def test_recall_counts_the_evidence_found_within_k():
    assert recall_at_k(["x", "a", "y", "b"], TWO_QUOTES, 2) == 0.5
    assert recall_at_k(["x", "a", "y", "b"], TWO_QUOTES, 4) == 1.0
    assert recall_at_k(["x"], TWO_QUOTES, 5) == 0.0


def test_a_quote_in_two_chunks_counts_once():
    assert recall_at_k(["a1", "a2"], [{"a1", "a2"}, {"b"}], 5) == 0.5


def test_finding_either_chunk_of_a_quote_finds_it():
    assert recall_at_k(["a2"], [{"a1", "a2"}], 5) == 1.0


def test_no_evidence_gives_zero_not_an_error():
    assert recall_at_k(["a"], [], 5) == 0.0
    assert reciprocal_rank(["a"], []) == 0.0
    assert ndcg_at_k(["a"], [], 10) == 0.0
    assert context_precision(["a"], []) == 0.0
    assert context_recall(["a"], []) == 0.0


def test_reciprocal_rank_is_the_position_of_the_first_hit():
    assert reciprocal_rank(["a"], TWO_QUOTES) == 1.0
    assert reciprocal_rank(["x", "y", "b"], TWO_QUOTES) == pytest.approx(1 / 3)
    assert reciprocal_rank(["x"], TWO_QUOTES) == 0.0


def test_ndcg_is_one_for_the_ideal_order():
    assert ndcg_at_k(["a", "b", "x"], TWO_QUOTES, 10) == pytest.approx(1.0)


def test_ndcg_follows_the_formula():
    # One relevant result at rank 2, against an ideal of one at rank 1.
    assert ndcg_at_k(["x", "a"], [{"a"}], 10) == pytest.approx(0.6309, abs=1e-4)


def test_ndcg_doesnt_reward_finding_the_same_quote_twice():
    assert ndcg_at_k(["a1", "a2"], [{"a1", "a2"}, {"b"}], 10) == pytest.approx(1 / 1.6309, abs=1e-3)


def test_two_quotes_in_one_chunk_can_still_reach_a_perfect_score():
    assert ndcg_at_k(["both", "x"], [{"both"}, {"both"}], 10) == pytest.approx(1.0)


def test_chunk_size_alone_doesnt_change_a_perfect_ranking():
    small_chunks = [{"a"}, {"b"}]
    one_large_chunk = [{"ab"}, {"ab"}]

    assert ndcg_at_k(["a", "b"], small_chunks, 10) == ndcg_at_k(["ab"], one_large_chunk, 10) == pytest.approx(1.0)


def test_the_ideal_order_takes_the_chunk_that_covers_the_most_first():
    evidence = [{"a", "both"}, {"b", "both"}]

    assert ndcg_at_k(["both"], evidence, 10) == pytest.approx(1.0)
    assert ndcg_at_k(["a", "b"], evidence, 10) < 1.0


def test_ndcg_only_looks_at_the_first_k():
    assert ndcg_at_k(["x", "y", "a"], [{"a"}], 2) == 0.0


def test_context_precision_rewards_relevant_passages_coming_first():
    assert context_precision(["a", "b", "x"], TWO_QUOTES) == pytest.approx(1.0)
    assert context_precision(["x", "a", "b"], TWO_QUOTES) == pytest.approx((1 / 2 + 2 / 3) / 2)


def test_context_recall_is_what_reached_the_model():
    assert context_recall(["a", "x"], TWO_QUOTES) == 0.5
