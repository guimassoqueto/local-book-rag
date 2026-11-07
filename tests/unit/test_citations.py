import pytest

from app.generation.citations import citation_for, cited_numbers, normalize_citations, resolve_citations
from tests.fakes import make_chunk


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A claim [1].", [1]),
        ("Two claims [1] and [2].", [1, 2]),
        ("Adjacent [1][3].", [1, 3]),
        ("A list [1, 2].", [1, 2]),
        ("A semicolon list [1; 2].", [1, 2]),
        ("A range [2-4].", [2, 3, 4]),
        ("An en dash [2–4].", [2, 3, 4]),
        ("Repeated [2] and [2].", [2]),
        ("Order of appearance [3] then [1].", [3, 1]),
        ("No citation here.", []),
        ("Not a citation [see above].", []),
    ],
)
def test_finding_citations(text, expected):
    assert cited_numbers(text) == expected


def test_a_python_list_in_inline_code_is_not_a_citation():
    assert cited_numbers("Created with brackets, e.g. `t = [1, 2, 3]`, as shown [4].") == [4]


def test_a_python_list_in_a_code_block_is_not_a_citation():
    assert cited_numbers("Like this:\n```python\nt = [1, 2, 3]\n```\nAs shown [4].") == [4]


def test_an_absurd_range_is_not_expanded():
    assert len(cited_numbers("A typo [1-99999].")) == 2


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A claim【3】.", "A claim[3]."),
        ("A claim【3†L1-L4】.", "A claim[3]."),
        ("A claim［3］.", "A claim[3]."),
        ("A claim〔3〕.", "A claim[3]."),
        ("Two【1, 2】.", "Two[1, 2]."),
        ("Unchanged [3].", "Unchanged [3]."),
    ],
)
def test_each_models_way_of_citing_is_normalized(text, expected):
    assert normalize_citations(text) == expected


def test_citations_point_at_the_numbered_sources():
    sources = [make_chunk("First.", index=0), make_chunk("Second.", index=1)]

    valid, invented = resolve_citations("Claim [2].", sources)

    assert [citation.number for citation in valid] == [2]
    assert valid[0].chunk_id == sources[1].chunk_id
    assert invented == []


def test_numbers_that_match_no_source_are_reported():
    valid, invented = resolve_citations("Claim [1], and another [7], and [0].", [make_chunk()])

    assert [citation.number for citation in valid] == [1]
    assert invented == [7, 0]


def test_a_reference_names_everything_that_exists():
    chunk = make_chunk(section="Economic Decisions", page_start=85, page_end=87)

    assert citation_for(1, chunk).reference == "Title, Chapter 1, Economic Decisions, pp. 85-87"


def test_a_reference_skips_what_a_format_lacks():
    assert citation_for(1, make_chunk(section=None)).reference == "Title, Chapter 1"


def test_a_single_page_reads_naturally():
    assert citation_for(1, make_chunk(page_start=85)).pages == "p. 85"


def test_the_excerpt_opens_the_passage():
    citation = citation_for(1, make_chunk("Word " * 100))

    assert citation.excerpt.startswith("Word Word")
    assert citation.excerpt.endswith("…")
    assert len(citation.excerpt) < 90


def test_a_short_passage_is_its_own_excerpt():
    assert citation_for(1, make_chunk("Short.")).excerpt == "Short."
