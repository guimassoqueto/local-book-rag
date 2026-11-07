"""Takes a document from a file to verified vectors in the index."""

from pathlib import Path

from app.config.settings import Settings
from app.embeddings.base import EmbeddingProvider
from app.errors import IndexingError
from app.ingestion.base import DocumentFormat
from app.ingestion.pipeline import IngestionPipeline, ProcessedDocument
from app.storage.catalog import IndexRecord
from app.storage.chroma import ChunkStore
from app.storage.repositories import ProcessedDocuments
from app.utils.logging import get_logger, log_event
from app.utils.ollama_runtime import OllamaRuntime

logger = get_logger("services.ingestion")


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        pipeline: IngestionPipeline,
        processed: ProcessedDocuments,
        embedder: EmbeddingProvider,
        runtime: OllamaRuntime,
    ) -> None:
        self._settings = settings
        self._pipeline = pipeline
        self._processed = processed
        self._embedder = embedder
        self._runtime = runtime

    def ingest(
        self,
        path: Path,
        document_format: DocumentFormat,
        book_id: str,
        revision: int,
        fallback_title: str,
        index: IndexRecord,
        store: ChunkStore,
    ) -> ProcessedDocument:
        """Process a document and store its vectors under the given revision.

        Args:
            path: the document.
            document_format: its validated format.
            book_id: the book it belongs to.
            revision: the revision to store it as.
            fallback_title: the title to use when the document doesn't state one.
            index: the index it goes into.
            store: that index's chunks.

        Raises:
            BookRagError: a stage failed. Vectors and files of this revision may be left
                behind for the caller to remove.
        """
        processed = self._pipeline.process(path, document_format, book_id, fallback_title)
        self._processed.save(book_id, revision, processed)

        self._release_gpu()
        chunks = processed.chunks
        vectors = self._embedder.embed_documents([chunk.text for chunk in chunks])
        store.add(chunks, vectors, revision, index.embedding_model, index.version)

        stored = store.count_revision(book_id, revision)
        if stored != len(chunks):
            raise IndexingError(f"{book_id} has {stored} stored vectors for {len(chunks)} chunks.")
        log_event(logger, "book indexed", chunks=len(chunks), embedding_model=index.embedding_model)
        return processed

    def _release_gpu(self) -> None:
        """Bulk embedding gets the GPU to itself: the LLM would otherwise stay loaded next to it."""
        if self._settings.embedding.document_device == "gpu":
            self._runtime.unload(self._settings.llm.model)
