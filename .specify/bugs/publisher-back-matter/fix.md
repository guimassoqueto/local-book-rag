# Bug Fix: Matter that isn't the book is indexed as the book's

- **Slug**: publisher-back-matter
- **Fixed**: 2026-11-19
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Ingestion now keeps only the book's own text, before it detects the language and builds the
chapters. Two rules drop what an e-book carries that isn't the book:
- **Gutenberg's boundary.** When a book has both of Project Gutenberg's markers, what lies outside
  them goes.
- **Whole headings.** A section headed by a table of contents or a printed index goes, with
  everything under it.

A publisher's pages without a heading stay, as the owner chose: the conversion removes them.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `app/ingestion/structure_extractor.py` | modified | `book_blocks()`, with `_between_gutenberg_markers()` and `_is_marker()`. The constants `_GUTENBERG_START`, `_GUTENBERG_END` and `_NOT_THE_BOOK` sit beside the other structure rules |
| `app/ingestion/pipeline.py` | modified | `process()` filters the normalized blocks before the empty-text check, the language and the structure. `ProcessedDocument.normalized` keeps every block, for debugging |
| `tests/unit/test_structure_extractor.py` | added tests | 15 cases of `book_blocks()` |
| `tests/unit/test_pipeline.py` | added tests | the rules on the pipeline's path, and a book that is only a table of contents |
| `README.md` | modified | "Preparing a book" says what is left out, and that a publisher's pages without a heading are removed when converting |
| `docs/decisions.md` | modified | a new Ingestion entry: the rules, what decided them, the boundary with conversion quirks, the chapter numbers that move, and the measurement |
| `docs/benchmark-results.md` | modified | a section with the two retrieval runs and their comparison. The Known limitation now covers only the publisher's pages without a heading |

## Diff Highlights

```python
_GUTENBERG_START = re.compile(r"\*{3}\s*START OF TH(E|IS) PROJECT GUTENBERG EBOOK\b.*\*{3}", re.IGNORECASE)
_GUTENBERG_END = re.compile(r"\*{3}\s*END OF TH(E|IS) PROJECT GUTENBERG EBOOK\b.*\*{3}", re.IGNORECASE)
_NOT_THE_BOOK = frozenset({"table of contents", "contents", "sumário", "index", "índice remissivo"})

def book_blocks(blocks):
    kept, dropping = [], None  # the level of the heading being dropped
    for block in _between_gutenberg_markers(blocks):
        if block.kind is BlockKind.HEADING:
            level = block.level or 1
            if dropping is not None and level <= dropping:
                dropping = None
            if dropping is None and block.text.strip().casefold() in _NOT_THE_BOOK:
                dropping = level
        if dropping is None:
            kept.append(block)
    return tuple(kept)
```

```python
# app/ingestion/pipeline.py, in process()
book = replace(normalized, blocks=book_blocks(normalized.blocks))
...
language = self._language_of(book, path)
structure = build_structure(replace(book, language=language), title)
```

## Tests Added or Updated

- `test_structure_extractor.py::test_only_the_text_between_gutenbergs_markers_is_the_book`: the
  header, the EPUB's metadata before it, the license, and the notice between the END marker and
  the license all go. The markers go too.
- `::test_older_gutenberg_markers_say_this_ebook`: "START OF THIS PROJECT GUTENBERG EBOOK".
- `::test_one_gutenberg_marker_alone_keeps_every_block` (START or END alone).
- `::test_a_trailing_table_of_contents_goes_with_everything_it_holds`: *História econômica
  global*'s shape.
- `::test_a_dropped_section_ends_at_the_next_heading_at_its_level_or_above`: a deeper heading
  under it goes too.
- `::test_a_table_of_contents_or_a_printed_index_is_not_the_book`: the five titles, in any case.
- `::test_a_heading_that_only_mentions_one_stays`: "Indexes and keys", "Índice", "The contents of
  a module".
- `::test_chapters_stay_consecutive_when_the_first_heading_is_dropped`.
- `test_pipeline.py::test_only_the_books_own_text_is_structured_and_chunked`: a Portuguese book
  between an English Gutenberg header and license. Its chapters are its own, numbered from 1, its
  language is `pt`, and no chunk holds Gutenberg's text or the table of contents. The normalized
  document keeps them.
- `test_pipeline.py::test_a_book_that_is_only_a_table_of_contents_is_empty`.

Before the fix, the structure tests didn't import (`book_blocks` didn't exist), and both pipeline
tests failed.

## Local Verification

- **`make lint-check`**: clean. **`make test`**: 985 passed, against 968 before (17 added).
- **The real books** (Principle V), the pipeline run on the host:

  | Book | Before | After | What went |
  | ---- | ------ | ----- | --------- |
  | *História econômica global* | 15 chapters, 268 chunks | 15 chapters, 263 chunks | the table of contents and the five advertisements, chunks 263–267 |
  | *On Liberty* | 11, 177 | 9, 165 | Gutenberg's header (2 chunks) and license (9), with the EPUB's metadata and the notice after the END marker |
  | *Quincas Borba* | 206, 455 | 202, 443 | Gutenberg's header and license, the EPUB's metadata ("Front matter"), and "FIM" (Deviations) |
  | *Think Python* | 25, 369 | 23, 317 | "Contents" (24 chunks) and "Index" (28) |

  Every book's language is the same as before: `pt`, `en`, `pt`, `en`.
- **`validate-benchmark`** on the fixed code: 0 problems, so no evidence quote was in the dropped
  matter.
- **Retrieval** (Principle VI): the default configuration, each run on a fresh workspace, on
  `main`'s code (`84f8bf1`) and on the fix, paired by `devtools/compare_runs.py`, 75 pairs, none
  left out. Recall@5 went from 0.899 to 0.904, MRR from 0.948 to 0.954, and nDCG@10 from 0.882 to
  0.887 (+0.005, interval +0.000 to +0.015, which barely leaves zero out). No question got worse,
  and four improved. Two of those undo what the Markdown conversion had cost:
  `think_python_multi_section_05`'s MRR went from 0.5 to 1.0, and `on_liberty_conceptual_01`'s
  Recall@5 from 0.571 to 1.0. `main`'s run gave the same rows as specs/005's Markdown run.
  Recorded in `docs/benchmark-results.md`.
- **The stack.**
  - **The rebuild.** `make up` deleted the library, *História econômica global* included, as the
    assessment said. `reset-everything` followed, and `doctor` passed.
  - **The book.** It was added back with `add-book` as `book_001`: 15 chapters, 263 chunks.
  - **The search that reproduced the bug** ("Compre agora e leia um livro de Agatha Christie")
    now returns unrelated passages, reranked at 0.001 and 0.000. No chunk of the book holds
    "Compre agora e leia".

## Deviations from Assessment

- ***Quincas Borba*'s "FIM" heading went too.** Its only text was Gutenberg's END marker and the
  notice after it. With those gone it has no text, and headings without text are dropped as they
  always were. The novel's last words, in CAPITULO CCI, stay.
- ***Think Python*'s own "Contents" (24 chunks) went**, which the assessment's step 2 didn't list.
  It follows from the owner's answer, which put "Contents" on the list. Its chapters after the
  Preface move down by one.
- **The EPUB's metadata before Gutenberg's header** went too ("**Title:** On Liberty …"), since it
  lies before the START marker. It was chapter 0, "Front matter". *On Liberty*'s chapter 0 now holds
  its title page, and *Quincas Borba* has no chapter 0.
- **The retrieval rows don't record what was retrieved**, so what outranked the evidence on `main`
  couldn't be read, only inferred.

## Follow-ups

- **The conversion.** *História econômica global*'s author bio, edition notes, catalog record and
  copyright (chunk 262 and the end of 261) are the owner's conversion's to remove, in their plugin
  or by hand. Until then, `docs/benchmark-results.md` records them as a known limitation.
- **The retrieval rows** could record the retrieved chunk IDs, so that Principle VI's reading of
  what moved can be done from the results.
