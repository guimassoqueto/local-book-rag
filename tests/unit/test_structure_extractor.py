from app.ingestion.base import Block, BlockKind, DocumentFormat, ExtractedDocument
from app.ingestion.structure_extractor import FRONT_MATTER_TITLE, build_structure


def heading(text, level):
    return Block(BlockKind.HEADING, text, level=level)


def text(content="Some text."):
    return Block(BlockKind.PARAGRAPH, content)


def structure_of(*blocks, title=None):
    return build_structure(ExtractedDocument(DocumentFormat.MARKDOWN, tuple(blocks), title=title))


def outline(structure):
    return [(chapter.number, chapter.title) for chapter in structure.chapters]


def test_top_headings_are_chapters():
    structure = structure_of(heading("One", 1), text(), heading("Two", 1), text())

    assert outline(structure) == [(1, "One"), (2, "Two")]


def test_a_single_top_heading_is_the_title_so_the_next_level_holds_the_chapters():
    structure = structure_of(heading("The Book", 1), heading("One", 2), text(), heading("Two", 2), text())

    assert outline(structure) == [(1, "One"), (2, "Two")]


def test_subheadings_are_sections():
    structure = structure_of(
        heading("One", 1), text("Intro."), heading("Sub", 2), text("Body."), heading("Two", 1), text()
    )

    sections = structure.chapters[0].sections
    assert [section.title for section in sections] == [None, "Sub"]
    assert sections[1].blocks[-1].text == "Body."


def test_text_before_the_first_chapter_is_front_matter():
    structure = structure_of(text("Dedication."), heading("One", 1), text(), heading("Two", 1), text())

    assert outline(structure) == [(0, FRONT_MATTER_TITLE), (1, "One"), (2, "Two")]


def test_a_book_without_headings_is_one_chapter():
    structure = structure_of(text(), text(), title="The Title")

    assert outline(structure) == [(1, "The Title")]


def test_parts_do_not_count_as_chapters():
    structure = structure_of(
        heading("Part I", 1),
        heading("One", 2),
        text(),
        heading("Two", 2),
        text(),
        heading("Part II", 1),
        heading("Three", 2),
        text(),
    )

    assert outline(structure) == [(1, "One"), (2, "Two"), (3, "Three")]


def test_chapters_can_sit_next_to_parts():
    structure = structure_of(
        heading("Preface", 1),
        text(),
        heading("Part I", 1),
        heading("One", 2),
        text(),
        heading("Conclusion", 1),
        text(),
    )

    assert outline(structure) == [(1, "Preface"), (2, "One"), (3, "Conclusion")]


def test_a_part_with_an_introduction_keeps_it():
    structure = structure_of(
        heading("Parte I", 1),
        text("Why this part."),
        heading("One", 2),
        text(),
        heading("Parte II", 1),
        heading("Two", 2),
        text(),
    )

    assert outline(structure) == [(1, "Parte I"), (2, "One"), (3, "Two")]


def test_a_chapter_called_part_of_something_is_still_a_chapter():
    structure = structure_of(heading("Part of the Problem", 1), text(), heading("Next", 1), text())

    assert outline(structure) == [(1, "Part of the Problem"), (2, "Next")]


def test_sections_of_a_chapter_inside_a_part_stay_in_it():
    structure = structure_of(heading("Part I", 1), heading("One", 2), text(), heading("Sub", 3), text())

    assert outline(structure) == [(1, "One")]
    assert [section.title for section in structure.chapters[0].sections] == [None, "Sub"]


def test_numbered_chapters_outrank_their_depth():
    chapters = [
        block for number in ("I", "II", "III", "IV", "V") for block in (heading(f"CAPITULO {number}", 3), text())
    ]

    structure = structure_of(heading("The Novel", 1), heading("The Novel", 2), *chapters, heading("License", 2), text())

    assert outline(structure) == [
        (1, "CAPITULO I"),
        (2, "CAPITULO II"),
        (3, "CAPITULO III"),
        (4, "CAPITULO IV"),
        (5, "CAPITULO V"),
        (6, "License"),
    ]


def test_a_printed_chapter_label_does_not_turn_sections_into_chapters():
    structure = structure_of(
        heading("The way of the program", 1),
        heading("Chapter 1", 4),
        text(),
        heading("What is a program?", 2),
        text(),
        heading("Variables", 1),
        heading("Chapter 2", 4),
        text(),
        heading("Assignment", 2),
        text(),
    )

    assert outline(structure) == [(1, "The way of the program"), (2, "Variables")]


def test_a_section_about_a_chapter_is_not_a_chapter():
    structure = structure_of(
        heading("One", 1),
        text(),
        heading("Chapter summary", 3),
        text(),
        heading("Two", 1),
        text(),
        heading("Chapter summary", 3),
        text(),
    )

    assert outline(structure) == [(1, "One"), (2, "Two")]


def test_one_numbered_heading_proves_nothing():
    structure = structure_of(heading("One", 1), text(), heading("Chapter 5", 2), text(), heading("Two", 1), text())

    assert outline(structure) == [(1, "One"), (2, "Two")]


def test_headings_without_text_are_dropped():
    structure = structure_of(heading("Empty", 1), heading("Full", 1), text())

    assert outline(structure) == [(1, "Full")]


def test_metadata_is_carried_over():
    document = ExtractedDocument(DocumentFormat.EPUB, (heading("One", 1), text()), title="T", author="A", language="pt")

    structure = build_structure(document)

    assert (structure.title, structure.author, structure.language) == ("T", "A", "pt")
