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


def test_pages_are_unavailable(tmp_path):
    document = load(tmp_path, "# Title\n\nText.")

    assert all(block.page_start is None and block.page_end is None for block in document.blocks)


def test_a_single_top_heading_is_the_title(tmp_path):
    assert load(tmp_path, "# The Book\n\n## One\n\nText.").title == "The Book"


def test_several_top_headings_are_not_a_title(tmp_path):
    assert load(tmp_path, "# One\n\nText.\n\n# Two\n\nText.").title is None


def test_front_matter_gives_the_metadata(tmp_path):
    document = load(tmp_path, "---\ntitle: Front Title\nauthor: Someone\nlanguage: pt-BR\n---\n\n# Heading\n\nText.")

    assert document.title == "Front Title"
    assert document.author == "Someone"
    assert document.language == "pt-BR"
    assert document.blocks[0].text == "Heading"


def test_a_leading_rule_is_not_front_matter(tmp_path):
    document = load(tmp_path, "---\n\nJust text after a rule.\n\n---\n\nMore text.")

    assert any("Just text" in block.text for block in document.blocks)


def test_a_file_without_text_is_rejected(tmp_path):
    with pytest.raises(EmptyDocumentError):
        load(tmp_path, "   \n\n  ")
