---

description: "Task list for downloading a summary as Markdown"
---

# Tasks: Download a summary as Markdown

**Input**: Design documents from `specs/011-summary-download/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. SC-005 asks for unit tests of each behavior, and research.md R8 lists them.
Two kinds of test task:
- **New-behavior tests** (US1) check the file's text and name, and the tab's button and events.
  They are written first, and fail until US1's implementation.
- **Guard tests** (US2) check that the tab no longer saves, and that saving from the command line
  stays as it was. They pass as soon as US1's tab change is in, and keep passing.

**Organization**: By user story, in priority order. Each story's code is done and unit-tested in
its own phase. Their checks on the stack share one rebuild, which deletes the owner's library, so
they come together after both stories (Phase 5):
- **US1** (P1) builds the file in the service, and replaces the tab's button. On the stack,
  SC-001 to SC-003.
- **US2** (P2) adds no code: the tab writes nothing into the library, and `summarize --save` works
  as on `main`. On the stack, SC-004.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: a different file, and no dependency on an unfinished task.
- **[Story]**: the user story the task belongs to (US1, US2).

## Path Conventions

A single Python project, with `app/` and `tests/` at the repository root (plan.md, Project
Structure). Line numbers are `main`'s at `b85b4cc`, for orientation: names decide.

- **In the Bash tool**, run
  `export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"` before `make` or
  `uv`.
- **`$SCRATCH`** is the session's scratchpad: the book's copy, `main`'s saved files, the throwaway
  check scripts and the downloaded files stay there, out of the repository. It stands for
  quickstart.md's `/tmp`.
- **`make up` recreates the app container**, which deletes the owner's library (`book_001`,
  `02_a_era_das_revolucoes`, 831 chunks), its logs and the reranker's downloaded weights
  (Principle II, quickstart.md § 3). Only T013 runs it, once the owner has confirmed, and
  `reset-everything` and the book's return follow.
- **Commits** happen only when the owner asks. `make up` builds from the working tree, so the
  checks on the stack don't need one.

---

## Phase 1: Setup

**Purpose**: A known starting point, and `main`'s side of SC-004, taken while the running container
is still `main`'s code.

- [X] T001 Check the starting point. The branch is `feat/summary-download`, with only
  `specs/011-summary-download/` added on top of `main` (`git status --short`, `git log main..`),
  and `uv.lock` is `main`'s. With asdf's paths, `make lint-check` and `make test` pass. Note the
  number of unit tests, for the results (T019).
- [X] T002 [P] Before the rebuild, on the running container (quickstart.md § 2). Check with
  `docker compose ps` that it is up; if it is stopped, start it with `docker compose start`, never
  `make up`. Then:
  - copy the book's original out, under its original name, which `source.json`'s
    `original_filename` gives:
    `docker compose cp app:/app/data/original_books/book_001/original.md "$SCRATCH/02_a_era_das_revolucoes.md"`;
  - pick a short chapter (`brief` keeps it to a minute or two with `gpt-oss:20b`), chapter 4 unless
    it is long, and use the same one in T014 and T015. Chapter 4 is the book's list of
    illustrations, so chapter 6, "Prefácio", was used;
  - `docker compose exec app book-rag summarize book_001 <chapter> --type brief --save`, which
    saves a summary into the library that T013's rebuild deletes anyway;
  - keep `ls data/summaries/book_001` and the JSON file's keys
    (`python -c 'import json,sys; print(sorted(json.load(open(sys.argv[1]))))' <file>` in the
    container) in `$SCRATCH/main-saved.txt`.

**Checkpoint**: `$SCRATCH` holds the book's copy, its checksum equal to `source.json`'s
`checksum` (`sha256sum`), and `main-saved.txt`, not empty.

---

## Phase 2: Foundational (Blocking Prerequisites)

None. US1 adds the service method and changes the tab, and US2 adds only guard tests, which need
US1's tab change. Phase 1's outputs are the only thing that has to come first: T002 before T013
rebuilds the container.

---

## Phase 3: User Story 1 - Download the summary the tab shows (Priority: P1) 🎯 MVP

**Goal**: The tab's "Download the summary", disabled until a summary is generated, has the browser
save a Markdown file of the summary it shows, built by `ChapterSummarizer.summary_file`, with its
title, type line, the summary unchanged and the note naming its model (FR-001 to FR-008, FR-015).

**Independent Test**: User Story 1's test in spec.md. In this phase, `make test`. On the stack,
T014 (SC-001 to SC-003).

### Tests for User Story 1 (write first, and see them fail)

- [X] T003 [US1] In `tests/unit/test_summarization.py`, after the save tests, the file's text
  (FR-005 to FR-007; `data-model.md`, `SummaryFile.text`; contracts/summary-file.md, The text).
  Build summaries with the module's `summarizer(...)`, `chapter(...)` and `FINAL`, and vary their
  fields with `dataclasses.replace`. Then `service.summary_file(summary).text`:
  - for the local model: `# The Book, chapter 4: <chapter title>` first, `Brief summary.` after a
    blank line, then `summary.text.strip()` once, then `---` and
    ``Written by `fake-llm`, a local model.``, each block separated by one blank line, and one
    newline at the end;
  - with `language="Portuguese"`: the type line is `Brief summary, in Portuguese.`;
  - with `chapter_title=""`: the title is `# The Book, chapter 4`;
  - with a text that has no `## References` (a summary without citations): the same blocks, and
    no references section;
  - for a cloud model, with the module's `cloud(...)` and `choices(...)` as the existing cloud save
    test builds them: ``Written by `fc-b`, a cloud model from FakeCloud.``;
  - after a failed attempt, `fc-a` rate-limited then `fc-b`, as
    `test_a_saved_summary_records_its_provider_its_failures_and_a_cloud_models_tokens` sets it up:
    the note names `fc-b`, and `fc-a` appears nowhere in the file's text.
- [X] T004 [US1] In `tests/unit/test_summarization.py`, after T003 (one file), the file's name and
  what building it touches (FR-008, FR-009; `data-model.md`, `SummaryFile.name`;
  contracts/summary-file.md, The name). A parametrized test over `book_title`, `book_id`,
  `chapter_number`, `summary_type` and `language`, set with `dataclasses.replace`:
  - the contract table's four rows, `02_a_era_das_revolucoes` to `!!!` with `book_007`;
  - a title in another script (`Война и мир` gives `война-и-мир_chapter_04_brief.md`);
  - a title with a decomposed accent (`"Brás"`) gives the same name as its composed form
    (`"Brás"`);
  - a chapter number of three digits (`chapter_123`);
  - a 300-character title of words: the name is at most 100 characters, ends with
    `_chapter_04_standard_english.md` whole, and its book part ends at a word, with no `-` at its
    end;
  - a 300-character title of one word: cut at the limit, never to nothing.

  Then one test that building the file reads and writes nothing: after `summarize`, note
  `len(llm.calls)`, call `summary_file`, and check that the count is the same and that the
  summary documents' folder under `tmp_path` holds no file.
- [X] T005 [P] [US1] In `tests/unit/test_interface.py`, beside
  `test_a_summary_can_be_generated_and_saved`, the tab (FR-001 to FR-003, FR-013;
  contracts/summarization-tab.md, The tab and Events; `data-model.md`, The Summarization tab's
  values):
  - a button labelled "Download the summary" exists, built with `interactive=False`, and no block
    is labelled "Save the summary";
  - `handler(interface, "summarize")(book.book_id, 1, "brief", "Same as the book")` returns five
    values: the report, the summary's text, a name ending with `_chapter_01_brief.md`, a file text
    that starts with `# ` and holds the summary's text, and a button update with
    `interactive=True`;
  - the download's event, the `BlockFunction` in `interface.fns` whose `targets` hold the button's
    `click`: its `fn` is `None`, its `js` creates a `Blob` and sets `download`, its `inputs` are the
    two hidden boxes, the name's first, its `outputs` are empty, and its `api_visibility` is
    `"private"`;
  - the two hidden boxes are `gr.Textbox` with `visible=False`, and are `summarize`'s third and
    fourth outputs.

### Implementation for User Story 1

- [X] T006 [US1] In `app/generation/summarization.py` (research.md R3 to R5; contracts/summary-file.md):
  - a frozen dataclass `SummaryFile`, next to `ChapterSummary`, with `name` and `text`
    (`data-model.md`, `SummaryFile.name`, `SummaryFile.text`), and a docstring in the module's
    style;
  - `ChapterSummarizer.summary_file(self, summary: ChapterSummary) -> SummaryFile`, after `save`,
    whose docstring says what the file holds and that it reads and writes nothing. It tells local
    from cloud with `self._models.is_cloud_provider(summary.provider)` and names the cloud provider
    with `self._models.label_of(summary.provider)`;
  - module-level helpers after `without_references`, one per rule of the contract: the title, the
    type line, the note, and the name, with its safe parts (NFC, lowercase, runs of non-`isalnum`
    characters to `-`, the book ID when nothing is left) and its 100-character limit, which cuts
    only the book part, at its last `-` within what fits when there is one. A constant for the
    limit, with a comment that gives its reason (research.md R5).

  T003 and T004 pass.
- [X] T007 [US1] In `app/interface/summarization.py` (research.md R2 and R6;
  contracts/summarization-tab.md):
  - `save` becomes `download = gr.Button("Download the summary", interactive=False)`, in its
    place, and `file_name` and `file_text`, `gr.Textbox(visible=False)`, join it;
  - `current` (`gr.State`), `on_save` and the `save.click(..., api_name="save_summary")` event are
    removed, and the `ChapterSummary` import with them if nothing else uses it;
  - `on_generate` builds `file = container.summaries.summary_file(summary)` and returns
    `summary_report(...)`, `summary.text`, `file.name`, `file.text` and
    `gr.Button(interactive=True)`, with its return annotation to match; `summarize`'s outputs
    become `[report, summary_text, file_name, file_text, download]`, its inputs and `api_name`
    unchanged;
  - a module constant holds the download's JavaScript: a function of `(name, text)` that makes a
    `Blob` typed `text/markdown;charset=utf-8`, an object URL to it, and a link with `download` set
    to the name; it appends the link to `document.body`, clicks it, removes it, and revokes the URL
    after a second. Its comment says why the browser makes the file: Gradio's download button
    serves a file from its cache, which the app sweeps after 50 minutes (research.md R1, R2);
  - `download.click(None, inputs=[file_name, file_text], js=<the constant>, api_visibility="private")`.

  T005 passes.
- [X] T008 [US1] In `tests/unit/test_interface.py`, the earlier tests that T007 breaks, found with
  `grep -n '"summarize")\|save_summary\|generated' tests/unit/test_interface.py`:
  - `test_every_primary_operation_is_reachable` no longer lists `save_summary`;
  - `test_a_summary_can_be_generated_and_saved` becomes
    `test_a_summary_can_be_generated_and_downloaded`: it unpacks five values, makes no
    `save_summary` call, and keeps its assertions on the report and the text;
  - the tests that unpack `report, text, generated, _` (such as
    `test_a_cloud_summary_names_its_provider_and_its_tokens`) unpack the five values, and those
    that read `generated.model` or `generated.provider` read the model from the file's note
    instead (``Written by `fc-b`, a cloud model from FakeCloud.``). What each test asserts stays.
- [X] T009 [US1] Checkpoint: `make lint-check` and `make test` pass, with T003 to T005.

**Checkpoint**: The tab offers the download, built by the service, and nothing else in the tab or
the API saves a summary.

---

## Phase 4: User Story 2 - Keeping a summary in the library stays with the command (Priority: P2)

**Goal**: The tab writes nothing into the library, `save_summary` is gone, and `book-rag
summarize --save` and the saved summaries are as on `main` (FR-009, FR-011, FR-013).

**Independent Test**: User Story 2's test in spec.md. In this phase, `make test`. On the stack,
T014's listings and T015 (SC-003, SC-004).

### Tests for User Story 2 (guards)

- [X] T010 [US2] In `tests/unit/test_interface.py`, after T008 (one file):
  - `save_summary` is not among the API names, and `summarize` is, in
    `test_every_primary_operation_is_reachable` or a test beside it;
  - in `test_a_summary_can_be_generated_and_downloaded`, `library.summary_documents.saved()` is
    empty after `summarize` through the tab, as it was after the old test's save of one.

### Implementation for User Story 2

- [X] T011 [US2] Checkpoint: `make test` passes with T010. Nothing is implemented here. Then
  `git diff main -- tests/unit/test_commands.py` prints nothing, and
  `git diff main -- tests/unit/test_summarization.py` adds lines only, so the tests of `save` and
  of `summarize --save` are as on `main` (FR-011).

**Checkpoint**: Saving into the library is the command line's alone, and works as before.

---

## Phase 5: Polish & Cross-Cutting Concerns (on the real stack, and the records)

**Purpose**: Both stories on the real stack, with the owner's book, the local model and a real
browser, then the records and the results.

- [X] T012 Before the rebuild, the owner confirms it: `make up` deletes their library, `book_001`,
  and the summary T002 saved, which T013 restores from T002's copy of the book.
- [X] T013 Rebuild, reset and the book back (quickstart.md § 3):
  - `make up` rebuilds the app image from the working tree and recreates its container. ChromaDB
    and Ollama keep their data, models included;
  - `docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"` deletes the
    emptied library and every `book_chunks_v*` collection;
  - `docker compose cp "$SCRATCH/02_a_era_das_revolucoes.md" app:/tmp/`, then
    `docker compose exec app book-rag add-book /tmp/02_a_era_das_revolucoes.md`;
  - `list-books` shows `book_001` `INDEXED` with 831 chunks, and `doctor` reports no failure.
- [X] T014 The browser check, SC-001 to SC-003, FR-004 and FR-009 (quickstart.md § 4 and § 5;
  research.md R9). First keep `ls -R data/summaries` from the container in `$SCRATCH/before.txt`.
  Then write the throwaway `$SCRATCH/download_check.py` and run it from the repository with
  `uv run --no-project --with playwright python -I "$SCRATCH/download_check.py"`, launching the
  host's Chrome with `chromium.launch(channel="chrome")`. It:
  - opens `http://127.0.0.1:7860`, goes to the Summarization tab, and checks that "Download the
    summary" is disabled and that no "Save the summary" exists;
  - picks `02_a_era_das_revolucoes`, T002's chapter, `brief` and "Same as the book", generates,
    and waits for the summary, allowing several minutes;
  - checks that the button is enabled, starts recording the page's requests (`page.on("request")`),
    clicks it inside `page.expect_download()`, and saves the file into `$SCRATCH`;
  - checks: the suggested name is `02-a-era-das-revolucoes_chapter_<NN>_brief.md`; the file's
    first line is `# 02_a_era_das_revolucoes, chapter <n>: <title>` with the chapter's title as the
    Chapter dropdown shows it; its third line is `Brief summary.`; it ends with `---`, a blank line
    and ``Written by `gpt-oss:20b`, a local model.``, the model the tab's report names; every `##`
    heading and every reference line of the file appear, in the same order, in the text of the
    tab's summary; and the click sent no request to the server;
  - picks another chapter without generating, clicks again, and checks that the same name and the
    same bytes come.

  Then render the file with `markdown_it` (`uv run python`, CommonMark), and check one `h1`, the
  summary's Portuguese `h2` sections and `References`, an `hr` before the last paragraph, the model
  in a `code` element, and no `#`, `---` or `[^` left in the rendered text (SC-002). Then
  `ls -R data/summaries` into `$SCRATCH/after.txt`, and `diff` it with `before.txt`: no difference
  (SC-003). If the script can't run, the owner does § 4 by hand, and reports what they saw.

  If the file is empty or never comes, the hidden boxes' values didn't reach the JavaScript: switch
  them to `visible="hidden"` (research.md R6), record the correction at the end of `spec.md`, and
  run T009 and T014 again.
- [X] T015 [P] SC-004, quickstart.md § 6. Run T002's `summarize --save` on the branch's container,
  and keep the same listing and keys in `$SCRATCH/branch-saved.txt`. `diff` it with
  `main-saved.txt`: no difference. The summary it saves stays in the library with its book.
- [X] T016 [P] In `README.md` (FR-017, research.md R10):
  - the interface table's Summarization row: summarize a chapter in any of the types, and download
    the result as a Markdown file; its own model choice, as in Chat;
  - in Summaries, after the paragraph on where a saved summary goes: the tab's "Download the
    summary" saves a Markdown file on the user's machine, named after the book, the chapter, the
    type and the language asked for, holding a title, the type, the summary with its citations and
    references, and a closing note naming the model that wrote it, local or from its cloud
    provider. Keeping a summary in the library, where `reindex-all --regenerate-summaries` finds
    it, is `summarize --save`'s.
- [X] T017 [P] In `docs/decisions.md`, Generation (FR-018, research.md R10), a new entry after
  "Summaries name their language, and show their headings in it.", titled "The Summarization tab
  downloads a summary, and the browser makes the file.":
  - why the tab downloads instead of saving: a saved summary stays in the app container, which
    `make up` recreates after any change, and which the owner's machine can't open without copying
    it out (Principle II); keeping one in the library stays `summarize --save`'s;
  - why the browser makes the file: Gradio's download button downloads a file it already serves
    from its cache, and the cache sweep (Infrastructure) deletes it after 50 minutes, so a late
    click would fail without a word; built in the page, the file can't expire, and the click
    reaches no server;
  - why the note names the model, and that one only: a downloaded file leaves the tab's report and
    a saved summary's JSON file behind, and a summary is written by one model (Cloud models);
  - the note's form: a closing line after a rule, not Markdown's footnote syntax, which some
    viewers show as written.
- [X] T018 The library (quickstart.md § 7). The book has been back since T013, and T015's summary is
  saved with it. Tell the owner both, and that the copy in `$SCRATCH` can go.
- [X] T019 Add a section "Results of the implementation, <date>" at the end of `spec.md`, as
  `specs/007-retrieval-rows` recorded its results:
  - SC-001 to SC-003: T014's file, its checks, the rendering and the listings, and how the check
    ran, by script or by hand;
  - SC-004: T015's comparison;
  - SC-005: the unit test counts, before (T001) and after;
  - any correction made during the implementation, under "Corrections during implementation".

  Mark the tasks done in this file.
- [X] T020 Final pass: `make lint-check` and `make test`. `git diff main --name-only` lists only
  `app/generation/summarization.py`, `app/interface/summarization.py`,
  `tests/unit/test_summarization.py`, `tests/unit/test_interface.py`,
  `tests/unit/test_provider_kinds.py`, `README.md`, `docs/decisions.md` and files in
  `specs/011-summary-download/`. The history is untouched: the
  quickstart's § 7 `git diff` prints nothing (FR-019). No throwaway script is in the repository.
- [ ] T021 When the owner asks for the pull request: the title is
  `feat: download a summary as Markdown from the Summarization tab`. Its merge makes a minor
  release, v0.11.0, if `git describe --tags --abbrev=0 origin/main`, after `git fetch --tags`,
  still prints `v0.10.3` (`spec.md`, Assumptions). No commit has `!` after its type, and the
  description has no `BREAKING CHANGE` footer. Once it opens, `bd update iss-e25 --external-ref
  gh-<n>`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: first. T002 before T013 rebuilds the container.
- **Foundational (Phase 2)**: none.
- **US1 (Phase 3)**: after T001.
- **US2 (Phase 4)**: after T008, since its guards live in the tests T008 rewrites.
- **Polish (Phase 5)**: after both stories, in order T012, T013, then T014 and T015. T016 and T017
  can come any time after T007. T018 after T015, T019 after T014 and T015, T020 last. T021 waits
  for the owner.

### Within Each User Story

- New-behavior tests first, and they fail: T003 and T004 before T006, T005 before T007.
- T003 before T004, and T008 before T010: one file each.
- T006 before T007, which calls `summary_file`.
- Each story ends with its checkpoint (T009, T011).

### Parallel Opportunities

- T002 beside T001 and the whole of US1: it touches only the running container and `$SCRATCH`.
- T005, in `tests/unit/test_interface.py`, beside T003 and T004, in `tests/unit/test_summarization.py`.
- T014 and T015, after T013: one reads the browser's download, the other the command's files.
- T016 and T017: two documents.

---

## Parallel Example: User Story 1

```bash
# The tests, together, in two files:
Task: "T003 and T004 in tests/unit/test_summarization.py: the file's text and name, nothing touched"
Task: "T005 in tests/unit/test_interface.py: the button, summarize's five outputs, the JavaScript event"

# Then the implementation, in order:
Task: "T006 in app/generation/summarization.py: SummaryFile and summary_file"
Task: "T007 in app/interface/summarization.py: the download button, the hidden boxes, the JavaScript"
```

## Parallel Example: the checks on the stack

```bash
# Once T013 has the book back:
Task: "T014 SC-001 to SC-003: the download in Chrome, its file, its rendering, the library's listing"
Task: "T015 SC-004: summarize --save against main's"
```

---

## Implementation Strategy

### Baseline First

T002 copies the book out and takes `main`'s saved files while the running container is still
`main`'s code, so that T013 can restore the library and T015 has something to compare with.

### MVP (User Story 1)

After T009, the tab downloads the summary it shows, as a file that names its book, chapter, type
and model. That is the feature. Stopping there is a valid state, checked on the stack by T013 and
T014.

### Incremental Delivery

1. Setup: the starting point, the book's copy and `main`'s saved files.
2. US1: the service builds the file, and the tab downloads it.
3. US2: guards that the tab saves nothing and the command line saves as before.
4. Polish: one rebuild, the browser check, the command's check, the records and the results.

Each checkpoint leaves `make lint-check` and `make test` passing.

---

## Notes

- [P] tasks touch different files and don't depend on an unfinished task.
- The line numbers are `main`'s at `b85b4cc`. After earlier tasks, find the code by its names.
- Never edit `specs/001` to `specs/010`, or the bug and assessment records (FR-019).
- The throwaway scripts and the downloaded files stay in `$SCRATCH`, and none is committed.
  Playwright runs from a temporary environment, and nothing is added to `pyproject.toml` or
  `uv.lock`.
- If a test or a check finds something the plan didn't foresee, the plan or the spec is corrected
  first, as "Corrections during implementation" at the end of `spec.md`.
