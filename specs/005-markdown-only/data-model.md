# Data model: Markdown-only books

What changes shape, and what doesn't. Each entry says where it lives and which requirement or
decision it follows (`research.md`, R1 to R18).

## Stored, and unchanged

| Entity | Where | Why it doesn't change |
| ------ | ----- | --------------------- |
| Catalog `books` row | `app/storage/catalog.py` | Keeps every column, `author` and `format` included. `author` is written empty, and `format` is always `markdown` (R1, R4). No migration. |
| Journal entries | catalog | No operation is added or changed (FR-006). |
| Stored original | `data/original_books/<book_id>/r<revision>.md` | Same layout, and the same `source.json` record (R4). |
| Index record | catalog `indexes` | Same fields. Its fingerprint changes (below). |

## Changed

### `DocumentFormat` (`app/ingestion/base.py`)

One member, `MARKDOWN = "markdown"`. `PDF` and `EPUB` go (R4).

### `Block` (`app/ingestion/base.py`)

| Field | Before | After |
| ----- | ------ | ----- |
| `kind`, `text`, `level` | | unchanged |
| `page_start`, `page_end` | first and last page, or None | removed (FR-014) |
| `margin` | found at a page's edge | removed (R6) |

### `ExtractedDocument` (`app/ingestion/base.py`)

| Field | Before | After |
| ----- | ------ | ----- |
| `format`, `blocks` | | unchanged |
| `title` | from front matter or a single H1 | removed: the pipeline is given the title (R1) |
| `author` | from front matter | removed (R1) |
| `language` | from front matter `language` or `lang` | unchanged |

The saved `extracted.json` and `normalized.json` lose the same keys. They are debugging output,
which nothing reads back.

### `BookStructure` (`app/ingestion/structure_extractor.py`)

`title`, `language` and `chapters` stay. `author` goes. `build_structure(document, title)` takes
the title, which names the one chapter of a book without headings, as the pipeline's title does
on `main` (Corrections during planning). The rules that find chapters and sections don't change.

### `ProcessedDocument` (`app/ingestion/pipeline.py`)

`author` goes. `title` is the title the pipeline was given: the stem of the file's name, as given
(FR-005).

### `Chunk` (`app/ingestion/chunker.py`), and the chunk metadata in ChromaDB

| Field | After |
| ----- | ----- |
| `chunk_id`, `book_id`, `book_title`, `chapter_number`, `chapter_title`, `section_title`, `chunk_index`, `language`, `text` | unchanged |
| `page_start`, `page_end` | removed (FR-014) |

`app/storage/chroma.py` stores every field but the text as metadata, so the metadata loses the same
two keys. `chunks.jsonl` follows.

### `Citation` (`app/generation/citations.py`)

`page_start`, `page_end` and the `pages` property go. `reference` is "book, chapter, section",
leaving out a missing section. `excerpt` stays.

### `RetrievalFilters` (`app/retrieval/base.py`)

`book_ids`, `chapter_numbers`, `section_titles` and `languages` stay. `page_start` and `page_end`
go, with the dense store's page conditions (`app/retrieval/dense.py`).

### Settings (`app/config/settings.py`, `config/ingestion.yaml`)

| Key | After |
| --- | ----- |
| `pdf` (`extractor`, `extract_tables`, `ocr.enabled`), `PdfConfig`, `PdfOcrConfig` | removed (FR-008) |
| `normalization` (`remove_repeated_margins`), `NormalizationConfig` | removed with its only key (R6) |
| `chunking.preserve.page_numbers` | removed (FR-014). `preserve` keeps `chapters`, `sections`, `paragraphs` |
| `languages`, the rest of `chunking` | unchanged |

Every model forbids unknown keys, so any of the removed keys stops the app at startup, and the
error names it (User Story 2, scenario 2).

### Index fingerprint (`app/services/index_service.py`)

`METADATA_SCHEMA_VERSION` goes from 1 to 2. `chunking` is serialized without
`preserve.page_numbers`. The fingerprint changes. An index built before is one whose
configuration changed: `doctor` reports it, new books are refused, and `reindex-all` builds the
next version (FR-015, R7).

### Progress (`app/utils/progress.py`, `app/services/ingestion_service.py`)

- `INGEST_STEPS`' extraction stage: `StageSpec(EXTRACT, "Extracting the text")`, without a unit
  or an estimate.
- `Stage.uncount`, `Progress._uncount`, the stage state's `ocr`, and the `ocr` field of the stage
  log line: removed.
- `DocumentLoader.load(path)`: no `stage` parameter (R8).

The other stages, the stage lines' other fields, and the snapshot's shape stay.

### `BenchmarkBook` (`app/evaluation/dataset.py`) and `books.yaml`

| Field | After |
| ----- | ----- |
| `key`, `role`, `title`, `author`, `language`, `license` | unchanged. `title` names the book in the tool's messages, not in the library |
| `filename` | the Markdown file in `benchmarks/books` |
| `sha256` | the Markdown file's checksum, checked before `run` and `validate` (R11) |
| `url` | removed: moved into `original` |
| `original` | new: `{url, sha256}` of the PDF or EPUB it was converted from. Provenance, never fetched |
| `conversion` | new: text, MarkItDown's version and the plugins, as the owner names them |

`extra="forbid"` refuses a `books.yaml` that still has `url` at the top level. An example:

```yaml
books:
  - key: think_python
    role: English book
    title: Think Python, 2nd edition
    author: Allen B. Downey
    language: en
    filename: <the owner's file name>.md
    sha256: <the Markdown file's sha256>
    original:
      url: https://greenteapress.com/thinkpython2/thinkpython2.pdf
      sha256: 6033000bac3f9268ad75ee041bf8e5d9a3bc8a33bb156399cbd014918cb59f94
    conversion: <MarkItDown version and plugins>
    license: Creative Commons Attribution-NonCommercial 3.0
```

`BenchmarkQuestion` and `ChapterKeyPoints` keep their schema. Their quotes and chapter names are
corrected to the Markdown text (FR-019, R11).

### `Experiment.kind` (`app/evaluation/benchmark.py`)

`retrieval`, `generation`, `summarization`, `performance`, `quiz` and `quiz_check`. `extraction`
goes (FR-017).

### Benchmark rows

| File | Change |
| ---- | ------ |
| retrieval `rows.csv` | `relevant_pages` removed. `relevant_chapters` and `relevant_chunks` stay |
| quiz `reading.csv` (`READING_FIELDS`) | `pages` removed. An older run's file, which has the column, is still read |

### The results environment

Unchanged: the dataset's checksum, now over a `books.yaml` that names Markdown files, and each
book's checksum, now the Markdown file's (FR-021). The package list loses nothing it tracks:
Docling was never in `_TRACKED_PACKAGES`.

## Removed outright

- `app/ingestion/pdf_loader.py`, `epub_loader.py` and `docling_loader.py`;
  `app/evaluation/extraction_metrics.py`.
- `ScannedDocumentError` (`app/errors.py`), `comparable_text` (`app/ingestion/base.py`).
- `_require_pdf`, `_require_epub` and their constants (`app/ingestion/validation.py`).
- `fetch_books` (`app/evaluation/dataset.py`), and the `fetch-benchmark-books` command.
- `devtools/measure_library_progress.py`.

## New, outside the application

- **`devtools/dump_chunks.py`**: per Markdown file, the chapters, their sections and the chunk
  texts, with no title, author or pages (R12).
- **`devtools/compare_runs.py`**: two retrieval results, merged and paired by question (R13).
- **`benchmarks/experiments/markdown_books.yaml`** (host, not committed): kind `retrieval`, one
  variant `default` with no overrides.
