"""Takes a document from a file to verified vectors in the index."""

from pathlib import Path

from app.config.settings import Settings
from app.embeddings.base import EmbeddingProvider
from app.errors import IndexingError
from app.ingestion.base import DocumentFormat
from app.ingestion.pipeline import EXTRACT, PREPARE, IngestionPipeline, ProcessedDocument
from app.storage.catalog import IndexRecord
from app.storage.chroma import ChunkStore
from app.storage.repositories import ProcessedDocuments
from app.utils.logging import get_logger, log_event
from app.utils.ollama_runtime import OllamaRuntime
from app.utils.progress import Progress, StageSpec

logger = get_logger("services.ingestion")

# The stages of indexing one book, which every operation that indexes a book declares
# (specs/004-library-progress, data-model.md).
INGEST_STEPS = (
    # Not counted: a Markdown book's text is read in a tenth of a second or less (specs/005-markdown-only, R8).
    StageSpec(EXTRACT, "Extracting the text"),
    StageSpec(PREPARE, "Preparing the chunks"),
    StageSpec("embed", "Embedding the chunks", unit="chunks", estimate=True),
    StageSpec("save", "Saving to the index"),
)


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
        title: str,
        index: IndexRecord,
        store: ChunkStore,
        progress: Progress | None = None,
    ) -> ProcessedDocument:
        """Process a document and store its vectors under the given revision.

        Args:
            path: the document.
            document_format: its validated format.
            book_id: the book it belongs to.
            revision: the revision to store it as.
            title: the book's title, the stem of the name its original arrived as.
            index: the index it goes into.
            store: that index's chunks.
            progress: told of each of INGEST_STEPS.

        Raises:
            BookRagError: a stage failed. Vectors and files of this revision may be left
                behind for the caller to remove.
        """
        progress = progress or Progress()
        processed = self._pipeline.process(path, document_format, book_id, title, progress)
        self._processed.save(book_id, revision, processed)

        self._release_gpu()
        chunks = processed.chunks
        with progress.stage("embed") as stage:
            stage.count(len(chunks))
            vectors = self._embedder.embed_documents([chunk.text for chunk in chunks], on_batch=stage.advance)
        with progress.stage("save"):
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
