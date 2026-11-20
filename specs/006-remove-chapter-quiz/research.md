# Research: Removing the chapter quiz

The decisions behind `plan.md`, each with what was chosen, why, and what else was considered. The
code they rest on was read on `main` at `56600c7` on 2026-11-19, with Gradio 6.32.0 from
`uv.lock`, and the running stack was inspected read-only the same day. Line numbers are `main`'s,
for orientation; names are what the tasks follow.

## R1. What goes whole

**Decision.** Four modules and four test files are deleted:

| Deleted | What it holds |
| ------- | ------------- |
| `app/services/quiz_service.py` | `QuizService`, the quiz's states and results (`Question`, `QuestionReady`, `QuizReady`, `Result`), passage choice, letters, grading, the download |
| `app/generation/quiz.py` | `QuizWriter`, the reading of its replies, `REFUSAL_KINDS` |
| `app/interface/quiz.py` | `build_quiz_tab` |
| `app/evaluation/quiz_metrics.py` | the known cases, `reading.csv` (written and read), the check's verdict, the letter spread and the other quiz figures |
| `tests/unit/test_quiz_service.py`, `test_quiz_writer.py`, `test_quiz_metrics.py` | their unit tests |
| `tests/integration/test_quiz.py` | the quiz on the real models, and the stricter language check (R2) |

Outside these files, only the shared modules of R2 import from them, and those imports go with
the quiz's parts.

**Rationale.** Every symbol in them serves the quiz, and nothing else uses them.

**Alternatives considered.** *Keep the writer for a later feature*: the owner chose removal over
improvement (spec, Context), and `specs/003-chapter-quiz` keeps the design if a quiz ever comes
back.

## R2. The quiz's parts of shared modules

**Decision.** Each shared module loses exactly its quiz part:

| Module | What goes |
| ------ | --------- |
| `app/generation/prompts.py` | the "Quizzes" block at the end (lines 261–391): `QUIZ_LETTERS`, `QuizSource`, the `_QUIZ_*` texts, `_quiz_heading`, `lettered_options`, `quiz_question_messages`, `quiz_check_messages`, `quiz_answer_messages`; and the `dataclass` import, which only `QuizSource` used |
| `app/interface/formatting.py` | the "Quiz tab" block (lines 225–281): `quiz_slot_markdown`, `quiz_choices`, `quiz_progress`, `quiz_outcome`, `quiz_reference`, `quiz_feedback`, `quiz_result_markdown`; and the import of `Question`, `QuizReady`, `Result` |
| `app/interface/gradio_app.py` | the import and call of `build_quiz_tab`, `refresh()`'s `quiz_book` parameter and its dropdown, and `quiz.book` in `selections` and `outputs`. Two comments are reworded (R4) |
| `app/container.py` | the `QuizWriter` and `QuizService` imports, the `quizzes` field, the checker's provider and the service built over `root / "quiz_downloads"` |
| `app/errors.py` | `QuizAlreadyGradedError`, and `NothingToAskError`, which only `QuizService` raises |
| `app/config/settings.py` | `QuizCheckConfig`, `QuizConfig`, `GenerationConfig.quiz`, and the validator's lines on the check's model and on the quiz's token limits (R7) |
| `config/generation.yaml` | the `quiz` section (lines 45–77) and its comments |
| `app/generation/factory.py` | the `model` and `reasoning` parameters of `create_llm_provider` (R3) |
| `app/ingestion/language.py` | `confident_reply_language` and `_MIN_REPLY_CONFIDENCE`, whose comment names the quiz. Only the writer called it. `reply_language` keeps `_identifier(restricted=True)`, which the generation metrics use |
| `app/evaluation/benchmark.py` | the two kinds and everything only they read (R5) |
| `app/evaluation/report.py` | the quiz's sections and the reading (R6) |
| `app/main.py` | `_benchmark_report`'s reading of `reading.csv`, and its import of `read_reading` |

What the quiz shares stays: `format_passage`, the language rules and the other prompts; the
response languages; the context's safety margin; `_identifier`; `BenchmarkJudgeError`, which
RAGAS's adapter raises. An import that the removal leaves unused is reported by `make lint-check`
(ruff's F401) and removed with the rest.

**Rationale.** FR-002 and FR-004 remove the quiz and what only it used; FR-009 keeps the rest as
it is. Each entry above was found by name and checked for other callers with `git grep` on
2026-11-19.

**Alternatives considered.** *Leave unused helpers in place*: they would be code that seems to
serve something, which FR-004 and FR-006 rule out.

## R3. The provider factory

**Decision.** `create_llm_provider(settings, runtime)` builds the provider for `llm.model`, with
its profile as `config/models.yaml` gives it, and `settings.llm` as its configuration. The
`model` and `reasoning` parameters go, with the copy of `llm` for another model and the copy of
the profile for another reasoning level. The docstring stops naming the quiz.

Only two callers passed them, both the key check: the container's checker and `_run_quiz_check`
in the benchmark. A benchmark variant still runs another model or another reasoning level through
its overrides, which `apply_overrides` turns into a whole `Settings` before the factory sees it,
as `_run_generation` and the judges do today.

**Rationale.** FR-004. A per-call model and reasoning exist only for a second task on another
model or level, and no task left has one.

**Alternatives considered.** *Keep the parameters for a later task*: unused code (FR-004), and
adding them back is a few lines when a task needs them.

## R4. What came with the quiz and stays

**Decision.** Three things stay, each with its reason restated without the quiz (FR-007):

- **The stop on SIGTERM.** `stop_on_sigterm`, installed by `serve()`, is unchanged. Its comment
  says what it does for every restart: `docker compose stop` and `restart` send SIGTERM, which the
  container's first process ignored until it was killed 10 s later. Turned into the interrupt
  Gradio closes on, the restart takes about 1 s, and Gradio deletes its cache, the copies of
  uploaded books among it. The comment no longer names quiz results or `FR-018`, which pointed at
  `specs/003`.
- **Gradio's cache sweep.** `delete_cache=CACHE_SWEEP` stays, because Gradio caches every upload.
  In Gradio 6.32, `Blocks` starts its `temp_file_sets` with `upload_file_set`, the upload route
  adds each uploaded file to that set, and `delete_files_created_by_app` sweeps every set in
  `temp_file_sets`. Each book uploaded in the Library tab, up to `uploads.max_size_mb`, leaves a
  copy there. The comment on `CACHE_SWEEP` says so, instead of naming a download.
- **The Library tab's operation thread.** The code doesn't change. Its entry in
  `docs/decisions.md` (Library lifecycle) keeps the lesson, that `operation()`'s log context can't
  be reset across the worker threads that run a Gradio generator's steps, without "which the quiz
  found first" (R12).

**Rationale.** FR-007, and Principle VIII's check: a behavior that looks odd is first looked up in
`docs/decisions.md`. Its Generation entry "The download is the service's file, and Gradio's copy
goes on shutdown" holds both reasons, measured: the restart went from 10 s to 1 s, and copies
outlived a restart without the handler.

**Alternatives considered.**
- *Remove the cache sweep with the download.* Uploaded books' copies would stay in the container
  until it is recreated, each up to the upload limit.
- *Remove the SIGTERM handler.* Every restart would wait 10 s to be killed, and Gradio would never
  delete its cache.

## R5. The experiment kinds, and the fields only the quiz read

**Decision.** In `app/evaluation/benchmark.py`:

- **The kinds.** `Experiment.kind` takes `retrieval`, `generation`, `summarization` and
  `performance`, from `ExperimentKind` (R6).
- **The fields.** `local_books`, `targets`, `seed`, `known_cases` and `case_set` go, with the
  classes `LocalBook` and `QuizTarget`, the validator `check_needs_its_cases`, the docstring's
  five lines, and `load_experiment`'s resolution of the known cases' path. `load_experiment` keeps
  reading and validating the file.
- **The runner.** `run()` loses its two `case`s, and checks the dataset's books alone:
  `_check_books()` loses its `local_books` parameter and loop, `_open()` its `local_books`
  parameter, and `_describe_environment()` records the checksums of the dataset's books only.
  `_run_quiz_check`, `_run_quiz` and `_run_target` go, and `_write()` keeps the plain summary.
- **The module.** `summarize_quiz`, `_QUIZ_ROW_METRICS`, `_QUESTION_METRICS`, `QUIZ_METRICS` and
  `_WHOLE_BOOK` go, with the imports from `quiz_metrics`, `quiz` and `quiz_service`, and
  `QUIZ_LETTERS` and `QuizSource` from the prompts. `_SEED`, the seed of generation and judging,
  stays: it isn't the quiz's.

An experiment file of a removed kind is refused by `load_experiment`, before any workspace is
opened. Pydantic names the allowed kinds, and `extra="forbid"` names the fields the model no
longer has (`targets`, `seed`, `local_books`, `known_cases`, `case_set`), all in one
`ConfigurationError`: "Invalid experiment <path>: …". So is an experiment of a remaining kind that
sets one of those fields, by the same `extra="forbid"`. `BenchmarkRunner` reads the dataset when it
is built, before the experiment is loaded, so a missing dataset is still reported first (spec,
US3).

**Rationale.** FR-011. Only the quiz's experiment files set any of these fields: the three in
`specs/003-chapter-quiz/benchmarks/` and their copies in the host's `benchmarks/experiments/`.
Only `_run_quiz` and `_run_quiz_check` pass local books to `_open()`; `_run_retrieval` and the
others open the dataset's books alone (checked 2026-11-19). So FR-011's "local books unless
another kind indexes them" resolves to removing them.

**Alternatives considered.** *Keep `local_books` as a general field.* No kind left indexes them,
so a retrieval experiment that listed one would check its checksum and then ignore the book,
which misleads.

## R6. `benchmark-report` refuses a kind it doesn't render

**Decision.** `render()` checks the result's kind before anything else. A kind outside
`EXPERIMENT_KINDS` raises `ConfigurationError`:

> This is a result of the 'quiz' kind, which this benchmark doesn't run. benchmark-report renders
> retrieval, generation, summarization and performance runs.

`main()` already prints a `BookRagError` as `error: …` and exits with 1. `render()` returns the
Markdown as a whole and `_benchmark_report` prints it only on success, so a refused result prints
nothing else (FR-012). `render()` loses its `reading` parameter, and `_comparisons()` its
`quiz_check` case.

The four kinds have one definition, in a new module `app/evaluation/kinds.py`: `ExperimentKind`, a
`Literal` of the four, and `EXPERIMENT_KINDS`, its values. `benchmark.py` types `Experiment.kind`
with the first, and `report.py` checks against the second. The module imports nothing from the
application.

This also refuses the `extraction` kind's results, which `specs/005-markdown-only` left
renderable (its `contracts/benchmark.md`). None exists: the host's `benchmarks/results/` holds
retrieval and quiz runs only, and the app container holds no `benchmarks/` (both checked
2026-11-19).

**Rationale.** FR-012. A result of a removed kind can't be rendered right: a `quiz_check` summary
has a shape of its own, and a `quiz` run's figures lose the sections that read them.
`report.py` must stay light: `benchmark-report` imports it alone, and `benchmark.py` imports the
container, RAGAS and the rest of the application.

**Alternatives considered.**
- *Render a removed kind with the generic tables.* A partial report, or a `KeyError`, for a
  `quiz_check` result.
- *List the kinds twice, with a test that they agree.* Two lists to keep in step, for one line
  of code.
- *Have `report.py` import `Experiment` from `benchmark.py`.* That would load the whole
  application to print a Markdown table.

## R7. A configuration with a `quiz` section stops the app

**Decision.** With `QuizConfig` gone, `GenerationConfig` has no `quiz` field, and its
`ConfigModel` forbids unknown keys (`extra="forbid"`). `load_settings` raises
`ConfigurationError("Invalid configuration in <dir>: …")`, whose problems name
`generation.quiz` as a key that isn't permitted. Any command fails the same way at startup. The
validator in `Settings` loses the check of `generation.quiz.check.model` and the loop over the
quiz's two token limits, and keeps the one over the two remaining tasks.

**Rationale.** FR-003 and Principle I: an unknown key is an error. No new code: the refusal is
the one every unknown key gets.

**Alternatives considered.** *Accept and ignore the old section for a release.* Principle I
forbids ignoring a key, and the repository's configuration loses the section in the same commit.

## R8. Proving the prompts unchanged

**Decision.** Three checks, all before the pull request:

1. **The diff.** `git diff main...HEAD -- app/generation/prompts.py` removes lines and adds none.
   The three dots compare with where the branch left `main`, so a later merge into `main` doesn't
   count. The
   modules that hold the judges' prompts, `app/evaluation/summary_metrics.py` and
   `app/evaluation/ragas_llm.py`, aren't in the diff at all, nor are `question_answering.py`,
   `summarization.py` and `citations.py`.
2. **The prompts themselves (SC-002).** A throwaway script builds every remaining prompt from
   fixed inputs, an English and a Portuguese question and passage:
   - `question_answering_messages` and `abstention_check_messages`, with no language (the
     question's own) and with a named one;
   - `map_messages`, `collapse_messages`, `final_summary_messages` and `verification_messages`,
     for each of the four summary types in `config/generation.yaml` (`brief`, `standard`,
     `comprehensive`, `analytical`), in the book's language and in a named one;
   - the summary judge's two prompts, `_COVERAGE_PROMPT` and `_RATING_PROMPT` in
     `summary_metrics.py`, formatted with fixed values.

   RAGAS's judges aren't built by the application: the package writes their prompts, and neither
   its version nor its adapter changes.
3. **The report (US3).** The same script renders the host's retrieval results
   (`markdown_books_*`), the only kind the host holds, without and with a baseline. The other
   kinds rest on `test_report.py`'s tests of them, which don't change.

The script prints one SHA-256 per prompt and per rendering, and runs on a `git worktree` of
`main` and on the branch, each on its own tree, with the same `.venv`. The outputs are identical.
It stays outside the repository, in the session's scratchpad, and its result is recorded in the
spec, under "Results of the implementation".

**Rationale.** SC-002 asks for the prompts built on both versions from the same inputs. The diff
alone shows the code is the same, and the script shows the outputs are.

**Alternatives considered.**
- *A committed `devtools/` script.* It would outlive a one-time check, and need tests of its own.
- *Golden-file tests of the prompts.* They would fail on every future prompt change, which the
  benchmark is meant to judge, not a snapshot.

## R9. Proving the index and the catalog untouched

**Decision.** SC-006 is shown by what the diff touches, as a positive rule:
`git diff main...HEAD --name-only` lists only the files that `plan.md`'s Project Structure names,
the records
(`README.md`, `docs/decisions.md`, `docs/benchmark-results.md`) and this spec's folder. None of
them is an input of the fingerprint:
- `app/services/index_service.py` (`current_configuration`, `METADATA_SCHEMA_VERSION`);
- the embedding providers in `app/embeddings/`, and their profiles, templates and tokenizers in
  `config/models.yaml` and `app/utils/tokenization.py`;
- `app/ingestion/chunker.py`, `app/ingestion/pipeline.py` and `config/ingestion.yaml`.

Nor is the catalog's schema in `app/storage/catalog.py`. `app/ingestion/language.py` is in the
list, but only loses `confident_reply_language`, which ingestion never calls. A file outside the
list stops the check until the plan names it, which also shows US1's "nothing else moves". The
unit tests of the fingerprint and the catalog pass unchanged.

**Rationale.** FR-010. The quiz read chunks and wrote nothing to the library, so nothing in the
library's code needs to move.

**Alternatives considered.** *Build an index on `main`, then check it on the branch.* `make up`
recreates the app container with an empty catalog, so no index record would survive between the
two, and the diff already proves the inputs equal.

## R10. The tests

**Decision.** The four test files of R1 go whole. In the shared files, every test was read and
sorted: deleted when it tests only the quiz, edited when it mentions the quiz in passing, and
rewritten when it is the only test of something that stays and checks it through the quiz.

| File | Deleted | Edited or rewritten | Added |
| ---- | ------- | ------------------- | ----- |
| `tests/unit/test_container.py` | its three tests: the checker's level, the checker's model and profile, `quiz_downloads` | | the container builds one provider, for `llm.model` with its profile, shared by questions and summaries (FR-004). Without it, `assemble()` would have no test |
| `tests/unit/test_llm_provider.py` | `test_a_reasoning_level_replaces_the_profiles_for_that_provider_only` | `test_the_factory_builds_a_named_model_from_its_own_profile` and `test_a_model_without_a_profile_is_refused` name the model through a copy of the settings with another `llm.model`, not the removed parameter. The section comment stops naming `generation.quiz.check` | |
| `tests/unit/test_config.py` | the eight quiz-settings tests, from `test_an_unknown_quiz_key_is_rejected` and `test_the_quiz_settings_load_with_their_defaults` to `test_the_checker_reasoning_can_be_left_to_the_profile` | | an unknown section under `generation`, with a neutral name such as `retired`, stops loading, naming it (FR-003) |
| `tests/unit/test_report.py` | `quiz_results` and the six tests that render a `quiz` or `quiz_check` run | | `render()` refuses an `extraction` result and one of a made-up kind, naming the kind (FR-012); a retrieval result with `by_book` renders "## By book", which only the quiz's fixture exercised |
| `tests/unit/test_interface.py` | the quiz block: its helpers and twelve tests (lines 432–612) | the fixture loses `quizzes`; `test_every_primary_operation_is_reachable` loses `prepare_quiz` and `grade_quiz`; `test_the_interface_clears_gradios_copies_of_downloads_within_the_hour` is renamed for uploads, its assertion unchanged; the imports of `QuizWriter`, `QuizService` and `Path` go | the tabs are Library, Chat, Summarization and Research, in that order (FR-001) |
| `tests/unit/test_benchmark.py` | the quiz drafts and helpers (`QUIZ_DRAFT`, `quiz_reply`, `quiz_experiment`, `answers`, `local_book`, `question_rows`, `quiz_rows`, `FOX`, `known_case`, `check_experiment`, `check_models`, `cases_of`, `check_summary`), and the tests of the two kinds: targets, seed, local books, the reading, the default count, closed-book answers, failed targets, the known cases, the check's verdict and the key's length | the `lab` fixture loses `quiz_llm` and `quizzes`. `test_an_extraction_experiment_is_refused_naming_the_kinds_left` stays on `extraction`, and the allowed kinds it reads are exactly the four, which shows no other kind is left (FR-011). Three are rewritten without the quiz: `test_unknown_quiz_keys_are_refused` becomes a retrieval experiment refused for an unknown key, which, with SC-001's search of the names, shows that the five removed fields are refused; `test_the_environment_records_the_commit_and_every_books_checksum` runs a retrieval experiment; `test_the_known_cases_are_read_beside_the_experiment` becomes `load_experiment` reading a valid retrieval file. The `re` import goes | |
| `tests/unit/test_commands.py` | | the fixture loses `quizzes=None` | `benchmark-report` on an `extraction` result fails naming the kind, and prints nothing to standard output |

Unchanged: `test_sigterm_shuts_gradio_down_as_an_interrupt_does`, every other test file, and the
shared helpers (`tests/conftest.py`, `tests/fakes.py`, `tests/library.py`,
`tests/historical_spelling.py`), which hold nothing quiz-only. The factory keeps its profile
check, since `apply_overrides` and a copy of the settings can hand it a model without one.

No test searches the repository for the word: SC-001 is a one-time check (quickstart), and a
permanent one would trip on Portuguese text in a future fixture. Nor does any test name the quiz,
its kinds or its fields. The refusal tests check their rules with `extraction` or made-up names,
and the quiz's real configuration, experiments and result are refused on the stack (quickstart
§ 6). So SC-001's searches hold for the tests too.

**Rationale.** FR-005: what the shared files checked about the rest stays checked. Six behaviors
were tested only through the quiz: the container's wiring, the factory's profile for a named
model and its refusal of a model without one, an experiment's unknown keys, the environment's
record, and `load_experiment`'s success path. The added tests cover the new refusals (FR-003,
FR-011, FR-012) and the tabs (FR-001).

**Alternatives considered.** *Delete `test_container.py` with its three tests*: `assemble()`, which
builds the whole application, would have no unit test.

## R11. `README.md`

**Decision.**
- **Interface.** "has five tabs" becomes four, and the Quiz row goes.
- **Quizzes.** The section goes whole, from its heading to the start of Benchmarks.
- **Benchmarks.** From "Two more kinds measure the Quiz tab" to the end of the `quiz_check`
  paragraph, everything goes: the two kinds' table, `local_books`, the copy of `specs/003`'s
  experiments, the reading and the known cases. One sentence in that passage isn't the quiz's:
  "Pass the code's commit with `--commit`, since the container holds no `.git`." It moves to the
  general part, after the first code block, since `make benchmark` doesn't pass it.
- **Configuration.** The row for `config/generation.yaml` stops naming the quiz.

**Rationale.** FR-014, and SC-001 for the whole file.

**Alternatives considered.** *A note that the quiz was removed.* The README says how the system
works; why the quiz went is `docs/decisions.md`'s (R12).

## R12. `docs/decisions.md`

**Decision.**
- **Deleted**, as only the quiz needed them (Clarifications):
  - in Generation: "A quiz question is written from one passage, by one call", "The model never
    chooses a letter", "The application chooses the passages", "A quiz's default length follows
    the text's", "The Quiz tab builds its question slots up front", "Questions don't point to
    their passage", "An empty fifth wrong answer is no answer", "The model skips a passage with
    nothing to ask about", "Preparing a quiz logs its own operation lines", "The quiz's key check
    reasons on a provider of its own", and "The download is the service's file, and Gradio's copy
    goes on shutdown", whose lasting part moves (below);
  - in Evaluation: "The quiz measurement pairs runs by seed", "The quiz's length bias is measured
    both ways", "The quiz's key check ships switched off, unproven", and "A comparator answers in
    JSON, not in words".
- **Reworded**, the lesson kept:
  - Ingestion, "Pages were dropped, not read from markers in the Markdown": the list of places
    that locate a passage loses "the quiz's pointers".
  - Library lifecycle, "The operation runs in a thread of its own, and the tab polls its
    progress": without "which the quiz found first".
  - Evaluation, "The benchmark's files left the repository": without "as the quiz's experiments
    are in `specs/003`".
- **Added**:
  - in Infrastructure, after "Nothing is kept in a volume": "The app stops on SIGTERM, and Gradio's
    cache is swept." It holds the measured reasons of R4: the restart in 1 s instead of 10,
    Gradio's cache deleted on close, and `delete_cache=(600, 3000)` for the copies of uploaded
    books.
  - at the end, a section "Removed: the chapter quiz (v0.6.0)" with one entry: what was removed;
    why, which is the owner's use and the two measured shortfalls of the spec's Context; the
    follow-ups dropped; and where the reasoning lives, in `specs/003-chapter-quiz`,
    `.specify/assessments/chapter-quiz/` and the tag `v0.5.0`, the last release with the quiz,
    which no later merge moves.
    It says the quiz's decisions were deleted rather than shortened.

Four entries hold no word "quiz" and are quiz-only all the same: "The application chooses the
passages", "An empty fifth wrong answer is no answer", "The model skips a passage with nothing to
ask about" and "A comparator answers in JSON, not in words". They are deleted with the others.

**Rationale.** FR-015, the owner's choice (Clarifications), and SC-001: after the change, the
file mentions the quiz only in its removal entry.

**Alternatives considered.** *One line per deleted decision, as `specs/005` did for PDF and EPUB*:
the owner chose deletion.

## R13. `docs/benchmark-results.md`

**Decision.**
- **The quiz's section stays**, as history, with a first line saying that the quiz was removed
  in v0.6.0 (`specs/006-remove-chapter-quiz`), so these runs are a record of it. Its run names
  stay as identifiers, though their folders are deleted from the host (R14).
- **Known limitations.** The publisher's advertisements stay a known limitation, worded by what
  still retrieves them: in *História econômica global*'s e-book, the catalog record, copyright
  and five advertisements came in as part of its last chapter, and the Chat tab can retrieve them.
  "The quiz experiments still name the PDF" goes.

**Rationale.** FR-016, and SC-001: the quiz's runs and the removal line are the only mentions
left.

**Alternatives considered.** *Delete the quiz's section.* `docs/benchmark-results.md` is the
record of the runs (Principle VIII), and the owner kept the history (spec, Input).

## R14. The host's files

**Decision.** Last, after the check on the stack that renders one of the quiz's results
(quickstart § 6, spec FR-013), these are deleted from the host's `benchmarks/`, which git
ignores:
- `experiments/quiz.yaml`, `quiz_models.yaml`, `quiz_check.yaml` and `key_cases.yaml`;
- the seven result folders `results/quiz_20261111T130111197357Z`, `…T131123067024Z`,
  `…T131922236657Z`, `…T155628394801Z`, `results/quiz_check_20261111T133933416099Z`,
  `results/quiz_models_20261111T132900247542Z` and `…T160250850655Z`, about 3.3 MB, with the
  agent's unreviewed marks in `marks_review.csv`.

**Rationale.** FR-013 and the owner's answer (Clarifications). The application refuses the
experiments (R5) and the results (R6), and `docs/benchmark-results.md` keeps what they found.
The host's other files stay: the dataset, the books (the PDF of *História econômica global* and the
EPUB originals among them), the eight remaining experiment files and the other results.

**Alternatives considered.** *Keep the results*: the owner chose deletion.

## R15. The running stack, and what `make up` deletes

**Decision.** The checks on the stack come after `make up`, which runs
`docker compose up -d --build`. It rebuilds the app's image and recreates its container, which
deletes what the container holds:
- the library: on 2026-11-19, `list-books` showed it empty;
- `data/quiz_downloads`, which the old code created at start;
- the logs.

ChromaDB and Ollama keep their data, the models included. A recreated app container starts a new
catalog, which numbers its indexes from 1 again, while ChromaDB keeps any `book_chunks_v*`
collection. So `reset-everything`, confirmed with `DELETE EVERYTHING`, comes first, before any
book is added (`docs/decisions.md`, Infrastructure). It deletes the library, empty as it is, and
every `book_chunks_v*` collection.

**Rationale.** Principle II: whatever recreates a container says what that deletes.

**Alternatives considered.** *Restart without rebuilding.* The image would keep `main`'s code, as
`config/` and the code are in the image.

## R16. The release

**Decision.** The pull request's title is `feat: remove the chapter quiz`, without `!`, and its
description has no `BREAKING CHANGE` footer. The release workflow then makes v0.6.0, which the
records name (R12, R13).
- **The branch's commits.** None has `!` after its type or a `BREAKING CHANGE` footer. The squash
  merge copies their messages into its body, where commitizen reads a footer at the start of a
  line. `specs/005`'s `feat!:` commit appeared there as `* feat!: …` and the release stayed minor,
  but a footer would have made it major.
- **The check before the merge.** `git fetch --tags` and
  `git describe --tags --abbrev=0 origin/main` show `v0.5.0`, so the merge makes v0.6.0. If
  another release came first, the records are corrected to the version this merge produces,
  before it merges.

**Rationale.** FR-018 and the owner's answer (Clarifications).

**Alternatives considered.** *`feat!:`, for v1.0.0*: the owner chose `feat:`, the way
`specs/005` was merged.
