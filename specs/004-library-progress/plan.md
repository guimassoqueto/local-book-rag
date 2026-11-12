# Implementation Plan: The progress of library operations

**Branch**: `feat/library-progress` | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-library-progress/spec.md`

## Summary

The Library tab gets a progress area that follows its seven operations stage by stage: a bar that
fills with pages while a PDF's text is extracted and with chunks while they are embedded, a
moving bar for the stages that can't be counted, the time left within a counted stage, the time
elapsed, and a line saying how the operation ended. The seven buttons are disabled while one runs.
The commands print the same stages to the error stream, and the log gets a line per stage.

**How.** A tracker, `Progress` in `app/utils/progress.py`, is threaded through the operations: the
services declare their stages and open them, the PDF loader counts pages, the embedding batches
count chunks. It computes the counts, the time left (a median pace, robust to a stalled batch)
and the outcome, and logs each stage's end. The tab runs the service call in a thread and renders
the tracker's snapshot every half second; the commands give it a sink that prints. Nothing the
display does can reach the operation, and the operations make the same calls as today.

`research.md` holds the 15 decisions behind this.

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed with uv.

**Primary Dependencies**: Gradio 6.31 (`gr.HTML` with a native `<progress>`), PyMuPDF for the page
count, filelock for the library lock, the existing embedding provider's `on_batch`. No new
dependency.

**Storage**: None new. The tracker lives in memory for one operation. Stage lines go to the existing
`logs/app.jsonl`, in the app container. The measurement writes to `benchmarks/workspace/progress`,
the `bench_progress_v` collections and `benchmarks/results`, in the app container.

**Testing**: pytest.
- `make test`: the tracker, the operations with and without progress, failures forced at each
  stage, the tab's handlers and events, with fake models, real SQLite and embedded ChromaDB.
- `devtools/measure_library_progress.py`: the four benchmark books on the real stack, against a
  baseline from `main`'s code (constitution V).
- The tab in the browser and the commands in the container (`quickstart.md`).

**Target Platform**: The Docker Compose stack on the owner's Linux machine: an RTX 5060 Ti with
16 GB, `qwen3-embedding:0.6b` on the GPU in batches of 16, PyMuPDF for PDFs.

**Project Type**: A single Python application: Gradio interface, command line, services.

**Performance Goals**: The first stage on screen within 1 s of the click (SC-001); the area
refreshed at least once a second (FR-003); no operation more than 5% or 1 s slower than today
(SC-005); times left within half and double of the truth for 90% of those shown (SC-003).

**Constraints**:
- Reporting changes nothing an operation does, records or leaves (FR-011, FR-013): same calls,
  same exceptions, same journal, same fingerprint, no reindex.
- A failure of the display never reaches the operation (FR-012).
- The tab and the commands compute nothing (FR-016).

**Scale/Scope**: Seven operations; books of up to a few hundred pages and chunks, measured at 3 to
39 s each; a reindex of a handful of books, plus a few saved summaries at about 104 s each.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --------- | ----- | --------------- | ------------ |
| I. Local-first and model-independent | No inference call is added; no model is named in code; no setting is added. | Pass | Pass: the tracker's thresholds are constants of the code, as FR-006 sets them, not a model's property. |
| II. The library is never at risk | Every change still runs in its journaled operation, under the lock; a crash at any step leaves what it leaves today, since the same calls are made in the same order, and R15 says, stage by stage, what that is and how recovery finishes or undoes it; the progress begins inside the lock, after the checks, and every stage that changes the library runs while the journal entry is open (R9, FR-017); nothing in the progress raises into an operation (R10, FR-012). Nothing new is deleted or confirmed. No volume or mount. The measurement stays in `benchmarks/workspace/progress` and `bench_progress_v` (R14). `make up`, which recreates the app container and so deletes the library, is flagged where the quickstart uses it. | Pass | Pass: contracts/progress.md, Guarantees; quickstart § 3. |
| III. Index integrity | No embedding, template, tokenizer or chunking change; the fingerprint is untouched (FR-013), so no reindex. | Pass | Pass: the digests of SC-004 prove the chunks unchanged. |
| IV. One service layer | Stages, counts, times left and outcomes come from the services, through `Progress`; the tab and the commands render `snapshot()` and sink views, and compose the success line from the result as they compose today's notifications. | Pass | Pass: contracts/library-tab.md, contracts/commands.md. The throttle is the tracker's (R7). |
| V. Verified on real models and real books | Ingestion changes (the loader and pipeline signatures, the page count) are checked on the four benchmark books, *Think Python*, *História econômica global*, *On Liberty* and *Quincas Borba*: identical digests, counts reaching their totals. No prompt, parser or judge changes. Every long call still goes through the same providers. | Pass | Pass: quickstart § 1 and § 3. |
| VI. Measured, not assumed | No claim of quality or speed; the time left and the overhead are measured against `main` on a fresh workspace (R14), three runs each, medians compared, and the estimate's accuracy is a fixed criterion with a fixed sampling (SC-003). No judge or metric of the benchmarks changes. | Pass | Pass: the measurement records what a benchmark run records: configuration, Ollama version, models with digest and quantization, hardware, packages, commit and the books' checksums (R14). |
| VII. Every answer traceable | Answers and summaries aren't touched; the reindex's summaries are written by the same calls. | Pass | Pass |
| VIII. Decisions are recorded | Tasks update `README.md` (the area, the commands' lines, the stage lines in the log) and `docs/decisions.md` (what is counted, what isn't, why, the median pace, the polling thread), with the spec's and the measurement's numbers. | Pass | Pass |

No violation: Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/004-library-progress/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R15
├── data-model.md        # StageSpec, the stages of each operation, ProgressView, Outcome, the log line
├── quickstart.md        # baseline, unit tests, real books, browser, commands, log
├── contracts/
│   ├── progress.md      # the tracker and the signatures it is threaded through
│   ├── library-tab.md   # the area, the events, the handlers
│   └── commands.md      # the error stream and standard output
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
app/
├── utils/progress.py               # new: Progress, Stage, StageSpec, ProgressView, Outcome
├── ingestion/
│   ├── base.py                     # DocumentLoader.load(path, stage=None)
│   ├── pdf_loader.py               # counts pages; drops the count for OCR
│   ├── docling_loader.py, epub_loader.py, markdown_loader.py   # the new parameter, unused
│   └── pipeline.py                 # opens extract and prepare
├── services/
│   ├── ingestion_service.py        # opens embed (on_batch) and save
│   ├── book_service.py             # add, replace, reindex_book, remove: stage lists, store, swap
│   ├── library_service.py          # reindex_all: adopt, books with steps, switch, summaries
│   ├── library_data.py             # delete_book and clear: their steps
│   └── reset_service.py            # the resets' stage lists
├── interface/
│   ├── common.py                   # running a service call in a thread and following its snapshot
│   ├── formatting.py               # progress_html, progress_text, the outcome lines
│   └── library.py                  # the area, the event chains, the generator handlers
└── main.py                         # the seven commands pass a Progress printing to stderr

devtools/measure_library_progress.py   # new: the measurement of R14

tests/unit/
├── test_progress.py                # new: the tracker
├── test_progress_devtool.py        # new: the measurement's computations
├── test_commands.py                # new: the commands' error stream and standard output
├── test_book_lifecycle.py, test_library_rebuild.py   # with and without progress; failures per stage
├── test_recovery.py                # unchanged, and must pass
├── test_pdf_loader.py, test_pipeline.py              # the page count, the stages
└── test_interface.py               # formatting, follow(), handlers, outcome lines, button events

README.md, docs/decisions.md
```

**Structure Decision**: The existing single application. The one new module is
`app/utils/progress.py`, since `app/ingestion` must report to it and can't import from
`app/services` (R1).

## Complexity Tracking

None.
