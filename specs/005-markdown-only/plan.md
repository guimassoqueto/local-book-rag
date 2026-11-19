# Implementation Plan: Markdown-only books

**Branch**: `feat/markdown-only` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-markdown-only/spec.md`

## Summary

The library reads Markdown alone, and removes PDF and EPUB from every place they reach:
- **Ingestion.** A `.pdf` or `.epub` is refused before anything is stored, with a message to
  convert it first. The PDF, EPUB and Docling loaders, OCR, the PDF settings and the running-head
  cleaning go, and so do Docling, PyMuPDF and EbookLib.
- **Pages.** They go from chunks, citations, prompts, filters, the passages shown and the
  benchmark's rows.
- **Books.** A book is titled by its file name and has no author.
- **The benchmark.** The extraction experiment and `fetch-benchmark-books` go. The benchmark's
  three books become the owner's Markdown conversions, with their provenance recorded and checked
  before a run.

**How.**
- **What a Markdown file gives stays the same.** Every step removed is a no-op for Markdown on
  `main`: no Markdown block has a page or a margin. So the chunks stay byte for byte, which a dump
  on `main`'s image and on the branch's proves on the real books (R12).
- **The format value stays.** One value, so the catalog and the stored originals keep their shape
  (R4).
- **The title is given, not read.** The pipeline takes it as an argument, and every caller already
  passes the file's stem (R1).
- **The fingerprint moves.** The metadata schema version goes to 2 (R7).
- **The comparison.** The retrieval benchmark's default configuration runs on `main` with the
  original books, before the rebuild, and on the branch with the Markdown. A development tool
  pairs the two runs by question with the project's bootstrap (R13).

`research.md` holds the 19 decisions behind this.

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed with uv.

**Primary Dependencies**:
- **Kept.** `markdown`, `pyyaml`, BeautifulSoup and `lxml`, which read Markdown, and Gradio 6.31,
  or 6.32 if the pending bump lands first (R10).
- **Removed.** `docling` (its extra), `pymupdf` and `ebooklib`, with whatever only they pulled in:
  `torchvision`, `pypdfium2`, `rapidocr`, the `docling-*` and `pymupdf*` packages.
- `torch` stays for the reranker. No new dependency.

**Storage**:
- **The catalog.** Same schema: `author` written empty, `format` always `markdown`.
- **ChromaDB.** The chunk metadata loses `page_start` and `page_end`, under a new index version.
- **On disk.** The originals and the processed files keep their layout.
- **The benchmark.** The dataset changes on the host, in `benchmarks/datasets`, and may be
  recorded in `specs/005-markdown-only/benchmarks/` (R19).

**Testing**: pytest.
- `make test`: the refusals, the title rule, the removed settings, the fingerprint, pages gone,
  the dataset schema and its check, and the Library tab's pickers. The lifecycle, catalog and
  progress tests that used a PDF or an EPUB are rewritten with Markdown. About 75 tests go with
  the PDF and EPUB loaders, the extraction metrics, Docling's integration test and the progress
  tool.
- `make test-integration`, on the real models.
- `devtools/dump_chunks.py`, for identical chunks (SC-002).
- `devtools/compare_runs.py`, for the paired retrieval comparison (FR-020).
- `quickstart.md`, for the tab in the browser and the commands in the container.

**Target Platform**: The Docker Compose stack on the owner's Linux machine:
- an RTX 5060 Ti with 16 GB;
- gpt-oss:20b, qwen3-embedding:0.6b and Qwen3-Reranker-0.6B, the reranker on the CPU by default;
- today's app image: 11 GB, `main`'s code with the pending bump's lock (R10).

**Project Type**: A single Python application: Gradio interface, command line, services.

**Performance Goals**:
- a refusal within a second, in all four ways in (SC-003);
- an image smaller than `main`'s (SC-004).

Nothing else may get slower: the steps removed did nothing for Markdown.

**Constraints**:
- **The same chunks.** The same chapters, sections and chunk texts as `main` for any Markdown file
  (FR-005, SC-002).
- **Nothing else changes** (FR-013): questions, summaries, quizzes, retrieval, the operations and
  their confirmations.
- **The library and the benchmark.** No book needs migrating, since `make up` empties the library.
  The benchmark changes only in `benchmarks/workspace` and the `bench_*` collections.
- **The pending bump** (`.pre-commit-config.yaml`, `uv.lock`) never enters this feature's commits
  (R10).

**Scale/Scope**:
- **The application.** About 25 modules change, and 4 are deleted: `pdf_loader.py`,
  `epub_loader.py`, `docling_loader.py` and `extraction_metrics.py`.
- **The tests and tools.** About 25 test files change, 5 are deleted, and 1 development tool goes
  while 2 are added.
- **The records.** README sections, `docs/decisions.md` and `docs/benchmark-results.md`.
- **The data.** 3 benchmark books, 90 questions of which 75 are answerable, and 1 owner's book.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --------- | ----- | --------------- | ------------ |
| I. Local-first and model-independent | No inference call is added, and no model is named in code. Three settings go (`pdf`, `normalization`, `chunking.preserve.page_numbers`), none is added, and the removed ones stop the app at startup as unknown keys. The reranker is the only GPU user left, still behind its provider. | Pass | Pass: `data-model.md`, Settings. |
| II. The library is never at risk | No operation is added or changed. The lock, the journal, recovery and checksums work as today (FR-006). A refusal happens inside `_read_upload`, before the journal entry and before storing, so a crash can't leave anything of it, and a replaced book keeps its revision (R2). Nothing is deleted or confirmed differently. No volume or mount. `make up`, which deletes the app container's library (today `book_001`), is said so where the quickstart uses it (§ 4), and comes after the baselines that need `main`'s image. The benchmark work stays in `benchmarks/workspace` and the `bench_*` collections. `dump_chunks.py` calls the pipeline only (R12). | Pass | Pass: `contracts/books.md` (When), quickstart § 3–4. |
| III. Index integrity | The chunk metadata's schema and the chunking settings change, so `METADATA_SCHEMA_VERSION` goes to 2 and the fingerprint moves. An index built before needs an explicit `reindex-all`, which builds a new version and writes nothing into the live one. After the rebuild, `reset-everything` clears the old collections before the first book (R7). | Pass | Pass: `data-model.md`, Index fingerprint. |
| IV. One service layer | The refusal and its message are the service's (`validate_upload`, through `BookService`), for the tab and the commands alike. The tab's `file_types` only filters the browser's dialog (FR-004). A PDF forced past it is refused by Gradio's own preprocessing, before any handler, so the interface still decides nothing itself, and the service refuses whatever reaches it (R3). | Pass | Pass, with the tab's message corrected in the spec (Corrections during planning). |
| V. Verified on real models and real books | The ingestion change is checked on the three converted benchmark books and the owner's `01_historia_economica_global.md`: added in the tab and with `add-book`, chunks dumped on both versions of the code, retrieval compared (R12–R14). The prompts change only by a `Pages:` part that a Markdown chunk never had, and `make test-integration` runs them against gpt-oss:20b, qwen3-embedding:0.6b and Qwen3-Reranker-0.6B. The quiz prompts' wording and parsers don't change. | Pass | Pass: quickstart § 3, 5, 6, 8. |
| VI. Measured, not assumed | No improvement is claimed. The comparison is information (FR-020): the same experiment and default variant, on `main` and on the branch, each in a fresh `benchmarks/workspace`. It is paired by question with `paired_difference` (4,000 resamples, 95%), and a difference counts only if its interval leaves zero out, after reading its questions. Each result records the environment, the dataset's checksum and the books' checksums. No judge or metric is added or changed: the extraction metrics and two page columns are removed. | Pass | Pass: `contracts/benchmark.md`. Both images built from the same lock but this feature (R10). |
| VII. Every answer traceable | As amended (2.0.1), citations resolve to book, chapter and section, and every place that locates a passage does so. The no-evidence path, summaries citing by lookup, and the quiz's page check are unchanged. A regression would show in `make test-integration`'s citation and abstention tests and in reading the Chat tab, `ask`, a summary and a quiz (SC-008). The generation benchmark's citation accuracy isn't rerun (spec, Assumptions). | Pass | Pass: `contracts/passages.md`. |
| VIII. Decisions are recorded | Tasks update `README.md` (Library, Following an operation, Index, Retrieval, Questions, Summaries, Quizzes, Benchmarks, Deployment notes, Configuration). They update `docs/decisions.md`: the new Ingestion entries, "What an operation counts", and the closing section "Removed with PDF and EPUB (v1.0.0)". They update `docs/benchmark-results.md`. `docs/decisions.md` was read first for each removed rule (Ingestion, and the Evaluation lessons). The delivered specs aren't edited. | Pass | Pass: R17. The constitution's line naming `c7bb785` as the dataset's last version would become stale, so it needs a PATCH amendment if R19 is confirmed. |

No violation: Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-markdown-only/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R19
├── data-model.md        # what changes shape, what is removed, what stays
├── quickstart.md        # unit tests, the gate, main's runs, rebuild, branch's runs, browser, records
├── contracts/
│   ├── books.md         # accepted files, messages, what is read, the tab, the commands, progress
│   ├── passages.md      # where a passage is: prompt header, citations, search, quiz, rows
│   └── benchmark.md     # the dataset's books and their check, commands, the two devtools
├── benchmarks/          # if R19 is confirmed: the validated dataset and the experiments
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
app/
├── ingestion/
│   ├── base.py                 # DocumentFormat.MARKDOWN only; Block, ExtractedDocument slimmed; no comparable_text
│   ├── validation.py           # .md/.markdown; PDF and EPUB refused with the convert-first message
│   ├── markdown_loader.py      # no title, no author; front matter still removed, language still read
│   ├── html_blocks.py          # no anchors
│   ├── normalizer.py           # the cleaning that applies to any text, no configuration
│   ├── structure_extractor.py  # build_structure(document, title); no author
│   ├── chunker.py              # no pages
│   ├── pipeline.py             # process(path, format, book_id, title, progress); no author
│   └── pdf_loader.py, epub_loader.py, docling_loader.py   # deleted
├── config/settings.py          # no PdfConfig, NormalizationConfig, page_numbers
├── container.py                # one loader; Normalizer()
├── errors.py                   # no ScannedDocumentError
├── generation/                 # citations.py, prompts.py, summarization.py: no pages
├── retrieval/                  # base.py, dense.py: no page range
├── services/
│   ├── book_service.py         # no author written
│   ├── ingestion_service.py    # extraction stage without unit or estimate
│   ├── index_service.py        # METADATA_SCHEMA_VERSION = 2
│   ├── quiz_service.py         # _reference without pages
│   └── health_service.py       # the GPU line names the reranker only
├── utils/progress.py           # no uncount, no OCR state
├── interface/
│   ├── formatting.py           # no pages_of, quiz_pages, "Pages" column
│   └── library.py              # the pickers' types and label, the note
├── evaluation/
│   ├── dataset.py              # BenchmarkBook's new fields; no fetch_books
│   ├── benchmark.py            # the books' check before run/validate; no extraction kind; no page columns
│   ├── quiz_metrics.py         # READING_FIELDS without pages
│   └── extraction_metrics.py   # deleted
└── main.py                     # no fetch-benchmark-books; search without a page range; help texts

config/ingestion.yaml           # languages and chunking only
pyproject.toml, uv.lock         # without ebooklib, pymupdf and the docling extra
docker-compose.yml              # the comment names the reranker only

devtools/
├── dump_chunks.py              # new (R12)
├── compare_runs.py             # new (R13)
└── measure_library_progress.py # deleted

tests/
├── documents.py                # the PDF and EPUB writers go
├── library.py, fakes.py        # Markdown loader only; chunks without pages
├── integration/test_docling.py # deleted
└── unit/
    ├── test_pdf_loader.py, test_epub_loader.py, test_extraction_metrics.py, test_progress_devtool.py   # deleted
    ├── test_dump_chunks.py, test_compare_runs.py           # new: the two devtools' logic
    └── the files R16 lists                                 # rewritten or changed

README.md, docs/decisions.md, docs/benchmark-results.md
```

**Structure Decision**: The existing single application. Nothing new is added to `app/`: the
feature removes code. The two new tools live in `devtools/`, outside the image, like the progress
tool they replace.

## Complexity Tracking

None.
