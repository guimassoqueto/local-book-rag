import zipfile

import pytest

from app.errors import InvalidDocumentError
from app.ingestion.base import DocumentFormat
from app.ingestion.validation import safe_filename, validate_upload
from tests.documents import write_epub, write_pdf

MEGABYTE = 2**20


def write(path, content: bytes):
    path.write_bytes(content)
    return path


def test_accepts_each_supported_format(tmp_path):
    pdf = write_pdf(tmp_path / "book.pdf", [[("Some text.", 11)]])
    book = write_epub(tmp_path / "book.epub", [("c.xhtml", "One", "<p>Text.</p>")])
    markdown = write(tmp_path / "book.md", "# Title\n\nText, with accents: ção.".encode())

    assert validate_upload(pdf, "book.pdf", MEGABYTE) is DocumentFormat.PDF
    assert validate_upload(book, "book.epub", MEGABYTE) is DocumentFormat.EPUB
    assert validate_upload(markdown, "book.md", MEGABYTE) is DocumentFormat.MARKDOWN


def test_extension_case_does_not_matter(tmp_path):
    path = write(tmp_path / "upload", b"%PDF-1.7 content")

    assert validate_upload(path, "BOOK.PDF", MEGABYTE) is DocumentFormat.PDF


@pytest.mark.parametrize("name", ["book.docx", "book", "book.txt", "book.pdf.exe"])
def test_rejects_unsupported_extensions(tmp_path, name):
    path = write(tmp_path / "upload", b"%PDF-1.7")

    with pytest.raises(InvalidDocumentError, match="Unsupported file type"):
        validate_upload(path, name, MEGABYTE)


def test_rejects_a_pdf_that_is_not_one(tmp_path):
    path = write(tmp_path / "upload", b"plain text pretending")

    with pytest.raises(InvalidDocumentError, match="not a PDF"):
        validate_upload(path, "book.pdf", MEGABYTE)


def test_rejects_an_epub_that_is_not_one(tmp_path):
    pdf = write_pdf(tmp_path / "real.pdf", [[("Text.", 11)]])

    with pytest.raises(InvalidDocumentError, match="not an EPUB"):
        validate_upload(pdf, "book.epub", MEGABYTE)


def test_rejects_a_zip_that_is_not_an_epub(tmp_path):
    path = tmp_path / "upload.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/zip")

    with pytest.raises(InvalidDocumentError, match="not an EPUB"):
        validate_upload(path, "book.epub", MEGABYTE)


def test_rejects_an_epub_that_expands_too_far(tmp_path):
    path = tmp_path / "bomb.epub"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("big.bin", b"\0" * (25 * 1024))

    with pytest.raises(InvalidDocumentError, match="expands"):
        validate_upload(path, "book.epub", max_bytes=1024)


def test_rejects_binary_markdown(tmp_path):
    path = write(tmp_path / "upload", b"# Title\0binary")

    with pytest.raises(InvalidDocumentError, match="binary"):
        validate_upload(path, "book.md", MEGABYTE)


def test_rejects_markdown_that_is_not_utf8(tmp_path):
    path = write(tmp_path / "upload", "ação".encode("latin-1"))

    with pytest.raises(InvalidDocumentError, match="UTF-8"):
        validate_upload(path, "book.md", MEGABYTE)


def test_rejects_empty_files(tmp_path):
    path = write(tmp_path / "upload", b"")

    with pytest.raises(InvalidDocumentError, match="empty"):
        validate_upload(path, "book.pdf", MEGABYTE)


def test_rejects_files_over_the_limit(tmp_path):
    path = write(tmp_path / "upload", b"%PDF-" + b"x" * MEGABYTE)

    with pytest.raises(InvalidDocumentError, match="upload limit"):
        validate_upload(path, "book.pdf", MEGABYTE)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("/absolute/path/book.pdf", "book.pdf"),
        ("..\\..\\windows\\book.pdf", "book.pdf"),
        ("book\x00name.pdf", "bookname.pdf"),
        ("..", "unnamed"),
    ],
)
def test_uploaded_names_lose_their_paths(name, expected):
    assert safe_filename(name) == expected
