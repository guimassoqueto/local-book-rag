---

description: "Task list for Markdown-only books"
---

# Tasks: Markdown-only books

**Input**: Design documents from `specs/005-markdown-only/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md),
[checklists/removal-and-measurement.md](checklists/removal-and-measurement.md)

**Tests**: Included. The constitution's Development Workflow asks for automated tests of every
significant component. FR-010 asks that what today's tests check through a PDF or an EPUB stays
checked with Markdown, and SC-006 asks `make test` to pass. Within each story, the tests come first
and must fail before the implementation, except where a task says it changes only tests.

**Organization**: By user story, in priority order. Before them, the baselines on `main`'s code, in
Setup, which need `main`'s image and so come before any change under `app/` (research.md R10, R12,
R13). The stories build on each other:
- **US1** refuses PDF and EPUB, and titles books by their file names.
- **US2** removes what US1 made unreachable, and pages.
- **US3** moves the benchmark to the Markdown books.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: a different file, and no dependency on an unfinished task.
- **[Story]**: the user story the task belongs to (US1 to US3).

## Path Conventions

A single Python project, with `app/`, `config/`, `devtools/` and `tests/` at the repository root
(plan.md, Project Structure).

- **In the Bash tool**, run
  `export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"` before `make` or
  `uv`.
- **The pending dependency bump stays stashed** for the whole feature (`stash@{0}`, "chore:
  commitizen 4.19.4 + uv.lock (owner undecided)"; research.md R10). Never pop it, and never commit
  `.pre-commit-config.yaml` or `uv.lock` except for T035's lock change.
- **`make up` recreates the app container, which deletes the library it holds** (principle II). The
  owner allows it, and a reset, at any time (checklist CHK006). Every task that runs it says so.
  After it, `reset-everything` comes first (FR-015).
- **Between T002 and T046**, the app container must keep `main`'s code: no `make up` in between.
  Nothing is mounted, so changes on the host don't reach it (quickstart.md § 3).
- **Files go into the container** with `docker compose cp -a` from a staging folder: `/app` belongs
  to root, and `-a` keeps the files the app user's. Development tools run from `/app` as
  `python -I /tmp/devtools/<tool>.py`.
- **The dataset and experiments** are on the host, in `benchmarks/` (ignored by git). Their copy in
  `specs/005-markdown-only/benchmarks/` is made at T056.
- **Commits** happen only when the owner asks.

---

## Phase 1: Setup

**Purpose**: A known starting point, `main`'s image, and the two baselines that only `main`'s code
can give: the retrieval run on the original books (FR-020) and the chunk dump (SC-002).

- [ ] T001 Check the starting point and record it in this file's Notes:
  - `git stash list` shows the bump, and `git status --short` is empty;
  - the books are in `benchmarks/books`, with the sha256s of research.md R11: `think-python.md` `380a8ec6…`, `quincas-borba.md` `ae3e75a1…`, `on-liberty.md` `5588535e…`, `01_historia_economica_global.md` `7d79a99e…`, plus the three originals;
  - `make lint-check` and `make test` pass, with the passing count. Uses the `Makefile`.
- [ ] T002 Rebuild the running image from `main`'s code and lock (research.md R10, quickstart.md § 3).
  1. Check that `git diff main --stat -- app config pyproject.toml uv.lock Dockerfile` is empty.
  2. Run `docker compose exec app book-rag list-books` and record what the library holds.
  3. `make up`, **which deletes the library the app container holds**, then
     `docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"`, then
     `docker compose exec app book-rag doctor`.
  4. Record in Notes:
     - `docker image ls local-book-rag-app --format '{{.Size}}'`, the size of `main`'s image (SC-004);
     - the container's versions of gradio, docling, pymupdf, ebooklib and torchvision
       (`importlib.metadata`);
     - that `sha256sum /app/uv.lock` in the container equals `git show main:uv.lock | sha256sum`.
  - No `make up` from here until T046.
- [ ] T003 [P] Write `tests/unit/test_dump_chunks.py`, loading `devtools/dump_chunks.py` with `importlib`, as `tests/unit/test_default_llm_devtool.py` does. It covers `dump(processed)` (research.md R12, contracts/benchmark.md) on made-up objects:
  - `{"chapters": [{"number", "title", "sections"}], "chunks": [{"chapter_number", "chapter_title", "section_title", "text"}]}`, in the book's order, a missing section as `null`;
  - nothing else: no title, author, page, book ID or chunk ID, even when a chunk object carries `page_start` and `page_end`, as `main`'s do;
  - the JSON is written with sorted keys;
  - two objects that differ only by title, author or page fields give identical files.
- [ ] T004 Write `devtools/dump_chunks.py`, so that T003 passes. It has a module docstring saying what it is for and how to run it (quickstart.md § 3, § 5), and these arguments: `--out DIRECTORY`, then the Markdown files.
  - It builds the pipeline with `app.container.build_pipeline(load_settings(environment.config_dir))`.
  - For each file it calls `pipeline.process(path, validate_upload(path, path.name, 2**30), "book", path.stem)` **positionally**, so that the same call works on `main` and on this branch (research.md R4). It writes `DIRECTORY/<file name>.json`.
  - `dump()` reads only the named attributes, never `dataclasses.asdict`, so `main`'s extra chunk fields don't reach the output.
  - It touches neither the library nor the index.
- [ ] T005 [P] On the host, write `benchmarks/experiments/markdown_books.yaml` as `contracts/benchmark.md` gives it: kind `retrieval`, one variant `default` without overrides. It isn't committed until T056.
- [ ] T006 Run the retrieval baseline on `main`'s image (FR-020, quickstart.md § 3), in the background.
  - Use a staging folder holding `main`'s dataset (`benchmarks/datasets` as it is now), `benchmarks/books` (the originals and the Markdown files) and T005's experiment.
  - Run `docker compose exec app rm -rf /app/benchmarks/workspace`, copy the folder in, then `book-rag benchmark benchmarks/experiments/markdown_books.yaml --commit "$(git rev-parse --short main)"`, and copy `app:/app/benchmarks/results` out.
  - Record in Notes: the results directory, its 75 rows, each metric's mean, `dataset_sha256` and the books' sha256s.
  - This must finish before T042 rewrites the host's dataset.
- [ ] T007 Dump the chunks on `main`'s image (SC-002, quickstart.md § 3). Copy `devtools/dump_chunks.py` to `/tmp/devtools/` in the container, and run it with `--out /tmp/chunks-main` on the four `/app/benchmarks/books/*.md` (through `sh -c`, so that the container expands the glob). Copy `/tmp/chunks-main` to `benchmarks/results/chunks-main/` on the host, and record each file's sha256 and chunk count in Notes.

**Checkpoint**: Both baselines are on the host. The container keeps `main`'s code until T046.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The tests that check something independent of the format, through a PDF or an EPUB,
check it with Markdown (FR-010), while `app/` is still `main`'s. US2 can then delete the PDF and
EPUB code without losing a check.

**⚠️ CRITICAL**: No user story starts until this phase is complete. These tasks change tests only,
and `make test` must pass after each.

- [ ] T008 [P] In `tests/unit/test_book_lifecycle.py`:
  - Rewrite `test_a_replacement_can_change_format` as "a replacement under another name retitles the book". Replace with `other.markdown`, then assert that the title is `other`, the format `markdown`, and the original path ends with `original_r2.md`.
  - Rewrite the failed replacement at line 124 with a Markdown file that fails inside the operation: one holding only headings, which raises `EmptyDocumentError` after storing. Assert that the book and `library_state` are as they were before.
  - Drop the `write_pdf` import.
- [ ] T009 [P] In `tests/unit/test_book_service.py`:
  - Delete `test_pdf_books_keep_their_pages`.
  - Rewrite `test_epub_books_have_no_pages_but_keep_their_chapters` with a Markdown file of two `#` chapters: the chapters are kept, in order. Drop its author and page assertions.
  - Drop the `write_epub` and `write_pdf` imports.
- [ ] T010 [P] Change the made-up books' file names and formats from PDF to Markdown, without changing what each test checks:
  - `tests/unit/test_catalog.py`: `book.pdf`, `original.pdf` and `format="pdf"` become `book.md`, `original.md` and `"markdown"`;
  - `tests/unit/test_interface.py`, lines 37 and 40;
  - `tests/unit/test_summarization.py`, lines 29 and 32;
  - `tests/unit/test_quiz_service.py`, line 86;
  - the local book `m.pdf` in `tests/unit/test_benchmark.py`, line 543.
- [ ] T011 In `tests/library.py`, give the test library's pipeline the Markdown loader only. Drop the `PdfLoader` and `EpubLoader` imports, and `DocumentFormat.PDF` and `DocumentFormat.EPUB`.
- [ ] T012 Checkpoint: `make test` passes with `app/` unchanged.
  `git grep -n -E 'write_pdf|write_epub|PdfLoader|EpubLoader' -- tests` lists only these, which US2 deletes:
  - `tests/documents.py`;
  - `tests/unit/test_pdf_loader.py` and `test_epub_loader.py`;
  - `tests/unit/test_extraction_metrics.py`;
  - `tests/integration/test_docling.py`.

**Checkpoint**: The lifecycle, the journal, duplicates, the catalog and progress are tested on
Markdown alone.

---

## Phase 3: User Story 1 - Adding books as Markdown, and only as Markdown (Priority: P1) 🎯 MVP

**Goal**: A `.md` or `.markdown` file goes in as today, titled by its file name and without an
author. A `.pdf` or `.epub` is refused before anything is stored, with the convert-first message,
and the tab's pickers offer only Markdown.

**Independent Test**: User Story 1's test in spec.md: add a Markdown book from the tab and with
`add-book`; try a PDF and an EPUB in the four ways in, and see each refused with nothing changed.
In this phase, `make test`; on the real stack, T047 and T051.

### Tests for User Story 1 (write first, and see them fail)

- [ ] T013 [P] [US1] Rewrite `tests/unit/test_validation.py` (contracts/books.md, Accepted files):
  - **Accepted:** `.md`, `.markdown` and `BOOK.MD`.
  - **`.pdf` refused** with exactly "This is a PDF. Books are Markdown files: convert it to Markdown first, with MarkItDown for example, and add the .md file."; `.epub` the same, with "This is an EPUB.".
  - **Other types refused:** `.docx` with "Unsupported file type '.docx'. Books are Markdown files: .markdown, .md.". A file named only `.md` is refused as an unsupported type.
  - **Unchanged:** the empty file, the size limit, the missing path, binary data, non-UTF-8, and the name cleaning (`safe_filename`). A PDF's bytes saved as `book.md` are refused as binary data.
  - **Deleted:** the PDF signature and EPUB ZIP tests (lines 42 to 72).
- [ ] T014 [P] [US1] In `tests/unit/test_markdown_loader.py` and `tests/unit/test_pipeline.py` (FR-005, research.md R1). Keep every expected chapter, section and chunk text as it is (SC-002).
  - Replace `test_a_single_top_heading_is_the_title`, `test_front_matter_gives_the_metadata` and `test_a_book_without_a_title_uses_the_fallback` with tests that:
    - the pipeline's title is the `title` it is given, whatever the front matter's `title` or a single `#` heading says;
    - `ProcessedDocument` has no `author`;
    - front matter is still removed from the text, and `language`, else `lang`, still sets the language;
    - front matter that doesn't parse, or isn't closed, stays in the text;
    - a file without headings is one chapter titled with the given title;
    - a single `#` heading is still not a chapter.
- [ ] T015 [P] [US1] In `tests/unit/test_book_service.py` and `tests/unit/test_book_lifecycle.py` (FR-002, FR-005, SC-003):
  - **Refusals change nothing.** `add_book` with `book.pdf`, and `replace_book` with `book.epub`, raise `InvalidDocumentError` with T013's messages, and `library_state` and `trace_journal` are identical before and after. The replaced book keeps its revision.
  - **The order of the checks.** With the library lock held, a `.pdf` raises `LibraryBusyError`, not the format's error.
  - **The title is the stem** on every path, and the author is `None` on every one:
    - `add_book` (`01_historia_economica_global.md` gives `01_historia_economica_global`, even with a front-matter `title`);
    - `replace_book` under another name;
    - `reindex_book`;
    - `reindex_all`;
    - and after `reset_index`, the originals brought back.
- [ ] T016 [P] [US1] In `tests/unit/test_interface.py` and `tests/unit/test_commands.py` (FR-004, contracts/books.md, research.md R3):
  - each Library picker has `file_types == [".md", ".markdown"]` and the label "Markdown book (.md, .markdown)";
  - the note under "Add a book" says that books are Markdown files, that a PDF or EPUB is converted first, names MarkItDown, and says that the file's name becomes the title;
  - each picker's `preprocess` of a `FileData` for `book.pdf` raises Gradio's `Error`;
  - `add-book`'s and `replace-book`'s help say Markdown, as contracts/books.md gives them;
  - `add-book` with a `.pdf` exits non-zero and prints the convert-first message.

### Implementation for User Story 1

- [ ] T017 [US1] In `app/ingestion/validation.py` (research.md R2), so that T013 passes:
  - the accepted extensions are `.md` and `.markdown`;
  - a `_CONVERT_FIRST` map gives `.pdf` and `.epub` their messages, verbatim from contracts/books.md;
  - the other-type message becomes "Unsupported file type '{extension}'. Books are Markdown files: .markdown, .md.";
  - `_require_pdf`, `_require_epub`, their constants and the `zipfile` import go;
  - `_require_text` is unchanged.

  `DocumentFormat` keeps its members until T027.
- [ ] T018 [US1] In `app/ingestion/markdown_loader.py`, `app/ingestion/pipeline.py` and `app/services/ingestion_service.py` (research.md R1), so that T014 passes:
  - **The loader** no longer reads `title` or `author`, and `_single_top_heading` goes.
  - **The pipeline.** `process(path, document_format, book_id, title, progress)` uses `title`, a rename of `fallback_title`, always, and ignores any title or author in the extracted document. `ProcessedDocument` loses `author`.
  - **The service.** `IngestionService.ingest` renames its parameter the same way.
  - **Docstrings** say that the title is the stem of the file's name.

  `ExtractedDocument`'s fields go at T028.
- [ ] T019 [US1] In `app/services/book_service.py` and `app/services/library_service.py`, write the author as `None` where `processed.author` was written (line 56), and check that every caller passes `Path(<original_filename>).stem` as the title, so that T015 passes.
- [ ] T020 [US1] In `app/interface/library.py` and `app/main.py` (contracts/books.md), so that T016 passes:
  - **The tab.** Both pickers get `file_types=[".md", ".markdown"]` and the label "Markdown book (.md, .markdown)". A `gr.Markdown` note goes under "Add a book": "Books are Markdown files. Convert a PDF or an EPUB to Markdown first, with MarkItDown for example. The file's name becomes the book's title."
  - **The commands.** The help of `add-book` reads "add a Markdown book (.md, .markdown) to the library", and of `replace-book` "swap a book for a new Markdown file, keeping its ID".
- [ ] T021 [US1] Checkpoint: `make lint` and `make test` pass, and T008 to T016 too.

**Checkpoint**: User Story 1 works on its own. PDF and EPUB code still exists, but nothing reaches
it.

---

## Phase 4: User Story 2 - Nothing left of PDF and EPUB (Priority: P2)

**Goal**: No PDF, EPUB, OCR or Docling code, setting, dependency or test, and no pages. Citations
point to book, chapter and section. The removed settings stop the app at startup. The fingerprint
moves.

**Independent Test**: User Story 2's test in spec.md. In this phase, `make test` and the
repository search of T037. On the real stack, T046 and T047.

### Tests for User Story 2 (write first, and see them fail)

- [ ] T022 [P] [US2] In `tests/unit/test_config.py` (FR-008, FR-014, User Story 2 scenario 2), check that each of these stops loading with a `ConfigurationError` naming the key, added one at a time to a copy of `config/`:
  - a `pdf` section;
  - a `normalization` section;
  - `page_numbers: true` under `chunking.preserve`.

  Also check that `config/ingestion.yaml` as shipped loads.
- [ ] T023 [P] [US2] In `tests/unit/test_index_service.py` (FR-015, research.md R7):
  - the configuration's `metadata_schema` is 2;
  - its `chunking` holds no `page_numbers`;
  - an index recorded with the old fingerprint needs a reindex: `needs_reindex()` is true, and `require_writable` raises `ReindexRequiredError`.
- [ ] T024 [P] [US2] Remove pages from the ingestion and storage tests (data-model.md), keeping every expected text (SC-002):
  - `tests/fakes.py`: `make_chunk` without `page_start` and `page_end`;
  - `tests/unit/test_chunker.py`: delete the page tests at lines 60 to 83, and drop the pages from the one at line 111;
  - `tests/unit/test_chunk_store.py`: the null test checks a null section only, and the page-range test goes;
  - `tests/unit/test_normalizer.py`: only the cleaning tests stay (NFC, ligatures, invisible characters, whitespace), and the margin and page-merge tests go, with `NormalizationConfig`;
  - `tests/unit/test_structure_extractor.py`: line 173 uses `DocumentFormat.MARKDOWN`, and its author goes;
  - `tests/unit/test_html_blocks.py`: the two anchor tests go, and the others read `html_to_blocks(html)` as returning the blocks alone.
- [ ] T025 [P] [US2] Remove pages from the generation and retrieval tests (`contracts/passages.md`):
  - `tests/unit/test_citations.py`: a reference is "book, chapter, section", and there is no `pages`;
  - `tests/unit/test_question_answering.py`: the passage header holds no `Pages:`, and `test_formats_without_pages_leave_them_out` goes;
  - `tests/unit/test_filters.py`: the page ranges go;
  - `tests/unit/test_bm25.py`: no `page_start` arguments;
  - `tests/unit/test_summarization.py`: references are `- [n] <section>: “<excerpt>”`;
  - `tests/unit/test_quiz_service.py`: `_reference` without pages, lines 111 and 879;
  - `tests/integration/test_quiz.py`, line 77: no `page_start`.

  The quiz's page-mention check and the writer prompt's wording stay tested as they are (FR-016).
- [ ] T026 [P] [US2] Remove pages, OCR, the extraction kind and Docling from the interface, command, benchmark and service tests:
  - `tests/unit/test_interface.py`: `SCORE_COLUMNS` without "Pages", and the sources, passages and `quiz_reference` without pages;
  - `tests/unit/test_commands.py`: `search --page-start 1` is refused by argparse, and the output reads `<chunk_id> (<chapter>, <section>) …`;
  - `tests/unit/test_benchmark.py`: retrieval rows without `relevant_pages`, quiz reading rows without `pages`, and an experiment of kind `extraction` refused, naming the allowed kinds;
  - `tests/unit/test_progress.py`: the OCR tests at lines 167 and 312 go, and the counted test stage's unit is "chunks";
  - `tests/unit/test_health_service.py`, `test_a_missing_gpu_is_reported`: the message is exactly "no GPU visible to the application: the reranker stays on the CPU".

### Implementation for User Story 2

- [ ] T027 [US2] Remove the PDF and EPUB readers (FR-007, data-model.md):
  - **Deleted modules:** `app/ingestion/pdf_loader.py`, `epub_loader.py` and `docling_loader.py`.
  - **`DocumentFormat`** keeps `MARKDOWN` only.
  - **`app/storage/repositories.py`**: the extension map is `{MARKDOWN: ".md"}`.
  - **`app/container.py`**: `_build_loaders` returns `{DocumentFormat.MARKDOWN: MarkdownLoader()}`.
  - **`app/errors.py`**: `ScannedDocumentError` goes, and `InvalidDocumentError`'s docstring says "is not a readable Markdown file".
  - **Deleted tests:** `tests/unit/test_pdf_loader.py`, `test_epub_loader.py` and `tests/integration/test_docling.py`. The PDF and EPUB writers in `tests/documents.py` go, and the module too if nothing is left in it.
- [ ] T028 [US2] Slim the ingestion types (data-model.md, research.md R1, R15), so that T024 passes:
  - **`app/ingestion/base.py`**: `Block` loses `page_start`, `page_end` and `margin`; `ExtractedDocument` loses `title` and `author`; `DocumentLoader.load(path)` loses `stage`; `comparable_text` goes. `ORDINAL` stays.
  - **`app/ingestion/html_blocks.py`**: `anchors`, the positions it returns and the `XMLParsedAsHTMLWarning` filter go, and `html_to_blocks` returns the blocks.
  - **`app/ingestion/markdown_loader.py`** follows.
  - **`app/ingestion/structure_extractor.py`**: `BookStructure` loses `author`, `build_structure(document, title)` takes the title, and `_WHOLE_BOOK_TITLE` goes.
  - **`app/ingestion/pipeline.py`** calls `self._loaders[...].load(path)` inside the extraction stage, and `build_structure(replace(normalized, language=language), title)`.
- [ ] T029 [US2] Remove the PDF settings and cleaning (FR-008, research.md R6), so that T022 passes:
  - **`app/config/settings.py`**: `PdfConfig`, `PdfOcrConfig`, `NormalizationConfig`, `Settings.pdf`, `Settings.normalization` and `ChunkPreservation.page_numbers` go.
  - **`config/ingestion.yaml`** keeps `languages` and `chunking`, with `preserve` holding `chapters`, `sections` and `paragraphs`.
  - **`app/ingestion/normalizer.py`**: `Normalizer()` takes no configuration. `_drop_running_margins`, `_printed_page_offsets`, `_offsets`, `_roman_value`, `_margin_key`, `_merge_across_pages`, `_continues` and their constants go. `_clean` stays.
  - **`app/container.py`** builds `Normalizer()`.
  - **`app/evaluation/benchmark.py`**: `index_key` loses its `extraction` entry.
- [ ] T030 [US2] Remove pages from chunks and the index (FR-014, FR-015, research.md R7), so that T023 passes:
  - **`app/ingestion/chunker.py`**: `Chunk` and `_Piece` lose `page_start` and `page_end`, and the page collection goes.
  - **`app/services/index_service.py`**: `METADATA_SCHEMA_VERSION = 2`.
  - **`app/storage/chroma.py`** follows on its own, through `_CHUNK_FIELDS`. Check it.
- [ ] T031 [US2] Remove pages from what is shown, sent and filtered (`contracts/passages.md`), so that T025 and T026 pass:
  - `app/generation/citations.py`: `Citation` loses `page_start`, `page_end` and `pages`, and `reference` is book, chapter, section;
  - `app/generation/prompts.py`, `_describe`: no `Pages:`;
  - `app/generation/summarization.py`, `_with_references`: the section and the excerpt;
  - `app/retrieval/base.py` and `app/retrieval/dense.py`: the page range and its conditions go;
  - `app/main.py`: `search` loses `--page-start` and `--page-end`, and prints `({chunk.chapter_title}, {chunk.section_title})`, leaving out a missing section;
  - `app/interface/formatting.py`: `pages_of` and `quiz_pages` go, "Pages" leaves `SCORE_COLUMNS` and `score_rows`, and the passages and `quiz_reference` show book, chapter, section;
  - `app/services/quiz_service.py`, `_reference`;
  - `app/evaluation/benchmark.py`: `_relevant_places` drops `relevant_pages`, and the reading row (line 772) drops `pages`;
  - `app/evaluation/quiz_metrics.py`: `READING_FIELDS` drops `pages`, and an older `reading.csv` that has it is still read.

  Keep `_PAGE_NUMBER` in `app/generation/quiz.py`, and the quiz writer's "Don't ask about page numbers" (FR-016).
- [ ] T032 [US2] Progress without pages or OCR (FR-011, research.md R8):
  - **`app/services/ingestion_service.py`**: `INGEST_STEPS`' extraction becomes `StageSpec(EXTRACT, "Extracting the text")`.
  - **`app/utils/progress.py`**: `Stage.uncount`, `Progress._uncount`, the state's `ocr` and the `ocr` log field go, and the module docstring no longer says that a loader counts pages.
- [ ] T033 [US2] Remove the extraction kind (FR-017, research.md R15):
  - in `app/evaluation/benchmark.py`, `"extraction"` leaves `Experiment.kind`, and `_run_extraction`, `_EXTRACTION_METRICS`, its `match` arm and the `extraction_scores` import go;
  - `app/evaluation/extraction_metrics.py` and `tests/unit/test_extraction_metrics.py` are deleted.
- [ ] T034 [US2] Remove the remaining mentions (FR-012):
  - in `app/services/health_service.py`, the GPU line without a GPU reads "no GPU visible to the application: the reranker stays on the CPU";
  - in `docker-compose.yml`, the comment at line 96 names the reranker only.

  Then `git grep -n -i -E '\b(pdfs?|epubs?|ocr|docling|pymupdf|fitz|ebooklib)\b' -- app config docker-compose.yml Dockerfile Makefile` lists only T017's refusal messages. Reword any docstring or comment it finds.
- [ ] T035 [US2] Remove the dependencies (FR-009, research.md R9):
  - In `pyproject.toml`, `ebooklib` and `pymupdf` leave `dependencies`, and the `docling` extra goes, with its `torchvision`. `torch` stays in `reranking`.
  - Run `uv lock`, with the bump still stashed, then `uv sync`.
  - Record in Notes every package the lock drops, from `git diff -- uv.lock`, and check that none of `docling`, `pymupdf`, `ebooklib`, `pypdfium2`, `rapidocr` or `torchvision` is left. Commit nothing else from the stash.
- [ ] T036 [US2] Delete `devtools/measure_library_progress.py` and `tests/unit/test_progress_devtool.py` (FR-010, research.md R15).
- [ ] T037 [US2] Checkpoint:
  - `make lint` and `make test` pass;
  - `git grep -n -E 'page_start|page_end|pages_of|quiz_pages|uncount|ScannedDocumentError' -- app tests devtools` finds nothing;
  - `git grep -n -i -E '\b(pdfs?|epubs?|ocr|docling|pymupdf|ebooklib)\b' -- app tests devtools config` lists only the refusal messages and their tests.

  Record the count in Notes.

**Checkpoint**: Nothing of PDF, EPUB or pages is left in the application or its tests.

---

## Phase 5: User Story 3 - The benchmark on Markdown books (Priority: P3)

**Goal**: The dataset names the three Markdown books, with their provenance, and the benchmark
checks them before it runs. `fetch-benchmark-books` is gone. Both retrieval runs are compared
question by question.

**Independent Test**: User Story 3's test in spec.md: `validate-benchmark` on the Markdown
dataset, the retrieval experiment in a fresh workspace, and its paired comparison with T006's
run (T048, T049).

### Tests for User Story 3 (write first, and see them fail)

- [ ] T038 [P] [US3] In `tests/unit/test_dataset.py` (data-model.md, `BenchmarkBook`):
  - the new schema loads: `filename` and `sha256` of the Markdown, `original: {url, sha256}` and `conversion`;
  - a `books.yaml` with a top-level `url` is refused, and the error names it;
  - `dataset_checksum` changes when a book's `sha256` does;
  - the `fetch_books` tests, and their `respx` mocks, go.
- [ ] T039 [P] [US3] In `tests/unit/test_benchmark.py` (contracts/benchmark.md, FR-018), check that `run()` and `validate()` stop before any work, writing no results directory, in two cases:
  - a dataset book is missing: "<key>: benchmarks/books/<filename> is missing. The benchmark's books are Markdown conversions that the owner makes: see README, Benchmarks.";
  - its sha256 differs: "<key>: <path> isn't the file the dataset names: its sha256 is <x>, not <y>. Its evidence quotes may not be found in it.".

  Local books keep their check.
- [ ] T040 [P] [US3] Write `tests/unit/test_compare_runs.py`, loading `devtools/compare_runs.py` with `importlib` (contracts/benchmark.md, FR-020). On two made-up `results.json` dicts:
  - each run's `default` variant is renamed by `--labels`;
  - a question whose `relevant_chunks` is empty in either run is left out of the pairing, and listed and counted;
  - each metric's difference equals `app.evaluation.report.paired_difference` on the merged rows;
  - the questions whose Recall@5, MRR or nDCG@10 moved are listed with both values and both `relevant_chunks`;
  - two runs with no question in common, a run with two variants, or a run that isn't a retrieval run each stop with an error.
- [ ] T041 [P] [US3] In `tests/unit/test_commands.py`: `fetch-benchmark-books` is refused by argparse as an unknown command.

### Implementation for User Story 3

- [ ] T042 [US3] In `app/evaluation/dataset.py` (data-model.md, research.md R11), so that T038 passes:
  - `BenchmarkBook` gets `original: BookOrigin` (`url: str`, `sha256: str`) and `conversion: str`, and loses `url`;
  - `fetch_books` and the `httpx` import go;
  - the module docstring says that the books are the owner's Markdown conversions, checked by their sha256.
- [ ] T043 [US3] In `app/evaluation/benchmark.py`, add `_check_books(experiment)`, so that T039 passes. It checks every dataset book and every local book of the experiment, for presence and sha256, with contracts/benchmark.md's messages. It is called first in `run()`, and for the dataset's books at the start of `validate()`. It replaces `_check_local_books`.
- [ ] T044 [US3] In `app/main.py`, remove the `fetch-benchmark-books` subcommand and its handler, so that T041 passes.
- [ ] T045 [US3] Write `devtools/compare_runs.py`, so that T040 passes (contracts/benchmark.md, research.md R13). It has a module docstring saying what it compares and how to run it, and these arguments: two results directories and `--labels BASELINE CHANGED`.
  - It merges both runs' rows under the new labels, and recomputes the summaries with `app.evaluation.benchmark.summarize`, by category and by book too.
  - It renders them with `app.evaluation.report.render(merged, baseline=<BASELINE>)`.
  - Before that rendering, it writes each run's environment line, then the questions left out, by ID.
  - After it, it writes the table of the questions that moved.

**Checkpoint**: `make lint` and `make test` pass, and the benchmark code is ready for the Markdown
dataset.

---

## Phase 6: Polish & Cross-Cutting Concerns (on the real stack)

**Purpose**: The feature on the converted books and the real models, the comparison, and the
records.

- [ ] T046 Rebuild with this branch's code (quickstart.md § 4). First check that T006 and T007 are done, and run `book-rag list-books`.
  - `make up`, **which deletes the library the app container holds**, then `reset-everything --confirm "DELETE EVERYTHING"` and `doctor`, which reports no failure, with a GPU line naming the reranker only (SC-006, FR-012).
  - **SC-004.** Record the image's size beside T002's, and check that `docling`, `pymupdf`, `ebooklib`, `torchvision`, `pypdfium2` and `rapidocr` are absent.
  - **The removed settings in the container.** Run the three checks of quickstart.md § 4 on a copy of `/app/config` with `CONFIG_DIR`. Each stops, and names its key (User Story 2 scenario 2).
- [ ] T047 Compare the chunks on this branch's image with `main`'s (SC-002, quickstart.md § 5).
  - Run `dump_chunks.py` on the four Markdown books, copy the output to `benchmarks/results/chunks-branch/`, and `cmp` each file with T007's.
  - Every file must be identical. If one differs, `diff` it, stop, and report.
  - Record the result in Notes.
- [ ] T048 Make the dataset Markdown, and validate it (FR-018, FR-019, quickstart.md § 7).
  - **On the host, `benchmarks/datasets/books.yaml`.** Write the new schema: the Markdown files' names and sha256s from T001, the originals' URLs and sha256s from the current file, and `conversion` holding "MarkItDown 0.1.9 (microsoft/markitdown ed17895), Python 3.14.7, plugin markitdown-pdf-headings 0.2.0 (guimassoqueto/markitdown-pdf-headings f10b81b, PDFs only); command: markitdown --use-plugins BOOK > BOOK.md". Its header comment says that rebuilding the books takes this conversion, and that a newer one makes a new dataset version.
  - **Delete** `benchmarks/experiments/extraction.yaml`.
  - **Validate.** Copy the folder into the container, and run `validate-benchmark`.
  - **Correct each quote and chapter name it lists** to the Markdown text, holding the same evidence, at most 30 words. Expected first: `think_python_factual_05` takes `lexi-con`, and `think_python_chapter_specific_01` takes `n − 1` (research.md R11). Copy the folder in and validate again, until nothing is listed, with all 75 answerable questions kept.
  - **Record** each change, before and after, in Notes.
- [ ] T049 Run the retrieval experiment on the Markdown books (FR-020, quickstart.md § 7).
  - Start from a fresh workspace (`rm -rf /app/benchmarks/workspace`) and pass `--commit "$(git describe --always --dirty)"`. Run it in the background.
  - Copy the results out, and run `uv run python devtools/compare_runs.py <T006's directory> <this one> --labels originals markdown`.
  - For each difference whose interval leaves zero out, read the questions behind it in both runs' `rows.csv`: was the evidence found in each run, and what was retrieved instead?
  - Record the comparison and the reading in Notes.
- [ ] T050 Run `make test-integration` against the stack's models (SC-006). Record passed and skipped in Notes.
- [ ] T051 Check the commands on the real stack (SC-001, SC-003, SC-008, contracts/books.md):
  - **Adding.** Copy the four Markdown books into `/tmp` under their own names, and add each with `add-book`. `list-books` shows each titled by its stem, with an empty author, and its chapters match its headings when read against the file.
  - **Refusing.** Copy `think-python.pdf` and `on-liberty.epub` to `/tmp`. `add-book /tmp/think-python.pdf` and `replace-book book_001 /tmp/on-liberty.epub` are each refused within a second, with the convert-first message. `list-books` is unchanged, and the log shows no operation started for either.
  - **Gone.** `fetch-benchmark-books` is refused.
  - **Reading (SC-008).** On *História econômica global* and *On Liberty*: one `ask` and one `search`, a saved chapter summary (`book-rag summarize … --save`, as `book-rag summarize --help` gives it), and a chapter quiz's pointers. None shows a page, and every citation reads book, chapter[, section].

  Record what was read in Notes.
- [ ] T052 **STOP: the owner's walkthrough in the browser** (quickstart.md § 6, SC-001, SC-003, SC-008), on the stack T051 left. The owner:
  1. opens each picker: the dialog offers only `.md` and `.markdown`, and the note is under "Add a book";
  2. adds one converted book through the tab;
  3. drops `think-python.pdf` on "Add a book", and `on-liberty.epub` on "Change a book" with a book chosen: each is refused at once, and the book list doesn't change;
  4. asks three questions in the Chat tab, on the two books, and reads the sources, the passages and the scores table, which has no Pages column;
  5. reads a chapter quiz's pointers.

  Record the owner's findings in Notes. Fix what they find before going on.
- [ ] T053 [P] Update `README.md` (FR-022, research.md R17). Change these sections:
  - **Library:**
    - the commands use a `.md` that keeps its name on the way into the container;
    - preparing a book: converted outside, with MarkItDown for example, named as it should be titled, headings for chapters and sections with the chapter rules, optional front matter for `language`;
    - what is refused;
    - the title is the file's name, and there is no author.
  - **Following an operation:** extraction without a count, and no OCR or `ocr` field.
  - **Index:** metadata without pages.
  - **Retrieval:** filters without a page range.
  - **Questions, Summaries and Quizzes:** citations and pointers without pages.
  - **Benchmarks:**
    - how the books are made and checked, with their provenance;
    - how to refresh them after a new MarkItDown or plugin;
    - no `fetch-benchmark-books` and no `extraction` kind;
    - where the dataset is recorded (`specs/005-markdown-only/benchmarks/`).
  - **Deployment notes:** the GPU is for the reranker.
  - **Configuration:** `ingestion.yaml` holds languages and chunking.
- [ ] T054 [P] Update `docs/decisions.md` (FR-023, research.md R17, SC-004).
  - **New entries under Ingestion**, each with its reason, and saying that it departs from the first version's spec:
    - Markdown only, converted outside;
    - the title is the file's name, and there is no author;
    - pages are dropped rather than read from markers;
    - the benchmark's books record their conversion, and the plugin fixes that Think Python showed;
    - normalization keeps only the cleaning that applies to any text;
    - the dependencies removed, with both image sizes (T002, T046) and the packages the lock dropped (T035).
  - **Updated in place:** "What an operation counts", since extraction isn't counted, and the line naming `c7bb785` as the dataset's place.
  - **Moved** to a closing section, "Removed with PDF and EPUB (v1.0.0)", one line each with the failure that taught it: running heads by page numbers; table-of-contents entries claiming one heading; outline headings never taken for running heads; Docling with OCR.
  - **Kept** under Evaluation: *Think Python*'s coverage lesson, beside the Docling comparison.
- [ ] T055 [P] Update `docs/benchmark-results.md`:
  - mark the Extraction section as measured on PDF and EPUB before v1.0.0 (FR-017);
  - add a section on the Markdown books: the conversion, T048's corrections, and both runs with their paired comparison and the reading of T049, as information (FR-020);
  - under Known limitations, note that the quiz experiments still name the PDF until the quiz is removed;
  - point Reproducing to the converted books and to where the dataset is recorded.
- [ ] T056 Record the validated dataset (research.md R19): copy `benchmarks/datasets/books.yaml`, `questions.jsonl` and `chapter_key_points.jsonl` into `specs/005-markdown-only/benchmarks/datasets/`, and `benchmarks/experiments/markdown_books.yaml` into `specs/005-markdown-only/benchmarks/experiments/`. Check that `git diff --no-index` against `git show c7bb785:benchmarks/datasets/questions.jsonl` shows only T048's changes.
- [ ] T057 Search the repository (SC-005, quickstart.md § 9). Run its `git grep` with the listed exclusions, and the pages search over `README.md`, `app/main.py` and `app/interface`. Only refusal and conversion mentions are left, plus the quiz's page rule. `git grep -n -i -E 'docling|pymupdf|ebooklib|pypdfium|rapidocr' uv.lock` finds nothing. Fix what is left.
- [ ] T058 **STOP: the constitution's amendment** (research.md R19). The owner runs `/speckit-constitution`, for a PATCH that names `specs/005-markdown-only/benchmarks/` where the Development Workflow names `c7bb785` as the dataset's last version. Wait for it, and check that `git diff` touches only `.specify/memory/constitution.md`.
- [ ] T059 Final check:
  - `make lint-check` and `make test` pass;
  - quickstart.md is reread against what was done, and corrected where it differs;
  - every checklist item is still `[x]`;
  - the plugin's commit `f10b81b` is still reachable, or the conversion record names the commit that replaced it (research.md R11).

  Draft the pull request in Notes:
  - **The title:** `feat!: accept only Markdown books`.
  - **The body:** ends with FR-025's `BREAKING CHANGE:` footer.
  - **After the merge:** the stashed dependency bump is redone as its own `chore:` with `make update` (research.md R10).

  The pull request is opened only when the owner asks.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**:
  - T002 comes before any change under `app/`, `config/`, `pyproject.toml` or `uv.lock`.
  - T006 and T007 need T002, and T007 also T004.
  - T006 must finish before T048 rewrites the host's dataset.
- **Foundational (Phase 2)**: after T001. It blocks US2, which deletes the code the old tests used.
- **US1 (Phase 3)**: after Phase 2.
- **US2 (Phase 4)**: after US1. T027 removes `DocumentFormat` members that US1's T017 stops using.
- **US3 (Phase 5)**: after US2. T042 and T043 can start after Phase 2, but `make test` at its checkpoint needs US2's removals.
- **Polish (Phase 6)**: after US3, in order T046 → T047 → T048 → T049, then T050 to T052. T053 to T055 can go in parallel once T049 is recorded, then T056 → T057 → T058 → T059.

### Within Each User Story

- Tests first, and seen to fail; then the implementation; then the checkpoint.
- Tasks marked [P] touch different files and can run together.

### Parallel Opportunities

- T003 and T005 alongside T002's rebuild, then T006 in the background while T007 runs.
- **Phase 2**: T008, T009 and T010.
- **US1**: T013 to T016 together.
- **US2**: T022 to T026 together. The implementation, T027 to T036, is mostly sequential, since several tasks touch `app/evaluation/benchmark.py` and `app/container.py`.
- **US3**: T038 to T041 together.
- **Records**: T053, T054 and T055.

---

## Parallel Example: User Story 1

```bash
# The tests of User Story 1, together:
Task: "T013 Rewrite tests/unit/test_validation.py"
Task: "T014 Title and front-matter tests in tests/unit/test_markdown_loader.py and test_pipeline.py"
Task: "T015 Refusal, order and title tests in tests/unit/test_book_service.py and test_book_lifecycle.py"
Task: "T016 Picker, note and help tests in tests/unit/test_interface.py and test_commands.py"
```

## Parallel Example: User Story 2

```bash
# The tests of User Story 2, together:
Task: "T022 Removed settings in tests/unit/test_config.py"
Task: "T023 Fingerprint in tests/unit/test_index_service.py"
Task: "T024 Pages out of the ingestion and storage tests"
Task: "T025 Pages out of the generation and retrieval tests"
Task: "T026 Pages, OCR, extraction and Docling out of the interface, command, benchmark and service tests"
```

---

## Implementation Strategy

### Baselines First

1. **T002 rebuilds `main`'s image.** Then T006 runs in the background while T007 dumps the chunks,
   and Phase 2 starts on the host.

### MVP (User Story 1)

2. **Phase 2, then Phase 3.** STOP and validate with `make test`: PDF and EPUB are refused, and
   titles come from file names. That is the change the owner asked for.

### Incremental Delivery

3. **US2**: the removal, pages and the dependencies.
4. **US3**: the benchmark's books and the comparison tool.
5. **Polish**, on the real stack:
   - the rebuild, the identical chunks and the dataset;
   - the comparison, the integration tests and the commands;
   - the owner's walkthrough, the records, the amendment and the pull request's draft.

---

## Notes

- `[P]` means a different file and no dependency on an unfinished task.
- Each checkpoint leaves the app working. Stop at any checkpoint to validate.
- Results stay in `benchmarks/results`, out of the repository. No text of a book enters the
  repository or the log, apart from the dataset's evidence quotes (T056), which were in it until
  `c7bb785`.
