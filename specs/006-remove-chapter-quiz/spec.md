# Feature Specification: Removing the chapter quiz

**Feature Branch**: `feat/remove-chapter-quiz`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "Remove the chapter quiz (specs/003-chapter-quiz, released in
v0.3.0) completely: the owner tried it for a while, doesn't use it, and isn't satisfied with its
quality, so it goes rather than being improved. Everything it added goes with it: the Quiz tab,
the quiz service and question writer, their prompts and the key check, the generation.quiz
section of config/generation.yaml, the quiz and quiz_check benchmark kinds and their metrics,
benchmark-report's quiz reading (reading.csv), the quiz's error and its tests, and any code only
the quiz used (such as the LLM provider factory's per-call model and reasoning override, which
only the key check uses). When it's done, no reference to the quiz remains in the code, the
configuration or the tests, comments included; the word still appears as 19th-century Portuguese
spelling in the books and the benchmark dataset ("não quiz fitar"), which isn't the quiz.
Library, chat, summaries, retrieval and the other benchmarks work exactly as before, their
prompts unchanged byte for byte. The catalog and the index are untouched, since the quiz stored
nothing in them, so no reindex is needed. README.md stops describing the quiz, and
docs/decisions.md records the removal and its reason, keeping only lessons that still apply to
the remaining code. The history stays: specs/003-chapter-quiz, .specify/assessments/chapter-quiz,
and the quiz's runs in docs/benchmark-results.md."

## Context

The Quiz tab came with v0.3.0 (`specs/003-chapter-quiz`), after an assessment that ended in go
(`.specify/assessments/chapter-quiz/`). It writes a multiple-choice quiz on a chapter or a whole
book with `llm.model`, one question per passage, grades it, shows the passage to reread for each
question missed, and offers the result as a download.

The owner tried it for a while, doesn't use it, and isn't satisfied with it. The measurements
recorded when it shipped point the same way (`docs/decisions.md`, Evaluation):

- **Keys the passage doesn't state.** About a quarter of gpt-oss's keys aren't stated by their
  passage: the agent's reading, never reviewed, found 65 of 88 sound, against a target of 90%.
  The check written to catch the others ships switched off, because it hasn't proved itself.
- **The right answer stands out.** It is the longest option in about half the questions (53%,
  against a target of 35%), a miss the owner accepted for the time being.

Improving it would take the two follow-ups that `specs/003` left open: the key check's proof (its
User Story 5) and a rule against a key that stands out by its length. The owner chose to remove
the quiz instead, so both are dropped.

What the quiz added:

- **The interface**: the Quiz tab, whose book list is refreshed with the other tabs' after a
  change to the library.
- **Configuration**: the `generation.quiz` section of `config/generation.yaml`, with temperature
  and token limits, the rule for a quiz's default length, the most questions a quiz can have, the
  attempts per passage, and the key check with its own model and reasoning. At startup, the app
  checks that the check's model has a profile, and that both token limits leave room for a
  prompt.
- **Generation**: the question writer and its prompts, the key check, and a stricter language
  check for short texts, which only the writer calls. The LLM provider factory can build a
  provider for another model, or with another reasoning level than its profile's, which only the
  key check asks for.
- **Files**: the result's download, written into `data/quiz_downloads`, which the quiz empties at
  each start and each new quiz.
- **Benchmarks**: two experiment kinds, `quiz`, which measures writer models and prompt rounds,
  and `quiz_check`, which measures the key check on known cases. With them came their metrics,
  their report sections, the experiment fields only they read, and `benchmark-report`'s reading of
  a quiz run's `reading.csv`, where a person marks each question. The experiment files and the
  known cases are recorded in `specs/003-chapter-quiz/`. The host's `benchmarks/` holds copies of
  them in `experiments/`, and the result folders of the quiz's seven runs in `results/`.
- **Errors and tests**: an error for grading a quiz twice, four test files of the quiz's own, unit
  and integration, and quiz cases in seven others.

What it didn't touch: the catalog, the journal, the library lock and the index. The quiz read a
book's chunks and stored nothing in the library. So removing it changes no schema and no index
fingerprint, and needs no reindex. As with any change to the code, the first `make up` recreates
the app container, which empties the library and takes `data/quiz_downloads` with it
(constitution, Principle II).

Some of what came with the quiz now serves the rest of the application too:

- **Stopping on SIGTERM.** The app turns the stop signal into the interrupt that Gradio closes
  on, so a restart takes about 1 s instead of the 10 s after which Docker kills it. It came with
  the quiz's download (`docs/decisions.md`, Generation), and every restart benefits.
- **Gradio's cache sweep.** The interface has Gradio delete its cached files older than 50
  minutes. It came for the download too, but Gradio also caches each book uploaded in the Library
  tab.
- **The Library tab's operation thread.** Its design rests on a lesson the quiz learned first: the
  log context of an operation can't be reset across the worker threads that run a Gradio
  generator's steps (`docs/decisions.md`, Library lifecycle).

The word "quiz" also appears in the 19th-century Portuguese of *Quincas Borba*, one of the
benchmark's books ("não quiz fitar", in the dataset's questions). That spelling isn't the feature,
and stays.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The application without the quiz (Priority: P1)

The owner opens the interface and finds the Library, Chat, Summarization and Research tabs, and
no Quiz tab. Each works as on `main`. Adding, replacing or removing a book refreshes the other
tabs' book lists. A question gets the same prompt, and a chapter summary is made the same way. The
commands are the same. A `config/generation.yaml` that still has a `quiz` section stops the app at
startup, naming the key, as any unknown key does. Restarting the app still takes about a second.

**Why this priority**: This is the change the owner asked for: the quiz goes, and nothing else
moves.

**Independent Test**: Start the stack on this branch's image. Check the tabs, add a book and see
the other tabs' lists take it, then ask a question and make a summary. Start the app again with a
`quiz` section added back, and see it refused. Restart the app container and time it. Run
`make test`, `make test-integration` and `doctor`.

**Acceptance Scenarios**:

1. **Given** the new application, **When** the owner opens the interface, **Then** it has the
   Library, Chat, Summarization and Research tabs, in today's order, and no Quiz tab.
2. **Given** a book added, replaced or removed in the Library tab, **When** the operation
   finishes, **Then** the Chat and Summarization tabs' book lists show the library as it now is,
   as today.
3. **Given** a question in the Chat tab or with `ask`, a chapter summary, or a `search`, **When**
   it runs, **Then** it works as on `main`, and the prompts the model receives are the same, byte
   for byte (SC-002).
4. **Given** a `config/generation.yaml` with a `quiz` section, or any key under it, **When** the
   app or a command starts, **Then** it stops with an error that names the key, as for any unknown
   key.
5. **Given** the running app, **When** its container is stopped or restarted, **Then** the app
   shuts down on the stop signal, as today, without waiting to be killed.

---

### User Story 2 - Nothing left of the quiz (Priority: P2)

The code, the configuration and the tests no longer hold the quiz, nor anything that served only
the quiz: its service, writer, prompts, key check, download, settings, experiment kinds, error,
tests and comments, and the factory's per-task model and reasoning. A comment that named the quiz
as the reason for something that stays gives the reason that still holds. The README describes
the application without it, and `docs/decisions.md` records why it went.

**Why this priority**: The owner asked for the quiz to be removed completely, not switched off.
Code nobody uses still has to be maintained, tested and upgraded, and a comment that cites a
removed feature misleads the next reader.

**Independent Test**: Search the repository for the quiz (SC-001). Read the README's description
of the interface, the benchmarks and the configuration. Run the unit tests.

**Acceptance Scenarios**:

1. **Given** the repository, **When** it is searched for "quiz" in any case, **Then** nothing is
   found outside the records that SC-001 lists.
2. **Given** the LLM provider factory, **When** a provider is built, **Then** it is built for the
   configured model with its profile's settings, the only way left to build one. A benchmark
   variant still gets its provider through its configuration overrides, as today.
3. **Given** the unit and integration tests, **When** they run, **Then** they pass, and what the
   shared test files checked about the rest of the application is still checked.
4. **Given** the README, **When** the owner reads it, **Then** it describes no Quiz tab, no quiz
   settings and no quiz experiments.

---

### User Story 3 - Benchmarks without the quiz's kinds (Priority: P3)

The benchmark runs four kinds of experiment, retrieval, generation, summarization and
performance, each as on `main`. An experiment of the `quiz` or `quiz_check` kind is refused as
unknown. `benchmark-report` renders the four kinds as today, reads no `reading.csv`, and refuses
a result of a removed kind, naming it, instead of rendering part of it. The quiz's measurements
stay in `docs/benchmark-results.md`, as history.

**Why this priority**: The benchmark decides every later comparison (constitution, Principle
VI), so the kinds that remain must not move. The quiz's kinds come after the tab: without the
quiz, there is nothing for them to measure.

**Independent Test**: Run the benchmark's unit tests. Load a `quiz` and a `quiz_check`
experiment, and see each refused. Render a quiz result with `benchmark-report`, and see it
refused. Render a retrieval result, and compare it with `main`'s rendering of the same file.

**Acceptance Scenarios**:

1. **Given** an experiment of the `retrieval`, `generation`, `summarization` or `performance`
   kind, **When** it runs, **Then** it runs as on `main`, and its result records the same fields.
2. **Given** an experiment file of the `quiz` or `quiz_check` kind, **When** `benchmark` loads
   it, **Then** it is refused as an unknown kind, as any other unknown kind is, before anything
   runs.
3. **Given** a result of the `quiz` or `quiz_check` kind kept from before, **When**
   `benchmark-report` reads it, **Then** it refuses it with a message that names the kind, and
   prints no partial report.
4. **Given** the result of a run of a remaining kind, **When** `benchmark-report` renders it,
   with or without `--baseline`, **Then** its output is the same as `main`'s for the same file.

---

### Edge Cases

- **A browser page left open on the old version** loses its Quiz tab at the next load. A quiz in
  progress is lost, as a restart already lost it: the quiz kept nothing outside the browser
  session.
- **A `config/generation.yaml` kept from before**, with its `quiz` section, stops the app at
  startup, naming the key (FR-003). The repository's configuration loses the section, so only a
  copy kept elsewhere can still hold it.
- **A model with a profile only for the key check** doesn't exist: `check.model` is null today,
  so `config/models.yaml` doesn't change.
- **An experiment of a removed kind** is refused when it is loaded, before any workspace is
  opened.
- **A quiz run's result folder**, with `reading.csv` beside its `results.json`, is refused by
  `benchmark-report` for its kind. Nothing reads `reading.csv` any more.
- **The word in Portuguese**: "quiz" in book text and in the benchmark dataset is 19th-century
  spelling, not the feature. The books are outside the repository, and the dataset is under
  `specs/`, so the search of SC-001 doesn't meet them.
- **The download folder left in a running container**, `data/quiz_downloads`, goes when `make up`
  recreates the container. Nothing in the new code reads or deletes it.

## Clarifications

### Session 2026-11-19 (specify)

- Q: The quiz's experiments are deleted from the host's `benchmarks/experiments/`. Are the result
  folders of its seven runs in `benchmarks/results/` deleted too, or kept as the owner's files?
  → A: Deleted too, all seven, with the experiments (FR-013). What they found stays in
  `docs/benchmark-results.md`, and the agent's unreviewed marks go with them.
- Q: Do the decisions in `docs/decisions.md` that explain only the quiz move to a closing
  section, one line each, as `specs/005` did with PDF and EPUB, or are they deleted? → A:
  Deleted, and only the removal is recorded, with its reason (FR-015). Lessons that still apply to
  the remaining code stay where they are, worded without the quiz.
- Q: Is the pull request's title `feat:`, released as v0.6.0, or a breaking `feat!:` with a
  `BREAKING CHANGE` footer, released as v1.0.0? → A: `feat:`, released as v0.6.0, with no
  footer, the way `specs/005` was merged in the end (FR-018).

### Corrections during planning, 2026-11-19

- FR-004 named one quiz-only error, and there are two: `NothingToAskError`, for a chapter with
  nothing to ask about, is raised only by the quiz's service too, and goes (`research.md`, R2).
- FR-007's cache sweep stays. In Gradio 6.32, every upload joins the files that `delete_cache`
  sweeps, so the copies of uploaded books still need it (R4).
- FR-011's local books go. Only the quiz's two kinds index them, and only the quiz's experiment
  files set them (R5).
- FR-012 also refuses the results of the `extraction` kind, which `specs/005` left renderable.
  None exists, on the host or in the container (R6).

## Requirements *(mandatory)*

### Functional Requirements

#### Removing the quiz

- **FR-001**: The interface MUST NOT have a Quiz tab. The Library, Chat, Summarization and
  Research tabs keep their order and behavior, and a change to the library MUST refresh their
  book lists as today.
- **FR-002**: The quiz's service, question writer, prompts, key check and result download MUST be
  removed. Nothing in the application writes or reads `data/quiz_downloads`.
- **FR-003**: The `generation.quiz` section of `config/generation.yaml`, its settings and their
  startup checks MUST be removed. A configuration that still holds the section, or any key under
  it, MUST stop the app at startup with an error that names the key, as any unknown key does.
- **FR-004**: Code that only the quiz used MUST be removed with it:
  - the LLM provider factory's per-task model and reasoning: every provider is built for the
    configured model and its profile, as Chat's and Summarization's are today;
  - the stricter language check for short texts, which only the question writer calls;
  - the errors for grading a quiz twice and for a chapter with nothing to ask about.

  What the quiz shares with the rest of the application stays, such as the context's safety
  margin and the response languages.
- **FR-005**: The quiz's own tests MUST be removed, unit and integration, and so MUST the quiz
  cases in the test files shared with other components. What those shared files check about the
  rest of the application MUST still be checked.
- **FR-006**: Comments, docstrings, the configuration's comments, the commands' help, the
  interface's labels and log messages MUST NOT mention the quiz. A comment that gives the quiz as
  the reason for something that stays MUST give the reason that still holds.
- **FR-007**: What came with the quiz and that the rest of the application relies on MUST stay:
  - **the stop on SIGTERM**, which makes a restart take about 1 s instead of 10 s;
  - **the Library tab's operation thread**, whose reason stays recorded without the quiz;
  - **Gradio's cache sweep**, since Gradio also caches every book uploaded in the Library tab
    (Corrections during planning). `docs/decisions.md` records why.
- **FR-008**: A dependency MUST be removed only if the lock shows it was installed for the quiz
  alone. None is known: the quiz's modules import nothing that the rest of the application
  doesn't.

#### Keeping everything else

- **FR-009**: The Library, Chat, Summarization and Research tabs, retrieval, the commands and the
  four remaining experiment kinds MUST work as on `main`. For the same input, the prompts sent for
  answers, for summaries and by the benchmark's judges MUST be identical to `main`'s, byte for
  byte.
- **FR-010**: The catalog, the journal, the library lock and the index MUST NOT change: no
  schema, no index fingerprint and no index version changes, and no reindex is needed.

#### Benchmarks

- **FR-011**: The `quiz` and `quiz_check` experiment kinds MUST be removed, with their metrics,
  their report sections, the experiment fields that only they read (quiz targets, the seed, known
  cases and case sets, and local books, which no other kind indexes), and `benchmark-report`'s
  reading of `reading.csv`. An experiment of either kind MUST be refused as an unknown kind, as
  any other unknown kind is.
- **FR-012**: `benchmark-report` MUST refuse a result whose experiment kind isn't one of the four
  that remain, with a message that names the kind, and print nothing else. A result of a
  remaining kind MUST render as on `main`.
- **FR-013**: The quiz's experiments MUST be deleted from the host's `benchmarks/experiments/`
  (`quiz.yaml`, `quiz_models.yaml`, `quiz_check.yaml` and `key_cases.yaml`), as `extraction.yaml`
  was with PDF and EPUB, since the application refuses them. So MUST the result folders of the
  quiz's seven runs in `benchmarks/results/` (`quiz_*`, `quiz_models_*` and `quiz_check_*`), the
  agent's unreviewed marks among them. Nothing will read them, and `docs/benchmark-results.md`
  keeps what they found (FR-016). Both are outside the repository, so only the host changes.

#### Records

- **FR-014**: `README.md` MUST describe the application without the quiz. The interface's table
  loses the Quiz row, and the "Quizzes" section goes. The Benchmarks section loses the two kinds,
  their experiments, how to restore them, and the reading. The configuration table's row for
  `config/generation.yaml` stops naming the quiz.
- **FR-015**: `docs/decisions.md` MUST record the removal: what was removed, in which release
  (FR-018), and why, which is the owner's use and the measured shortfalls of the Context. The
  decisions that explain only the quiz MUST be deleted, not kept as a closing section as
  `specs/005` kept PDF and EPUB's: their full reasoning stays in `specs/003-chapter-quiz` and in
  the repository's history. Lessons that still apply stay where they are, worded without the
  quiz:
  - pages dropped (Ingestion), which names the quiz's pointers among the places pages left;
  - the stop on SIGTERM and the cache sweep (FR-007), which today sit in the quiz's entry about
    its download;
  - the Library tab's operation thread (Library lifecycle);
  - where the benchmark's experiment files are recorded (Evaluation), which cites the quiz's.
- **FR-016**: `docs/benchmark-results.md` MUST keep the quiz's runs as history, with a line
  saying that the quiz was removed, and in which release (FR-018). Its Known limitations MUST
  keep the publisher's advertisements indexed as part of a book, worded by what still retrieves
  them, the Chat tab. They MUST drop the limitation about the quiz's experiments naming a PDF.
- **FR-017**: The history MUST NOT be edited: `specs/003-chapter-quiz`,
  `.specify/assessments/chapter-quiz/`, and the mentions of the quiz in `specs/001` to `specs/005`
  (Principle VIII).
- **FR-018**: The pull request's title MUST be a `feat:`, without `!`, and its description MUST
  have no `BREAKING CHANGE` footer, so that the release is v0.6.0. The records MUST name v0.6.0 as
  the release that removed the quiz. Should another release come out first, they name the version
  this merge produces instead.

### Key Entities

- **Generation configuration**: `config/generation.yaml` without its `quiz` section. Everything
  else in it stays as it is.
- **Experiment kind**: four remain, retrieval, generation, summarization and performance.
- **Benchmark result**: a folder with `results.json`, whose experiment kind decides how
  `benchmark-report` renders it. A removed kind's result is refused (FR-012).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Outside `docs/decisions.md`, `docs/benchmark-results.md`, `specs/` and
  `.specify/assessments/`, a search of the repository's tracked files for "quiz", in any case,
  finds nothing. In `docs/decisions.md`, it finds only the entry that records the removal
  (FR-015). In `docs/benchmark-results.md`, it finds only the quiz's runs, kept as history, and
  the line saying that it was removed (FR-016).
- **SC-002**: For the same inputs, the prompts that the application builds for an answer, for
  each step of a chapter summary, and for the benchmark's judges are identical, byte for byte, on
  `main` and on this branch, built on both from the same fixed inputs.
- **SC-003**: `make test` and `make test-integration` pass, and `doctor` reports no failure on the
  running stack.
- **SC-004**: On the running stack, with this branch's image:
  - the interface shows the Library, Chat, Summarization and Research tabs, and no other;
  - a book added in the Library tab appears in the Chat and Summarization tabs' lists;
  - a question is answered with its citations, and a chapter summary is saved;
  - restarting the app container takes under 2 s.
- **SC-005**: Each refusal holds: the app started with a `quiz` section in
  `config/generation.yaml` stops and names the key; a `quiz` and a `quiz_check` experiment are
  refused as unknown kinds; and `benchmark-report` refuses a quiz result, naming its kind.
- **SC-006**: For the same configuration, the index fingerprint and the catalog's schema are the
  same as `main`'s, so an index that `main` built would be current on this branch.

## Assumptions

- **No data migrates.** The quiz stored nothing in the catalog or the index. Its download folder
  and Gradio's copies of it live in the app container, which the first `make up` recreates. That
  empties the library, as any change to the code does (Principle II), and the owner adds their
  books again afterwards.
- **No benchmark measures this change.** It claims no gain in quality or speed, and changes no
  default of what remains (Principle VI). The prompts and parsers of what remains don't change,
  which SC-002 checks, so no run on the real models is needed beyond `make test-integration`
  (Principle V).
- **`specs/003`'s follow-ups are dropped**, not done: the key check's proof (User Story 5, tasks
  T052 and T053) and a length rule for a key that stands out. The ingestion bug about the
  publisher's advertisements stays open, since the Chat tab retrieves them too.
- **The history is kept** (Principle VIII): the quiz's spec, its assessment, its experiments and
  known cases recorded in `specs/003-chapter-quiz/`, and its runs in `docs/benchmark-results.md`.
- **The constitution and `AGENTS.md` don't change.** Neither mentions the quiz.
