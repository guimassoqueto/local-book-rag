"""Decides what an uploaded file really is, without trusting its name."""

import zipfile
from pathlib import Path

from app.errors import InvalidDocumentError
from app.ingestion.base import DocumentFormat

_FORMATS_BY_EXTENSION = {
    ".pdf": DocumentFormat.PDF,
    ".epub": DocumentFormat.EPUB,
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
}
_PDF_SIGNATURE = b"%PDF-"
_PDF_SIGNATURE_WINDOW = 1024  # readers tolerate junk before the signature, up to about this far
_EPUB_MIMETYPE = b"application/epub+zip"
_MAX_EPUB_EXPANSION = 20  # how much larger than its upload limit an unzipped EPUB may get


def safe_filename(filename: str) -> str:
    """Reduce an uploaded name to a bare file name: it is only ever recorded, never used as a path."""
    name = Path(filename.replace("\\", "/")).name
    name = "".join(character for character in name if character.isprintable()).strip()
    return name if name not in ("", ".", "..") else "unnamed"


def validate_upload(path: Path, filename: str, max_bytes: int) -> DocumentFormat:
    """Check an upload's size and that its content matches its extension.

    Args:
        path: where the upload is on disk.
        filename: the name it arrived with.
        max_bytes: the upload size limit.

    Returns:
        The document's format.

    Raises:
        InvalidDocumentError: the file is too large, has an unsupported extension, or
            is not what its extension claims.
    """
    extension = Path(safe_filename(filename)).suffix.lower()
    document_format = _FORMATS_BY_EXTENSION.get(extension)
    if document_format is None:
        supported = ", ".join(sorted(_FORMATS_BY_EXTENSION))
        raise InvalidDocumentError(f"Unsupported file type '{extension}'. Supported types: {supported}.")

    size = path.stat().st_size
    if size == 0:
        raise InvalidDocumentError("The file is empty.")
    if size > max_bytes:
        raise InvalidDocumentError(f"The file is {size // 2**20} MB, over the {max_bytes // 2**20} MB upload limit.")

    match document_format:
        case DocumentFormat.PDF:
            _require_pdf(path)
        case DocumentFormat.EPUB:
            _require_epub(path, max_bytes * _MAX_EPUB_EXPANSION)
        case DocumentFormat.MARKDOWN:
            _require_text(path)
    return document_format


def _require_pdf(path: Path) -> None:
    with path.open("rb") as file:
        if _PDF_SIGNATURE not in file.read(_PDF_SIGNATURE_WINDOW):
            raise InvalidDocumentError("The file has a .pdf extension but is not a PDF.")


def _require_epub(path: Path, max_unzipped_bytes: int) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.read("mimetype").strip() != _EPUB_MIMETYPE:
                raise InvalidDocumentError("The file has an .epub extension but is not an EPUB.")
            if sum(entry.file_size for entry in archive.infolist()) > max_unzipped_bytes:
                raise InvalidDocumentError("The EPUB expands to too much data.")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise InvalidDocumentError("The file has an .epub extension but is not an EPUB.") from exc


def _require_text(path: Path) -> None:
    content = path.read_bytes()
    if b"\0" in content:
        raise InvalidDocumentError("The file has a Markdown extension but holds binary data.")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidDocumentError("Markdown files must be UTF-8.") from exc
