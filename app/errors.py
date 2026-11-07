"""Failures the application reports to the user, whichever interface started the work."""


class BookRagError(Exception):
    """Base class. The message is shown to the user as it is."""


class ConfigurationError(BookRagError):
    """A configuration file is missing, malformed or inconsistent."""


class ServiceUnavailableError(BookRagError):
    """Ollama or ChromaDB cannot be reached."""


class ModelNotFoundError(BookRagError):
    """A configured model is not on the Ollama server."""


class InvalidDocumentError(BookRagError):
    """An upload is not a readable PDF, EPUB or Markdown file."""


class EmptyDocumentError(BookRagError):
    """A document was read successfully, but it holds no text."""


class ScannedDocumentError(BookRagError):
    """A PDF has page images instead of text, and OCR is not enabled."""


class UnsupportedLanguageError(BookRagError):
    """A document's language is not in the supported list."""


class DuplicateBookError(BookRagError):
    """The same file is already in the library."""

    def __init__(self, book_id: str, title: str) -> None:
        super().__init__(f"This file is already in the library as {book_id} ('{title}').")
        self.book_id = book_id


class BookNotFoundError(BookRagError):
    """No book in the catalog has the given ID."""


class EmbeddingDimensionError(BookRagError):
    """A model produced vectors of a size other than the configured or indexed one."""


class ReindexRequiredError(BookRagError):
    """The embedding or chunking configuration no longer matches the index."""


class IndexingError(BookRagError):
    """Vectors could not be stored, or the stored ones failed verification."""


class NothingToSearchError(BookRagError):
    """No indexed book matches what a search asked for."""
