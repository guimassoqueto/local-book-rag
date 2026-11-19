"""The cleaning that applies to any text (specs/005-markdown-only, research.md R6)."""

from app.ingestion.base import Block, BlockKind, DocumentFormat, ExtractedDocument
from app.ingestion.normalizer import Normalizer


def normalize(blocks):
    return list(Normalizer().normalize(ExtractedDocument(DocumentFormat.MARKDOWN, tuple(blocks))).blocks)


def paragraph(text):
    return Block(BlockKind.PARAGRAPH, text)


def test_whitespace_is_normalized_in_prose():
    assert normalize([paragraph("Too   many\n spaces here.")])[0].text == "Too many spaces here."


def test_code_and_tables_keep_their_lines():
    code = Block(BlockKind.CODE, "def f():\n    return 1   \n")

    assert normalize([code])[0].text == "def f():\n    return 1"


def test_ligatures_and_invisible_characters_are_cleaned():
    assert normalize([paragraph("ofﬁce ﬂow­-less​ness")])[0].text == "office flow-lessness"


def test_unicode_is_preserved_and_composed():
    decomposed = "coração"

    assert normalize([paragraph(decomposed)])[0].text == "coração"


def test_paragraphs_are_never_joined():
    blocks = [paragraph("No final stop"), paragraph("lower start."), paragraph("The oppor-"), paragraph("tunity.")]

    assert [block.text for block in normalize(blocks)] == ["No final stop", "lower start.", "The oppor-", "tunity."]


def test_repeated_text_stays():
    assert len(normalize([paragraph("A refrain.") for _ in range(5)])) == 5


def test_empty_blocks_disappear():
    assert normalize([paragraph("   ")]) == []
