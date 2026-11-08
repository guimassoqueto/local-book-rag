"""From a document on disk to chunks ready for embedding. No model generates anything here."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from app.errors import EmptyDocumentError, UnsupportedLanguageError
from app.ingestion.base import BlockKind, DocumentFormat, DocumentLoader, ExtractedDocument
from app.ingestion.chunker import Chunk, Chunker
from app.ingestion.language import detect_language, normalize_language
from app.ingestion.normalizer import Normalizer
from app.ingestion.structure_extractor import BookStructure, build_structure


@dataclass(frozen=True)
class ProcessedDocument:
    """Every stage's output: the earlier ones are kept for debugging and reprocessing."""

    extracted: ExtractedDocument
    normalized: ExtractedDocument
    structure: BookStructure
    chunks: tuple[Chunk, ...]
    title: str
    author: str | None
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
        self, path: Path, document_format: DocumentFormat, book_id: str, fallback_title: str
    ) -> ProcessedDocument:
        """Extract, normalize, structure and chunk a document.

        Args:
            path: the document.
            document_format: its validated format.
            book_id: the ID its chunks are stamped with.
            fallback_title: the title to use when the document doesn't state one.

        Raises:
            BookRagError: the document cannot be processed. The subclass says why.
        """
        extracted = self._loaders[document_format].load(path)
        normalized = self._normalizer.normalize(extracted)
        if not any(block.kind is not BlockKind.HEADING for block in normalized.blocks):
            raise EmptyDocumentError(f"{path.name} holds no text after cleaning.")

        language = self._language_of(normalized, path)
        title = normalized.title or fallback_title
        structure = build_structure(replace(normalized, title=title, language=language))
        chunks = self._chunker.chunk(book_id, title, structure)
        return ProcessedDocument(extracted, normalized, structure, tuple(chunks), title, normalized.author, language)

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
