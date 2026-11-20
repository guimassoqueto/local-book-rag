"""From a document on disk to chunks ready for embedding. No model generates anything here."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from app.errors import EmptyDocumentError, UnsupportedLanguageError
from app.ingestion.base import BlockKind, DocumentFormat, DocumentLoader, ExtractedDocument
from app.ingestion.chunker import Chunk, Chunker
from app.ingestion.language import detect_language, normalize_language
from app.ingestion.normalizer import Normalizer
from app.ingestion.structure_extractor import BookStructure, book_blocks, build_structure
from app.utils.progress import Progress

# The stages this pipeline reports, which an operation declares (app/services/ingestion_service.py).
EXTRACT = "extract"
PREPARE = "prepare"


@dataclass(frozen=True)
class ProcessedDocument:
    """Every stage's output: the earlier ones are kept for debugging and reprocessing."""

    extracted: ExtractedDocument
    normalized: ExtractedDocument
    structure: BookStructure
    chunks: tuple[Chunk, ...]
    title: str
    language: str


class IngestionPipeline:
    def __init__(
        self,
        loaders: Mapping[DocumentFormat, DocumentLoader],
        normalizer: Normalizer,
        chunker: Chunker,
        supported_languages: tuple[str, ...],
    ) -> None:
        self._loaders = loaders
        self._normalizer = normalizer
        self._chunker = chunker
        self._supported_languages = supported_languages

    def process(
        self,
        path: Path,
        document_format: DocumentFormat,
        book_id: str,
        title: str,
        progress: Progress | None = None,
    ) -> ProcessedDocument:
        """Extract, normalize, structure and chunk a document.

        Args:
            path: the document.
            document_format: its validated format.
            book_id: the ID its chunks are stamped with.
            title: the book's title, which is the name of the file it arrived as, without its
                extension. Nothing in the document changes it (specs/005-markdown-only, FR-005).
            progress: told of extraction and preparation. Without one, or outside an operation,
                nothing is reported.

        Raises:
            BookRagError: the document cannot be processed. The subclass says why.
        """
        progress = progress or Progress()
        with progress.stage(EXTRACT):
            extracted = self._loaders[document_format].load(path)
        with progress.stage(PREPARE):
            normalized = self._normalizer.normalize(extracted)
            # The book's own text only: its language, chapters and chunks never come from a
            # distributor's license or a table of contents.
            book = replace(normalized, blocks=book_blocks(normalized.blocks))
            if not any(block.kind is not BlockKind.HEADING for block in book.blocks):
                raise EmptyDocumentError(f"{path.name} holds no text after cleaning.")

            language = self._language_of(book, path)
            structure = build_structure(replace(book, language=language), title)
            chunks = self._chunker.chunk(book_id, title, structure)
        return ProcessedDocument(extracted, normalized, structure, tuple(chunks), title, language)

    def _language_of(self, document: ExtractedDocument, path: Path) -> str:
        if document.language:
            language = normalize_language(document.language)
        else:
            language = detect_language(" ".join(block.text for block in document.blocks))
        if language not in self._supported_languages:
            supported = ", ".join(self._supported_languages)
            raise UnsupportedLanguageError(
                f"{path.name} is in '{language}'. Supported languages are {supported} (languages.supported)."
            )
        return language
