# Implementation Plan: A quiz on a chapter or a book

**Branch**: `feat/chapter-quiz` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-chapter-quiz/spec.md`

## Summary

A Quiz tab quizzes the reader on one chapter or a whole book, with five options per question. The
application owns everything the assessment's probe showed the model doing badly:
- which passages the questions come from;
- which letter is right;
- the order;
- the score;
- what happens to a reply it can't read.

**The model's part** is to write one question per passage, and it never sees a letter. Its reply
is a question, one right answer, four wrong ones and an explanation, as JSON. It can also skip a
passage with nothing to ask about.

**How it reaches the reader.** Questions appear one by one as they are ready. After submission,
every missed question shows its passage. A Markdown download is the only record.

**Measuring it.** Two new benchmark experiment kinds:
- `quiz` measures question writing on six fixed chapters, for any configured model;
- `quiz_check` proves the optional key check on hand-labeled cases, by the rule fixed in FR-027.

`research.md` holds the 14 decisions behind this.

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed with uv.

**Primary Dependencies**: Gradio 6.31 for the tab; the existing Ollama provider
(llama-index-llms-ollama); pydantic for the configuration; PyYAML for the experiments. No new
dependency.

**Storage**: None for quizzes: they live in the session's memory (FR-018). The measurement writes to
`benchmarks/results` and `benchmarks/workspace`, inside the app container. Downloads go through a
temporary directory and Gradio's cache, which is emptied on restart and hourly.

**Testing**: pytest.
- `make test`: unit tests, with fake models, real SQLite and embedded ChromaDB.
- `make test-integration`: the real configured model.
- The `quiz` and `quiz_check` experiments: the real model on real books (constitution V).

**Target Platform**: The Docker Compose stack on the owner's Linux machine: an RTX 5060 Ti with
16 GB, Ollama 0.40.15, gpt-oss:20b.

**Project Type**: A single Python application: Gradio interface, command line, services.

**Performance Goals**: No time limit (SC-008). The estimate is 3 to 5 s per question, so one to
two minutes for 20, plus the check when it is on. The first question appears after one call.

**Constraints**:
- Everything local (constitution I).
- Nothing written to the library (II).
- Every prompt fitted to an 8,192-token window. One 500-token passage per call (FR-011).

**Scale/Scope**:
- One reader.
- At most 50 questions per quiz.
- A whole book of about 200 passages.
- The measurement: about 85 questions per model, on six chapters.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Check | Before research | After design |
| --------- | ----- | --------------- | ------------ |
| **I. Local-first and model-independent** | No inference leaves the machine; models named only in configuration; new settings validated at startup. | PASS: writer and checker are local Ollama models. | PASS. `generation.quiz` is validated, unknown keys fail (FR-029). `check.model` must have a profile. `create_llm_provider` gains an optional model name and still resolves its profile. No code branches on a model name. The cloud-checker idea is left to its own change, after an amendment (`spec.md` § Clarifications). |
| **II. The library is never at risk** | Library changes journaled; no volumes; benchmarks only in their workspace. | PASS: a quiz only reads. | PASS. `QuizService` reads a book's chunks once and writes nothing to the catalog, index or files. The experiments index into `benchmarks/workspace`, including the owner's book as a `local_book` copied into `benchmarks/books`, and never read the library (FR-021). No volume or host folder. The quickstart's restarts and stops say what they keep. |
| **III. Index integrity** | Embedding and chunking unchanged; new settings outside the fingerprint unless they shape the index. | PASS. | PASS. No quiz setting shapes stored vectors, so `IndexService.current_configuration` is untouched. |
| **IV. One service layer** | Operations are service methods; the tab only reads and shows. | PASS. | PASS. `QuizService` holds every rule. The tab streams its events and shows them (`contracts/quiz-tab.md`). The benchmark calls the same service. |
| **V. Verified on real models and real books** | Prompts, parsers and judges checked on real models; long calls through `app/generation`; prompts fitted. | Applies: a new prompt, a new reader, a judge. | PASS. `tests/integration/test_quiz.py` covers the reply format, the skip, the language and the check's readability on the configured model. The `quiz` experiment covers quality on six real chapters in two languages (R14). Readers accept what models write (R4). Every call goes through the provider and is fitted (FR-011). |
| **VI. Measured, not assumed** | Claims measured against a baseline; a judge proves itself first; results record their environment; intervals read honestly. | Applies: quality targets, and the key check is a judge. | PASS. The `quiz` experiment measures SC-001 to SC-006 and SC-008 against the probe's baselines. Seeded passages pair variants for `--baseline` (R6). `quiz_check` applies FR-027, with its comparator and a paired interval, on held-out test cases no wording was tried on, before the check can be on by default. Results record digests, versions, hardware, configuration, commit and book checksums (FR-023). Sound keys come from hand marks, never a judge's score. |
| **VII. Every answer traceable** | Claims trace to passages; no-evidence path kept. | Applies: keys are claims. | PASS. Every question carries its one passage, shown with pages after submission and referenced in the download. Keys must be stated by the passage (FR-005), and the check's verdict is about exactly that. The answering and summary paths are untouched. |
| **VIII. Decisions are recorded** | README and `docs/decisions.md` updated; odd behavior's reasons read first. | Applies. | PASS. The tasks update `README.md` (Interface table, a Quiz section, Benchmarks) and `docs/decisions.md` (R2 to R12, and the check's verdict), and record the runs in `docs/benchmark-results.md`. The decisions this plan builds on were read first: language naming, judges' reasoning, the abstention check's fail-open, benchmarks out of the repository. |

No violation, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-chapter-quiz/
├── spec.md
├── plan.md                  # this file
├── research.md              # Phase 0: decisions R1–R14
├── data-model.md            # Phase 1
├── quickstart.md            # Phase 1: validation scenarios
├── contracts/
│   ├── quiz-service.md      # QuizService
│   ├── model-replies.md     # writer, checker and comparator: what is sent, what is read
│   ├── quiz-tab.md          # the tab, and the download's layout
│   └── quiz-experiments.md  # kinds quiz and quiz_check, reading.csv, key_cases.yaml
├── benchmarks/              # created by /speckit-implement
│   ├── quiz.yaml
│   └── quiz_check.yaml
├── key_cases.yaml           # created by /speckit-implement, from the probe's 24
├── checklists/
│   └── requirements.md
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
app/
├── config/settings.py              # + QuizConfig, QuizCheckConfig, GenerationConfig.quiz, cross-file rules
├── container.py                    # + Container.quizzes; the checker's provider
├── generation/
│   ├── factory.py                  # create_llm_provider(…, model=None)
│   ├── prompts.py                  # + quiz writer, checker and comparator messages
│   └── quiz.py                     # new: QuizWriter, Draft/Skip/Refusal, read_draft, read_check
├── services/
│   └── quiz_service.py             # new: QuizService, Scope, Question, Quiz, events, Result
├── interface/
│   ├── quiz.py                     # new: build_quiz_tab
│   ├── formatting.py               # + slot feedback and ranking Markdown
│   └── gradio_app.py               # + the tab, the refresh, delete_cache
├── evaluation/
│   ├── benchmark.py                # + kinds quiz and quiz_check, local_books, targets, seed, known_cases, commit, book checksums
│   ├── quiz_metrics.py             # new: letter spread, thirds, reading.csv, sound share, the rule
│   └── report.py                   # + the quiz sections
└── main.py                         # benchmark --commit

config/generation.yaml              # + generation.quiz

tests/
├── unit/
│   ├── test_quiz_service.py        # new: passages, letters, order, default, events, grading, document
│   ├── test_quiz_writer.py         # new: reading replies, form, cross-references, check verdicts
│   ├── test_config.py              # + the quiz settings
│   ├── test_benchmark.py           # + the quiz kinds, local books, known cases
│   ├── test_report.py              # + the quiz sections
│   ├── test_llm_provider.py        # + the factory's model argument
│   └── test_interface.py           # + the formatting helpers
└── integration/
    └── test_quiz.py                # new: the configured model on public-domain passages

README.md                           # Interface table, Quiz section, Benchmarks
docs/decisions.md                   # Generation and Evaluation entries
docs/benchmark-results.md           # the quiz runs and the check's proof
```

**Structure Decision**: The existing single-project layout. The rules go in `app/services`, model
I/O in `app/generation`, and the tab in `app/interface`, beside the others. The measurement goes
in `app/evaluation`, as new kinds of the existing runner (research R1, R12).

## Order of work

These are the dependencies that `/speckit-tasks` turns into tasks:

1. **Foundation**: the settings and validation, the factory's model argument, the prompts, and
   `QuizWriter` with its reader, tested on fakes.
2. **User Story 1**: `QuizService` for one chapter (passages, letters, order, default, events,
   grading). Then the tab with streaming, Stop and Submit. Then `test_quiz.py` on the real model.
3. **User Story 4, measurement-first**: the `quiz` kind and its report, run on the six chapters.
   Then the reading. Its numbers decide whether the prompt needs another round before the rest is
   built on it.
4. **User Story 2**: the whole-book allocation, ruled-out chapters, and the ranking.
5. **User Story 3**: the result document, the download, and `delete_cache`.
6. **User Story 5**, in the three steps of research R11, so the check isn't tuned to its own
   test:
   1. **Development.** `key_cases.yaml` starts from the probe's 24 as development cases. At most
      three wordings are tried on them, each with the writer and at most one other configured
      model. That bound is FR-027's allotment.
   2. **Test cases.** The best try is fixed, then measurement runs it never saw are read and
      marked, until the test cases hold at least 10 flawed and 30 sound. The owner reviews the
      labels.
   3. **The rule.** One `quiz_check` run on the test cases gives FR-027's verdict and the shipped
      default. SC-003 is then judged on a run in the shipped configuration.
7. **Records**: the README, `docs/decisions.md`, `docs/benchmark-results.md`, and the quickstart
   run end to end.

## Corrections to the spec made during planning

They are recorded in `spec.md` § Clarifications, under "Corrections during planning":
- **FR-002's limit** counts all the chosen text's passages. "Usable" ones can't be known before
  the model reads them (R5).
- **A preparation is stopped with Stop, then a new one prepared.** Gradio queues a second Prepare
  behind the first (R9).
- **FR-018 and SC-012.** The application's own state keeps nothing. Gradio's served copy of a
  download is removed on restart and hourly (R9).
- **FR-023's commit** is passed to the run with `--commit`, since the container holds no `.git`.

`checklists/model-and-measurement.md` then found 38 points to settle in the requirements on model
output, the key check and the measurement. They are resolved in `spec.md` § Clarifications,
"Corrections from the requirements checklist", and in `research.md` R4, R11 and R12, the data
model and the contracts.

The owner then asked that questions never point to where the answer is: no "segundo o trecho",
passage numbers, pages, sections, or chapters in a whole-book quiz. 20 of the probe's 24 questions
did this. The writer now gets its passage without anything to point at, and replies that point
anyway are refused and written again (FR-004, FR-010, SC-015, research R4).

## Complexity Tracking

No constitution violations to justify.
