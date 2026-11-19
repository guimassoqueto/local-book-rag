"""devtools/dump_chunks.py: what a Markdown book becomes, to compare main's code with this branch's.

The script runs in the app container on both versions of the code (specs/005-markdown-only, SC-002),
so it isn't a package: it is loaded here by path. What it reads from the pipeline is checked here,
on made-up objects shaped like main's and this branch's.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("dump_chunks", PROJECT / "devtools" / "dump_chunks.py")
dump_chunks = importlib.util.module_from_spec(_spec)
sys.modules["dump_chunks"] = dump_chunks
_spec.loader.exec_module(dump_chunks)


def section(title):
    return SimpleNamespace(title=title, blocks=())


def chunk(number, chapter, section_title, text, **extra):
    fields = {"chapter_number": number, "chapter_title": chapter, "section_title": section_title, "text": text}
    names = {"chunk_id": f"book_chapter_{number:02d}_chunk", "book_id": "book", "book_title": "Title"}
    return SimpleNamespace(**names, **fields, **extra)


def processed(title="Title", author=None, **chunk_extra):
    chapters = (
        SimpleNamespace(number=0, title="Front matter", sections=(section(None),)),
        SimpleNamespace(number=1, title="One", sections=(section(None), section("A part"))),
    )
    chunks = (
        chunk(0, "Front matter", None, "Before anything.", **chunk_extra),
        chunk(1, "One", "A part", "The first chapter.", **chunk_extra),
    )
    structure = SimpleNamespace(title=title, author=author, language="en", chapters=chapters)
    return SimpleNamespace(structure=structure, chunks=chunks, title=title, author=author, language="en")


def test_the_dump_holds_chapters_sections_and_chunks_in_order():
    assert dump_chunks.dump(processed()) == {
        "chapters": [
            {"number": 0, "title": "Front matter", "sections": [None]},
            {"number": 1, "title": "One", "sections": [None, "A part"]},
        ],
        "chunks": [
            {"chapter_number": 0, "chapter_title": "Front matter", "section_title": None, "text": "Before anything."},
            {"chapter_number": 1, "chapter_title": "One", "section_title": "A part", "text": "The first chapter."},
        ],
    }


def test_nothing_else_reaches_the_dump_even_from_mains_chunks():
    text = json.dumps(dump_chunks.dump(processed(page_start=None, page_end=None)))

    for absent in ("page_start", "page_end", "book_title", "book_id", "chunk_id", "Title", "author"):
        assert absent not in text


def test_title_author_and_pages_never_change_the_file(tmp_path):
    mains = tmp_path / "main.json"
    branch = tmp_path / "branch.json"

    dump_chunks.write(mains, dump_chunks.dump(processed("A Front-Matter Title", "Someone", page_start=3, page_end=4)))
    dump_chunks.write(branch, dump_chunks.dump(processed("01_file_name")))

    assert mains.read_bytes() == branch.read_bytes()


def test_the_file_has_sorted_keys_and_keeps_the_text_as_written(tmp_path):
    path = tmp_path / "book.json"
    dump_chunks.write(path, {"chunks": [{"text": "Capítulo 1", "chapter_number": 1}], "chapters": []})

    written = path.read_text(encoding="utf-8")

    assert written.index('"chapters"') < written.index('"chunks"')
    assert written.index('"chapter_number"') < written.index('"text"')
    assert "Capítulo 1" in written
