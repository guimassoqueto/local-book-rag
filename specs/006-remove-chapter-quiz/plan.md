# Implementation Plan: Removing the chapter quiz

**Branch**: `feat/remove-chapter-quiz` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-remove-chapter-quiz/spec.md`

## Summary

The quiz goes from every place it reaches:
- **The interface.** The Quiz tab, its formatting, and its book list among the lists the
  interface refreshes.
- **Generation.** The question writer, its prompts, the key check, and the provider factory's
  per-call model and reasoning, which only the key check used.
- **The service and its files.** `QuizService`, its download folder, and the two errors only it
  raised.
- **Configuration.** The `generation.quiz` section. A leftover one stops the app, as any unknown
  key does.
- **The benchmark.** The `quiz` and `quiz_check` kinds, the experiment fields only they read,
  their metrics and report sections, and `reading.csv`. `benchmark-report` refuses a result of a
  removed kind.
- **The records.** `README.md` stops describing the quiz. `docs/decisions.md` deletes the quiz's
  decisions and records the removal. `docs/benchmark-results.md` keeps the quiz's runs as history.
  The host's quiz experiments and results are deleted.

**How.**
- **Removal by exact parts.** Four modules are deleted, and eleven shared ones lose their quiz
  parts (R1, R2). Three of them also gain what the removal needs: `report.py` refuses a kind it
  doesn't run, `benchmark.py` takes the kinds from the new `kinds.py`, and `gradio_app.py`
  restates two comments (R4, R6). Nothing else in them changes, so the remaining prompts, the
  index fingerprint and the catalog are untouched, which the diff and a dump on both trees prove
  (R8, R9).
- **Three things stay, with their reason restated.** The stop on SIGTERM, Gradio's cache sweep,
  which Gradio 6.32 applies to uploads too, and the Library tab's operation thread (R4).
- **One definition of the kinds**, in a new small module, so that `benchmark-report` can refuse a
  removed kind without loading the runner (R6).
- **Tests.** Six behaviors that were tested only through the quiz get tests of their own (R10).

`research.md` holds the 16 decisions behind this.

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed with uv.

**Primary Dependencies**: Unchanged: Gradio 6.32.0, Pydantic, py3langid and RAGAS stay. No
package is added or removed, since the quiz's modules import nothing that the rest of the
application doesn't (FR-008).

**Storage**:
- **The catalog, ChromaDB and the library's files**: unchanged (FR-010).
- **`data/quiz_downloads`**: no longer written. The running container's goes with `make up`.
- **The host's `benchmarks/`**: four experiment files and seven result folders deleted (R14).

**Testing**: pytest.
- `make test`: four test files deleted, seven shared ones changed. New tests cover the refusals
  (configuration, experiment, report) with `extraction` or made-up names, so that no test names
  the quiz, plus the container's one provider and the four tabs (R10). The quiz's real files are
  refused on the stack (quickstart § 6).
- `make test-integration`, on the real models, without `test_quiz.py`.
- A throwaway script that compares the prompts and a report on `main` and on the branch (R8).
- `quickstart.md`, for the tabs in the browser and the commands in the container.

**Target Platform**: The Docker Compose stack on the owner's Linux machine:
- an RTX 5060 Ti with 16 GB;
- gpt-oss:20b, qwen3-embedding:0.6b and Qwen3-Reranker-0.6B;
- today's app container: `main`'s image, built on 2026-11-19, with an empty library.

**Project Type**: A single Python application: Gradio interface, command line, services.

**Performance Goals**: A restart under 2 s, as on `main` (SC-004). Nothing may get slower: no
remaining path's code changes.

**Constraints**:
- **The same prompts**, byte for byte, for answers, summaries and the judges (FR-009, SC-002).
- **The same library**: catalog, journal, lock and index untouched, and no reindex (FR-010,
  SC-006).
- **The history untouched**: `specs/001` to `specs/005` and `.specify/assessments/chapter-quiz/`
  (FR-017).
- **The release**: a `feat:` title and v0.6.0, named in the records (FR-018).

**Scale/Scope**:
- **The application.** Four modules deleted; eleven changed, with `config/generation.yaml`; one
  added, `app/evaluation/kinds.py`.
- **The tests.** Four files deleted, seven changed.
- **The records.** `README.md`, `docs/decisions.md` and `docs/benchmark-results.md`.
- **The host.** Four experiment files and seven result folders, about 3.3 MB.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --------- | ----- | --------------- | ------------ |
| I. Local-first and model-independent | No inference call is added, and no model is named in code. The removal takes out the code that let one task pick its own model and reasoning, so every provider comes from configuration: `llm.model` with its profile, or a benchmark variant's overrides. One section goes (`generation.quiz`) and none is added; a leftover one stops the app at startup as an unknown key. No profile changes. | Pass | Pass: `contracts/configuration.md`. |
| II. The library is never at risk | No operation on the books, the catalog or the index is added or changed, and the quiz wrote nothing to them (FR-010). The application deletes nothing new. No volume or mount. `make up` recreates the app container, and the quickstart says what that deletes: the library (empty on 2026-11-19), the logs and `data/quiz_downloads`. It says that `reset-everything`, confirmed in the service with `DELETE EVERYTHING`, then deletes every `book_chunks_v*` collection (§ 4). Benchmark code still reaches only `benchmarks/workspace` and the `bench_*` collections. The host's quiz files are deleted by hand, outside the application (R14). | Pass | Pass: quickstart § 4 and § 7. |
| III. Index integrity | No embedding or chunking setting, template, tokenizer or metadata field changes. So the fingerprint and `METADATA_SCHEMA_VERSION` stay, and no reindex is needed. The diff touches none of the fingerprint's inputs (R9). | Pass | Pass: `data-model.md`, Stored, and unchanged. |
| IV. One service layer | No operation is added, and the Quiz tab goes with its service. Each refusal lives where its kind of rule already does: configuration in `Settings`, experiments in `Experiment`, and results in `render()` (`app/evaluation/report.py`). `app/main.py` only reads input and prints, and the Gradio app only wires tabs. | Pass | Pass: `contracts/benchmark.md`. |
| V. Verified on real models and real books | The quiz's prompts and parsers go, and no other prompt or parser changes. The diff of `prompts.py` only removes lines, and a dump of every remaining prompt matches on `main` and on the branch (R8). `make test-integration` runs the remaining paths on gpt-oss:20b, qwen3-embedding:0.6b and Qwen3-Reranker-0.6B. SC-004 reads an answer and a summary in the browser, on a real book. Ingestion doesn't change. | Pass | Pass: quickstart § 3 and § 5. |
| VI. Measured, not assumed | No improvement is claimed and no default changes for what remains, so no benchmark comparison is needed. No judge or metric is added or changed: the key check and the quiz's metrics are removed, and the remaining judges' prompts are byte-identical (R8). The remaining kinds record the same fields; `environment.book_sha256` loses only local books, which no remaining kind used (R5). | Pass | Pass: `contracts/benchmark.md`. |
| VII. Every answer traceable | Answers, citations, the no-evidence path and summaries' citations by lookup don't change: their code isn't in the diff, and their prompts match `main`'s. A regression would show in `make test-integration`'s abstention cases, and in SC-004's reading of an answer's citations. The generation benchmark's citation accuracy and abstention quality, and the summary's uncited count, depend on no code this feature changes. | Pass | Pass. |
| VIII. Decisions are recorded | Tasks update `README.md` (Interface, Quizzes, Benchmarks, Configuration) and `docs/decisions.md`: deleted, reworded and added entries, and the removal (R12). They update `docs/benchmark-results.md` (R13). `docs/decisions.md` was read first for each behavior that looks odd and stays: the stop on SIGTERM, the cache sweep and the Library tab's thread (R4). The delivered specs aren't edited. | Pass | Pass: R11 to R13. |

No violation: Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-remove-chapter-quiz/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R16
├── data-model.md        # what goes, what changes shape, what stays
├── quickstart.md        # tests, the search, the same as main, rebuild, stack, refusals, host files, records
├── contracts/
│   ├── interface.md     # the four tabs, the refresh, Gradio's files, stopping
│   ├── configuration.md # generation.yaml, a leftover quiz section, the provider
│   └── benchmark.md     # kinds, experiment files, commands, refusals, the host's files
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
app/
├── services/quiz_service.py     # deleted
├── generation/
│   ├── quiz.py                  # deleted
│   ├── prompts.py               # the Quizzes block and the dataclass import go
│   └── factory.py               # create_llm_provider(settings, runtime)
├── interface/
│   ├── quiz.py                  # deleted
│   ├── formatting.py            # the Quiz tab block and its import go
│   └── gradio_app.py            # four tabs, refresh without the quiz's book, two comments reworded
├── evaluation/
│   ├── quiz_metrics.py          # deleted
│   ├── kinds.py                 # new: ExperimentKind, EXPERIMENT_KINDS
│   ├── benchmark.py             # four kinds; no local_books, targets, seed, known_cases, case_set
│   └── report.py                # refuses a removed kind; no reading, no quiz sections
├── ingestion/language.py        # no confident_reply_language
├── config/settings.py           # no QuizConfig or QuizCheckConfig; the validator without the quiz
├── container.py                 # no quizzes
├── errors.py                    # no QuizAlreadyGradedError or NothingToAskError
└── main.py                      # benchmark-report reads no reading.csv

config/generation.yaml           # no quiz section

tests/
├── integration/test_quiz.py     # deleted
└── unit/
    ├── test_quiz_service.py, test_quiz_writer.py, test_quiz_metrics.py   # deleted
    └── test_container.py, test_llm_provider.py, test_config.py, test_report.py,
        test_interface.py, test_benchmark.py, test_commands.py           # changed (R10)

README.md, docs/decisions.md, docs/benchmark-results.md
```

**Structure Decision**: The existing single application. The feature removes code. The one new
module, `kinds.py`, holds the four experiment kinds, so that the report checks them without
loading the runner (R6). No development tool is added: the comparisons with `main` use a
throwaway script (R8).

## Complexity Tracking

None.
