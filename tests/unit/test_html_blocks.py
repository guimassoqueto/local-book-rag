from app.ingestion.base import BlockKind
from app.ingestion.html_blocks import html_to_blocks


def blocks_of(html):
    return html_to_blocks(html)[0]


def test_extracts_each_kind_of_block():
    blocks = blocks_of(
        """
        <h2>Heading</h2>
        <p>A <em>paragraph</em>, in   two
           lines.</p>
        <ul><li>one</li><li>two</li></ul>
        <ol><li>first</li></ol>
        <pre><code>x = 1
    y = 2</code></pre>
        <table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
        """
    )

    assert [block.kind for block in blocks] == [
        BlockKind.HEADING,
        BlockKind.PARAGRAPH,
        BlockKind.LIST,
        BlockKind.LIST,
        BlockKind.CODE,
        BlockKind.TABLE,
    ]
    assert blocks[0].level == 2
    assert blocks[1].text == "A paragraph, in two lines."
    assert blocks[2].text == "- one\n- two"
    assert blocks[3].text == "1. first"
    assert blocks[4].text == "x = 1\n    y = 2"
    assert blocks[5].text == "| A | B |\n| --- | --- |\n| 1 | 2 |"


def test_inline_markup_does_not_split_words():
    assert blocks_of("<p><b>W</b>ord and <i>an</i>other</p>")[0].text == "Word and another"


def test_nested_lists_keep_their_depth():
    [block] = blocks_of("<ul><li>outer<ul><li>inner</li></ul></li><li>next</li></ul>")

    assert block.text == "- outer\n  - inner\n- next"


def test_scripts_and_styles_are_never_text():
    blocks = blocks_of("<style>p{}</style><script>alert(1)</script><p>Visible.</p><noscript>hidden</noscript>")

    assert [block.text for block in blocks] == ["Visible."]


def test_comments_are_not_text():
    assert [block.text for block in blocks_of("<!-- secret --><p>Visible.</p>")] == ["Visible."]


def test_containers_are_walked_in_order():
    blocks = blocks_of("<div><section><h1>One</h1><div><p>Two</p></div></section><blockquote>Three</blockquote></div>")

    assert [block.text for block in blocks] == ["One", "Two", "Three"]


def test_a_div_with_text_is_a_paragraph():
    assert blocks_of('<div class="para">Only a div here.</div>')[0].kind is BlockKind.PARAGRAPH


def test_loose_text_between_blocks_is_kept():
    blocks = blocks_of("<div>Loose <b>text</b><p>Inside</p>after</div>")

    assert [block.text for block in blocks] == ["Loose text", "Inside", "after"]


def test_anchors_point_at_their_blocks():
    _, positions = html_to_blocks(
        '<p>Intro</p><h2 id="first">One</h2><p>Body</p><div id="second"><p>Two</p></div>',
        anchors=frozenset({"first", "second", "missing"}),
    )

    assert positions == {"first": 1, "second": 3}


def test_inline_anchors_point_at_the_block_holding_them():
    _, positions = html_to_blocks(
        '<p>Intro</p><p><a id="target"></a>The section starts here.</p>', anchors=frozenset({"target"})
    )

    assert positions == {"target": 1}


def test_table_cells_escape_pipes():
    [block] = blocks_of("<table><tr><td>a|b</td></tr></table>")

    assert "a\\|b" in block.text
