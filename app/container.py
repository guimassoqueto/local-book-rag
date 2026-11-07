"""Composition root: the one place that builds the application's object graph."""

from dataclasses import dataclass

from app.config.loader import load_settings
from app.config.settings import EnvironmentSettings, Settings
from app.ingestion.base import DocumentFormat, DocumentLoader
from app.ingestion.chunker import Chunker
from app.ingestion.docling_loader import DoclingLoader
from app.ingestion.epub_loader import EpubLoader
from app.ingestion.markdown_loader import MarkdownLoader
from app.ingestion.normalizer import Normalizer
from app.ingestion.pdf_loader import PdfLoader
from app.ingestion.pipeline import IngestionPipeline
from app.services.book_service import BookService
from app.services.health_service import HealthService
from app.storage.catalog import BookCatalog
from app.storage.chroma import ChromaServer
from app.storage.repositories import OriginalDocuments, ProcessedDocuments
from app.utils.logging import configure_logging
from app.utils.ollama_runtime import OllamaRuntime
from app.utils.tokenization import create_token_counter


@dataclass(frozen=True)
class Container:
    settings: Settings
    environment: EnvironmentSettings
    runtime: OllamaRuntime
    health: HealthService
    books: BookService


def build_container(console_logs: bool = False) -> Container:
    """Validate the configuration and wire the application together.

    Args:
        console_logs: also log to stdout, for a long-running server.
    """
    environment = EnvironmentSettings()
    settings = load_settings(environment.config_dir)
    configure_logging(
        environment.log_level, settings.logging.inference_level, environment.logs_dir, console=console_logs
    )

    runtime = OllamaRuntime(environment.ollama_base_url, settings.ollama.request_timeout_seconds)
    chroma = ChromaServer(environment.chroma_host, environment.chroma_port)
    data = environment.data_dir
    books = BookService(
        catalog=BookCatalog(data / "metadata" / "catalog.db"),
        originals=OriginalDocuments(data / "original_books"),
        processed=ProcessedDocuments(data / "processed"),
        pipeline=build_pipeline(settings),
        max_upload_bytes=settings.uploads.max_size_mb * 2**20,
    )
    return Container(
        settings=settings,
        environment=environment,
        runtime=runtime,
        health=HealthService(settings, runtime, chroma),
        books=books,
    )


def build_pipeline(settings: Settings) -> IngestionPipeline:
    """Build the ingestion pipeline the configuration describes."""
    counter = create_token_counter(settings.embedding_profile.tokenizer)
    return IngestionPipeline(
        loaders=_build_loaders(settings),
        normalizer=Normalizer(settings.normalization),
        chunker=Chunker(settings.chunking, counter),
        supported_languages=settings.languages.supported,
    )


def _build_loaders(settings: Settings) -> dict[DocumentFormat, DocumentLoader]:
    pdf = settings.pdf
    if pdf.extractor == "docling":
        pdf_loader: DocumentLoader = DoclingLoader(ocr=pdf.ocr.enabled)
    else:
        pdf_loader = PdfLoader(pdf, ocr_loader=DoclingLoader(ocr=True) if pdf.ocr.enabled else None)
    return {
        DocumentFormat.PDF: pdf_loader,
        DocumentFormat.EPUB: EpubLoader(),
        DocumentFormat.MARKDOWN: MarkdownLoader(),
    }
