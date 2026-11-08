import pytest

from app.container import build_pipeline
from app.errors import EmptyDocumentError, UnsupportedLanguageError
from app.ingestion.base import DocumentFormat, ExtractedDocument
from app.ingestion.chunker import Chunker
from app.ingestion.language import detect_language, normalize_language
from app.ingestion.markdown_loader import MarkdownLoader
from app.ingestion.normalizer import Normalizer
from app.ingestion.pipeline import IngestionPipeline
from tests.fakes import WordCounter

ENGLISH = "The quick brown fox jumps over the lazy dog, and then it goes back to the forest to rest for the day."
PORTUGUESE = "O rato roeu a roupa do rei de Roma, e depois voltou para casa porque já não tinha mais nada para fazer."


@pytest.fixture
def pipeline(settings):
    return IngestionPipeline(
        loaders={DocumentFormat.MARKDOWN: MarkdownLoader()},
        normalizer=Normalizer(settings.normalization),
        chunker=Chunker(settings.chunking, WordCounter()),
        supported_languages=("en", "pt"),
    )


def process(pipeline, tmp_path, text):
    path = tmp_path / "book.md"
    path.write_text(text, encoding="utf-8")
    return pipeline.process(path, DocumentFormat.MARKDOWN, "book_001", "fallback title")


def test_a_book_goes_through_every_stage(pipeline, tmp_path):
    result = process(
        pipeline,
        tmp_path,
        f"---\ntitle: My Book\nauthor: Me\n---\n\n# One\n\n{ENGLISH}\n\n## Sub\n\n{ENGLISH}\n\n# Two\n\n{ENGLISH}\n",
    )

    assert result.title == "My Book"
    assert result.author == "Me"
    assert result.language == "en"
    assert [chapter.title for chapter in result.structure.chapters] == ["One", "Two"]
    assert {chunk.book_title for chunk in result.chunks} == {"My Book"}
    assert [chunk.section_title for chunk in result.chunks] == [None, "Sub", None]
    assert result.extracted.blocks and result.normalized.blocks


def test_a_book_without_a_title_uses_the_fallback(pipeline, tmp_path):
    result = process(pipeline, tmp_path, f"# One\n\n{ENGLISH}\n\n# Two\n\n{ENGLISH}\n")

    assert result.title == "fallback title"


def test_the_language_is_detected(pipeline, tmp_path):
    assert process(pipeline, tmp_path, f"# Um\n\n{PORTUGUESE}\n\n# Dois\n\n{PORTUGUESE}\n").language == "pt"


def test_a_declared_language_wins_and_loses_its_region(pipeline, tmp_path):
    text = f"---\nlanguage: pt-BR\n---\n\n# Um\n\n{ENGLISH}\n\n# Dois\n\n{ENGLISH}\n"

    assert process(pipeline, tmp_path, text).language == "pt"


def test_unsupported_languages_are_rejected(pipeline, tmp_path):
    german = "Der schnelle braune Fuchs springt über den faulen Hund und geht dann zurück in den Wald."

    with pytest.raises(UnsupportedLanguageError, match="'de'"):
        process(pipeline, tmp_path, f"# Eins\n\n{german}\n\n# Zwei\n\n{german}\n")


def test_a_document_with_only_headings_is_empty(pipeline, tmp_path):
    with pytest.raises(EmptyDocumentError):
        process(pipeline, tmp_path, "# One\n\n# Two\n")


def test_every_format_gets_a_loader_from_the_configuration(settings):
    pipeline = build_pipeline(settings)

    assert set(pipeline._loaders) == set(DocumentFormat)


def test_language_codes_are_reduced(tmp_path):
    assert normalize_language("pt-BR") == "pt"
    assert normalize_language("en_US") == "en"
    assert normalize_language("PT") == "pt"


def test_language_detection_is_deterministic():
    assert {detect_language(PORTUGUESE) for _ in range(5)} == {"pt"}


def test_extracted_document_is_kept_apart_from_the_normalized_one(pipeline, tmp_path):
    result = process(pipeline, tmp_path, f"# One\n\nToo   many spaces. {ENGLISH}\n\n# Two\n\n{ENGLISH}\n")

    assert isinstance(result.extracted, ExtractedDocument)
    assert result.extracted is not result.normalized
