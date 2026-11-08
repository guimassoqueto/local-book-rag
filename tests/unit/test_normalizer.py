from app.config.settings import NormalizationConfig
from app.ingestion.base import Block, BlockKind, DocumentFormat, ExtractedDocument
from app.ingestion.normalizer import Normalizer

ON = NormalizationConfig(remove_repeated_margins=True)


def normalize(blocks, config=ON):
    return list(Normalizer(config).normalize(ExtractedDocument(DocumentFormat.PDF, tuple(blocks))).blocks)


def paragraph(text, page=None, margin=False):
    return Block(BlockKind.PARAGRAPH, text, page_start=page, page_end=page, margin=margin)


def test_running_headers_are_removed():
    blocks = [paragraph("Economics in One Lesson", page, margin=True) for page in range(1, 5)]
    blocks.append(paragraph("Real content.", 1))

    assert [block.text for block in normalize(blocks)] == ["Real content."]


def test_running_headers_with_changing_page_numbers_are_removed():
    blocks = [paragraph(f"{page} Opportunity Cost", page, margin=True) for page in range(10, 14)]

    assert normalize(blocks) == []


def test_running_heads_unique_to_a_section_are_found_by_their_page_number():
    blocks = [
        paragraph("10.13. Debugging 99", 121, margin=True),
        paragraph("100 Chapter 10. Lists", 122, margin=True),
        paragraph("11.6. Memos 109", 131, margin=True),
        paragraph("110 Chapter 11. Dictionaries", 132, margin=True),
        paragraph("Real content.", 121),
    ]

    assert [block.text for block in normalize(blocks)] == ["Real content."]


def test_front_matter_running_heads_in_roman_numerals_are_found():
    blocks = [
        paragraph("vi Preface", 6, margin=True),
        paragraph("Acknowledgments ix", 9, margin=True),
        paragraph("x Preface", 10, margin=True),
        paragraph("Real content.", 6),
    ]

    assert [block.text for block in normalize(blocks)] == ["Real content."]


def test_a_number_that_does_not_follow_the_pages_stays():
    blocks = [
        paragraph("10.13. Debugging 99", 121, margin=True),
        paragraph("In the year 1984", 40, margin=True),
        paragraph("100 Chapter 10. Lists", 122, margin=True),
        paragraph("11.6. Memos 109", 131, margin=True),
    ]

    assert [block.text for block in normalize(blocks)] == ["In the year 1984"]


def test_bare_page_numbers_are_removed_even_when_few():
    assert normalize([paragraph("12", 12, margin=True), paragraph("xiv", 14, margin=True)]) == []


def test_text_at_the_edge_of_one_page_stays():
    blocks = [paragraph("A closing thought that happens to sit low on the page.", 3, margin=True)]

    assert len(normalize(blocks)) == 1


def test_repeated_text_away_from_the_margins_stays():
    blocks = [paragraph("A refrain.", page) for page in range(1, 6)]

    assert len(normalize(blocks)) == 5


def test_margin_removal_can_be_switched_off():
    blocks = [paragraph("Header", page, margin=True) for page in range(1, 5)]

    assert len(normalize(blocks, NormalizationConfig(remove_repeated_margins=False))) == 4


def test_whitespace_is_normalized_in_prose():
    assert normalize([paragraph("Too   many\n spaces here.")])[0].text == "Too many spaces here."


def test_code_and_tables_keep_their_lines():
    code = Block(BlockKind.CODE, "def f():\n    return 1   \n")

    assert normalize([code])[0].text == "def f():\n    return 1"


def test_ligatures_and_invisible_characters_are_cleaned():
    assert normalize([paragraph("ofﬁce ﬂow­-less​ness")])[0].text == "office flow-lessness"


def test_unicode_is_preserved_and_composed():
    decomposed = "coração"

    assert normalize([paragraph(decomposed)])[0].text == "coração"


def test_paragraphs_cut_by_a_page_break_are_rejoined():
    merged = normalize([paragraph("The argument continues on", 4), paragraph("the following page.", 5)])

    assert [(block.text, block.page_start, block.page_end) for block in merged] == [
        ("The argument continues on the following page.", 4, 5)
    ]


def test_a_word_cut_by_a_page_break_is_rejoined():
    merged = normalize([paragraph("The oppor-", 4), paragraph("tunity cost.", 5)])

    assert merged[0].text == "The opportunity cost."


def test_finished_paragraphs_are_not_merged():
    blocks = [paragraph("This one ends.", 4), paragraph("this one starts low.", 5)]

    assert len(normalize(blocks)) == 2


def test_capitalized_starts_are_not_merged():
    assert len(normalize([paragraph("No final stop", 4), paragraph("Next paragraph.", 5)])) == 2


def test_paragraphs_on_the_same_page_are_not_merged():
    assert len(normalize([paragraph("No final stop", 4), paragraph("lower start.", 4)])) == 2


def test_empty_blocks_disappear():
    assert normalize([paragraph("   ")]) == []
