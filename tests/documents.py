"""Builds real documents for the tests, so that the parsers run on real files."""

import textwrap
from pathlib import Path

import pymupdf
from ebooklib import epub

LINE_WIDTH = 85
BODY_SIZE = 11


def write_pdf(path: Path, pages: list[list[tuple[str, float]]], toc: list[list] | None = None, **metadata: str) -> Path:
    """Write a PDF.

    Args:
        path: where to write it.
        pages: for each page, its paragraphs as (text, font size). Size 0 marks a bold paragraph.
        toc: table of contents entries, as [level, title, page].
        **metadata: title and author.
    """
    document = pymupdf.open()
    for paragraphs in pages:
        page = document.new_page()
        y = 100.0
        for text, size in paragraphs:
            font = "hebo" if size == 0 else "helv"
            size = size or BODY_SIZE
            for line in textwrap.wrap(text, LINE_WIDTH) or [""]:
                page.insert_text((72, y), line, fontsize=size, fontname=font)
                y += size * 1.3
            y += size * 1.5
    if toc:
        document.set_toc(toc)
    if metadata:
        document.set_metadata(metadata)
    document.save(path)
    document.close()
    return path


def add_page_furniture(path: Path, header: str | None, page_numbers: bool) -> None:
    """Stamp a running header and page numbers on every page."""
    document = pymupdf.open(path)
    for index, page in enumerate(document):
        if header:
            page.insert_text((72, 40), header, fontsize=9, fontname="helv")
        if page_numbers:
            page.insert_text((280, page.rect.height - 25), str(index + 1), fontsize=9, fontname="helv")
    document.saveIncr()
    document.close()


def write_image_pdf(path: Path, pages: int) -> Path:
    """Write a PDF whose pages are pictures, like a scanned book."""
    document = pymupdf.open()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200), False)
    pixmap.set_rect(pixmap.irect, (200, 200, 200))
    for _ in range(pages):
        document.new_page().insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pixmap)
    document.save(path)
    document.close()
    return path


def write_table_pdf(path: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 80), "Text above the table, which is long enough to count as a real paragraph.", fontsize=11)
    left, top, cell_width, cell_height = 72, 120, 120, 30
    rows = [("Country", "Capital"), ("Brazil", "Brasilia"), ("Portugal", "Lisbon")]
    for row, cells in enumerate(rows):
        for column, text in enumerate(cells):
            x = left + column * cell_width
            y = top + row * cell_height
            page.draw_rect(pymupdf.Rect(x, y, x + cell_width, y + cell_height), color=(0, 0, 0))
            page.insert_text((x + 6, y + 20), text, fontsize=11)
    document.save(path)
    document.close()
    return path


def write_encrypted_pdf(path: Path) -> Path:
    document = pymupdf.open()
    document.new_page().insert_text((72, 100), "Secret text.", fontsize=11)
    document.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    document.close()
    return path


def write_epub(
    path: Path,
    chapters: list[tuple[str, str, str]],
    toc: tuple | list | None = None,
    title: str = "An EPUB Book",
    author: str = "An Author",
    language: str = "en",
) -> Path:
    """Write an EPUB.

    Args:
        path: where to write it.
        chapters: for each spine document, (file name, title, body HTML).
        toc: the table of contents. None links every document, and () leaves it empty.
        title: the book's title.
        author: the book's author.
        language: the book's language.
    """
    book = epub.EpubBook()
    book.set_identifier("test-book")
    book.set_title(title)
    book.set_language(language)
    book.add_author(author)

    items = []
    for file_name, chapter_title, body in chapters:
        item = epub.EpubHtml(title=chapter_title, file_name=file_name, lang=language)
        item.content = f"<html><body>{body}</body></html>"
        book.add_item(item)
        items.append(item)

    book.toc = [epub.Link(i.file_name, i.title, i.file_name) for i in items] if toc is None else toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = items
    epub.write_epub(str(path), book)
    return path
