"""Decides whether an uploaded file is a book the library reads: Markdown, and nothing else."""

from pathlib import Path

from app.errors import InvalidDocumentError
from app.ingestion.base import DocumentFormat

_FORMATS_BY_EXTENSION = {
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
}
# Books are converted to Markdown outside the application (specs/005-markdown-only), so the two
# formats it used to read are refused with the way forward rather than as unknown types.
_CONVERT_FIRST = {".pdf": "a PDF", ".epub": "an EPUB"}


def safe_filename(filename: str) -> str:
    """Reduce an uploaded name to a bare file name: it is only ever recorded, never used as a path."""
    name = Path(filename.replace("\\", "/")).name
    name = "".join(character for character in name if character.isprintable()).strip()
    return name if name not in ("", ".", "..") else "unnamed"


def validate_upload(path: Path, filename: str, max_bytes: int) -> DocumentFormat:
    """Check that an upload is a Markdown file the library can read.

    Args:
        path: where the upload is on disk.
        filename: the name it arrived with.
        max_bytes: the upload size limit.

    Returns:
        The document's format.

    Raises:
        InvalidDocumentError: the file isn't Markdown (a PDF or an EPUB is told to convert it
            first), or is missing, empty, too large, binary or not UTF-8.
    """
    extension = Path(safe_filename(filename)).suffix.lower()
    if extension in _CONVERT_FIRST:
        raise InvalidDocumentError(
            f"This is {_CONVERT_FIRST[extension]}. Books are Markdown files: convert it to Markdown first, "
            "with MarkItDown for example, and add the .md file."
        )
    document_format = _FORMATS_BY_EXTENSION.get(extension)
    if document_format is None:
        accepted = ", ".join(sorted(_FORMATS_BY_EXTENSION))
        raise InvalidDocumentError(f"Unsupported file type '{extension}'. Books are Markdown files: {accepted}.")

    if not path.is_file():  # a path typed at the command line, never an upload
        raise InvalidDocumentError(f"The file {safe_filename(filename)} doesn't exist.")
    size = path.stat().st_size
    if size == 0:
        raise InvalidDocumentError("The file is empty.")
    if size > max_bytes:
        raise InvalidDocumentError(f"The file is {size // 2**20} MB, over the {max_bytes // 2**20} MB upload limit.")

    _require_text(path)
    return document_format


def _require_text(path: Path) -> None:
    content = path.read_bytes()
    if b"\0" in content:
        raise InvalidDocumentError("The file has a Markdown extension but holds binary data.")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidDocumentError("Markdown files must be UTF-8.") from exc
