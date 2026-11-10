---

description: "Task list for a quiz on a chapter or a book"
---

# Tasks: A quiz on a chapter or a book

**Input**: Design documents from `specs/003-chapter-quiz/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. The constitution's Development Workflow asks for automated tests for every
significant component, and FR-030 for real-model checks. Within each story, the tests come first
and must fail before the implementation.

**Organization**: Grouped by user story. The phases follow the plan's Order of work, not the order
of priority:
1. **US1, one chapter (P1)**, is the MVP.
2. **US4, the measurement (P4)**, comes next. Its numbers decide whether the prompt needs another
   round before more is built on it, and its marked questions become the check's development
   cases.
3. **US2 (P2)** and **US3 (P3)** extend the tab.
4. **US5, the key check (P5)**, needs the measurement and the known cases.
5. **The records** come last.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: a different file, and no dependency on an unfinished task.
- **[Story]**: the user story the task belongs to (US1 to US5).

## Path Conventions

A single Python project, with `app/`, `config/` and `tests/` at the repository root (plan.md,
Project Structure).

- **In the Bash tool**, run
  `export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"` before `make` or
  `uv`.
- **`make up` recreates the app container, which empties the library** (README, Running). After
  it, run `docker compose exec app book-rag reset-everything --confirm "DELETE EVERYTHING"`, which
  deletes the old ChromaDB collections. Then add *História econômica global* again, from
  `~/Documents/livros/01_historia_economica_global.pdf`, through the Library tab or `book-rag
  add-book`. Every task that runs `make up` says so.
- **Long runs**, such as the measurement and the check's proof, take minutes. Run them in the
  background.
- **Commits** happen only when the owner asks.

---

## Phase 1: Setup

**Purpose**: A known starting point.

- [ ] T001 Run `make lint-check` and `make test` on `feat/chapter-quiz`, and record the passing test count in this file's Notes, as the baseline. Uses the `Makefile`.
- [ ] T002 Check that the owner's copy of the book exists at `~/Documents/livros/01_historia_economica_global.pdf`, record its `sha256sum` in this file's Notes for `local_books`, and confirm it equals `book_001`'s checksum in the library: `docker compose exec app python -c` reading `container.books.get_book("book_001").checksum`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The settings, the factory, the prompts and the writer that every story uses.

**⚠️ CRITICAL**: No user story starts until this phase is complete.

### Tests (write first, and see them fail)

- [ ] T003 [P] Add quiz settings tests to `tests/unit/test_config.py`, per `data-model.md` § Quiz settings. They cover:
  - the defaults load: `temperature: 0.2`, `max_tokens: 1500`, `words_per_question: 300`, `default_max: 20`, `max_questions: 50`, `attempts_per_passage: 3`, `check.enabled: false`, `check.model: null`, `check.reasoning: medium`, `check.max_tokens: 2000`;
  - an unknown key under `generation.quiz` stops startup;
  - `check.model` without an `llm_profiles` entry is refused;
  - `max_tokens` or `check.max_tokens` that leaves no room in `llm.context_size` is refused;
  - `default_max` larger than `max_questions` is refused;
  - `check.reasoning` outside `low`, `medium`, `high` or null is refused.
- [ ] T004 [P] Add tests to `tests/unit/test_llm_provider.py`: `create_llm_provider(settings, runtime, model="other")` builds a provider for that model with its own profile's tokenizer and reasoning, and a model without a profile raises `ConfigurationError`.
- [ ] T005 [P] Create `tests/unit/test_quiz_writer.py`, with tests of `read_draft`, per `contracts/model-replies.md` § The writer. They cover:
  - a JSON object alone, inside code fences, or with text around it;
  - `{"skip": …}` read as a skip;
  - each refusal kind:
    - `unreadable` and `cut_off` (`finish_reason == "length"`);
    - `blank_field`;
    - `wrong_count` (3 or 5 wrong answers);
    - `repeated_option`, compared casefolded, with spacing collapsed and final punctuation removed;
    - `cross_reference`: "todas as anteriores", "none of the above", "ninguna de las anteriores", "both A and B", "opção C". "vitamina A" and the Portuguese article "a" must pass;
    - `passage_reference`: "segundo o trecho", "de acordo com a passagem 2", "trecho 3", "the passage", "page 12", a section title from the chunk's metadata, and the chapter's title in a whole-book quiz only. A bare "o trecho da ferrovia" must pass;
    - `wrong_language`: a Spanish draft when Portuguese was named. A short ambiguous text passes.
- [ ] T006 [P] Add prompt tests to `tests/unit/test_quiz_writer.py`. The writer's messages:
  - carry the passage without a number, section or pages, under the book's title and author;
  - add the chapter's title only in a one-chapter quiz;
  - name the language, e.g. "Write … in Portuguese";
  - hold the rules of `contracts/model-replies.md`, and contain no sample values;
  - a passage too long for `context_size × (1 − safety_margin) − max_tokens` is refused before sending (FR-011).

### Implementation

- [ ] T007 Add `QuizCheckConfig` and `QuizConfig` to `app/config/settings.py`, and `quiz: QuizConfig` to `GenerationConfig`, with the types and defaults of `data-model.md` § Quiz settings. Extend `Settings.check_rules_across_files`:
  - `check.model` needs an `llm_profiles` entry;
  - `quiz.max_tokens` and `quiz.check.max_tokens` must each be below `llm.context_size`;
  - `default_max ≤ max_questions`.
- [ ] T008 Add the `generation.quiz` block to `config/generation.yaml`, with the defaults of T003 and a comment on each key in the file's style. `check.enabled: false` until FR-027's verdict (T054).
- [ ] T009 Give `create_llm_provider` in `app/generation/factory.py` an optional `model: str | None = None`. It builds the `LLMConfig` with that model and uses `settings.llm_profiles[model]`, raising `ConfigurationError` when there is no profile.
- [ ] T010 Add `quiz_question_messages`, `quiz_check_messages` and `quiz_answer_messages` to `app/generation/prompts.py`, per `contracts/model-replies.md` (writer, checker, comparator):
  - the passage is formatted without a number, section or pages;
  - the language is named through `language_name`;
  - the field names come without sample values.
- [ ] T011 Create `app/generation/quiz.py` with `Draft`, `Skip`, `Refusal` (kinds: `unreadable`, `cut_off`, `blank_field`, `wrong_count`, `repeated_option`, `cross_reference`, `passage_reference`, `wrong_language`) and `CheckVerdict` (`supported`, `accepted`, `readable`). It also holds:
  - `read_draft(generation, named_language, forbidden_titles)`, with the phrase and pattern lists of `contracts/model-replies.md`, and `reply_language` for the language;
  - `read_check(text, key)`;
  - `QuizWriter`, whose methods are:
    - `write(chunk, …)`: one attempt; it returns a `Draft`, a `Skip`, a `Refusal`, or "passed over" when the passage doesn't fit;
    - `check(question, chunk)`: temperature 0, `check.max_tokens`, `check.reasoning`, one retry at 0.5 with a new seed when unreadable;
    - `answer(question, chunk | None)`: the comparator, at temperature 0.

  Every call goes through `LLMProvider.generate`.
- [ ] T012 Run `make lint` and `make test` (`Makefile`). T003 to T006 pass, and the T001 baseline still passes.

**Checkpoint**: The settings, factory, prompts and writer are tested on fakes.

---

## Phase 3: User Story 1 - A quiz on one chapter, with a score that can be trusted (Priority: P1) 🎯 MVP

**Goal**: The Quiz tab prepares a quiz on one chapter, shows each question as soon as it is ready, and grades it. Missed questions show their passage.

**Independent Test**: `quickstart.md` § 3 and § 4 on Capítulo 1 of `book_001`.

### Tests for User Story 1 (write first, and see them fail)

- [ ] T013 [P] [US1] Create `tests/unit/test_quiz_service.py` with scope and count tests, per `contracts/quiz-service.md`. They cover:
  - `limit()`: the chapter's passages, capped at `max_questions` (50);
  - `default_count()`: `⌊words / 300 + 0.5⌋`, at least 1, at most `default_max` (20) and the limit. 3,115 words gives 10, 5,010 gives 17, 9,757 gives 20, and 3,150 gives 11 (half-up);
  - a book not in `INDEXED` or `REINDEXING` raises `NothingToSearchError`;
  - an unknown chapter raises `ChapterNotFoundError`;
  - a count outside `1 ≤ count ≤ limit()` raises `ConfigurationError`;
  - no language given for a book without one raises `ConfigurationError`.
- [ ] T014 [P] [US1] Add passage, letter and order tests to `tests/unit/test_quiz_service.py`, with the writer scripted. Over many seeds, with N from 1 to 13 on a 13-passage chapter:
  - one passage per question, each from its stratum;
  - every third has a question when N ≥ 3 (SC-005);
  - each letter is the key ⌊N/5⌋ or ⌈N/5⌉ times (SC-001);
  - the order is never the text's when N ≥ 2 (SC-014);
  - the same seed gives the same passages, order and letters.
- [ ] T015 [P] [US1] Add preparation tests to `tests/unit/test_quiz_service.py`:
  - events come as `QuizStarted`, then `QuestionReady` in position order, then `QuizReady`;
  - a refused draft is written again, up to 3 times, then another passage of the same stratum is used, then the nearest one. It keeps its position and letter;
  - every refusal is counted;
  - a skip is replaced the same way. Two skips in a row rule the chapter out: the quiz ends with a shortfall, or raises `NothingToAskError` when no question is ready (FR-007);
  - passages running out give `QuizReady.shortfall > 0`;
  - closing the generator stops at once;
  - a provider error propagates;
  - the chunks are read once, and nothing in the catalog or files changes.
- [ ] T016 [P] [US1] Add grading tests to `tests/unit/test_quiz_service.py`:
  - `score = 100 × right / len(questions)`, exactly (SC-009);
  - None counts as wrong;
  - answers of the wrong length raise `ConfigurationError`;
  - a one-chapter quiz gets an empty ranking.
- [ ] T017 [P] [US1] Add tests of the new formatting helpers to `tests/unit/test_interface.py`:
  - the slot's Markdown, "**7.** <question>";
  - the Radio's choices, "A) …" to "E) …";
  - the progress line, "Preparing: 7 of 20 questions ready";
  - a missed question's feedback: the reader's answer or "not answered", the right answer, the explanation, and the passage with its book, chapter, section and pages.

### Implementation for User Story 1

- [ ] T018 [US1] Add `NothingToAskError(BookRagError)` to `app/errors.py`.
- [ ] T019 [US1] Create `app/services/quiz_service.py` with the types of `data-model.md` (`Scope`, `Question`, `Quiz` and its state, `QuizStarted`, `QuestionReady`, `QuizReady`, `Result`, `ChapterTally`) and `QuizService`:
  - `limit()` and `default_count()`, per research R8;
  - one-chapter passage selection: strata, with a redraw until every third is covered (R6);
  - balanced letters and the order, redrawn if it matches the text's (R7);
  - `prepare()`, with retries, skips and the chapter rule (R5), the event stream, and the `seed`;
  - `grade()`.

  It reads chunks once through the `ChunkSource`. It runs inside `operation(logger, "prepare_quiz", …)`. It holds a hook for the check, off until US5.
- [ ] T020 [US1] Wire `QuizService` into `app/container.py`: `Container.quizzes`, with the writer's `QuizWriter` on the configured LLM.
- [ ] T021 [P] [US1] Add the slot, choices, progress and feedback helpers of T017 to `app/interface/formatting.py`.
- [ ] T022 [US1] Create `app/interface/quiz.py` with `build_quiz_tab`, per `contracts/quiz-tab.md`:
  - Book, Scope (chapters only, until US2), Questions (set from `default_count()`, with the limit in its info line), and Write in;
  - Prepare, and Stop through `cancels`;
  - `max_questions` pre-built slots, filled by the streaming generator with `gr.skip()` for the other slots;
  - Submit, active only on `QuizReady`, and the per-slot feedback;
  - handlers wrapped in `reports_errors`.
- [ ] T023 [US1] Add the Quiz tab to `app/interface/gradio_app.py`, after Summarization, and add its book list to `refresh`'s inputs and outputs.
- [ ] T024 [US1] Create `tests/integration/test_quiz.py` (`pytestmark = pytest.mark.integration`). It writes the passages into the file, from *On Liberty* (public domain), and runs the configured model through `QuizWriter`:
  - an English passage with questions named in Portuguese gives a readable `Draft` in form, in Portuguese, with no `passage_reference`;
  - a bibliography passage gives a `Skip`.
- [ ] T025 [US1] Run `make lint`, `make test` and `make test-integration`. Then `make up`, which empties the library: re-add `book_001` as the Path Conventions say. Walk through `quickstart.md` § 3 and § 4, and note in this file's Notes the time to the first question and to 10 questions.

**Checkpoint**: The MVP works: a graded one-chapter quiz, as each question arrives.

---

## Phase 4: User Story 4 - Comparing models on writing questions (Priority: P4)

**Goal**: A repeatable `quiz` experiment measures question writing on six chapters, and its reading is marked. Done measurement-first: it decides whether the prompt needs another round.

**Independent Test**: `quickstart.md` § 7. Run it, mark the reading, and check that `benchmark-report` shows every FR-019 measure.

### Tests for User Story 4 (write first, and see them fail)

- [ ] T026 [P] [US4] Add tests to `tests/unit/test_benchmark.py`:
  - `Experiment` accepts `kind: quiz` with `local_books`, `targets` and `seed`;
  - unknown keys are refused;
  - a `local_book` whose file is missing, or whose checksum differs, stops the run before any work;
  - the workspace indexes local books beside the dataset's;
  - a quiz run with a scripted writer gives question rows and quiz rows with the fields of `data-model.md` § Measurement;
  - the environment holds `commit` and every book file's checksum.
- [ ] T027 [P] [US4] Create `tests/unit/test_quiz_metrics.py`. It covers:
  - the letter spread, and `model_order_letter`;
  - the share of questions in each third;
  - `reading.csv` written with empty `mark`, `reasons` and `note`, and read back;
  - the share of sound keys over the marked rows only, with the unmarked counted (FR-020);
  - flawed rows counted by reason;
  - `refers_to_passage` notes counted (SC-015).
- [ ] T028 [P] [US4] Add tests to `tests/unit/test_report.py`. The quiz sections render:
  - the letter spread, `key_is_longest`, `closed_book_correct` (without a target), the thirds, `delivered_share`, refusals by kind, skips, passed-over passages, unreadable verdicts and times;
  - with marks, the sound share and `refers_to_passage`.

### Implementation for User Story 4

- [ ] T029 [US4] Extend `app/evaluation/benchmark.py`, per `contracts/quiz-experiments.md`:
  - `Experiment.kind` adds `quiz`, plus `local_books`, `targets` and `seed`;
  - a pre-flight that checks local books' files and checksums;
  - `_open` indexes local books;
  - `_run_quiz` prepares each target through `workspace.container.quizzes` with the seed, times it, and has the writer answer each question without its passage;
  - `_describe_environment` adds `commit` and the book checksums;
  - the run writes `reading.csv`.
- [ ] T030 [P] [US4] Create `app/evaluation/quiz_metrics.py`: the letter spread, the thirds, `reading.csv` writing and reading, the sound share over marked rows, the counts by reason and the `refers_to_passage` count.
- [ ] T031 [US4] Add the quiz sections to `app/evaluation/report.py`. When `reading.csv` holds marks, read them next to `results.json`.
- [ ] T032 [P] [US4] Add `--commit` to the `benchmark` command in `app/main.py`, and pass it to `BenchmarkRunner.run`.
- [ ] T033 [US4] Create `specs/003-chapter-quiz/benchmarks/quiz.yaml`:
  - `local_books`: `book_001`'s copy as `historia_economica_global`, with filename `historia-economica-global.pdf`, `language: pt`, and T002's sha256;
  - `targets`: the six chapters of FR-019, *Capítulo 1/3/6* at 10/17/20 and the benchmark chapters at FR-002's default. After the first indexing, write the computed defaults in as numbers;
  - `seed: 0`;
  - one variant, `gpt_oss_20b`.
- [ ] T034 [US4] Run the measurement as in `quickstart.md` § 7, in the background. Before it, `make up`, which empties the library: re-add `book_001` afterwards. The run copies the benchmarks from `c7bb785`, the experiment and the book into the container. Copy the results out, and run `make lint` and `make test` again first if code changed.
- [ ] T035 [US4] Mark every row of the run's `benchmarks/results/<run>/reading.csv` by FR-020's rubric, run `benchmark-report`, and record SC-002, SC-003, SC-004 and SC-015 in `specs/003-chapter-quiz/tasks.md` § Notes, with their counts.
  - **If a target misses**, revise the writer's prompt in `app/generation/prompts.py`, run T034 again with the same seed, and compare with `benchmark-report --baseline`. An interval including zero counts as no difference.
  - **Limit**: at most three rounds before reporting to the owner.
  - **Every marked question** of these runs is a development case for US5.

**Checkpoint**: The measurement runs and pairs across variants, and the first quality numbers are known.

---

## Phase 5: User Story 2 - A quiz on the whole book, and the chapters to reread (Priority: P2)

**Goal**: Whole-book quizzes, spread by chapter length, never from passages with nothing to ask about, with a ranking of the chapters missed.

**Independent Test**: `quickstart.md` § 5 on the whole of `book_001`.

### Tests for User Story 2 (write first, and see them fail)

- [ ] T036 [P] [US2] Add whole-book tests to `tests/unit/test_quiz_service.py`:
  - the largest-remainder allocation keeps each chapter within one of its share of words, over many N and seeds (SC-006);
  - a chapter ruled out by two skips in a row hands its questions to the others;
  - `forbidden_titles` passed to the writer includes the chapter's title in a whole-book quiz only;
  - the ranking orders by misses, then by share missed, then by book order.

### Implementation for User Story 2

- [ ] T037 [US2] Add whole-book scope (`chapter_number` None) to `app/services/quiz_service.py`: the allocation and its reallocation (R5, R6), the chapter's title in the writer's forbidden titles, and the ranking in `grade()`.
- [ ] T038 [US2] Add "The whole book" as the first Scope choice in `app/interface/quiz.py`, and render the ranking table in the Result through a helper in `app/interface/formatting.py`, with its test in `tests/unit/test_interface.py`.
- [ ] T039 [US2] Run `make test`. Then `make up`, which empties the library: re-add `book_001`. Walk through `quickstart.md` § 5, and record in this file's Notes the spread and any question from *Agradecimentos*, *Referências bibliográficas*, *Leituras complementares*, *Lista de ilustrações* or *Lista de tabelas* (SC-006).

**Checkpoint**: Whole-book quizzes and the chapter ranking work.

---

## Phase 6: User Story 3 - The result, downloaded (Priority: P3)

**Goal**: A Markdown download of the result, with nothing kept in the application.

**Independent Test**: `quickstart.md` § 6.

### Tests for User Story 3 (write first, and see them fail)

- [ ] T040 [P] [US3] Add `result_document()` tests to `tests/unit/test_quiz_service.py`:
  - the file name is `quiz-<book_id>[-ch<NN>]-<YYYYMMDDTHHMMSSZ>.md`;
  - every element of FR-017 is there, in `contracts/quiz-tab.md` § Download's layout, for a one-chapter and a whole-book quiz;
  - "not answered" appears for an unanswered question;
  - the checker's model appears only when the check is on;
  - passages appear as references, not text.

### Implementation for User Story 3

- [ ] T041 [US3] Add `result_document()` to `app/services/quiz_service.py`.
- [ ] T042 [US3] Add the Download button to `app/interface/quiz.py`. It writes `result_document()` into a temporary directory the tab owns, which is emptied on each Prepare and when the app starts. Create the Blocks in `app/interface/gradio_app.py` with `delete_cache=(3600, 3600)`.
- [ ] T043 [US3] Run `make test`. Then `make up`, which empties the library: re-add `book_001`. Walk through `quickstart.md` § 6, including the `find` after `docker compose restart app`, which keeps the library (SC-012).

**Checkpoint**: Results download, and nothing remains after a new quiz or a restart.

---

## Phase 7: User Story 5 - Fewer flawed keys reach the reader (Priority: P5)

**Goal**: The key check, decided by FR-027's rule on held-out test cases.

**Independent Test**: `quickstart.md` § 8 gives a verdict on the test set, and the shipped default follows it.

### Tests for User Story 5 (write first, and see them fail)

- [ ] T044 [P] [US5] Add check tests to `tests/unit/test_quiz_service.py`:
  - with `check.enabled`, a rejected question is replaced from its stratum, keeping its position and letter;
  - an unreadable verdict, after its retry, leaves the question shown and counted;
  - `checker` is recorded on the quiz;
  - a `check.model` other than the writer gets its own provider.
- [ ] T045 [P] [US5] Add `quiz_check` tests to `tests/unit/test_benchmark.py`:
  - `case_set` is required;
  - cases are filtered by set;
  - passages are located by quote, and a quote found nowhere is counted, not run;
  - rows and the summary follow `data-model.md` § Check row;
  - `rule_passes` is null on `development`, and null on `test` with fewer than 10 flawed or 30 sound;
  - (a) uses `paired_difference` and fails a tie;
  - (b) is `sound_rejected / sound_cases ≤ 0.10`.

### Implementation for User Story 5

- [ ] T046 [US5] Enable the check in `app/services/quiz_service.py` through `QuizWriter.check`. Build the checker's provider in `app/container.py`, from `check.model` with `check.reasoning` replacing its profile's reasoning, or reuse the writer's.
- [ ] T047 [US5] Add `kind: quiz_check` with `known_cases` and `case_set` to `app/evaluation/benchmark.py`, and FR-027's rule to `app/evaluation/quiz_metrics.py`, per `contracts/quiz-experiments.md` § `kind: quiz_check`.
- [ ] T048 [US5] Add to `tests/integration/test_quiz.py` the check's verdict on two cases written into the file, from *On Liberty*: one with a sound key, one with a deliberately wrong key. The verdict must be readable for both (FR-030).
- [ ] T049 [US5] Create `specs/003-chapter-quiz/key_cases.yaml`, per `contracts/quiz-experiments.md` § `key_cases.yaml`:
  - the probe's 24 as `set: development`: Q16 `key_not_stated`, Q17 `wrong_key`, Q18 and Q22 `two_defensible`, and the other 20 sound, with notes on Q2, Q7, Q9 and Q13;
  - every question marked in T035, also as development cases.

  Each case's `quote` is a verbatim span of at most 30 words, taken from its passage through the measurement's workspace. No passage text otherwise.
- [ ] T050 [US5] Create `specs/003-chapter-quiz/benchmarks/quiz_check.yaml` (`case_set: development`, `known_cases: …/key_cases.yaml`, the `local_books` of T033). Run the development tries, in the background:
  - at most three wordings of `quiz_check_messages`, each a commit, passed with `--commit`;
  - each wording with the writer and with at most one other configured model as variants.

  Fix the try that does best on the development cases, and record every try in this file's Notes.
- [ ] T051 [US5] Gather the test cases. Run the `quiz` experiment of T033 with a new `seed`, never used before, in the background, and mark its reading. Add its questions to `key_cases.yaml` as `set: test`, and repeat with further new seeds until there are at least 10 flawed and 30 sound. **STOP**: the owner reviews every flawed label and a sample of the sound ones (spec, Assumptions).
- [ ] T052 [US5] Run `quiz_check` with `case_set: test` on the fixed try, and record the verdict. Set `check.enabled` in `config/generation.yaml` as FR-027's rule says, and `check.model` and `check.reasoning` to the try's. If the check ships on, run the `quiz` experiment once more in the shipped configuration and mark it, so SC-003 is judged there. Record the remaining rate of flawed keys.

**Checkpoint**: The check is on or off by its proof, and the shipped configuration is measured.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: The records the constitution requires, and an end-to-end pass.

- [ ] T053 [P] Update `README.md`:
  - **the Interface table**: add a Quiz row;
  - **a Quiz section**: one chapter or the whole book, the default count, questions shown as they come, Stop, submission and feedback, the download, and nothing kept;
  - **the Benchmarks section**: the `quiz` and `quiz_check` experiments, copying them and the owner's book into the container, `--commit`, marking `reading.csv`, and the known cases.
- [ ] T054 [P] Add entries to `docs/decisions.md`, each with the measurement or failure behind it:
  - **under Generation**: one question per call (R2), the model never choosing a letter (R3), reading and refusals including `passage_reference` (R4), skips and the chapter rule (R5), passages and letters and order (R6, R7), the length-based default (R8), and the tab's pre-built slots, Stop and download cache (R9);
  - **under Evaluation**: the quiz measurement and its pairing, the rubric, development and test cases, and the check's verdict and remaining rate.
- [ ] T055 [P] Add a section to `docs/benchmark-results.md`: the measurement runs, each with its environment and commit; the prompt rounds; SC-002, SC-003, SC-004 and SC-015; the check's development tries and its verdict on the test cases.
- [ ] T056 Run the whole of `quickstart.md`, § 1 to § 8, on a fresh `make up`, which empties the library: re-add `book_001` first. Then `make lint-check`, `make test` and `make test-integration`, and record the results in this file's Notes.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: needs Setup. It blocks every story.
- **US1 (Phase 3)**: needs Foundational.
- **US4 (Phase 4)**: needs US1, since the experiment calls `QuizService`.
- **US2 (Phase 5)** and **US3 (Phase 6)**: need US1. They are independent of each other and of US4.
- **US5 (Phase 7)**: needs US4, for the measurement and the development cases of T035.
- **Polish (Phase 8)**: needs every story. T054 and T055 record US5's verdict.

### Within Each Story

- Tests are written first, and fail before the implementation.
- In `app/services/quiz_service.py`, the types and rules come before `prepare()`, and the service
  before the tab.
- Runs on the real stack come last in each story, after `make test`.

### Parallel Opportunities

- **Foundational**: T003, T004, T005 and T006, which are separate test files or sections.
- **US1**: tests T013 to T017; then T021, beside T019.
- **US4**: tests T026 to T028; then T030 and T032, beside T029.
- **US2 and US3**: they can proceed in parallel once US1 is done. They touch the same two files,
  so one of them has to merge the other's changes.
- **US5**: tests T044 and T045.
- **Polish**: T053, T054 and T055.

---

## Parallel Example: User Story 1

```bash
# The tests, together:
Task: "Scope and count tests in tests/unit/test_quiz_service.py"   # T013–T016 share a file: one author
Task: "Formatting helper tests in tests/unit/test_interface.py"    # T017

# Then, beside the service:
Task: "Slot, choices, progress and feedback helpers in app/interface/formatting.py"   # T021
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phases 1 and 2.
2. Phase 3, US1. **STOP and validate** with `quickstart.md` § 3 and § 4: a graded one-chapter quiz,
   with questions shown as they come.

### Measurement Next (User Story 4)

3. Phase 4. Its numbers say whether the writer's prompt holds up (SC-002, SC-003, SC-004, SC-015)
   before more is built on it. Its marked questions seed the check's development cases.

### Incremental Delivery

4. US2: the whole book and the ranking.
5. US3: the download.
6. US5: the check, by its proof. It ships switched off if the rule fails, and the feature is
   complete either way.
7. Polish: the records, and the quickstart end to end.

---

## Notes

- `[P]` means a different file and no dependency on an unfinished task.
- A story's checkpoint leaves the app working. Stop at any checkpoint to validate.
- Results stay in `benchmarks/results`, out of the repository, as does every `reading.csv`. No
  passage text of a book that isn't public enters the repository: known cases hold quotes of at
  most 30 words (FR-020, FR-026).
- **Baseline** (T001): _to fill_.
- **The owner's copy's sha256** (T002): _to fill_.
- **US1 timings** (T025): _to fill_.
- **Measurement results** (T035): _to fill_.
- **Check tries and verdict** (T050–T052): _to fill_.
