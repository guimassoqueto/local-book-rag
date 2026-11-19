# Contract: where a passage is, without pages

Every place that locates a passage gives the book, the chapter and the section, leaving out a
section the passage doesn't have, and nothing else (FR-014, constitution VII). On `main` a
Markdown passage already showed no page, so for a Markdown book the text below is what `main`
shows, apart from the scores table's column.

## What the model is given

The passage header in `format_passage` (`app/generation/prompts.py`):

```text
[3] Book: 01_historia_economica_global | Chapter: Capítulo 1 | Section: <section>
<the chunk's text>
```

There is no `Pages:` part, which only a PDF chunk had. The quiz writer still gets its passage
without a number, a section or pages, and its prompt's wording doesn't change. The quiz's check
that refuses a question naming a page stays (FR-016).

## What the reader sees

| Place | Shows |
| ----- | ----- |
| Answer sources (`sources_markdown`) | `- **[3]** 01_historia_economica_global, Capítulo 1, <section>` |
| Passages under an answer (`passages_markdown`) | `**[3]** 01_historia_economica_global, Capítulo 1, <section> · cited`, then the quoted text |
| The Chat tab's scores table (`SCORE_COLUMNS`) | In context, Chunk, Chapter, Dense, BM25, Fusion, Reranker. "Pages" is gone |
| A saved summary's references (`_with_references`) | `- [3] <section>: “<excerpt>”`, or the excerpt alone without a section |
| A quiz's pointer to its passage (`quiz_reference`, `QuizService._reference`) | `01_historia_economica_global, Capítulo 1, <section>`, and in a single chapter's quiz `Capítulo 1, <section>` |
| `ask` | the answer's sources, as in the tab |

## `search`

```text
book-rag search QUESTION [--book ID]... [--chapter N]... [--section TITLE]... [--language CODE]...
```

`--page-start` and `--page-end` are gone. They are now unknown arguments, which argparse refuses
naming them. Each passage prints as:

```text
book_001_chapter_01_chunk_0042 (Capítulo 1, <section>) dense=0.612 bm25=7.204 rerank=0.931
  '<the first 200 characters>'
```

## The index

Chunk metadata in ChromaDB holds `chunk_id`, `book_id`, `book_title`, `chapter_number`,
`chapter_title`, `section_title`, `chunk_index` and `language`, plus the revision key the store
adds. Retrieval filters by book, chapter, section and language.

## The benchmark's rows

- **Retrieval `rows.csv`**: `relevant_chapters` and `relevant_chunks`, with no `relevant_pages`.
- **Quiz `reading.csv`**: no `pages` column. An older run's file is still read.
