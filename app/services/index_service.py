"""Which vector index is in use, and whether the configuration still matches it."""

import hashlib
import json
from dataclasses import dataclass

from app.config.settings import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import create_embedding_provider
from app.errors import EmbeddingDimensionError, ReindexRequiredError
from app.storage.catalog import BookCatalog, IndexRecord, utc_now
from app.storage.chroma import ChromaServer, ChunkStore
from app.utils.ollama_runtime import OllamaRuntime

COLLECTION_PREFIX = "book_chunks_v"

# Bump when the fields stored with each chunk change: old records can't serve new code.
METADATA_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class IndexConfiguration:
    """Everything that decides what a vector means.

    The query template is left out on purpose: it changes how questions are embedded, not
    what is stored, so experimenting with it needs no rebuild.
    """

    embedding_model: str
    embedding_digest: str | None
    dimensions: int
    configuration: str
    fingerprint: str


class IndexService:
    def __init__(
        self,
        settings: Settings,
        catalog: BookCatalog,
        server: ChromaServer,
        runtime: OllamaRuntime,
        collection_prefix: str = COLLECTION_PREFIX,
    ) -> None:
        self._settings = settings
        self._catalog = catalog
        self._server = server
        self._runtime = runtime
        self._collection_prefix = collection_prefix

    def current_configuration(self) -> IndexConfiguration:
        """Describe the index the configuration asks for, reading the model's identity from Ollama.

        Raises:
            EmbeddingDimensionError: the model's real size contradicts embedding.dimensions.
        """
        embedding = self._settings.embedding
        info = self._runtime.model_info(embedding.model)
        if info.embedding_length != embedding.dimensions:
            raise EmbeddingDimensionError(
                f"{embedding.model} produces {info.embedding_length} dimensions, but embedding.dimensions "
                f"says {embedding.dimensions}."
            )
        shape = {
            "embedding_model": embedding.model,
            "embedding_digest": info.digest,
            "dimensions": info.embedding_length,
            "document_template": self._settings.embedding_profile.document_template,
            "tokenizer": self._settings.embedding_profile.tokenizer.model_dump(),
            "chunking": self._settings.chunking.model_dump(),
            "metadata_schema": METADATA_SCHEMA_VERSION,
        }
        serialized = json.dumps(shape, sort_keys=True)
        return IndexConfiguration(
            embedding_model=embedding.model,
            embedding_digest=info.digest,
            dimensions=embedding.dimensions,
            configuration=serialized,
            fingerprint=hashlib.sha256(serialized.encode()).hexdigest(),
        )

    def active(self) -> IndexRecord | None:
        return self._catalog.active_index()

    def require_writable(self) -> IndexRecord:
        """Return the index that new books go into, creating the very first one.

        Raises:
            ReindexRequiredError: the configuration changed. Adding to the index now would
                mix incompatible chunks, so nothing changes until an explicit reindex.
        """
        wanted = self.current_configuration()
        active = self._catalog.active_index()
        if active is None:
            return self._create(wanted)
        if active.fingerprint != wanted.fingerprint:
            raise ReindexRequiredError(
                f"The embedding or chunking configuration changed since index v{active.version} was built "
                f"with {active.embedding_model}. Run reindex-all to rebuild the library with it, or restore "
                "the previous configuration."
            )
        return active

    def create_staging(self) -> IndexRecord:
        """Create the index that a rebuild fills, which queries ignore until the rebuild swaps it in."""
        return self._create(self.current_configuration(), active=False)

    def needs_reindex(self) -> bool:
        active = self._catalog.active_index()
        return active is not None and active.fingerprint != self.current_configuration().fingerprint

    def store(self, record: IndexRecord) -> ChunkStore:
        return ChunkStore(self._server, record.collection)

    def query_embedder(self, record: IndexRecord) -> EmbeddingProvider:
        """The embedder for questions against an index: the model that built it, not the configured one."""
        return create_embedding_provider(self._settings, self._runtime, record.embedding_model, record.dimensions)

    def _create(self, configuration: IndexConfiguration, active: bool = True) -> IndexRecord:
        version = self._catalog.next_index_version()
        record = IndexRecord(
            version=version,
            collection=f"{self._collection_prefix}{version}",
            embedding_model=configuration.embedding_model,
            embedding_digest=configuration.embedding_digest,
            dimensions=configuration.dimensions,
            configuration=configuration.configuration,
            fingerprint=configuration.fingerprint,
            active=active,
            created_at=utc_now(),
        )
        self._server.create_collection(
            record.collection,
            {
                "embedding_model": record.embedding_model,
                "dimensions": record.dimensions,
                "index_version": record.version,
            },
        )
        self._catalog.add_index(record)
        return record
