import pymupdf

from app.container import build_pipeline
from app.evaluation.extraction_metrics import extraction_scores, toc_titles
from app.ingestion.base import DocumentFormat
from app.ingestion.chunker import Chunker
from tests.documents import write_epub, write_pdf
from tests.fakes import WordCounter

TEXT = "The quick brown fox jumps over the lazy dog, and then it goes back to the forest to rest for the day."


def process(settings, path, document_format):
    pipeline = build_pipeline(settings)
    pipeline._chunker = Chunker(settings.chunking, WordCounter())
    return pipeline.process(path, document_format, "book", "fallback")


def test_a_pdf_keeping_its_structure_scores_full_coverage(settings, tmp_path):
    pages = [[("Chapter One", 11), (TEXT, 11)], [("Chapter Two", 11), (TEXT, 11)], []]
    path = write_pdf(tmp_path / "b.pdf", pages, toc=[[1, "Chapter One", 1], [1, "Chapter Two", 2]])

    scores = extraction_scores(path, process(settings, path, DocumentFormat.PDF))

    assert scores.toc_entries == 2
    assert scores.toc_coverage == 1.0
    assert scores.chapters == 2
    assert scores.pages_covered == 2 / 3


def test_a_heading_printing_its_number_matches_an_outline_without_it(settings, tmp_path):
    pages = [[("1.1 Chapter One", 11), (TEXT, 11)], [("Chapter Two", 11), (TEXT, 11)]]
    path = write_pdf(tmp_path / "b.pdf", pages, toc=[[1, "1.1 Chapter One", 1], [1, "2 Chapter Two", 2]])
    processed = process(settings, path, DocumentFormat.PDF)
    with pymupdf.open(path) as document:
        document.set_toc([[1, "Chapter One", 1], [1, "Chapter Two", 2]])
        document.saveIncr()

    assert extraction_scores(path, processed).toc_coverage == 1.0


def test_a_lost_entry_lowers_the_coverage(settings, tmp_path):
    pages = [[("Chapter One", 11), (TEXT, 11)], [("Chapter Two", 11), (TEXT, 11)]]
    path = write_pdf(tmp_path / "b.pdf", pages, toc=[[1, "Chapter One", 1], [1, "Chapter Two", 2]])
    processed = process(settings, path, DocumentFormat.PDF)
    with pymupdf.open(path) as document:
        document.set_toc([[1, "Chapter One", 1], [1, "Chapter Two", 2], [1, "Never Extracted", 2]])
        document.saveIncr()

    assert extraction_scores(path, processed).toc_coverage == 2 / 3


def test_a_lost_heading_counts_even_when_its_title_survives_elsewhere(settings, tmp_path):
    pages = [[("Exercises", 11), (TEXT, 11)], [("Exercises", 11), (TEXT, 11)]]
    path = write_pdf(tmp_path / "b.pdf", pages, toc=[[1, "Exercises", 1], [1, "Exercises", 2]])
    processed = process(settings, path, DocumentFormat.PDF)
    with pymupdf.open(path) as document:
        document.set_toc([[1, "Exercises", 1], [1, "Exercises", 2], [1, "Exercises", 2]])
        document.saveIncr()

    assert extraction_scores(path, processed).toc_coverage == 2 / 3


def test_epubs_are_read_from_their_own_table_of_contents(settings, tmp_path):
    path = write_epub(tmp_path / "b.epub", [("a.xhtml", "One", f"<p>{TEXT}</p>"), ("b.xhtml", "Two", f"<p>{TEXT}</p>")])

    scores = extraction_scores(path, process(settings, path, DocumentFormat.EPUB))

    assert toc_titles(path) == ["One", "Two"]
    assert scores.toc_coverage == 1.0
    assert scores.pages_covered is None


def test_a_format_without_a_table_of_contents_has_no_coverage(settings, tmp_path):
    path = tmp_path / "b.md"
    path.write_text(f"# One\n\n{TEXT}\n\n# Two\n\n{TEXT}\n", encoding="utf-8")

    scores = extraction_scores(path, process(settings, path, DocumentFormat.MARKDOWN))

    assert scores.toc_coverage is None
