---

description: "Task list for removing the chapter quiz"
---

# Tasks: Removing the chapter quiz

**Input**: Design documents from `specs/006-remove-chapter-quiz/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md),
[checklists/removal-and-records.md](checklists/removal-and-records.md)

**Tests**: Included. The constitution's Development Workflow asks for automated tests of every
significant component, FR-005 asks that what the shared test files check about the rest stays
checked, and research.md R10 lists every test deleted, rewritten and added. Two kinds of test task:
- **Coverage tests** (Phase 2) check behaviors that stay but were tested only through the quiz.
  They pass on `main`'s code and keep passing.
- **New-behavior tests** (in each story) check the four tabs and the refusals. They are written
  first and fail until their story's implementation.

**Organization**: By user story, in the order the code allows, which isn't quite the priority order:
- **US1** (P1) removes the Quiz tab. The service, the configuration and the benchmark's kinds
  still exist after it, unreachable from the interface. US1's scenario 4, the refusal of a
  leftover `quiz` section, completes in US2 (T033), since the configuration's readers go there.
- **US3** (P3) comes before US2. The benchmark and the report import the quiz's modules, so they
  must stop before US2 can delete those modules. US3 is complete on its own: the four kinds, the
  refusals, and the quiz's runs kept as history.
- **US2** (P2) removes the rest: the container's wiring, the service, the writer, the prompts, the
  settings, the factory's parameters, the errors, and the records.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: a different file, and no dependency on an unfinished task.
- **[Story]**: the user story the task belongs to (US1 to US3).

## Path Conventions

A single Python project, with `app/`, `config/` and `tests/` at the repository root (plan.md,
Project Structure). Line numbers are `main`'s at `56600c7`, for orientation: names decide.

- **In the Bash tool**, run
  `export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"` before `make` or
  `uv`.
- **`$SCRATCH`** is the session's scratchpad. The comparison script and its outputs stay there, out
  of the repository (research.md R8).
- **`make up` recreates the app container**, which deletes the library it holds (empty on
  2026-11-19), its logs and `data/quiz_downloads` (principle II, research.md R15). Only T038 runs
  it, and `reset-everything` follows.
- **The host's `benchmarks/`** is ignored by git. Only T042 deletes anything there (FR-013).
- **Commits** happen only when the owner asks. Their messages use `feat:`, `test:`, `refactor:`
  or `docs:`, never `!` and never a `BREAKING CHANGE` footer (FR-018).

---

## Phase 1: Setup

**Purpose**: A known starting point, and `main`'s side of the comparison of SC-002 and US3's
scenario 4, taken from `main`'s code before anything changes.

- [X] T001 Check the starting point. The branch is `feat/remove-chapter-quiz` with only `docs:`
  commits on top of `main`. `git status --short` is empty, and `uv.lock` is `main`'s. With asdf's
  paths, `make lint-check` and `make test` pass. Note the number of unit tests, for the results
  (T043).
- [X] T002 Write the throwaway script `$SCRATCH/same_as_main.py`, outside the repository
  (research.md R8, quickstart.md § 3). It prints, one per line:
  - `app.__file__`, so the output shows which tree it loaded;
  - one SHA-256 per prompt of `app/generation/prompts.py`, built from fixed inputs: an English
    and a Portuguese question, and two `Chunk`s with chapter and section;
    - `question_answering_messages` with `language=None` and with `"Portuguese"`, and
      `abstention_check_messages` with a fixed reply;
    - `map_messages`, `collapse_messages`, `final_summary_messages` and `verification_messages`,
      for each summary type in `config/generation.yaml` (`brief`, `standard`, `comprehensive`,
      `analytical`), with the book's language and with a named one;
  - the SHA-256 of `_COVERAGE_PROMPT` and `_RATING_PROMPT` from `app/evaluation/summary_metrics.py`,
    formatted with fixed values;
  - for each `benchmarks/results/markdown_books_*/results.json` on the host, the SHA-256 of
    `render(results)` and of `render(results, <its first variant>)`, from
    `app/evaluation/report.py`, with positional arguments, which both versions accept.

  It reads the settings with `load_settings(Path("config"))` from the tree it runs on, and labels
  each line with what it hashed.
- [X] T003 Run T002's script on `main`'s code and keep its output. From the repository's root:
  `REPO="$PWD"`, `git worktree add "$SCRATCH/main-tree" "$(git merge-base main HEAD)"`, then
  `cd "$SCRATCH/main-tree" && PYTHONPATH="$SCRATCH/main-tree" "$REPO/.venv/bin/python" "$SCRATCH/same_as_main.py" > "$SCRATCH/main.txt"`.
  `PYTHONPATH` puts the worktree's `app` ahead of the editable install. Check that the first line
  names the worktree, then go back to `$REPO` and `git worktree remove "$SCRATCH/main-tree"`.

**Checkpoint**: `$SCRATCH/main.txt` holds `main`'s hashes.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Six behaviors that stay are tested today only through the quiz (research.md R10).
Their tests come first, without the quiz, so that no story removes the only test of something
that stays. Each passes on `main`'s code.

- [X] T004 [P] In `tests/unit/test_container.py`, add a test that the container builds one
  provider, for `llm.model` with its profile, shared by questions and summaries (FR-004, R10):
  `c = assemble(settings, EnvironmentSettings(data_dir=tmp_path))`, then
  `c.questions._llm is c.summaries._llm`, `c.questions._llm.model == settings.llm.model` and
  `c.questions._llm._profile == settings.llm_profile`. Keep the three quiz tests until T026.
- [X] T005 [P] In `tests/unit/test_llm_provider.py`, rewrite
  `test_the_factory_builds_a_named_model_from_its_own_profile` and
  `test_a_model_without_a_profile_is_refused` to name the model through a copy of the settings,
  `settings.model_copy(update={"llm": settings.llm.model_copy(update={"model": "gemma4:12b"})})`
  (and `"unknown-model"` for the refusal), not through the `model=` parameter. Their assertions
  stay: gemma4's reasoning and tokenizer, and the refusal naming the model.
- [X] T006 [P] In `tests/unit/test_benchmark.py`, add three tests on a retrieval experiment, next
  to the quiz ones they will replace (R10):
  - a retrieval experiment with an unknown top-level key (`seeds: 3`) is refused;
  - a retrieval run records the commit and the dataset books' checksums:
    `runner.run(<retrieval experiment>, commit="abc1234")`, then `environment["commit"]` and
    `environment["book_sha256"]` (`data-model.md`, `results.json` `environment.book_sha256`);
  - `load_experiment` reads a valid retrieval experiment file, equal to `Experiment.model_validate`
    of the same mapping.
- [X] T007 [P] In `tests/unit/test_report.py`, give a retrieval result fixture a `by_book` entry,
  and check that `render()` writes its "## By book" table, which only the quiz's fixture exercised
  (R10).
- [X] T008 Checkpoint: `make test` passes on `main`'s code with T004 to T007.

---

## Phase 3: User Story 1 - The application without the quiz (Priority: P1) 🎯 MVP

**Goal**: The interface has the Library, Chat, Summarization and Research tabs, in today's order,
and no Quiz tab. Changing the library refreshes the other tabs' book lists. The stop on SIGTERM and
the cache sweep stay, with their reasons restated.

**Independent Test**: User Story 1's test in spec.md: the tabs, a book added and the lists
refreshed, a question and a summary as on `main`. In this phase, `make test`; on the real stack,
T039 and T040. Scenario 4 waits for US2 (T024, T033).

### Tests for User Story 1 (write first, and see them fail)

- [X] T009 [US1] In `tests/unit/test_interface.py` (FR-001, FR-007, contracts/interface.md):
  - **Add** a test that the interface's tabs are Library, Chat, Summarization and Research, in
    that order: `[b.label for b in interface.blocks.values() if isinstance(b, gr.Tab)]`. It fails
    while the Quiz tab exists.
  - **Rename** `test_the_interface_clears_gradios_copies_of_downloads_within_the_hour` for
    uploads, its assertion unchanged. `test_sigterm_shuts_gradio_down_as_an_interrupt_does` stays
    as it is.
  - **Delete** the quiz block (lines 432–612): its comment, `quiz_question`, `ENGLISH_DRAFT`,
    `quiz_interface`, `CURRENT`, `DOWNLOAD`, `SLOTS`, `quiz_result`, and its twelve tests, from
    `test_a_quiz_slot_shows_its_number_and_question` to
    `test_a_whole_book_result_ranks_the_chapters_to_reread`.
  - **Remove** `"prepare_quiz"` and `"grade_quiz"` from
    `test_every_primary_operation_is_reachable`.

  The `interface` fixture keeps `quizzes=QuizService(...)` until T026, since the container keeps
  the field until T028.

### Implementation for User Story 1

- [X] T010 [US1] In `app/interface/gradio_app.py` (research.md R2, R4), so that T009 passes:
  - **The tab.** The import and the call of `build_quiz_tab` go, and so do `refresh()`'s
    `quiz_book` parameter, its dropdown in the returned tuple, and `quiz.book` in `selections` and
    `outputs`.
  - **The comments.** The one above `CACHE_SWEEP` says that Gradio caches every upload, such as a
    book added in the Library tab, and that the sweep removes copies older than 50 minutes every
    10 minutes, and all of them on shutdown. The one above `signal.signal(...)` says that
    `docker compose stop` and `restart` send SIGTERM, which the container's first process ignored
    until it was killed 10 s later, so Gradio never shut down and its cached copies of uploads
    outlived the restart. Neither names the quiz, a download or `FR-018`.
- [X] T011 [US1] Delete `app/interface/quiz.py`. In `app/interface/formatting.py`, remove the "Quiz
  tab" block (lines 225–281: `quiz_slot_markdown`, `quiz_choices`, `quiz_progress`,
  `quiz_outcome`, `quiz_reference`, `quiz_feedback`, `quiz_result_markdown`) and the import of
  `Question`, `QuizReady`, `Result`, and any import left unused.
- [X] T012 [US1] Checkpoint: `make lint-check` and `make test` pass, T009 included. Nothing in
  `app/interface/` names the quiz (`git grep -i -n quiz -- app/interface`).

**Checkpoint**: The interface has four tabs. The quiz's service, settings and benchmark kinds still
exist, but no tab reaches them.

---

## Phase 4: User Story 3 - Benchmarks without the quiz's kinds (Priority: P3)

**Goal**: Four kinds of experiment, each as on `main`. A `quiz` or `quiz_check` experiment, or one
that sets a removed field, is refused when it loads. `benchmark-report` refuses a result of a kind
it doesn't render, and never reads `reading.csv`. The quiz's runs stay in
`docs/benchmark-results.md` as history.

**Independent Test**: User Story 3's test in spec.md. In this phase, `make test`; on the real
stack, T037 and T041.

### Tests for User Story 3 (write first, and see them fail)

- [X] T013 [P] [US3] In `tests/unit/test_benchmark.py` (FR-011, research.md R5, R10). No test
  names the quiz or its fields, so that SC-001's searches hold for the tests too. The quiz's own
  experiments are refused on the stack (T041).
  - **Refusal of the kinds.** `test_an_extraction_experiment_is_refused_naming_the_kinds_left`
    stays on `extraction`. The allowed kinds it reads must be exactly `'retrieval'`,
    `'generation'`, `'summarization'` and `'performance'`, which shows that no other kind is left.
    It fails while `'quiz_check'` is among them.
  - **Refusal of the fields.** No test of its own. T006 shows that a retrieval experiment refuses
    a key it doesn't know, and SC-001's search of the names shows that the five fields are no
    longer known.
  - **Deleted, with what only they use:** `QUIZ_DRAFT`, `quiz_reply`, `quiz_experiment`, `answers`,
    `local_book`, `question_rows`, `quiz_rows`, `FOX`, `known_case`, `check_experiment`,
    `check_models`, `cases_of` and `check_summary`. With them go these tests:
    - the ones T006 replaced: `test_unknown_quiz_keys_are_refused`,
      `test_the_environment_records_the_commit_and_every_books_checksum` and
      `test_the_known_cases_are_read_beside_the_experiment`;
    - the two kinds' own: `test_a_quiz_experiment_takes_targets_local_books_and_a_seed`,
      `test_the_seed_defaults_to_zero`,
      `test_a_local_book_that_isnt_the_owners_copy_stops_the_run_before_any_work`,
      `test_local_books_are_indexed_in_the_workspace_beside_the_datasets`,
      `test_a_quiz_run_writes_question_and_quiz_rows`,
      `test_the_default_count_is_used_when_a_target_has_none`,
      `test_a_closed_book_answer_that_cant_be_read_is_left_out_and_counted`,
      `test_the_same_seed_pairs_variants_question_by_question`,
      `test_a_quiz_run_writes_its_reading`,
      `test_a_failed_target_is_reported_and_the_run_goes_on`,
      `test_a_check_experiment_needs_its_case_set`,
      `test_a_known_case_outside_its_rules_is_refused`,
      `test_two_known_cases_with_one_id_are_refused`, the ten tests that use `check_models`, and
      `test_the_key_being_the_shortest_option_is_measured_too`.

  Remove the imports left unused, `re` among them. The `lab` fixture keeps `quiz_llm` and
  `quizzes=QuizService(...)` until T026.
- [X] T014 [P] [US3] In `tests/unit/test_report.py` (FR-012, contracts/benchmark.md):
  - **Add** a test, parametrized over `extraction` and a made-up kind such as `retired`:
    `render()` raises `ConfigurationError` naming the kind, for a result that holds nothing but
    its experiment. It fails while `render()` accepts any kind. No test names the quiz: T041
    refuses a real quiz result on the stack.
  - **Delete** `quiz_results`, its comment, and the six tests that render a quiz or `quiz_check`
    run: `test_the_quiz_report_shows_every_measure`,
    `test_closed_book_correct_is_shown_without_a_target`,
    `test_the_quiz_report_reads_the_marks_when_there_are_some`,
    `test_the_quiz_report_says_when_nothing_is_marked`,
    `test_quiz_variants_pair_question_by_question` and
    `test_a_check_run_shows_its_catches_and_its_verdict`.
- [X] T015 [P] [US3] In `tests/unit/test_commands.py`, add a test that `benchmark-report` on a
  result of a kind it doesn't render fails and prints nothing to standard output (FR-012). Write a
  `results.json` of kind `extraction` and a `reading.csv` beside it into `tmp_path`, then
  `run(main._benchmark_report, container, capsys, results=tmp_path, baseline=None)` raises
  `ConfigurationError` naming `'extraction'`, and `capsys.readouterr().out` is empty.
- [X] T016 [P] [US3] Delete `tests/unit/test_quiz_metrics.py`, whose module goes at T021.

### Implementation for User Story 3

- [X] T017 [US3] Create `app/evaluation/kinds.py`, with `ExperimentKind` and `EXPERIMENT_KINDS` as
  `data-model.md` defines them (`ExperimentKind`). Its docstring says why it is a module of its
  own: the runner and the report share the kinds, and the report must not load the runner's stack
  (research.md R6). It imports nothing from the application.
- [X] T018 [P] [US3] In `app/evaluation/benchmark.py` (research.md R5), so that T006 and T013 pass:
  - **The model.** `Experiment.kind` becomes an `ExperimentKind` (`data-model.md`,
    `Experiment.kind`). The fields `local_books`, `targets`, `seed`, `known_cases` and `case_set`
    go, with the docstring's lines on them (`data-model.md`, `Experiment.local_books`,
    `Experiment.targets`, `Experiment.seed`, `Experiment.known_cases`, `Experiment.case_set`).
    The classes `LocalBook` and `QuizTarget` go, and so does the validator
    `check_needs_its_cases`.
  - **The loader.** `load_experiment` keeps reading and validating the file, without resolving
    the known cases' path.
  - **The runner.** `run()` loses its `quiz` and `quiz_check` cases. `_check_books()` checks the
    dataset's books only, without its `local_books` parameter and loop, and `_open()` loses its
    `local_books` parameter. `_describe_environment()` records the dataset's books only
    (`data-model.md`, `results.json` `environment.book_sha256`). `_run_quiz_check`, `_run_quiz`
    and `_run_target` go, and `_write()` keeps the plain summary.
  - **The module.** `summarize_quiz`, `_QUIZ_ROW_METRICS`, `_QUESTION_METRICS`, `QUIZ_METRICS` and
    `_WHOLE_BOOK` go, with the imports from `app.evaluation.quiz_metrics`, `app.generation.quiz`
    and `app.services.quiz_service`, and `QUIZ_LETTERS` and `QuizSource` from the prompts.
    `_SEED` stays.
- [X] T019 [P] [US3] In `app/evaluation/report.py` (research.md R6, contracts/benchmark.md), so that
  T014 passes:
  - **The refusal.** `render(results, baseline=None)` (`data-model.md`, `render()`) first checks
    `results["experiment"]["kind"]` against `EXPERIMENT_KINDS`. Any other kind raises
    `ConfigurationError("This is a result of the '<kind>' kind, which this benchmark doesn't run. benchmark-report renders retrieval, generation, summarization and performance runs.")`.
  - **What goes.** The `reading` parameter, the `quiz_check` branch and the quiz sections in
    `render()`; `_quiz_sections`, `_check_section` and `_reading_section`; the `quiz_check` case
    of `_comparisons()`; the imports from `quiz_metrics` and of `REFUSAL_KINDS`. The docstrings
    stop naming the quiz.
- [X] T020 [US3] In `app/main.py`, `_benchmark_report` no longer imports `read_reading` or reads
  `reading.csv` (`data-model.md`, "Benchmark result files of the quiz"). It prints
  `render(json.loads(...), arguments.baseline)`, so that T015 passes.
- [X] T021 [US3] Delete `app/evaluation/quiz_metrics.py`. Nothing imports it any more
  (`git grep -n quiz_metrics -- app tests` prints nothing).
- [X] T022 [P] [US3] In `docs/benchmark-results.md` (FR-016, research.md R13):
  - **The quiz's section** stays, with a first line saying that the quiz was removed in v0.6.0
    (`specs/006-remove-chapter-quiz`), so its runs are a record of it.
  - **Known limitations.** The publisher's advertisements stay a limitation, worded without the
    quiz: in *História econômica global*'s e-book, the catalog record, the copyright and five
    advertisements came in as part of the last chapter, "Lista de tabelas", and questions, in the
    Chat tab or with `ask`, and `search` can retrieve them. "The quiz experiments still name the
    PDF" goes.
- [X] T023 [US3] Checkpoint: `make lint-check` and `make test` pass, T006 and T013 to T015
  included. `git grep -i -n quiz -- app/evaluation app/main.py` prints nothing.

**Checkpoint**: The benchmark has four kinds and refuses the others, and the report refuses their
results. The quiz's service, writer and settings still exist, used by the container alone.

---

## Phase 5: User Story 2 - Nothing left of the quiz (Priority: P2)

**Goal**: The code, the configuration and the tests no longer hold the quiz, nor anything only it
used. A leftover `quiz` section stops the app. The README describes the application without it,
and `docs/decisions.md` records why it went.

**Independent Test**: User Story 2's test in spec.md: the searches of SC-001, the README, and the
unit tests. On the real stack, T041's configuration check.

### Tests for User Story 2 (write first, and see them fail)

- [X] T024 [P] [US2] In `tests/unit/test_config.py` (FR-003, contracts/configuration.md):
  - **The refusal.** A new test, with a neutral name: an unknown section under `generation`, such
    as `retired: {}`, stops loading with `ConfigurationError` matching `generation.retired`. It
    passes before and after, since it checks the rule that refuses a leftover `quiz` section. No
    test names the quiz: T041 refuses `main`'s real configuration on the stack.
  - **Deleted:** the eight quiz-settings tests, `test_an_unknown_quiz_key_is_rejected`,
    `test_the_quiz_settings_load_with_their_defaults`,
    `test_the_checker_model_needs_a_profile`, `test_a_checker_model_with_a_profile_is_accepted`,
    `test_the_quiz_limits_must_leave_room_for_the_prompt`,
    `test_the_default_count_cannot_exceed_the_cap`,
    `test_the_checker_reasoning_takes_a_level_or_nothing` and
    `test_the_checker_reasoning_can_be_left_to_the_profile`.
- [X] T025 [P] [US2] In `tests/unit/test_llm_provider.py`, delete
  `test_a_reasoning_level_replaces_the_profiles_for_that_provider_only`, and keep `sent_reasoning`
  if T005's test still uses it. The section comment above `sent_reasoning` describes the factory
  without a per-task model, a reasoning of its own, or `generation.quiz.check`.
- [X] T026 [P] [US2] Remove the quiz from the fixtures that build a `Container`, which fail until
  T028 removes the field:
  - `tests/unit/test_commands.py`: `quizzes=None`;
  - `tests/unit/test_interface.py`: `quizzes=QuizService(...)` in the `interface` fixture, and the
    imports of `QuizWriter`, `QuizService`, and `Path` if nothing else uses it;
  - `tests/unit/test_benchmark.py`: the `lab` fixture's `quiz_llm` and `quizzes=QuizService(...)`,
    and the imports left unused.

  In `tests/unit/test_container.py`, delete the three quiz tests,
  `test_the_quiz_checker_reasons_at_its_own_level_on_the_writers_model`,
  `test_a_checker_model_of_its_own_gets_its_own_profile` and
  `test_quiz_downloads_go_to_the_data_directory`. T004's test stays.
- [X] T027 [P] [US2] Delete `tests/unit/test_quiz_service.py`, `tests/unit/test_quiz_writer.py` and
  `tests/integration/test_quiz.py`.

### Implementation for User Story 2

- [X] T028 [US2] In `app/container.py` (research.md R2), so that T026 passes: the imports of
  `QuizWriter` and `QuizService` go, with the `quizzes` field (`data-model.md`,
  `Container.quizzes`), the checker's provider, the writer, and the service built over
  `root / "quiz_downloads"` (`data-model.md`, `data/quiz_downloads`).
- [X] T029 [US2] Delete `app/services/quiz_service.py` and `app/generation/quiz.py`. In
  `app/errors.py`, remove `QuizAlreadyGradedError` and `NothingToAskError` (`data-model.md`,
  Errors).
- [X] T030 [P] [US2] In `app/generation/prompts.py`, remove the "Quizzes" block at the end (lines
  261–391: its comment, `QUIZ_LETTERS`, `QuizSource`, the `_QUIZ_*` texts, `_quiz_heading`,
  `lettered_options`, `quiz_question_messages`, `quiz_check_messages`, `quiz_answer_messages`) and
  the `dataclass` import. Nothing else changes: the file's diff only removes lines (research.md
  R8).
- [X] T031 [P] [US2] In `app/generation/factory.py` (research.md R3, `data-model.md`,
  `create_llm_provider`): `create_llm_provider(settings, runtime)` builds the provider for
  `llm.model`, with its profile and `settings.llm`. The `model` and `reasoning` parameters go,
  with the copies of `llm` and of the profile they made, and the docstring stops naming the quiz.
  The check that the model has a profile stays (T005).
- [X] T032 [P] [US2] In `app/ingestion/language.py`, remove `confident_reply_language`, and
  `_MIN_REPLY_CONFIDENCE` with its comment. `reply_language` and `_identifier` stay.
- [X] T033 [P] [US2] In `app/config/settings.py` and `config/generation.yaml` (research.md R7), so
  that T024 passes:
  - `QuizCheckConfig`, `QuizConfig` and `GenerationConfig.quiz` go (`data-model.md`,
    `GenerationConfig.quiz`), with the validator's check of `generation.quiz.check.model` and its
    loop over the quiz's two token limits. The loop over the two remaining tasks stays.
  - The `quiz` section of `config/generation.yaml` goes, from its comment to its last key (lines
    45–77), with one of the blank lines around it (`data-model.md`, `generation.quiz`).
- [X] T034 [P] [US2] In `README.md` (FR-014, research.md R11):
  - **Interface**: four tabs, and no Quiz row.
  - **Quizzes**: the section goes.
  - **Benchmarks**: from "Two more kinds measure the Quiz tab" to the end of the `quiz_check`
    paragraph, everything goes. The advice to pass `--commit`, since the container holds no
    `.git`, moves after the first code block, with an example such as
    `docker compose exec app book-rag benchmark benchmarks/experiments/retrieval.yaml --commit "$(git describe --always --dirty)"`.
  - **Configuration**: the row for `config/generation.yaml` stops naming the quiz.
- [X] T035 [P] [US2] In `docs/decisions.md` (FR-015, research.md R12):
  - **Delete** the quiz's decisions:
    - in Generation: "A quiz question is written from one passage, by one call", "The model never
      chooses a letter", "The application chooses the passages", "A quiz's default length follows
      the text's", "The Quiz tab builds its question slots up front", "Questions don't point to
      their passage", "An empty fifth wrong answer is no answer", "The model skips a passage with
      nothing to ask about", "Preparing a quiz logs its own operation lines", "The quiz's key
      check reasons on a provider of its own", and "The download is the service's file, and
      Gradio's copy goes on shutdown";
    - in Evaluation: "The quiz measurement pairs runs by seed", "The quiz's length bias is
      measured both ways", "The quiz's key check ships switched off, unproven", and "A comparator
      answers in JSON, not in words".
  - **Reword**, the lesson kept:
    - "Pages were dropped, not read from markers in the Markdown" (Ingestion) loses "the quiz's
      pointers";
    - "The operation runs in a thread of its own, and the tab polls its progress" (Library
      lifecycle) loses "which the quiz found first";
    - "The benchmark's files left the repository" (Evaluation) loses "as the quiz's experiments
      are in `specs/003`".
  - **Add**:
    - in Infrastructure, after "Nothing is kept in a volume", "The app stops on SIGTERM, and
      Gradio's cache is swept." It gives R4's reasons: the restart in 1 s instead of 10, Gradio's
      cache deleted on close, and `delete_cache=(600, 3000)` for the copies of uploaded books;
    - at the end, a section "Removed: the chapter quiz (v0.6.0)" with one entry. It says what
      went, and why: the owner's use, and the two shortfalls of the spec's Context. It names the
      follow-ups dropped, and says the quiz's decisions were deleted rather than shortened. It
      points to their reasoning in `specs/003-chapter-quiz`, `.specify/assessments/chapter-quiz/`
      and the tag `v0.5.0`, the last release with the quiz.
- [X] T036 [US2] Checkpoint, quickstart.md § 2 and the diff rules of § 3:
  - `make lint-check` and `make test` pass, T024 to T026 included;
  - both searches of § 2 print nothing outside the records, and the third finds only the
    removal's section and the quiz's section of the two documents (SC-001);
  - `git diff main...HEAD --name-only` lists only the files of plan.md's Project Structure, the
    records and this spec's folder (SC-006). The three dots compare with where the branch left
    `main`, so a later merge into `main` doesn't count;
  - `git diff main...HEAD -U0 -- app/generation/prompts.py | grep '^+[^+]'` prints nothing.

**Checkpoint**: Nothing of the quiz is left in the code, the configuration or the tests.

---

## Phase 6: Polish & Cross-Cutting Concerns (on the real stack)

**Purpose**: The comparison with `main`, the feature on the real stack and the real models, the
host's quiz files, and the record of the results.

- [X] T037 Run T002's script on the branch,
  `PYTHONPATH="$PWD" .venv/bin/python "$SCRATCH/same_as_main.py" > "$SCRATCH/branch.txt"`, and
  `diff "$SCRATCH/main.txt" "$SCRATCH/branch.txt"`. Only the `app.__file__` line differs (SC-002,
  US3's scenario 4). If any hash differs, stop and find why before going on.
- [X] T038 Rebuild and reset, quickstart.md § 4. `make up` rebuilds the app image and recreates its
  container, which deletes the library it holds (empty on 2026-11-19), its logs and
  `data/quiz_downloads`. ChromaDB and Ollama keep their data, models included. Then
  `docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"` deletes the
  empty library and every `book_chunks_v*` collection. Then `doctor` reports no failure (SC-003).
- [X] T039 `make test-integration` passes without `test_quiz.py`. `time docker compose restart app`,
  run while no library operation is in progress, takes under 2 s of wall-clock time (SC-003,
  SC-004).
- [X] T040 The interface on the real stack (SC-004, quickstart.md § 5). The owner, in the browser:
  - the tabs are Library, Chat, Summarization and Research;
  - `benchmarks/books/on-liberty.md`, added in the Library tab, appears in the Chat and
    Summarization lists once it is indexed;
  - a question in the Chat tab is answered with citations by book, chapter and section;
  - a chapter summary is made and saved.

  The agent can check the same through `ask` and `summarize` in the container meanwhile.
- [X] T041 The refusals on the stack (SC-005, quickstart.md § 6), each file put back or removed
  afterwards:
  - **The configuration.** `main`'s `config/generation.yaml`, which has the `quiz` section, is
    copied into the container: `doctor` stops, naming `generation.quiz`. Then the branch's is
    copied back, and `doctor` passes.
  - **The experiments.** The dataset of `specs/005-markdown-only/benchmarks/`, and
    `specs/003-chapter-quiz/benchmarks/quiz.yaml` and `quiz_check.yaml`, are copied into
    `/app/benchmarks`. `benchmark` refuses both experiments, naming the four kinds.
  - **A result.** `benchmarks/results/quiz_20261111T130111197357Z` is copied in, and
    `benchmark-report` prints contracts/benchmark.md's error and nothing else.

  Then `/app/benchmarks` is removed from the container.
- [X] T042 After T041, and only then, delete the host's quiz files (FR-013, research.md R14,
  quickstart.md § 7). They are the experiments `benchmarks/experiments/quiz.yaml`,
  `quiz_models.yaml`, `quiz_check.yaml` and `key_cases.yaml`, and the seven result folders
  `benchmarks/results/quiz_2026*`, `quiz_models_2026*` and `quiz_check_2026*`. List what is left:
  - the eight experiment files `default_llm_generation`, `default_llm_summarization`,
    `generation`, `historical_spelling`, `markdown_books`, `performance`, `retrieval` and
    `summarization`;
  - the results `markdown_books_*`, `chunks-*`, `library_progress_*` and
    `compare_originals_markdown.md`;
  - the books, unchanged.
- [X] T043 Add a subsection "Results of the implementation, <date>" under the Clarifications of
  `spec.md`, as `specs/003-chapter-quiz/spec.md` has one:
  - SC-001's searches;
  - SC-002's comparison: how many prompts and renderings were hashed, all equal;
  - SC-003: the unit test counts before (T001) and after, `make test-integration`, `doctor`;
  - SC-004: the restart time and the owner's check in the browser;
  - SC-005's three refusals, with the messages seen;
  - SC-006's diff, with its list of files;
  - FR-013's deletions.

  Mark the tasks done in this file.
- [X] T044 Final pass: quickstart.md § 2's searches and § 8's records once more, then
  `make lint-check` and `make test`.
- [ ] T045 When the owner asks for the pull request, quickstart.md § 9:
  - no commit of the branch has `!` after its type or a `BREAKING CHANGE` footer;
  - `git describe --tags --abbrev=0 origin/main`, after `git fetch --tags`, prints `v0.5.0`.
    Otherwise the records are corrected to the version this merge produces (FR-018).

  The title is `feat: remove the chapter quiz`, and the description ends without a
  `BREAKING CHANGE` footer.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: first. T003 needs T002, and both need nothing else: they read `main`'s code
  through a worktree.
- **Foundational (Phase 2)**: after Setup. It blocks every story, since the stories delete the
  tests these replace.
- **US1 (Phase 3)**: after Foundational.
- **US3 (Phase 4)**: after Foundational. It doesn't need US1, and could run before it.
- **US2 (Phase 5)**: after US1 and US3. It deletes the modules that the interface (US1) and the
  benchmark and report (US3) imported.
- **Polish (Phase 6)**: after US2. T037 needs T003. T038 comes before T039 to T041, and T042 comes
  after T041.

### Within Each User Story

- New-behavior tests first, and they fail: T009, T013 to T015, and T026. T024 passes before and
  after, since the rule it checks already refuses any unknown key.
- Then the consumers before what they import: the interface (T010) before its module goes (T011);
  `kinds.py` (T017) before the runner and the report (T018, T019); the report (T019) before
  `main.py` (T020); all three before `quiz_metrics.py` goes (T021); the container (T028) before
  the service and the writer go (T029); and those before the prompts, the factory, the language
  check and the settings (T030 to T033).
- Each story ends with its checkpoint (T012, T023, T036).

### Parallel Opportunities

- T004 to T007: four test files.
- T013 to T016: four test files.
- T018 and T019, once T017 is done: two modules.
- T022, any time in US3: a document.
- T024 to T027: test files. T026 touches `test_benchmark.py` and `test_interface.py` too, so it
  comes after T009 and T013.
- T030 to T033, once T029 is done: four modules.
- T034 and T035: two documents.

---

## Parallel Example: User Story 3

```bash
# The tests of User Story 3, together:
Task: "T013 In tests/unit/test_benchmark.py, exactly four kinds allowed, and the quiz's tests deleted"
Task: "T014 In tests/unit/test_report.py, render() refuses an extraction result and a made-up kind"
Task: "T015 In tests/unit/test_commands.py, benchmark-report on an extraction result fails, printing nothing"
Task: "T016 Delete tests/unit/test_quiz_metrics.py"

# Then, once T017 has created app/evaluation/kinds.py:
Task: "T018 In app/evaluation/benchmark.py, four kinds and no quiz-only fields"
Task: "T019 In app/evaluation/report.py, the refusal, and no reading or quiz sections"
```

## Parallel Example: User Story 2

```bash
# Once T029 has deleted the service and the writer:
Task: "T030 In app/generation/prompts.py, the Quizzes block"
Task: "T031 In app/generation/factory.py, create_llm_provider(settings, runtime)"
Task: "T032 In app/ingestion/language.py, confident_reply_language"
Task: "T033 In app/config/settings.py and config/generation.yaml, the quiz settings"

# And the records:
Task: "T034 README.md"
Task: "T035 docs/decisions.md"
```

---

## Implementation Strategy

### Baseline First

T002 and T003 hash `main`'s prompts and reports before any change, from a worktree, so the
comparison of T037 has something to compare with.

### MVP (User Story 1)

After T012, the application has no Quiz tab, which is what the owner sees. The rest of the quiz is
unreachable but still in the code: stopping there would be a valid, if incomplete, state.

### Incremental Delivery

1. Setup and Foundational: the baseline, and every behavior that stays tested without the quiz.
2. US1: the tab goes.
3. US3: the benchmark and the report stop using the quiz.
4. US2: the rest goes, with the records.
5. Polish: the comparison, the stack, the refusals, the host's files and the results.

Each checkpoint leaves `make lint-check` and `make test` passing.

---

## Notes

- [P] tasks touch different files and don't depend on an unfinished task.
- The line numbers are `main`'s at `56600c7`. After earlier tasks, find the code by its names.
- Never edit `specs/001` to `specs/005` or `.specify/assessments/chapter-quiz/` (FR-017).
- An import left unused by a removal is `make lint-check`'s to find (ruff F401). `make lint`
  removes it.
- If a test or a check finds something the plan didn't foresee, the plan or the spec is corrected
  first, as "Corrections during implementation" under the spec's Clarifications.
