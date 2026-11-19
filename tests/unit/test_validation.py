"""What the library accepts: Markdown only, and PDF and EPUB refused with a way forward.

No test here writes a real PDF or EPUB (specs/005-markdown-only, User Story 2 scenario 3): a file
is refused by its extension before its content is read, and a PDF renamed .md is a stand-in.
"""

import pytest

from app.errors import InvalidDocumentError
from app.ingestion.base import DocumentFormat
from app.ingestion.validation import safe_filename, validate_upload

MEGABYTE = 2**20
CONVERT_PDF = (
    "This is a PDF. Books are Markdown files: convert it to Markdown first, with MarkItDown for example, "
    "and add the .md file."
)
CONVERT_EPUB = (
    "This is an EPUB. Books are Markdown files: convert it to Markdown first, with MarkItDown for example, "
    "and add the .md file."
)


def write(path, content: bytes):
    path.write_bytes(content)
    return path


@pytest.mark.parametrize("name", ["book.md", "book.markdown", "BOOK.MD", "Book.Markdown"])
def test_accepts_markdown_whatever_the_case_of_its_extension(tmp_path, name):
    path = write(tmp_path / "upload", "# Title\n\nText, with accents: ção.".encode())

    assert validate_upload(path, name, MEGABYTE) is DocumentFormat.MARKDOWN


@pytest.mark.parametrize(("name", "message"), [("book.pdf", CONVERT_PDF), ("BOOK.EPUB", CONVERT_EPUB)])
def test_a_pdf_or_an_epub_is_refused_with_the_way_forward(tmp_path, name, message):
    path = write(tmp_path / "upload", b"whatever it holds")

    with pytest.raises(InvalidDocumentError) as refused:
        validate_upload(path, name, MEGABYTE)

    assert str(refused.value) == message


def test_a_pdf_is_refused_before_its_file_is_even_looked_at(tmp_path):
    with pytest.raises(InvalidDocumentError) as refused:
        validate_upload(tmp_path / "missing.pdf", "missing.pdf", MEGABYTE)

    assert str(refused.value) == CONVERT_PDF


def test_another_type_is_refused_with_the_accepted_ones(tmp_path):
    path = write(tmp_path / "upload", b"text")

    with pytest.raises(InvalidDocumentError) as refused:
        validate_upload(path, "book.docx", MEGABYTE)

    assert str(refused.value) == "Unsupported file type '.docx'. Books are Markdown files: .markdown, .md."


@pytest.mark.parametrize("name", ["book", "book.txt", "book.md.exe", ".md"])
def test_names_without_a_markdown_extension_are_refused(tmp_path, name):
    path = write(tmp_path / "upload", b"# Title\n\nText.")

    with pytest.raises(InvalidDocumentError, match="Unsupported file type"):
        validate_upload(path, name, MEGABYTE)


def test_a_file_named_only_md_has_no_extension(tmp_path):
    """Today's message, with nothing between the quotes, accepted as it is (specs/005, tasks T013)."""
    path = write(tmp_path / "upload", b"# Title\n\nText.")

    with pytest.raises(InvalidDocumentError) as refused:
        validate_upload(path, ".md", MEGABYTE)

    assert str(refused.value).startswith("Unsupported file type ''.")


def test_a_pdf_renamed_md_is_refused_as_binary_data(tmp_path):
    path = write(tmp_path / "upload", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\0")

    with pytest.raises(InvalidDocumentError, match="binary"):
        validate_upload(path, "book.md", MEGABYTE)


def test_rejects_binary_markdown(tmp_path):
    path = write(tmp_path / "upload", b"# Title\0binary")

    with pytest.raises(InvalidDocumentError, match="binary"):
        validate_upload(path, "book.md", MEGABYTE)


def test_rejects_markdown_that_is_not_utf8(tmp_path):
    path = write(tmp_path / "upload", "ação".encode("latin-1"))

    with pytest.raises(InvalidDocumentError, match="UTF-8"):
        validate_upload(path, "book.md", MEGABYTE)


def test_rejects_a_path_with_no_file(tmp_path):
    with pytest.raises(InvalidDocumentError, match="book.md doesn't exist"):
        validate_upload(tmp_path / "book.md", "book.md", MEGABYTE)


def test_rejects_empty_files(tmp_path):
    path = write(tmp_path / "upload", b"")

    with pytest.raises(InvalidDocumentError, match="empty"):
        validate_upload(path, "book.md", MEGABYTE)


def test_rejects_files_over_the_limit(tmp_path):
    path = write(tmp_path / "upload", b"# " + b"x" * MEGABYTE)

    with pytest.raises(InvalidDocumentError, match="upload limit"):
        validate_upload(path, "book.md", MEGABYTE)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("../../etc/passwd.md", "passwd.md"),
        ("/absolute/path/book.md", "book.md"),
        ("..\\..\\windows\\book.md", "book.md"),
        ("book\x00name.md", "bookname.md"),
        ("..", "unnamed"),
    ],
)
def test_uploaded_names_lose_their_paths(name, expected):
    assert safe_filename(name) == expected
