"""Runs each candidate reranker's real weights, which the first run downloads."""

import pytest

from app.config.settings import RerankerModelConfig
from app.retrieval.reranker import CrossEncoderReranker

pytestmark = pytest.mark.integration

MODELS = ["Qwen/Qwen3-Reranker-0.6B", "BAAI/bge-reranker-v2-m3"]
DOCUMENTS = [
    "The capital of Australia is Canberra, a planned city between Sydney and Melbourne.",
    "Kangaroos are marsupials that carry their young in a pouch.",
    "A capital gains tax applies to the profit from selling an asset.",
]


def config(model, device="cpu"):
    return RerankerModelConfig(provider="transformers", model=model, device=device, batch_size=8)


@pytest.mark.parametrize("model", MODELS)
def test_the_relevant_document_scores_highest(model):
    scores = CrossEncoderReranker(config(model)).score("What is the capital of Australia?", DOCUMENTS)

    assert scores[0] == max(scores)
    assert all(0 <= score <= 1 for score in scores)
    assert scores[0] > 0.5 > scores[1]


@pytest.mark.parametrize("model", MODELS)
def test_it_reads_portuguese(model):
    scores = CrossEncoderReranker(config(model)).score("Qual é a capital da Austrália?", DOCUMENTS)

    assert scores[0] == max(scores)


def test_nothing_to_score_loads_nothing():
    assert CrossEncoderReranker(config(MODELS[0])).score("question", []) == []


def test_on_the_gpu_the_model_leaves_vram_after_scoring():
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("no GPU")
    reranker = CrossEncoderReranker(config(MODELS[0], device="cuda"))

    scores = reranker.score("What is the capital of Australia?", DOCUMENTS)

    assert scores[0] == max(scores)
    assert next(reranker._encoder.parameters()).device.type == "cpu"
