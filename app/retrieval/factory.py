"""Builds the retrieval pipeline that a configuration describes."""

from app.config.settings import RetrievalConfig
from app.embeddings.base import EmbeddingProvider
from app.retrieval.base import Reranker, Retriever
from app.retrieval.bm25 import BM25Retriever, ChunkSource
from app.retrieval.dense import DenseRetriever
from app.retrieval.fusion import create_fusion
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.pipeline import RetrievalPipeline
from app.storage.chroma import ChunkStore


def create_pipeline(
    config: RetrievalConfig,
    embedder: EmbeddingProvider,
    store: ChunkStore,
    chunks: ChunkSource,
    reranker: Reranker,
) -> RetrievalPipeline:
    """Create a pipeline.

    Args:
        config: which strategy to run, and its parameters.
        embedder: embeds questions for this index.
        store: the index's chunks.
        chunks: the same chunks, as text, for lexical search.
        reranker: used only if the configuration enables reranking.
    """
    dense = DenseRetriever(embedder, store, config.dense.top_k)
    bm25 = BM25Retriever(config.bm25, chunks)
    retriever: Retriever
    match config.strategy:
        case "dense":
            retriever = dense
        case "bm25":
            retriever = bm25
        case "hybrid":
            retriever = HybridRetriever(dense, bm25, create_fusion(config.fusion))
    return RetrievalPipeline(retriever, reranker if config.reranker.enabled else None, config.reranker.top_k)
