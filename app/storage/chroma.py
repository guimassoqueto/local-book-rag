"""ChromaDB access: the server, and the chunk collection on top of it."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, fields
from functools import cached_property
from itertools import batched
from typing import Any

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaClientSettings
from llama_index.core.schema import BaseNode, TextNode
from llama_index.core.vector_stores import FilterOperator, MetadataFilter, MetadataFilters, VectorStoreQuery
from llama_index.vector_stores.chroma import ChromaVectorStore

from app.errors import EmbeddingDimensionError, IndexingError, ServiceUnavailableError
from app.ingestion.chunker import Chunk

_CHUNK_FIELDS = tuple(field.name for field in fields(Chunk) if field.name != "text")
_HNSW_SPACE = "cosine"  # matches the normalized vectors both embedding models produce
_MAX_WRITE_BATCH = 256


def revision_key(book_id: str, revision: int) -> str:
    """The metadata value that tells the revisions of a book apart."""
    return f"{book_id}:r{revision}"


class ChromaServer:
    """Connects on first use, so that the application can start while ChromaDB is down."""

    def __init__(self, host: str, port: int, client: ClientAPI | None = None) -> None:
        """Create the connection.

        Args:
            host: the server's host.
            port: the server's port.
            client: an existing client, which replaces connecting to the host.
        """
        self.address = f"{host}:{port}"
        self._host = host
        self._port = port
        if client is not None:
            self.__dict__["client"] = client

    @cached_property
    def client(self) -> ClientAPI:
        return chromadb.HttpClient(
            host=self._host,
            port=self._port,
            settings=ChromaClientSettings(anonymized_telemetry=False),
        )

    @contextmanager
    def translate_errors(self) -> Iterator[None]:
        """Turn the client's exceptions, which share no base class, into the application's own."""
        try:
            yield
        except (EmbeddingDimensionError, IndexingError):
            raise
        except Exception as exc:
            self.__dict__.pop("client", None)  # reconnect next time: the server may have restarted
            if "dimension" in str(exc).lower():
                raise EmbeddingDimensionError(f"ChromaDB rejected the vectors: {exc}") from exc
            raise ServiceUnavailableError(f"ChromaDB is not reachable at {self.address}: {exc}") from exc

    def version(self) -> str:
        with self.translate_errors():
            return self.client.get_version()

    def create_collection(self, name: str, metadata: dict[str, Any]) -> None:
        """Create a collection. The application supplies every vector, so it has no embedding function."""
        with self.translate_errors():
            self.client.get_or_create_collection(
                name,
                metadata=metadata,
                configuration={"hnsw": {"space": _HNSW_SPACE}},
                embedding_function=None,
            )

    def delete_collection(self, name: str) -> None:
        with self.translate_errors():
            if name in self.collection_names():
                self.client.delete_collection(name)

    def collection_names(self) -> list[str]:
        with self.translate_errors():
            return [collection.name for collection in self.client.list_collections()]

    def collection(self, name: str) -> Collection:
        with self.translate_errors():
            return self.client.get_collection(name, embedding_function=None)

    def max_write_batch(self) -> int:
        with self.translate_errors():
            return min(self.client.get_max_batch_size(), _MAX_WRITE_BATCH)


@dataclass(frozen=True)
class ScoredChunk:
    """A retrieved chunk. The score is LlamaIndex's exp(-distance): only its order is meaningful."""

    chunk: Chunk
    score: float


class ChunkStore:
    """The chunks of one index version, in a single collection, told apart by their metadata."""

    def __init__(self, server: ChromaServer, collection_name: str) -> None:
        self._server = server
        self.collection_name = collection_name

    @cached_property
    def _vector_store(self) -> ChromaVectorStore:
        return ChromaVectorStore(chroma_collection=self._collection)

    @property
    def _collection(self) -> Collection:
        return self._server.collection(self.collection_name)

    def add(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[list[float]],
        revision: int,
        embedding_model: str,
        index_version: int,
    ) -> None:
        """Store a book's chunks.

        Record IDs carry the revision, so that a replacement can sit next to the revision in
        use until it is verified.

        Args:
            chunks: the chunks.
            vectors: their embeddings, in the same order.
            revision: the book revision they belong to.
            embedding_model: stored with every record.
            index_version: stored with every record.
        """
        nodes = [
            _to_node(chunk, vector, revision, embedding_model, index_version)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        with self._server.translate_errors():
            for batch in batched(nodes, self._server.max_write_batch(), strict=False):
                self._vector_store.add(list(batch))

    def query(self, vector: list[float], top_k: int, filters: MetadataFilters) -> list[ScoredChunk]:
        """Find the chunks nearest to a vector, among those the filters allow."""
        query = VectorStoreQuery(query_embedding=vector, similarity_top_k=top_k, filters=filters)
        with self._server.translate_errors():
            result = self._vector_store.query(query)
        return [
            ScoredChunk(_to_chunk(node), score)
            for node, score in zip(result.nodes or [], result.similarities or [], strict=True)
        ]

    def count_revision(self, book_id: str, revision: int) -> int:
        with self._server.translate_errors():
            return len(
                self._collection.get(where={"book_revision": revision_key(book_id, revision)}, include=[])["ids"]
            )

    def delete_revision(self, book_id: str, revision: int) -> None:
        with self._server.translate_errors():
            self._collection.delete(where={"book_revision": revision_key(book_id, revision)})

    def delete_book(self, book_id: str) -> None:
        with self._server.translate_errors():
            self._collection.delete(where={"book_id": book_id})

    def count(self) -> int:
        with self._server.translate_errors():
            return self._collection.count()


def revision_filter(revisions: Sequence[str]) -> MetadataFilters:
    """Limit a query to the given revisions, which is what keeps books and replacements apart."""
    return MetadataFilters(
        filters=[MetadataFilter(key="book_revision", value=list(revisions), operator=FilterOperator.IN)]
    )


def _to_node(chunk: Chunk, vector: list[float], revision: int, embedding_model: str, index_version: int) -> BaseNode:
    metadata = {name: getattr(chunk, name) for name in _CHUNK_FIELDS}
    metadata |= {
        "book_revision": revision_key(chunk.book_id, revision),
        "embedding_model": embedding_model,
        "index_version": index_version,
    }
    return TextNode(id_=f"{chunk.chunk_id}:r{revision}", text=chunk.text, embedding=vector, metadata=metadata)


def _to_chunk(node: BaseNode) -> Chunk:
    return Chunk(text=node.get_content(), **{name: node.metadata[name] for name in _CHUNK_FIELDS})
