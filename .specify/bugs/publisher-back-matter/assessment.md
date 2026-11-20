# Bug Assessment: Matter that isn't the book is indexed as the book's

- **Slug**: publisher-back-matter
- **Created**: 2026-11-19
- **Source**: pasted text, the owner's request on `fix/publisher-back-matter`, which restates the
  known limitation recorded in `docs/benchmark-results.md` and `specs/005-markdown-only/spec.md`.
  No URL.
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> Publisher back matter is indexed as part of the book. In *História econômica global* (the
> owner's Markdown conversion `01_historia_economica_global.md`, made from the e-book with
> MarkItDown), the end of the file holds the publisher's back matter: a level-3 heading "Table of
> Contents" whose paragraph is the book's table of contents run into one line, then the catalog
> record, the copyright notice and five advertisements for other books ("Compre agora e leia").
> Ingestion puts all of it into the book's last chapter, "Lista de tabelas", so it is chunked,
> embedded and indexed as the book's own text: a question in the Chat tab or with `ask`, and
> `search`, can retrieve the advertisements as passages of the book, and a summary of that chapter
> can include them. Expected: the publisher's back matter doesn't count as the book's text, so
> retrieval and summaries never treat it as the book's content.

Two details differ from the report. The catalog record and the copyright come *before* the "Table
of Contents" heading, not after it. And the same kind of matter is in the benchmark's other books
too (Reproduction, step 2).

## Symptom

Text that isn't the book is indexed as one of its chapters, so retrieval returns it as the book's
passages. Asked about the advertisements, `search` ranks five of them first in *História econômica
global*. The two Project Gutenberg books each get a chapter of license text. Expected: only the
book's own text is chunked and indexed.

## Reproduction

1. **On the running stack** (v0.6.0, with `01_historia_economica_global.md` added as `book_001`):
   `docker compose exec app book-rag search "Compre agora e leia um livro de Agatha Christie" --book book_001`.
   The first four passages are chunks 0264, 0263, 0266 and 0267, located as "(Lista de tabelas,
   Table of Contents)": the advertisements and the run-on table of contents, reranked at 1.000,
   0.987, 0.983 and 0.798.
2. **Without services**, the real pipeline (`build_pipeline(settings).process(...)`) on the four
   Markdown books in `benchmarks/books`, 2026-11-19:

   | Book | What isn't the book's text, and where it lands |
   | ---- | ----------------------------------------------- |
   | *História econômica global* | The last chapter, "Lista de tabelas", has 7 chunks. Chunk 261 holds the list of tables, then the author's bio. Chunk 262 holds the edition notes, the catalog record ("Cip-Brasil. Catalogação na publicação … ISBN … CDD") and the copyright notice, with no heading. Chunks 263–267 are a section "Table of Contents": the table of contents run into one line, then the five advertisements |
   | *On Liberty* (Gutenberg) | Chapter 1, "The Project Gutenberg eBook of On Liberty" (2 chunks), is Gutenberg's header, and holds the book's title line as a section. Chapter 10, "THE FULL PROJECT GUTENBERG™ LICENSE", has 9 chunks. Chapter V also ends with the 25 lines between Gutenberg's END marker (line 4678) and the license heading (line 4704) |
   | *Quincas Borba* (Gutenberg) | Chapter 1, "The Project Gutenberg eBook of Quincas Borba" (1 chunk), and chapter 205, "THE FULL PROJECT GUTENBERG™ LICENSE" (9 chunks) |
   | *Think Python* | Chapter 24, "Index", is the printed index, page numbers included (28 chunks) |

3. **In the Summarization tab**, a Gutenberg book would list "THE FULL PROJECT GUTENBERG™
   LICENSE" as a chapter to summarize. This is inferred from step 2's chapters, and wasn't checked
   in the browser.

None of the dataset's 90 questions quotes any of this matter: `questions.jsonl` has no
"Gutenberg", "license", "Compre agora" or "ISBN".

## Suspected Code Paths

- `app/ingestion/structure_extractor.py:48` `build_structure`, `:73` `_split_chapters`. Every block
  after a chapter heading belongs to that chapter, up to the next chapter heading. A deeper heading
  becomes one of its sections (`_sections`, `:122`). The only matter set apart is "Front matter",
  the text before the first chapter heading, and it is kept, as chapter 0.
- `app/ingestion/markdown_loader.py`: reads the whole file into blocks, after removing the YAML
  front matter. It knows no other boundary, so it ignores Gutenberg's own START and END markers,
  which the conversions keep as text (`\*\*\* START OF THE PROJECT GUTENBERG EBOOK ON LIBERTY \*\*\*`,
  line 31).
- `app/ingestion/pipeline.py`: `process()` runs the loader, the normalizer, the structure and the
  chunker. It is the one path for adding, replacing and reindexing a book, so a filter on its blocks
  reaches all three.
- `app/ingestion/chunker.py`: chunks every section of every chapter, as it should once the matter
  is gone.

## Root Cause Hypothesis

Ingestion takes every block of a Markdown file as the book's text, and has no idea of matter that
isn't the book. E-books carry such matter as a matter of course: a distributor's header and
license, the publisher's catalog page and advertisements, a table of contents, a printed index.
MarkItDown converts it all. Since `specs/005-markdown-only`, the application reads the conversion
as it is, and `docs/decisions.md` records that "the application adds no rule for a conversion's
quirks". This matter isn't a quirk of the conversion, though: it is in the e-book. Confidence:
high. Step 2 shows each case, and step 1 shows retrieval ranking it first.

## Proposed Remediation

**Preferred**: two rules in ingestion, applied to the blocks before the structure is built, so that
adding, replacing and reindexing a book all get them.

1. **Gutenberg's boundary.** When a book holds Project Gutenberg's own markers,
   "\*\*\* START OF THE PROJECT GUTENBERG EBOOK … \*\*\*" and
   "\*\*\* END OF THE PROJECT GUTENBERG EBOOK … \*\*\*", only the blocks between them are the book.
   That drops Gutenberg's header, its license, and the text between them and the book. These
   markers are Gutenberg's standard, which every Gutenberg book carries. A book without both keeps
   all its blocks.
2. **Headed sections that are never the book's text.** A heading whose text is exactly one of a
   short list is dropped with every block under it, down to the next heading at its level or
   above. The list holds a table of contents, "Table of Contents", "Contents" and "Sumário", and a
   printed index, "Index" and "Índice remissivo" (the owner's answers). In *História econômica
   global*, that drops the table of contents and the five advertisements, chunks 263–267, since
   the section runs to the end of the book. In *Think Python*, it drops the printed index.

The list is a code constant beside the structure rules that already are (`_PART`, `_CHAPTER`),
matched without case. The rules see only headings and Gutenberg's markers, so they never guess at
prose.

**Not in the application's reach**: *História econômica global*'s author bio, edition notes,
catalog record and copyright. They run on inside "Lista de tabelas" with no heading (chunk 262,
and the end of 261), so no rule can tell them from the book without guessing at their wording. The
conversion can remove them, or mark them with a heading the second rule knows (Open Questions).

**Alternatives**:
- **Fix only the conversions**, in the owner's MarkItDown plugins, as `docs/decisions.md` did for
  *Think Python*'s unfenced code. Every book would have to be converted again. The benchmark's
  books are pinned to their conversion, so this would make a new dataset version, with its quotes
  validated again. A Gutenberg book converted by anyone else would still carry the license. The
  rules above leave the files, and the dataset, as they are.
- **A list of headings in `config/ingestion.yaml`.** A setting that changes what is chunked joins
  the index fingerprint (Principle III), so changing it would need a `reindex-all`. The structure
  rules today are code constants, and this list would be the first one in configuration.
- **Rules on the colophon's wording** ("ISBN", "©", "Catalogação na publicação"). These are fragile
  and publisher-specific, and a book about publishing could lose its text. Rejected.

**Files likely to change**:
- `app/ingestion/structure_extractor.py`, or a small step in `app/ingestion/pipeline.py` before
  it: the two rules.
- `tests/unit/test_structure_extractor.py`, and `test_pipeline.py` for the step if it lands there.
- `README.md` (what is read from a book), `docs/decisions.md` (Ingestion: the rules, the boundary
  with conversion quirks, and why), and `docs/benchmark-results.md` (Known limitations: the
  advertisements item).

**Tests to add or update**:
- **Gutenberg's markers.** The blocks before START and after END are dropped, and the markers
  with them. A book with only one of the two markers keeps all its blocks. A book without them is
  unchanged.
- **A trailing table of contents.** A "### Table of Contents" section running to the end is
  dropped with all it holds. One followed by a heading at its level or above drops only itself.
- **The printed index.** "# Index" is dropped. A heading that only contains the word, such as
  "Indexes and keys", stays.
- **Chapter numbers** stay consecutive when a dropped chapter came first, as Gutenberg's header
  does.
- **Real books** (Principle V):
  - the pipeline's chapters and chunk counts for the four books, before and after;
  - `validate-benchmark` still finds every evidence quote;
  - on the running stack, the `search` of step 1 no longer returns the advertisements.

## Risks & Considerations

- **Principle V.** An ingestion change is checked on real books: the benchmark's three and the
  owner's `01_historia_economica_global.md`, as step 2 lists them.
- **Principle VI.** The fix is made for retrieval quality, so the retrieval experiment's default
  variant runs before and after, each on a fresh `benchmarks/workspace`, paired by question as
  `specs/005` did. A workspace can't see an ingestion change, so it is deleted after the fix. The
  dataset's files don't change, so their checksums hold. No question quotes the dropped matter, so
  `validate-benchmark` should pass as it is.
- **Chapter numbers move.** Dropping Gutenberg's header, chapter 1 of both Gutenberg books, moves
  their later chapters down by one, and the chunk IDs with them. The dataset and the key points name
  chapters by title, so they hold. `make up` empties the library anyway (Principle II), so no
  stored chunk or summary keeps the old numbers. *On Liberty*'s title line, which sits under the
  Gutenberg header today, moves to "Front matter", chapter 0.
- **The index fingerprint doesn't change.** No setting, template, tokenizer or metadata field
  changes. So an index built before keeps the dropped matter until its books are processed again.
  In practice that is the next `make up`, which empties the library, or a `reindex-all`.
- **False positives.** A real chapter titled exactly "Index" or "Table of Contents" would be
  dropped. Exact titles keep that narrow, and the README says so.
- **The decision it touches.** "The application adds no rule for a conversion's quirks" stays true:
  these rules are about the e-book's own non-book matter, not about how it was converted.
  `docs/decisions.md` says where the line is.
- **The reported book stays partly unfixed by the application.** Its catalog record and copyright,
  chunk 262, remain, unless the conversion removes or marks them.

## Open Questions

None left. The owner answered on 2026-11-19:
- **The titles.** The two seen, and their unambiguous equivalents: "Table of Contents",
  "Contents" and "Sumário" for a table of contents, and "Index" and "Índice remissivo" for a
  printed index. Not "Índice" alone, which Portuguese books use for either one.
- **The printed index is in scope.** *Think Python*'s is dropped, since its entries and page
  numbers mean nothing in a library without pages.
- **The catalog record and the copyright stay with the conversion.** The owner's plugin, or a
  hand edit of the file, removes them. Until then, `docs/benchmark-results.md` records the
  limitation. No way to mark a book's end is added: that would be a feature of its own.
