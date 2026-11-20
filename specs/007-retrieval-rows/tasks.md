---

description: "Task list for recording what the retrieval benchmark retrieved"
---

# Tasks: What the retrieval benchmark retrieved

**Input**: Design documents from `specs/007-retrieval-rows/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. SC-006 asks for unit tests of each behavior, and research.md R11 lists them.
Two kinds of test task:
- **New-behavior tests** (US1, US2) check the two lists and the comparison's new table. They are
  written first, and fail until their story's implementation.
- **Guard tests** (US3) check that results written before this change render as they did. They
  pass on `main`'s code, or as soon as US2's reading exists, and they keep passing.

**Organization**: By user story, in priority order. Each story's code is done and unit-tested in
its own phase. Their checks on the stack share one rebuild, which deletes the owner's library, so
they come together after the three stories (Phase 6):
- **US1** (P1) records the two lists in each retrieval row. On the stack, SC-001 and SC-002.
- **US2** (P2) shows what ranked above the evidence in the comparison. Its unit tests use made-up
  results, so it doesn't need US1's code. On the stack, SC-005.
- **US3** (P3) adds no code: results written before render as before. Its tests guard
  `benchmark-report` and the comparison's `not recorded`, which US2 implements. On the stack,
  SC-003 and SC-004.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: a different file, and no dependency on an unfinished task.
- **[Story]**: the user story the task belongs to (US1 to US3).

## Path Conventions

A single Python project, with `app/`, `devtools/` and `tests/` at the repository root (plan.md,
Project Structure). Line numbers are `main`'s at `aa54d1b`, for orientation: names decide.

- **In the Bash tool**, run
  `export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"` before `make` or
  `uv`.
- **`$SCRATCH`** is the session's scratchpad: `main`'s outputs, the throwaway check scripts and
  their outputs stay there, out of the repository. It is quickstart.md's `$OUT`.
- **`$MAIN` and `$FIX`** are `benchmarks/results/markdown_books_20261120T021742092846Z` (`main`'s
  run) and `benchmarks/results/markdown_books_20261120T022603129972Z` (the fix's run, SC-001's
  baseline). `$NEW` and `$OFF` are the two runs of T024.
- **`make up` recreates the app container**, which deletes the owner's library (*História econômica
  global*), its logs, the reranker's downloaded weights and the container's copy of `benchmarks/`
  (principle II, research.md R10). Only T023 runs it, once the owner has confirmed, and
  `reset-everything` follows. The owner adds their book back at T033.
- **The host's `benchmarks/`** is ignored by git. The fix's two result folders are read, never
  written (FR-015). `benchmarks/` goes into the container with `docker compose cp -a`, and only
  the new runs' folders come out.
- **Commits** happen only when the owner asks.

---

## Phase 1: Setup

**Purpose**: A known starting point, and `main`'s side of the comparisons of SC-003 and SC-004,
taken before anything changes.

- [X] T001 Check the starting point. The branch is `feat/retrieval-rows`, with only the `docs:`
  commits of the spec and the plan on top of `main`. `git status --short` is empty, and `uv.lock`
  is `main`'s. With asdf's paths, `make lint-check` and `make test` pass. Note the number of unit
  tests, for the results (T034).
- [X] T002 [P] Record the fix's two result folders, file by file (FR-015, quickstart.md § 2):
  `sha256sum "$MAIN"/* "$FIX"/* > "$SCRATCH/old-runs.sha256"`.
- [X] T003 [P] Run the comparison on `main`'s code, before T015 to T017 change
  `devtools/compare_runs.py`, so that the working tree's `app/` and `devtools/` are still `main`'s:
  `uv run python devtools/compare_runs.py "$MAIN" "$FIX" --labels main fix > "$SCRATCH/compare-main.md"`.
  It lists four questions that moved, as `docs/benchmark-results.md` records. To take it again
  later, run the same command from a worktree of `main`, on absolute paths.
- [X] T004 [P] Render the fix's two runs with `benchmark-report` on `main`'s code (quickstart.md
  § 2). The running app container is v0.6.1's image, whose `app/` is `main`'s, with the owner's
  library: check it with `docker compose ps`. If it is stopped, start it with
  `docker compose start`, never `make up`. Then:
  - `docker compose cp -a benchmarks app:/app/`, which touches no book of the library;
  - for each of `$MAIN` and `$FIX`, `docker compose exec -T app book-rag benchmark-report <run>`
    into `$SCRATCH/report-main-<folder>.md`, and the same with `--baseline default` into
    `$SCRATCH/report-main-<folder>-baseline.md`.

**Checkpoint**: `$SCRATCH` holds `old-runs.sha256`, `compare-main.md` and four `report-main-*.md`,
none of them empty.

---

## Phase 2: Foundational (Blocking Prerequisites)

None. The three stories touch different files: US1 the runner, US2 the devtool, and US3 only
tests. Phase 1's outputs are the only thing that has to come first: T003 before US2 changes the
devtool, and T004 before T023 rebuilds the container.

---

## Phase 3: User Story 1 - Retrieval rows that say what the search returned (Priority: P1) 🎯 MVP

**Goal**: Each retrieval row records its ranking and its context, as chunk IDs in order, in
`rows.jsonl`, `results.json` and `rows.csv`, and its six scores are those lists' (FR-001 to
FR-008).

**Independent Test**: User Story 1's test in spec.md. In this phase, `make test`. On the stack,
T024 to T026 (SC-001, SC-002).

### Tests for User Story 1 (write first, and see them fail)

- [X] T005 [US1] In `tests/unit/test_benchmark.py`, the three files (FR-001, FR-002, FR-004,
  contracts/retrieval-rows.md; `data-model.md`, The retrieval row: `ranking`, `context`). Run
  `retrieval_experiment()` in the `lab`, then:
  - the row of `rows.jsonl`, `results.json`'s `rows[0]` and the row of `rows.csv`, read with
    `csv.DictReader`, hold `ranking` and `context`;
  - in the two JSON files, both are lists of strings, the same in both files;
  - in `rows.csv`, each is the JSON list joined with "; ";
  - they are the row's last two keys, after `rerank_seconds`, in the contract's field order;
  - `summary.csv`'s header holds neither (FR-006).
- [X] T006 [US1] In `tests/unit/test_benchmark.py`, the scores are the lists' (FR-003,
  contracts/retrieval-rows.md, What the lists satisfy). After the `lab`'s run:
  - open the variant's workspace again as the runner does,
    `runner._open(apply_overrides(settings, overrides))`, which indexes nothing;
  - resolve the question's evidence with `relevant_chunks(question, workspace.chunks["a_book"])`;
  - check that `recall_at_k` at 5 and 10, `reciprocal_rank` and `ndcg_at_k` at 10 of the row's
    `ranking`, and `context_precision` and `context_recall` of its `context`, equal the row's six
    scores.
- [X] T007 [US1] In `tests/unit/test_benchmark.py`, the lists as the search returned them (FR-001,
  FR-002; research.md R1):
  - wrap `RetrievalService.search` with `monkeypatch`: it calls the original, then returns its
    result reordered as a reranker would: a chunk that holds no evidence first, the real
    candidates reversed after it, and the passages a slice of them, `candidates[1:3]`. The row's
    `ranking` is those candidates' IDs, and its `context` the slice's, in their order. Its MRR is
    0.5, read from the recorded order;
  - run two variants with `retrieval.reranker.top_k` set to 1: one with reranking off, as
    `retrieval_experiment()`'s, and one with it on, which the `lab`'s `FakeReranker` scores. In
    both rows the context is `ranking[:1]`, and the ranking is longer (US1's scenario 4).

  The `lab`'s book gives three chunks, one per section, and BM25 finds all three for its
  question. So `candidates[1:3]` holds two, and a `top_k` of 1 leaves the ranking longer than the
  context.
- [X] T008 [US1] In `tests/unit/test_benchmark.py`, what stays:
  - in `test_rows_reach_the_disk_before_a_run_fails`, the row already in `rows.jsonl` holds both
    lists (edge case: a run that dies);
  - in `test_a_generation_run_reports_every_answer`, no row holds `ranking` or `context` (FR-007).

### Implementation for User Story 1

- [X] T009 [US1] In `app/evaluation/benchmark.py`, `_run_retrieval` (lines 334–362; research.md
  R1, R2), so that T005 to T008 pass:
  - add `"ranking": ranking` and `"context": context` as the row's last two keys, after
    `"rerank_seconds"` (`data-model.md`, The retrieval row: `ranking`, `context`). They are the
    very lists that the metric calls read, not copies built again;
  - the row's other fourteen fields stay as `data-model.md`, The retrieval row, gives them:
    `variant`, `question`, `book`, `category`, `relevant_chapters`, `relevant_chunks`,
    `recall_at_5`, `recall_at_10`, `mrr`, `ndcg_at_10`, `context_precision`, `context_recall`,
    `retrieval_seconds` and `rerank_seconds`. The search, `_relevant_places` and the metric calls
    don't change (FR-005).
- [X] T010 [US1] In `app/evaluation/benchmark.py`, `_write_csv` (lines 657–664; research.md R3):
  write a list as one cell, its items joined with "; ", the way `_relevant_places` joins
  `relevant_chunks`, and every other value as today (`data-model.md`, The retrieval row:
  `ranking` and `context` in `rows.csv`). No other kind's row holds a list, and neither does
  `summary.csv`, so those files come out byte for byte as before (FR-007, SC-001; `data-model.md`,
  Unchanged: the summaries, and the rows of the other kinds).
- [X] T011 [US1] Checkpoint: `make lint-check` and `make test` pass, T005 to T008 included.
  `git diff main --name-only -- app/` lists only `app/evaluation/benchmark.py`, uncommitted or
  committed.

**Checkpoint**: Every retrieval row records its two lists, and nothing else that the runner writes
changes. The check on the stack waits for Phase 6.

---

## Phase 4: User Story 2 - A comparison that shows what ranked above the evidence (Priority: P2)

**Goal**: `devtools/compare_runs.py` adds "What ranked above the evidence" after "Questions that
moved". For each question that moved, and each run, it shows the ranks that the evidence took and
the chunks that ranked above it. Everything it shows today stays (FR-009 to FR-012).

**Independent Test**: User Story 2's test in spec.md: the unit tests of this phase, on rows whose
rankings are known. On the stack, T029 (SC-005).

### Tests for User Story 2 (write first, and see them fail)

- [X] T012 [US2] In `tests/unit/test_compare_runs.py`, the reading of one run's row (FR-009,
  FR-010; `data-model.md`, The comparison's reading of a run; contracts/compare-runs.md, Cells and
  Examples):
  - give `row()` a `ranking` parameter, added to the row only when it is given, so that today's
    fixtures stay rows written before this change;
  - then, for each case, `compare_runs.ranked_above(row)` returns the pair of cells
    (`evidence at`, `ranked above it`). Take the contract's examples, with `relevant_chunks`
    `e1; e2; e3`:
    - evidence first, with no chunk between its pieces: `1, 2` and `none`;
    - evidence below other chunks: `3, 7` and `1: c7; 2: c9; 4: c2; 5: c4; 6: c5`, with `e3` at
      rank 11 not shown;
    - several quotes, the first at rank 1 and another lower within the first ten: `1, 4` and
      `2: c1; 3: c2`;
    - none within the first ten: `13` and the twelve chunks above it;
    - none retrieved: `not retrieved` and the first ten. A shorter ranking gives all of it, and an
      empty one `none`;
    - a ranking shorter than ten, with evidence: `c1, e1, c2` gives `2` and `1: c1`;
    - no `ranking` in the row: `not recorded` in both cells.
- [X] T013 [US2] In `tests/unit/test_compare_runs.py`, the table in `render_comparison`'s output
  (FR-009, FR-011, FR-012; contracts/compare-runs.md, Output and The new table):
  - two runs whose rows hold rankings, where `q2` moved: after the "Questions that moved" table
    come `## What ranked above the evidence`, its header and separator, and two rows for `q2`, the
    first label's then the second's. `q1`, which didn't move, has none;
  - one ID in both runs, at different ranks (`c1` above the evidence in one run, below it in the
    other): each run's row shows only its own reading, under its own label, and the ID appears
    only where that run put it above its evidence (FR-011; `data-model.md`, The chunk ID);
  - everything before `\n## What ranked above the evidence` is the same whether the rows hold
    rankings or not (FR-012);
  - two runs where no question moved: no such section.

### Implementation for User Story 2

- [X] T014 [P] [US2] Create `specs/007-retrieval-rows/benchmarks/experiments/no_reranking.yaml`, as
  research.md R9 gives it (`data-model.md`, Added): `name: no_reranking`, `kind: retrieval`, its
  description, and one variant, `hybrid_rrf`, overriding
  `retrieval: {reranker: {enabled: false}}`. Check with `uv run python` that `load_experiment`
  reads it, and that the variant's `index_key` equals the default's, so it reuses the default's
  workspace.
- [X] T015 [US2] In `devtools/compare_runs.py`, add `ranked_above(row)`, which returns the two
  cells for one run's row (research.md R5, R7; contracts/compare-runs.md, Cells), so that T012
  passes. It follows `data-model.md`, The comparison's reading of a run, part by part: The
  evidence, from The retrieval row's `relevant_chunks`, split on "; " without empty items; The
  evidence's ranks, in The retrieval row's `ranking`, from 1; The depth; The evidence shown; and
  The chunks above it. It covers the four states of its table. A row without `ranking` gives
  `not recorded` in both cells (FR-014). A named constant holds the ten, the deepest rank that
  Recall@10 and nDCG@10 read.
- [X] T016 [US2] In `devtools/compare_runs.py`, `render_comparison` (lines 115–145; research.md
  R6; contracts/compare-runs.md, Output), so that T013 passes. After the "Questions that moved"
  table, when at least one question moved, it appends:
  - an empty line, `## What ranked above the evidence` and an empty line;
  - the header `| question | run | evidence at | ranked above it |`, and a separator built as
    today's;
  - for each question that moved, in the order of `moved()`'s table, one row per run, the first
    label's then the second's, from that run's row in the merged results, whose `variant` is the
    label. Each run's chunk IDs are shown as it recorded them, and never matched with the other
    run's (FR-011; `data-model.md`, The chunk ID).

  `moved()`'s table, and everything printed before the new section, stay as they are (FR-012).
- [X] T017 [US2] In `devtools/compare_runs.py`, the module's docstring (research.md R12):
  - say that, for each question that moved, the output then shows, in each run, the ranks its
    evidence took and the chunks that ranked above it, down to the lowest-ranked evidence among
    the first ten;
  - say that a run written before the rows recorded rankings says so;
  - write "in one of the runs" where it says "in either run": a question is left out when one run
    resolved its evidence to no chunk.
- [X] T018 [US2] Checkpoint: `make lint-check` and `make test` pass, T012 and T013 included, with
  the earlier tests of `tests/unit/test_compare_runs.py` asserting what they did (FR-012). One of
  them, `test_the_questions_that_moved_are_listed_with_both_runs`, now looks for `q2`'s row only
  before the new section, which has rows for `q2` too.

**Checkpoint**: The comparison shows what ranked above the evidence of each question that moved,
from rows that recorded rankings, and `not recorded` for rows that didn't.

---

## Phase 5: User Story 3 - Older results, rendered as before (Priority: P3)

**Goal**: `benchmark-report` renders a result written before this change exactly as `main` does,
and the comparison pairs such results, with each other or with a new one, saying where a ranking
wasn't recorded (FR-013 to FR-015).

**Independent Test**: User Story 3's test in spec.md. In this phase, `make test`. On the stack,
T027 and T028 (SC-003, SC-004).

### Tests for User Story 3 (guards)

- [X] T019 [P] [US3] In `tests/unit/test_report.py` (FR-006, FR-013; contracts/retrieval-rows.md,
  What reads the rows): a retrieval result whose rows hold `ranking` and `context` renders exactly
  as the same result without them, both with `render(results)` and with `render(results,
  baseline)` on two variants. It passes on `main`'s code too, and keeps the lists out of the
  report.
- [X] T020 [US3] In `tests/unit/test_compare_runs.py`, after T012 and T013 (FR-014, FR-015;
  contracts/compare-runs.md, Old and new results):
  - with today's `BASELINE` and `CHANGED`, whose rows hold no rankings, the new section's rows for
    `q2` are `| q2 | originals | not recorded | not recorded |` and
    `| q2 | markdown | not recorded | not recorded |`;
  - a run without rankings paired with one that has them, in both orders: the old run's row says
    `not recorded`, and the new run's is read;
  - `render_comparison` leaves the results it is given as they were: each equals a
    `copy.deepcopy` of itself taken before the call.

### Implementation for User Story 3

- [X] T021 [US3] Checkpoint: `make test` passes with T019 and T020. Nothing is implemented here.
  The `not recorded` reading is T015's, and `git diff main...HEAD -- app/evaluation/report.py
  app/main.py` prints nothing (`data-model.md`, Unchanged: `benchmark-report`'s output).

**Checkpoint**: Results written before this change render as before, and pair with new ones.

---

## Phase 6: Polish & Cross-Cutting Concerns (on the real stack, and the records)

**Purpose**: The three stories on the real stack, the real models and the dataset's books, then the
records and the results.

- [ ] T022 Before the rebuild:
  - the change is committed, when the owner asks for it, so that the runs' `--commit` names a
    commit that holds it (research.md R10). If the owner prefers to run uncommitted, the runs
    record `-dirty`, as the fix's did;
  - the owner confirms the rebuild, which deletes their library.
- [ ] T023 Rebuild and reset (quickstart.md § 3):
  - `make up` rebuilds the app image and recreates its container, which deletes the owner's
    library, its logs, the reranker's weights and the container's copy of `benchmarks/`. ChromaDB
    and Ollama keep their data, models included;
  - `docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"` deletes the
    emptied library and every `book_chunks_v*` collection;
  - `docker compose exec app book-rag doctor` reports no failure.
- [ ] T024 The two runs (quickstart.md § 4):
  - copy `specs/007-retrieval-rows/benchmarks/experiments/no_reranking.yaml` into
    `benchmarks/experiments/`, then `docker compose cp -a benchmarks app:/app/`;
  - with `COMMIT="$(git describe --always --dirty)"`, run
    `docker compose exec app book-rag benchmark benchmarks/experiments/markdown_books.yaml --commit "$COMMIT"`,
    then the same with `no_reranking.yaml`;
  - copy out only the two folders that they print, as `$NEW` and `$OFF`:
    `docker compose cp "app:/app/$NEW" benchmarks/results/`, and the same for `$OFF`.

  Expected: the first run indexes the three books in a fresh workspace, and the second indexes
  nothing. Both say `complete: true`. Note each run's time, for the records.
- [ ] T025 [P] SC-001, quickstart.md § 5. Run its throwaway check, kept as `$SCRATCH/same_rows.py`,
  on `$FIX` and `$NEW`, then `cmp "$FIX/summary.csv" "$NEW/summary.csv"`. Expected:
  - the same configuration, dataset, books and embedding model's digest;
  - 75 rows, the same questions, and no row whose six scores, `relevant_chapters` or
    `relevant_chunks` differ;
  - `summary.csv` identical.

  If a row differs, stop. A run of `main`'s code on the same models tells whether this change
  moved it (research.md R8). Record what it finds before going on.
- [ ] T026 [P] SC-002, quickstart.md § 6. Write the throwaway `$SCRATCH/check_rows.py`. It:
  - loads `EnvironmentSettings()` (`app.config.settings`) and
    `load_settings(environment.config_dir)` (`app.config.loader`);
  - opens the default variant's workspace with
    `BenchmarkRunner(settings, environment)._open(settings)`, which indexes nothing, since the
    workspace exists;
  - for each row of `<run>/rows.jsonl`, takes the question from the dataset, resolves its evidence
    with `relevant_chunks`, and recomputes the six scores from the row's `ranking` and `context`
    (contracts/retrieval-rows.md, What the lists satisfy);
  - checks that `context` is `ranking[:5]`, and prints the shortest and longest ranking.

  Run it with `docker compose exec -T app python - "$NEW" < "$SCRATCH/check_rows.py"`. Expected:
  75 rows, every score equal, every context the ranking's first five, and no ranking longer than
  30.
- [ ] T027 [P] SC-003, quickstart.md § 7. On the branch's container:
  - for each of `$MAIN` and `$FIX`, `benchmark-report`, with and without `--baseline default`,
    piped into `cmp` with T004's file. All four print nothing;
  - `benchmark-report "$NEW"` against T004's report of `$FIX`, with `diff`. Only the line that
    says when, and with which Ollama, each ran differs. The lists appear nowhere.
- [ ] T028 SC-004, quickstart.md § 8:
  - `compare_runs.py "$MAIN" "$FIX" --labels main fix`, against T003's output with `diff`. It only
    adds lines at the end: the new section, with the four questions that moved, `main`'s row then
    the fix's, each `not recorded` in both cells;
  - `compare_runs.py "$FIX" "$NEW" --labels fix branch`: 75 pairs, none left out, every
    difference `+0.000 (+0.000 to +0.000)`, `None.` under "Questions that moved", and no new
    section;
  - `sha256sum -c --quiet "$SCRATCH/old-runs.sha256"` reports no change (FR-015).
- [ ] T029 SC-005, quickstart.md § 8:
  - run `compare_runs.py "$NEW" "$OFF" --labels default no_reranking` into
    `$SCRATCH/compare-reranking.md`;
  - write the throwaway `$SCRATCH/check_table.py` from FR-009's and FR-010's text, not from T015's
    code. For each question under "Questions that moved", it rebuilds both rows of the new table
    from the two runs' `results.json`, and compares them with the output's. Every row agrees;
  - read a few by hand: a question that the reranker lifted, and one that it sank. Note how many
    questions moved, and those examples, for the records.
- [X] T030 [P] In `README.md`, Benchmarks (FR-016, research.md R12):
  - after "Each result row lists the chapters and chunks the evidence resolved to", say that a
    retrieval row also lists its ranking, every passage the search considered in the order its
    scores read, and its context, the passages kept, by chunk ID. An ID holds within its run;
  - where the paragraph on `markdown_books` names `devtools/compare_runs.py`, add what it shows
    for each question that moved, in each run: the ranks its evidence took and the chunks that
    ranked above it, down to the lowest-ranked evidence among the first ten. A run from before
    this change says that it didn't record its ranking;
  - name `no_reranking`, in `specs/007-retrieval-rows/benchmarks/experiments/`, the default with
    reranking off, beside `markdown_books`.

  This can be done any time after US2.
- [X] T031 [P] In `docs/decisions.md`, Evaluation (FR-017, research.md R12), a new entry, "Retrieval
  rows record what was retrieved", after "Generation rows record how much of the evidence reached
  the model":
  - why: the reading that the publisher-back-matter fix couldn't do, which its report left as a
    follow-up, and Principle VI's reading of rows before concluding;
  - IDs and not texts, as the owner asked: an ID tells the book, the chapter's position and the
    chunk's place, and holds within its run only. It doesn't contradict "Relevance is stored as
    evidence quotes, not chunk IDs": a ranking's IDs are read only within their run;
  - the depth: the scores that decide whether a question moved read no deeper than the first ten,
    MRR down to the first piece of evidence, and `on_liberty_conceptual_01` moved below its first
    piece of evidence.

  This can be done any time after US2.
- [ ] T032 In `docs/benchmark-results.md` (FR-018, research.md R12), after T025 to T029:
  - a new section after "Matter that isn't the book's text", before "Recommendations", for
    T024's two runs: the date, the commit, the same dataset and books;
  - SC-001's result: the same rows as the fix's run, every score of every question, and
    `summary.csv` identical;
  - what the comparison with reranking off showed: how many questions moved, and T029's examples;
  - where the results are, outside the repository;
  - "Reproducing" names `no_reranking`: where it is, that it is copied into
    `benchmarks/experiments/`, and how long it takes.

  "Matter that isn't the book's text" keeps its inference (FR-018).
- [ ] T033 The library back (quickstart.md § 10). Ask the owner whether to add their book back
  from the file they name, then `docker compose cp "<file>" app:/tmp/` and
  `docker compose exec app book-rag add-book "/tmp/<file>"`. `list-books` shows it indexed.
- [ ] T034 Add a section "Results of the implementation, <date>" at the end of `spec.md`, as
  `specs/006-remove-chapter-quiz` recorded its results:
  - SC-001 and SC-002: the runs, the rows compared and the scores recomputed;
  - SC-003 and SC-004: the renderings and comparisons against `main`'s, and the checksums;
  - SC-005: how many questions moved, and the check of the table;
  - SC-006: the unit test counts, before (T001) and after;
  - SC-007: T035's list of files.

  Mark the tasks done in this file.
- [ ] T035 Final pass: quickstart.md § 9's diff and § 10's records and history once more, then
  `make lint-check` and `make test`. `git diff main...HEAD --name-only` lists only the files of
  plan.md's Project Structure, `README.md`, `docs/decisions.md`, `docs/benchmark-results.md` and
  `specs/007-retrieval-rows/`. None is in `app/retrieval`, `app/ingestion`, `app/generation`,
  `app/storage` or `config/` (SC-007).
- [ ] T036 When the owner asks for the pull request: the title is
  `feat: record what the retrieval benchmark retrieved`. Its merge makes a minor release,
  v0.7.0, if `git describe --tags --abbrev=0 origin/main`, after `git fetch --tags`, still prints
  `v0.6.1` (`spec.md`, Assumptions). No commit has `!` after its type, and the description has no
  `BREAKING CHANGE` footer, which would make the release a major one.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: first. T003 comes before T015 to T017 change the devtool, and T004 before
  T023 rebuilds the container.
- **Foundational (Phase 2)**: none.
- **US1 (Phase 3)**: after Setup.
- **US2 (Phase 4)**: after Setup. It doesn't need US1, and can run beside it.
- **US3 (Phase 5)**: T019 any time. T020 after T012, T013 and T015.
- **Polish (Phase 6)**: after the three stories, in order T022, T023, T024, then T025 to T029.
  T030 and T031 can come any time after US2. T032 comes after T025 to T029, T033 after T029, and
  T034 and T035 last. T036 waits for the owner.

### Within Each User Story

- New-behavior tests first, and they fail: T005 to T008, then T012 and T013.
- In US1, T009 before T010: one file.
- In US2, T015 before T016, which renders T015's cells, and T017 after both: one file. T014 any
  time.
- Each story ends with its checkpoint (T011, T018, T021).

### Parallel Opportunities

- T002 to T004: three outputs, from the host and the running container.
- US1 and US2: different files, so T005 to T011 can run beside T012 to T018.
- T014: a new file.
- T019: `tests/unit/test_report.py`, any time.
- T025 to T027, after T024: each reads the runs and writes only to `$SCRATCH`.
- T030 and T031: two documents.

---

## Parallel Example: User Story 1 and User Story 2

```bash
# Their tests, together, in two files:
Task: "T005 to T008 in tests/unit/test_benchmark.py: the lists in the three files, the scores again, the search's lists, what stays"
Task: "T012 and T013 in tests/unit/test_compare_runs.py: the reading of a run's row, and the table"

# Their implementations, together, in two files:
Task: "T009 and T010 in app/evaluation/benchmark.py: the row's two keys, and a list as one CSV cell"
Task: "T015 to T017 in devtools/compare_runs.py: ranked_above, the table, the docstring"
Task: "T014 specs/007-retrieval-rows/benchmarks/experiments/no_reranking.yaml"
```

## Parallel Example: the checks on the stack

```bash
# Once T024 has made both runs:
Task: "T025 SC-001: the same rows as the fix's run, and the same summary.csv"
Task: "T026 SC-002: the scores recomputed from the lists, in the container"
Task: "T027 SC-003: benchmark-report against main's renderings"
```

---

## Implementation Strategy

### Baseline First

T002 to T004 take `main`'s outputs and the fix's checksums before any change, while the running
container is still `main`'s code, so that T027 and T028 have something to compare with.

### MVP (User Story 1)

After T011, every retrieval row records what the search returned. That is the reading that the
publisher-back-matter fix couldn't do: a run's rows answer it, even before the comparison shows
it. Stopping there is a valid state, checked on the stack by T023 to T026.

### Incremental Delivery

1. Setup: `main`'s outputs, and the fix's checksums.
2. US1: the rows record the two lists.
3. US2: the comparison shows what ranked above the evidence.
4. US3: guards that older results render as before.
5. Polish: one rebuild, two runs, the checks of SC-001 to SC-005, the records and the results.

Each checkpoint leaves `make lint-check` and `make test` passing.

---

## Notes

- [P] tasks touch different files and don't depend on an unfinished task.
- The line numbers are `main`'s at `aa54d1b`. After earlier tasks, find the code by its names.
- Never edit `specs/001` to `specs/006` or `.specify/bugs/publisher-back-matter/` (FR-019).
- The throwaway scripts stay in `$SCRATCH`, and none is committed (research.md R13).
- If a test or a check finds something the plan didn't foresee, the plan or the spec is corrected
  first, as "Corrections during implementation" at the end of `spec.md`.
