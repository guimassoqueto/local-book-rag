"""Failures the application reports to the user, whichever interface started the work."""

from collections.abc import Sequence

from app.generation.base import Attempt, FailureReason


class BookRagError(Exception):
    """Base class. The message is shown to the user as it is."""


class ConfigurationError(BookRagError):
    """A configuration file is missing, malformed or inconsistent."""


class ServiceUnavailableError(BookRagError):
    """Ollama or ChromaDB cannot be reached."""


class ModelNotFoundError(BookRagError):
    """A configured model is not on the Ollama server."""


class InvalidDocumentError(BookRagError):
    """An upload is not a readable Markdown file."""


class EmptyDocumentError(BookRagError):
    """A document was read successfully, but it holds no text."""


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


class GenerationError(BookRagError):
    """The model finished without a usable answer."""


class ModelChoiceError(BookRagError):
    """A request named models that can't make a sequence. The message lists the models offered."""


class ModelFailedError(BookRagError):
    """A cloud model failed a request, so the next model of the sequence, if any, is asked.

    Its message reads "claude-sonnet-5-5 (Anthropic) failed: it limited the rate.", and never holds
    the key.

    Attributes:
        model: the model that failed.
        provider: its provider's name.
        reason: why it failed.
        detail: the provider's words, such as a refusal's category or the API's error type.
    """

    def __init__(
        self, model: str, provider: str, reason: FailureReason, detail: str = "", label: str | None = None
    ) -> None:
        super().__init__(f"{model} ({label or provider}) failed: {reason.describe(detail)}.")
        self.model = model
        self.provider = provider
        self.reason = reason
        self.detail = detail


class AllModelsFailedError(BookRagError):
    """The last model of a sequence, the local one, failed after the others did.

    Attributes:
        attempts: every failure, in order, the local model's last.
    """

    def __init__(self, attempts: Sequence[Attempt], descriptions: Sequence[str]) -> None:
        super().__init__("No model could answer. " + " ".join(descriptions))
        self.attempts = tuple(attempts)


class ChapterNotFoundError(BookRagError):
    """A book has no chapter with the given number."""


class LibraryBusyError(BookRagError):
    """Another operation is changing the library."""


class ConfirmationRequiredError(BookRagError):
    """A destructive operation was not confirmed with what it asks for."""


class MissingOriginalError(BookRagError):
    """A book's original document is no longer on disk."""


class NothingToReindexError(BookRagError):
    """The library has no documents to rebuild from."""


class BenchmarkDatasetError(BookRagError):
    """The benchmark dataset is malformed, or doesn't match its books."""


class BenchmarkJudgeError(BookRagError):
    """A benchmark's judge can't give a verdict it could be trusted on."""
