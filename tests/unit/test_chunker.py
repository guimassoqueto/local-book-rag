import pytest

from app.config.settings import ChunkingConfig, ChunkPreservation
from app.ingestion.base import Block, BlockKind
from app.ingestion.chunker import Chunker, split_sentences
from app.ingestion.structure_extractor import BookStructure, Chapter, Section


class WordCounter:
    def count(self, text):
        return len(text.split())


def config(target_size=20, overlap=0, strategy="structural", sections=True, paragraphs=True, page_numbers=True):
    return ChunkingConfig(
        strategy=strategy,
        target_size=target_size,
        overlap=overlap,
        unit="tokens",
        preserve=ChunkPreservation(chapters=True, sections=sections, paragraphs=paragraphs, page_numbers=page_numbers),
    )


def paragraph(words, page=None):
    text = " ".join(f"w{index}" for index in range(words)) + "."
    return Block(BlockKind.PARAGRAPH, text, page_start=page, page_end=page)


def sentences(count, words=5):
    return " ".join(" ".join([f"S{i}w0", *(f"s{i}w{j}" for j in range(1, words))]) + "." for i in range(count))


def book(*chapters, language="en"):
    return BookStructure("T", "A", language, tuple(chapters))


def chapter(*sections, number=1, title="One"):
    return Chapter(number, title, tuple(sections))


def section(*blocks, title=None):
    return Section(title, tuple(blocks))


def chunk(structure, **options):
    return Chunker(config(**options), WordCounter()).chunk("book_001", "The Book", structure)


def test_metadata_is_complete_and_uniform():
    structure = book(chapter(section(paragraph(5, page=7), title="Sec"), number=4, title="Opportunity Cost"))

    [only] = chunk(structure)

    assert only.chunk_id == "book_001_chapter_04_chunk_0000"
    assert only.book_id == "book_001"
    assert only.book_title == "The Book"
    assert only.chapter_number == 4
    assert only.chapter_title == "Opportunity Cost"
    assert only.section_title == "Sec"
    assert (only.page_start, only.page_end) == (7, 7)
    assert only.chunk_index == 0
    assert only.language == "en"


def test_formats_without_pages_get_null_pages():
    [only] = chunk(book(chapter(section(paragraph(5)))))

    assert (only.page_start, only.page_end) == (None, None)


def test_page_numbers_can_be_left_out():
    [only] = chunk(book(chapter(section(paragraph(5, page=7)))), page_numbers=False)

    assert (only.page_start, only.page_end) == (None, None)


def test_small_blocks_fill_a_chunk():
    chunks = chunk(book(chapter(section(paragraph(8, 1), paragraph(8, 2), paragraph(8, 3)))))

    assert len(chunks) == 2
    assert chunks[0].text.count("\n\n") == 1
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 2)
    assert (chunks[1].page_start, chunks[1].page_end) == (3, 3)


def test_paragraphs_that_fit_are_not_split():
    chunks = chunk(book(chapter(section(paragraph(15), paragraph(15)))))

    assert [len(item.text.split()) for item in chunks] == [15, 15]


def test_chapters_never_share_a_chunk():
    structure = book(chapter(section(paragraph(3)), number=1), chapter(section(paragraph(3)), number=2, title="Two"))

    assert [item.chapter_number for item in chunk(structure)] == [1, 2]


def test_sections_never_share_a_chunk():
    structure = book(chapter(section(paragraph(3), title="A"), section(paragraph(3), title="B")))

    assert [item.section_title for item in chunk(structure)] == ["A", "B"]


def test_sections_can_be_flowed_together():
    structure = book(chapter(section(paragraph(3), title="A"), section(paragraph(3), title="B")))

    assert len(chunk(structure, sections=False)) == 1


def test_a_long_paragraph_splits_between_sentences():
    long = Block(BlockKind.PARAGRAPH, sentences(8), page_start=3, page_end=3)

    chunks = chunk(book(chapter(section(long, title="Sec"))))

    assert len(chunks) > 1
    assert all(item.text.endswith(".") for item in chunks)
    assert all(len(item.text.split()) <= 20 for item in chunks)
    assert all(item.section_title == "Sec" and item.page_start == 3 for item in chunks)
    assert "\n" not in chunks[0].text


def test_a_paragraph_that_is_one_long_sentence_splits_between_words():
    chunks = chunk(book(chapter(section(paragraph(50)))))

    assert all(len(item.text.split()) <= 20 for item in chunks)
    assert " ".join(item.text for item in chunks).split() == paragraph(50).text.split()


def test_a_single_huge_word_is_cut():
    class CharacterCounter:
        def count(self, text):
            return len(text) // 4

    block = Block(BlockKind.PARAGRAPH, "x" * 1000)
    structure = book(chapter(section(block)))

    chunks = Chunker(config(target_size=50), CharacterCounter()).chunk("book_001", "T", structure)

    assert "".join(item.text for item in chunks).replace(" ", "") == "x" * 1000
    # Token counts are not additive, so joining pieces can land a token or two over the target.
    assert all(CharacterCounter().count(item.text) <= 52 for item in chunks)


def test_chunk_ids_are_stable_and_ordered():
    structure = book(chapter(section(paragraph(15), paragraph(15), paragraph(15))))

    first = chunk(structure)
    second = chunk(structure)

    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]
    assert [item.chunk_index for item in first] == [0, 1, 2]
    assert len({item.chunk_id for item in first}) == 3


def test_overlap_repeats_the_closing_sentences():
    long = Block(BlockKind.PARAGRAPH, sentences(8))

    chunks = chunk(book(chapter(section(long))), overlap=6)

    last_sentence = split_sentences(chunks[0].text)[-1]
    assert chunks[1].text.startswith(last_sentence)


def test_overlap_never_crosses_a_section():
    structure = book(chapter(section(paragraph(10), title="A"), section(paragraph(10), title="B")))

    chunks = chunk(structure, overlap=5)

    assert len(chunks) == 2
    assert chunks[1].text == paragraph(10).text


def test_overlap_keeps_chunks_within_the_target():
    long = Block(BlockKind.PARAGRAPH, sentences(30))

    chunks = chunk(book(chapter(section(long))), overlap=8)

    assert all(len(item.text.split()) <= 20 for item in chunks)


def test_every_sentence_survives_chunking():
    long = Block(BlockKind.PARAGRAPH, sentences(30))

    chunks = chunk(book(chapter(section(long))), overlap=8)

    found = {sentence for item in chunks for sentence in split_sentences(item.text)}
    assert set(split_sentences(long.text)) == found


def test_a_chunk_with_only_overlap_is_never_produced():
    long = Block(BlockKind.PARAGRAPH, sentences(4))

    chunks = chunk(book(chapter(section(long))), overlap=10)

    assert split_sentences(chunks[-1].text)[-1] == split_sentences(long.text)[-1]
    assert len({item.text for item in chunks}) == len(chunks)


def test_a_heading_stays_with_what_follows_it():
    heading = Block(BlockKind.HEADING, "A Heading", level=2)

    chunks = chunk(book(chapter(section(heading, paragraph(19)))))

    assert len(chunks) == 1
    assert chunks[0].text.startswith("A Heading\n\n")


def test_tables_split_between_rows_and_repeat_their_header():
    rows = "\n".join(f"| r{index} | a b c d e |" for index in range(10))
    table = Block(BlockKind.TABLE, f"| A | B |\n| --- | --- |\n{rows}")

    chunks = chunk(book(chapter(section(table))))

    assert len(chunks) > 1
    assert all(item.text.startswith("| A | B |\n| --- | --- |\n") for item in chunks)
    assert sum(item.text.count("| r") for item in chunks) == 10


def test_a_table_with_a_row_too_large_for_its_header_still_fits():
    row = " ".join(f"cell{index}" for index in range(30))
    table = Block(BlockKind.TABLE, f"| A | B |\n| --- | --- |\n{row}")

    chunks = chunk(book(chapter(section(table))))

    assert all(len(item.text.split()) <= 20 for item in chunks)


def test_many_tiny_blocks_count_their_separators():
    words = [Block(BlockKind.PARAGRAPH, "word") for _ in range(30)]

    chunks = chunk(book(chapter(section(*words))))

    assert all(item.text.count("word") + item.text.count("\n\n") // 2 <= 20 for item in chunks)


def test_long_code_splits_between_lines():
    code = Block(BlockKind.CODE, "\n".join(f"line {index} of the code" for index in range(10)))

    chunks = chunk(book(chapter(section(code))))

    assert len(chunks) > 1
    assert all("\n\n" not in item.text for item in chunks)
    assert chunks[0].text.startswith("line 0 of the code\nline 1 of the code")


def test_tables_and_code_are_not_overlapped():
    code = Block(BlockKind.CODE, "\n".join(f"line {index} of the code." for index in range(10)))

    chunks = chunk(book(chapter(section(code))), overlap=6)

    assert sum(item.text.count("line") for item in chunks) == 10


def test_paragraphs_can_be_split_freely():
    chunks = chunk(book(chapter(section(Block(BlockKind.PARAGRAPH, sentences(3))))), paragraphs=False, target_size=12)

    assert len(chunks) == 2


def test_the_fixed_strategy_ignores_structure_inside_a_chapter():
    structure = book(chapter(section(paragraph(12), title="A"), section(paragraph(12), title="B")))

    chunks = chunk(structure, strategy="fixed", target_size=10, overlap=2)

    assert [len(item.text.split()) for item in chunks[:-1]] == [10] * (len(chunks) - 1)
    assert chunks[1].text.split()[:2] == chunks[0].text.split()[-2:]


def test_the_fixed_strategy_still_stops_at_chapters():
    structure = book(chapter(section(paragraph(12)), number=1), chapter(section(paragraph(12)), number=2, title="Two"))

    chunks = chunk(structure, strategy="fixed", target_size=10, overlap=0)

    assert {item.chapter_number for item in chunks} == {1, 2}
    assert all(len({item.chapter_number}) == 1 for item in chunks)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("One. Two.", ["One.", "Two."]),
        ('He said "no." Then left.', ['He said "no."', "Then left."]),
        ("Dr. Smith came. He sat.", ["Dr. Smith came.", "He sat."]),
        ("O Sr. Silva saiu. Voltou.", ["O Sr. Silva saiu.", "Voltou."]),
        ("See J. R. Tolkien. Then read.", ["See J. R. Tolkien.", "Then read."]),
        ("See p. 45 and e.g. this. Next.", ["See p. 45 and e.g. this.", "Next."]),
        ("Really? Yes! Fine… Good.", ["Really?", "Yes!", "Fine…", "Good."]),
        ("It costs 3.50 today. Tomorrow more.", ["It costs 3.50 today.", "Tomorrow more."]),
        ("No terminal punctuation", ["No terminal punctuation"]),
        ("", []),
    ],
)
def test_sentence_splitting(text, expected):
    assert split_sentences(text) == expected
