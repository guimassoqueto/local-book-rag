"""Dense retrieval: nearest neighbors in the vector index."""

from llama_index.core.vector_stores import FilterOperator, MetadataFilter, MetadataFilters

from app.embeddings.base import EmbeddingProvider
from app.retrieval.base import BookScope, Passage
from app.storage.chroma import ChunkStore, revision_key


class DenseRetriever:
    def __init__(self, embedder: EmbeddingProvider, store: ChunkStore, top_k: int) -> None:
        self._embedder = embedder
        self._store = store
        self._top_k = top_k

    def retrieve(self, query: str, scope: BookScope) -> list[Passage]:
        vector = self._embedder.embed_query(query)
        results = self._store.query(vector, self._top_k, metadata_filters(scope))
        return [Passage(item.chunk, dense_score=item.score) for item in results]


def metadata_filters(scope: BookScope) -> MetadataFilters:
    """Express a scope in the vector store's terms. RetrievalFilters.allows says the same in Python."""
    filters = scope.filters
    conditions = [
        MetadataFilter(
            key="book_revision", value=revision_key(scope.book_id, scope.revision), operator=FilterOperator.EQ
        )
    ]
    if filters.chapter_numbers:
        conditions.append(
            MetadataFilter(key="chapter_number", value=list(filters.chapter_numbers), operator=FilterOperator.IN)
        )
    if filters.section_titles:
        conditions.append(
            MetadataFilter(key="section_title", value=list(filters.section_titles), operator=FilterOperator.IN)
        )
    if filters.languages:
        conditions.append(MetadataFilter(key="language", value=list(filters.languages), operator=FilterOperator.IN))
    if filters.page_start is not None:
        conditions.append(MetadataFilter(key="page_end", value=filters.page_start, operator=FilterOperator.GTE))
    if filters.page_end is not None:
        conditions.append(MetadataFilter(key="page_start", value=filters.page_end, operator=FilterOperator.LTE))
    return MetadataFilters(filters=conditions)
