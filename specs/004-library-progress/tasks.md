---

description: "Task list for the progress of library operations"
---

# Tasks: The progress of library operations

**Input**: Design documents from `specs/004-library-progress/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md),
[checklists/lifecycle-and-measurement.md](checklists/lifecycle-and-measurement.md)

**Tests**: Included. The constitution's Development Workflow asks for automated tests for every
significant component, and FR-011, FR-012 and SC-006 are proved by them. Within each phase, the
tests come first and must fail before the implementation.

**Organization**: Grouped by user story, in priority order. The baseline measurement comes first,
in Setup: it must run on `main`'s code, before anything under `app/` changes (research.md R14).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: a different file, and no dependency on an unfinished task.
- **[Story]**: the user story the task belongs to (US1 to US4).

## Path Conventions

A single Python project, with `app/`, `config/`, `devtools/` and `tests/` at the repository root
(plan.md, Project Structure).

- **In the Bash tool**, run
  `export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"` before `make` or
  `uv`.
- **`make up` recreates the app container, which deletes the library it holds** (principle II).
  Before it, run `docker compose exec app book-rag list-books`: go ahead only if the library is
  empty or the owner agrees. Every task that runs `make up` says so.
- **The measurement** runs in the app container, from `/app`, as
  `python -I /tmp/devtools/measure_library_progress.py`, after
  `docker compose cp devtools/measure_library_progress.py app:/tmp/devtools/` and
  `docker compose cp benchmarks/books/. app:/app/benchmarks/books/`. It takes minutes: run it in
  the background, and copy `app:/app/benchmarks/results` out after it.
- **Commits** happen only when the owner asks.

---

## Phase 1: Setup

**Purpose**: A known starting point, and the baseline of `main`'s code on the real books.

- [ ] T001 Run `make lint-check` and `make test` on `feat/library-progress`, and record the passing test count in this file's Notes, as the baseline. Uses the `Makefile`.
- [ ] T002 Check that the app container runs `main`'s code: `git diff main --stat -- app config` is empty, and a digest of every file under `/app/app` and `/app/config` in the container (`docker compose exec app sh -c 'cd /app && find app config -type f -name "*.py" -o -name "*.yaml" | sort | xargs sha256sum | sha256sum'`) equals the same on the host. Record both, and `docker compose exec app book-rag list-books`, in Notes. If they differ, stop and ask the owner before rebuilding.
- [ ] T003 [P] Write the tests of the measurement's computations in `tests/unit/test_progress_devtool.py`, in the style of `tests/unit/test_default_llm_devtool.py`, on made-up records: SC-002 (a count that reaches its total and never goes back passes; one that stops short or goes back fails), SC-003 (samples taken every quarter second while a time left shows, each counting once; the share within half and double the truth; a sample before 3 s and 10% fails it), SC-004 (equal digests pass, any byte differing fails), SC-005 (medians of three runs; within 5% or 1 s, whichever is larger, passes; the reindex with summaries left out) and SC-009 (the top-level stages' durations within 1 s of the operation's; steps not summed). Load the script with `importlib`, as that test does.
- [ ] T004 Write `devtools/measure_library_progress.py` (research.md R14), so that T003 passes. A module docstring saying what it measures and how to run it, as `devtools/measure_historical_spelling.py` has. Arguments: `--baseline` (call only the API `main` has: no `progress` argument, no import of `app.utils.progress`), `--runs` (default 3), `--books` (default `benchmarks/books`), `--baseline-results` (a baseline's directory, to compare with), `--commit`. It opens an isolated library as `BenchmarkRunner._open` does: `environment.model_copy(update={"data_dir": benchmarks/workspace/progress})` and `assemble(settings, environment, collection_prefix="bench_progress_v")`, never the library (principle II). Each run starts with `reset_everything(CONFIRM_RESET_EVERYTHING)`, then, in this order: add `think-python.pdf`, `historia-economica-global.pdf`, `on-liberty.epub`, `quincas-borba.epub`; process each again; remove *Quincas Borba*; replace *On Liberty* with `quincas-borba.epub`; reindex the library; reset the index; reindex the library (which brings the originals back); reset everything. It records each operation's duration (`durations.csv`) and, after each addition, reprocessing, replacement and reindex, the SHA-256 of each book's `extracted.json`, `normalized.json` and `chunks.jsonl` (`digests.json`). Without `--baseline`, it passes each operation a `Progress()` and samples `snapshot()` every quarter second from a thread (`timeline.jsonl`), and, once, after the runs, adds *On Liberty*, saves the summaries of its two chapters with the fewest passages (`container.summaries.summarize` and `save`), and reindexes with `regenerate_summaries=True`, for SC-002's summary count. It configures logging into the workspace's own `logs` directory with `configure_logging`, and reads the stage lines from there for SC-009. It writes `environment.json` with the fields of `BenchmarkRunner._describe_environment`, built from that module's helpers (`query_gpu`, `_cpu_model`, `_gpu_driver`, `_package_version`, `_TRACKED_PACKAGES`, `OllamaRuntime.version()` and `model_info()` for the embedding model and the LLM), without the dataset's checksum, plus the books' SHA-256 and `--commit`. All of it goes to `benchmarks/results/library_progress_<time>/`, with `report.md` giving SC-002, SC-003, SC-004, SC-005 and SC-009, each pass or fail, when there is a baseline to compare with.
- [ ] T005 Run the baseline, in the background, on `main`'s code (T002): `--baseline --runs 3 --commit "$(git rev-parse --short HEAD)"`, as in quickstart.md § 1. Copy the results out, and record their directory and each operation's median in Notes.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The tracker, the display's formatting and the tab's way of following an operation,
which every story uses.

**⚠️ CRITICAL**: No user story starts until this phase is complete.

### Tests (write first, and see them fail)

- [ ] T006 [P] Write `tests/unit/test_progress.py`, on a fake clock passed as `clock`, covering contracts/progress.md and data-model.md's Rules: a count starts at 0, only grows, and reaches its total; an advance past the total is held at the total and logged as a warning; a total of 0 reads as `done == total == 0`; no time left before the stage has run 3 s and done 10% of its items, nor for a spec with `estimate=False`; with advances at one pace but one ten times slower, every time left after it within half and double the time actually left (FR-006); the time left counts down between advances and stops at 0; the sink is called at each stage's start and end and at the outcome, and while advancing at most once per `interval`; a sink that raises is logged once at warning level, dropped, and the operation goes on and succeeds; a key not declared where it is opened is logged as a warning, shown without a position, and never raised; outside `operation()`, `stage()` and every `Stage` method do nothing and log nothing; an exception through a stage is raised unchanged and the outcome holds the stage's label, and for a step the step's label and the item (`Stage.item(item_id, note)`); `uncount(note)` drops the count from the view, keeps it for the log line, and logs `ocr: true` when the note says OCR; each stage line ("stage finished" or "stage failed") carries `stage`, `duration_seconds`, and `done`, `total`, `unit` only when counted, `within` and `item` only for a step, and no other field; `snapshot()` returns None before the operation, a frozen view while it runs, and a view with an `outcome` after.
- [ ] T007 [P] Add to `tests/unit/test_interface.py` the tests of the display's formatting (FR-002, contracts/library-tab.md, contracts/commands.md): elapsed 38 s reads `0:38`, 3725 s reads `1:02:05`; a time left of 12.1 s reads "about 15 s left", 59 s "about 60 s left", 61 s and 89 s "about 1 min left", 91 s "about 2 min left", 0 "almost done"; a counted stage gives `<progress value="130" max="244">` and "130 of 244 pages", an uncounted one `<progress>` without `value`, and a count of 0 "0 of 0" with `value` equal to `max`; a reindex view shows the stage line, the step line and the `meanwhile` line; the starting line "Adding a book: starting"; each outcome line of contracts/library-tab.md's table, the reindex failure with the item and the step; `progress_text` gives contracts/commands.md's lines, `done` and `failed while …` included.
- [ ] T008 [P] Add to `tests/unit/test_interface.py` the tests of `follow()` (research.md R2, R3): it runs the call in a daemon thread; it yields the snapshot when it changes and at least once a second; it returns the call's result; when the call raises, it yields the final view, then raises the same exception; a generator closed early leaves the call running to its end, its result unread.

### Implementation

- [ ] T009 Write `app/utils/progress.py`, so that T006 passes: `StageSpec` (`key: str`, `label: str`, `unit: str | None`, `estimate: bool`, `steps: tuple[StageSpec, ...]`), `StageView`, `ProgressView` (`operation`, `subject`, `stage`, `step`, `elapsed`, `meanwhile`, `outcome`), `Outcome` (`succeeded`, `stage`, `step`, `item`, `error`), `Stage` and `Progress`, exactly as contracts/progress.md and data-model.md give them. The time left is research.md R6's weighted median of seconds per item, shown "once it has run 3 seconds and done 10% of its items", as `max(items left × pace − seconds since the last advance, 0)`. The sink's throttle is R7's. Stage lines are logged with `log_event` (R13), on a logger from `get_logger("progress")`. One `threading.Lock` guards every read and write. Nothing here raises into the caller (R10).
- [ ] T010 [P] Add to `app/interface/formatting.py`, so that T007 passes: `progress_text(view)`, `progress_html(view)`, `starting_html(label)`, the outcome lines of contracts/library-tab.md (one function per operation's success, composed from what the service returns, and one for a failure, from the view's `Outcome`), and `PROGRESS_CSS` for the area's `css_template`. Times and counts in FR-002's forms.
- [ ] T011 Add `follow(call, progress)` to `app/interface/common.py`, so that T008 passes: start `call` in a `threading.Thread(daemon=True)`, poll `progress.snapshot()` every half second, yield it when it changed or a second has passed, then yield the final view and return the result or raise the call's exception.

**Checkpoint**: `make test` passes; nothing calls the tracker yet.

---

## Phase 3: User Story 1 - Adding, replacing or processing a book again, with how much is left (Priority: P1) 🎯 MVP

**Goal**: The Library tab shows the stages, counts and time left of adding, replacing and processing
a book again, disables its buttons meanwhile, and ends with an outcome line.

**Independent Test**: Spec, User Story 1: add *Think Python*, then process it again and replace it,
watching the area (quickstart.md § 4, steps 1 to 4 and 6).

### Tests for User Story 1 (write first, and see them fail)

- [ ] T012 [P] [US1] Add to `tests/unit/test_pdf_loader.py`: given a `Stage` spy, `PdfLoader.load` counts the PDF's pages as its total and advances to it; a scanned PDF with an OCR loader counts every page, then calls `uncount` with a note naming OCR, before handing it over; without a stage it behaves as today (the existing tests pass unchanged).
- [ ] T013 [P] [US1] Add to `tests/unit/test_pipeline.py`: `process(..., progress=...)` inside an operation opens `extract` then `prepare`; a Markdown or EPUB document's `extract` has no count; the `ProcessedDocument` is equal with a `Progress` and without (FR-013).
- [ ] T014 [US1] Add to `tests/unit/test_book_lifecycle.py`, for `add_book`, `replace_book` and `reindex_book` with a `Progress`: the stages of data-model.md's table in order (`store`, `extract`, `prepare`, `embed`, `save` for an addition; the same plus `swap` for a replacement; `extract` to `swap` for a reprocessing), each with its position; `embed` counted to the book's chunk count. With a `Progress` and without, the same catalog rows, files under the data directory, vector counts, and the same sequence of `begin_operation` and `end_operation` calls with the same kinds and details (a spy on the catalog) (FR-011, SC-004). No "undeclared stage" warning in `caplog` for any operation (FR-012). A failure forced in each stage (`originals.store` raising for `store`; the loader raising `InvalidDocumentError` for `extract`; a headings-only document for `prepare`; `FakeEmbedder(failure=...)` for `embed`; `ChunkStore.add` raising for `save`; `BookCatalog.apply` raising for `swap`) raises the same exception, leaves the same state as without a `Progress`, and the outcome names the stage's label (SC-006). A refused addition (a duplicate, a busy library, an index needing a reindex) leaves `snapshot()` None, and retrying a failed file shows no stage before `store` (spec, Corrections from the requirements checklist).
- [ ] T015 [P] [US1] Add to `tests/unit/test_interface.py`, with the existing `interface` fixture: the `add_book`, `replace_book` and `reindex_book` handlers are generators whose yields are the area's HTML with a stage line, ending with the outcome line; a refused call yields an empty area and raises `gr.Error`; for each of the three buttons, a private event sets the seven buttons `interactive=False` and the area to the starting line without touching the inputs, the handler keeps its `api_name` with `show_progress="hidden"`, and private events on its `success` and `failure` set the seven buttons `interactive=True`.

### Implementation for User Story 1

- [ ] T016 [P] [US1] Add the optional `stage` argument to `DocumentLoader.load` in `app/ingestion/base.py`, and to `app/ingestion/pdf_loader.py`, `docling_loader.py`, `epub_loader.py` and `markdown_loader.py`. In `PdfLoader.load`, `stage.count(len(document))` before the page loop and `stage.advance()` after each page; before handing a scanned PDF to OCR, `stage.uncount("with OCR")` (research.md R11). So that T012 passes.
- [ ] T017 [US1] Add `progress` to `IngestionPipeline.process` in `app/ingestion/pipeline.py`: open `extract` around the loader, passing it the stage, and `prepare` around normalizing, structure and chunking, with the keys as module constants (`EXTRACT`, `PREPARE`). Without a `Progress`, use `Progress()`, which does nothing outside an operation. So that T013 passes.
- [ ] T018 [US1] Add `progress` to `IngestionService.ingest` in `app/services/ingestion_service.py`: pass it to the pipeline; open `embed` with `count(len(chunks))` and `on_batch=stage.advance`; open `save` around `store.add` and the count check. Define there `INGEST_STEPS`, the `StageSpec`s of `extract` ("Extracting the text", unit `pages`, `estimate=True`), `prepare` ("Preparing the passages"), `embed` ("Embedding the passages", unit `passages`, `estimate=True`) and `save` ("Saving to the index"), as data-model.md names them.
- [ ] T019 [US1] Add `progress` to `add_book`, `replace_book` and `reindex_book` in `app/services/book_service.py`, defaulting to `Progress()`. Inside `operation()` and the journal entry, after the checks (research.md R9, spec FR-017), begin `progress.operation(label, stages, subject=book_id)`, with the labels as module constants ("Adding a book", "Replacing a book", "Processing a book again"); open `store` ("Storing the file", or "Storing the replacement") around storing the original and cataloging it, and `swap` ("Swapping in the new version") around applying the new revision and dropping the old one. The removal of an earlier failed attempt stays where it is, before the progress. So that T014 passes.
- [ ] T020 [US1] In `app/interface/library.py`: add the area, a `gr.HTML` with `css_template=PROGRESS_CSS`, under `status` and above `table`, and add it to `LibraryTab`; add a helper that wires a button's chain of contracts/library-tab.md (disable with the starting line, `queue=False`; the handler with `show_progress="hidden"` and today's `api_name`; enable on `success` and `failure`), and use it for Add, Replace and Process again; turn `on_add`, `on_replace` and `on_reindex_book` into generators that validate input as today, run the service call through `follow()` with a `Progress()`, yield `progress_html`, and end with the outcome line and today's notification. Keep each handler's event in `changes`. So that T015 passes.
- [ ] T021 [US1] Run `make lint` and `make test`.

**Checkpoint**: Adding, replacing and processing a book again show their progress in the tab; the
other four operations work as before.

---

## Phase 4: User Story 2 - Reindexing the library, book by book (Priority: P2)

**Goal**: A reindex shows each book with its steps, the switch, and the summaries, and a failure names
the book and the step.

**Independent Test**: Spec, User Story 2 (quickstart.md § 4, steps 5 and 9).

### Tests for User Story 2 (write first, and see them fail)

- [ ] T022 [P] [US2] Add to `tests/unit/test_library_rebuild.py`, for `reindex_all` with a `Progress`: `adopt` only when originals were brought back, already done with their count, its line logged; `books` counted to the number of books, without a time left, its note each book's title, its steps `extract` to `save` with `within` and `item` in their log lines; `switch`; `summaries` only when chosen, counted to the saved summaries whose chapter remains, "0 of 0" when none does, its note the summarizer's messages; the view's `meanwhile` set. With a `Progress` and without, the same catalog rows, collections, files and journal calls. A book with a working version that fails while embedding: the same exception, the same state, and the outcome's `stage`, `step` and `item` are "Indexing the books", "Embedding the passages" and the book's ID and title (FR-004). A book with nothing to lose that fails: the count goes on to the next book. A summary that fails: the count goes on. An empty library: refused, `snapshot()` None.
- [ ] T023 [P] [US2] Add to `tests/unit/test_interface.py`: the `reindex_all` handler yields the area with the `meanwhile` line, and ends with the outcome line and today's notifications and warnings; its button has the chain of T015.

### Implementation for User Story 2

- [ ] T024 [US2] In `app/services/library_service.py`, replace `on_progress` with `progress` in `reindex_all`, defaulting to `Progress()`. After the checks, begin `progress.operation("Reindexing the library", stages, meanwhile="Questions keep working on the current index meanwhile.")`, with `adopt` ("Bringing back kept originals", unit `originals`) only when some were adopted, opened and counted at once; `books` ("Indexing the books", unit `books`, `estimate=False`, `steps=INGEST_STEPS`) opened after `begin_operation`, with `stage.item(book.book_id, book.title)` before each book and `stage.advance()` after it, passing `progress` to `ingest`; `switch` ("Switching to the new index") around `finish_rebuild` to `end_operation`; `summaries` ("Writing the summaries again", unit `summaries`, `estimate=False`) only when chosen, counted once the chapters are known, passing `on_progress=stage.note` to the summarizer. So that T022 passes.
- [ ] T025 [US2] In `app/interface/library.py`, turn `on_reindex_all` into a generator like T020's, and wire its button's chain. So that T023 passes. Run `make lint` and `make test`.

**Checkpoint**: The reindex follows each book; US1 still passes.

---

## Phase 5: User Story 3 - Removing a book and resetting, without a guess (Priority: P3)

**Goal**: The removal and the two resets show their steps by name, with the moving bar, and end with
their outcome lines.

**Independent Test**: Spec, User Story 3 (quickstart.md § 4, step 7).

### Tests for User Story 3 (write first, and see them fail)

- [ ] T026 [P] [US3] Add to `tests/unit/test_book_lifecycle.py` (removal) and `tests/unit/test_library_rebuild.py` (resets): with a `Progress`, the steps of data-model.md's table in order, uncounted ("Moving its original to the archive" when archiving, "Deleting its original" otherwise; "Keeping a record of the originals" for the index reset, "Deleting the originals" for the full one); with and without a `Progress`, the same files, rows, collections and journal calls; a failure forced in each step (the store, `processed.delete` or `delete_all`, `summaries.delete` or `delete_all`, the originals, the catalog) raises the same exception, leaves the same state, and recovery then finishes it as without a `Progress`; a wrong confirmation leaves `snapshot()` None. `tests/unit/test_recovery.py` passes unchanged.
- [ ] T027 [P] [US3] Add to `tests/unit/test_interface.py`: the `remove_book`, `reset_index` and `reset_everything` handlers yield the area, end with the outcome line and an empty confirmation box, and a wrong confirmation raises `gr.Error` with an empty area; their buttons have the chain of T015.

### Implementation for User Story 3

- [ ] T028 [US3] Add `progress` to `LibraryData.delete_book` and `LibraryData.clear` in `app/services/library_data.py`, opening one stage per step, with the keys and labels of data-model.md; recovery keeps calling them without one. Add `progress` to `BookService.remove_book` ("Removing a book") and to `ResetService.reset_index` and `reset_everything` ("Resetting the index", "Resetting everything") in `app/services/book_service.py` and `app/services/reset_service.py`, beginning after the confirmation, inside the lock, `operation()` and the journal entry, and declaring the steps. So that T026 passes.
- [ ] T029 [US3] In `app/interface/library.py`, turn `on_remove`, `on_reset_index` and `on_reset_everything` into generators with the area and the confirmation box as outputs, and wire their buttons' chains. So that T027 passes. Run `make lint` and `make test`.

**Checkpoint**: All seven operations show their progress in the tab.

---

## Phase 6: User Story 4 - The same progress on the command line (Priority: P4)

**Goal**: The seven commands print the stages and counts to the error stream, and their results on
standard output as today.

**Independent Test**: Spec, User Story 4 (quickstart.md § 5).

### Tests for User Story 4 (write first, and see them fail)

- [ ] T030 [P] [US4] Write `tests/unit/test_commands.py`, calling the handlers of `app/main.py` (`_add_book`, `_replace_book`, `_reindex_book`, `_remove_book`, `_reindex_all`, `_reset_index`, `_reset_everything`) with a container built as `tests/unit/test_interface.py`'s `interface` fixture builds one, an `argparse.Namespace`, and `capsys`: standard output is today's line, exactly; for `reindex-all`, only its report; the error stream has a line per stage reached, in contracts/commands.md's form, ending with `done`; a failing addition ends its error stream with `failed while embedding the passages`.

### Implementation for User Story 4

- [ ] T031 [US4] In `app/main.py`, give the seven handlers a `Progress(sink=..., interval=2.0)` whose sink prints `progress_text(view)` to `sys.stderr`, and pass it to the service; drop `reindex_all`'s `on_progress=print`. So that T030 passes. Run `make lint` and `make test`.

**Checkpoint**: Every story is done; the measurement and the walkthrough remain.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: The real books, the browser, and the records.

- [ ] T032 Rebuild the app with the feature's code and measure it (quickstart.md § 3). `make up` recreates the app container, which deletes the library it holds: run `docker compose exec app book-rag list-books` first, and go ahead only if it is empty or the owner agrees. Then run the measurement without `--baseline`, with `--runs 3 --baseline-results <T005's directory> --commit "$(git describe --always --dirty)"`, in the background, and copy the results out. Record in Notes each criterion's number and verdict (SC-002, SC-003, SC-004, SC-005, SC-009). If SC-003 misses, tune research.md R6's thresholds or pace in `app/utils/progress.py`, with T006's tests, record the change in research.md R6, and measure again. A miss on SC-004 or SC-005 stops the feature until its cause is found.
- [ ] T033 Check the commands and the log on the real stack (quickstart.md § 5 and § 6): `book-rag add-book` with the owner's copy of *História econômica global* (`~/Documents/livros/01_historia_economica_global.pdf`, copied into the container), which the library holds after every rebuild, and `book-rag reindex-all`, each with its error stream saved to a file; then the stage lines in `/app/logs/app.jsonl`. Record in Notes the number of count lines per stage against SC-008's bound, and that no line holds a title, a file name or text from a book.
- [ ] T034 **STOP: the owner walks through quickstart.md § 4 in the browser** at `http://localhost:7860`, since Gradio's API can't render the area, and reports each step. The removal and the resets delete what the library holds: the owner decides when. If step 6 shows the outcome line covered by an error state, add the fallback of contracts/library-tab.md (the enabling event on `failure` sets the area again) to `app/interface/library.py`, with a test in `tests/unit/test_interface.py`, and repeat step 6. Record the walkthrough in Notes.
- [ ] T035 [P] Update `README.md`: under "Library" and "Changing the library", the progress area (its stages, counts, time left, starting and outcome lines, the disabled buttons, what it doesn't show); in "Running", or wherever the commands' output is described, the commands' progress on the error stream and `reindex-all`'s standard output; and the stage lines in the app's log, with their fields (FR-019).
- [ ] T036 [P] Update `docs/decisions.md`, under "Library lifecycle": what is counted and what isn't, and why, with the spec's measurements and T032's; the time left from a weighted median, and its thresholds; the operation in a thread of its own, followed by polling, and why not Gradio's progress bar or a generator service; the buttons' chain, since `then` doesn't run after an error; the removal of a failed attempt before the progress; `reindex-all`'s progress moved to the error stream (FR-019).
- [ ] T037 Run `make lint-check` and `make test`, read quickstart.md once more against what was built, and record the final test count in Notes.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none. T005's baseline must have finished before T032's `make up`, which
  is the first time the container gets the feature's code: edits on the host don't reach it before.
- **Foundational (Phase 2)**: needs T001, and T002 done before any file under `app/` changes. It
  blocks every story.
- **US1 (Phase 3)**: needs Foundational.
- **US2 (Phase 4)**: needs US1, for `INGEST_STEPS` and the ingestion's stages (T017, T018).
- **US3 (Phase 5)**: needs Foundational and T020's chain helper; independent of US2.
- **US4 (Phase 6)**: needs the service changes of US1 to US3 for its seven commands.
- **Polish (Phase 7)**: needs every story. T034 waits on the owner.

### Within Each Story

- Tests are written first, and fail before the implementation.
- The loaders before the pipeline, the pipeline before the ingestion service, the services before
  the tab and the commands.
- Runs on the real stack come last, in Polish.

### Parallel Opportunities

- **Setup**: T003 beside T001 and T002.
- **Foundational**: T006, T007 and T008; then T010 beside T009.
- **US1**: T012, T013 and T015; then T016 beside the tests' authors.
- **US2 and US3**: their tests, T022, T023, T026 and T027, once US1 is done. They touch the same
  files (`test_library_rebuild.py`, `test_interface.py`, `library.py`), so one merges the other's
  changes.
- **Polish**: T035 and T036.

---

## Parallel Example: User Story 1

```bash
# The tests, together:
Task: "PdfLoader page count tests in tests/unit/test_pdf_loader.py"      # T012
Task: "Pipeline stage tests in tests/unit/test_pipeline.py"              # T013
Task: "Library tab handler tests in tests/unit/test_interface.py"        # T015

# Then, beside the services:
Task: "The loaders' stage argument in app/ingestion/"                    # T016
```

---

## Implementation Strategy

### Baseline First

1. Phase 1, T002 before any change under `app/`, and T005 on the container's `main` code, in the
   background, while Phase 2 starts on the host.

### MVP (User Story 1)

2. Phase 2, then Phase 3. **STOP and validate**: `make test`, and the add handler's yields in a unit
   test. An addition is what the owner does most.

### Incremental Delivery

3. US2, the reindex, the longest operation.
4. US3, the removal and the resets.
5. US4, the commands.
6. Polish: the measurement against the baseline, the commands and the log on the real stack, the
   owner's walkthrough, the records.

---

## Notes

- `[P]` means a different file and no dependency on an unfinished task.
- A story's checkpoint leaves the app working. Stop at any checkpoint to validate.
- Results stay in `benchmarks/results`, out of the repository. No text of a book enters the
  repository or the log.
