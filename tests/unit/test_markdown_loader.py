import pytest

from app.errors import EmptyDocumentError
from app.ingestion.base import BlockKind, DocumentFormat
from app.ingestion.markdown_loader import MarkdownLoader


def load(tmp_path, text):
    path = tmp_path / "book.md"
    path.write_text(text, encoding="utf-8")
    return MarkdownLoader().load(path)


def test_preserves_the_document_structure(tmp_path):
    document = load(
        tmp_path,
        """# Title

Intro paragraph.

## Chapter

- item one
- item two

| A | B |
|---|---|
| 1 | 2 |

```python
# a comment, not a heading
x = 1
```
""",
    )

    kinds = [block.kind for block in document.blocks]
    assert kinds == [
        BlockKind.HEADING,
        BlockKind.PARAGRAPH,
        BlockKind.HEADING,
        BlockKind.LIST,
        BlockKind.TABLE,
        BlockKind.CODE,
    ]
    assert document.format is DocumentFormat.MARKDOWN
    assert [block.level for block in document.blocks if block.kind is BlockKind.HEADING] == [1, 2]
    assert "# a comment, not a heading" in document.blocks[-1].text


def test_blocks_carry_no_pages(tmp_path):
    document = load(tmp_path, "# Title\n\nText.")

    assert not any(hasattr(block, "page_start") or hasattr(block, "margin") for block in document.blocks)


def test_front_matter_is_removed_and_gives_only_the_language(tmp_path):
    document = load(tmp_path, "---\ntitle: Front Title\nauthor: Someone\nlanguage: pt-BR\n---\n\n# Heading\n\nText.")

    assert document.language == "pt-BR"
    assert [block.text for block in document.blocks] == ["Heading", "Text."]
    # The book's title is its file's name, and it has no author (specs/005-markdown-only, FR-005).
    assert getattr(document, "title", None) is None
    assert getattr(document, "author", None) is None


def test_lang_sets_the_language_when_language_is_missing(tmp_path):
    assert load(tmp_path, "---\nlang: pt\n---\n\n# Heading\n\nText.").language == "pt"


def test_a_single_top_heading_is_never_the_title(tmp_path):
    assert getattr(load(tmp_path, "# The Book\n\n## One\n\nText."), "title", None) is None


@pytest.mark.parametrize(
    "front",
    ["---\ntitle: [unclosed\n---\n", "---\ntitle: never closed\n"],
    ids=["not yaml", "not closed"],
)
def test_front_matter_that_does_not_parse_or_close_stays_in_the_text(tmp_path, front):
    document = load(tmp_path, f"{front}\n# Heading\n\nText.")

    assert any("title:" in block.text for block in document.blocks)
    assert document.language is None


def test_a_leading_rule_is_not_front_matter(tmp_path):
    document = load(tmp_path, "---\n\nJust text after a rule.\n\n---\n\nMore text.")

    assert any("Just text" in block.text for block in document.blocks)


def test_a_file_without_text_is_rejected(tmp_path):
    with pytest.raises(EmptyDocumentError):
        load(tmp_path, "   \n\n  ")
