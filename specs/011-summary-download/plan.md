# Implementation Plan: Download a summary as Markdown

**Branch**: `feat/summary-download` | **Date**: 2026-11-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-summary-download/spec.md`

## Summary

The Summarization tab's "Save the summary" becomes "Download the summary", which saves a Markdown
file of the summary on the owner's machine:
- **The service builds the file.** `ChapterSummarizer.summary_file(summary)` returns a
  `SummaryFile`, its name and its text: a title naming the book and the chapter, a line naming the
  type and the language asked for, the summary's text as the tab shows it, and, after a rule, a
  note naming the model that wrote it, local or from its cloud provider (R3 to R5).
- **The browser makes the file.** Gradio's download button downloads a file already on the server,
  and the app's cache sweep deletes such a file after 50 minutes, so a late click would fail (R1).
  So `summarize` hands the file's name and text to two hidden boxes, and the button's click runs a
  few lines of JavaScript that turn the text into a file under that name, with no call to the
  server (R2, R6).
- **The tab stops saving.** `on_save`, its `save_summary` endpoint and the summary state go.
  `book-rag summarize --save` keeps summaries in the library, as today (R7).
- **The records.** `README.md` (the interface table, Summaries) and `docs/decisions.md`
  (Generation) (R10).

**How.**
- **One method and one dataclass** in `app/generation/summarization.py`, reading only the summary
  it is given.
- **One tab changed**, `app/interface/summarization.py`: the button, two hidden boxes, the outputs
  of `summarize`, and the download's JavaScript.
- **Checked in a browser** on the stack rebuilt from the branch, with the owner's book and the
  local model, since the unit tests can't run the JavaScript (R9).

`research.md` holds the 10 decisions behind this.

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed with uv.

**Primary Dependencies**: Gradio 6.32.0, already there, and the standard library's `unicodedata`
for the file's name. No package is added or removed.

**Storage**: None changes, and none is added.
- **The download** writes nothing on the server: not in `data/`, not in Gradio's cache, not in
  `/tmp` (FR-009, FR-010).
- **Saved summaries**, `data/summaries/<book_id>/`, stay as they are, written only by
  `book-rag summarize --save` (FR-011).
- **The catalog, ChromaDB, `config/`**: unchanged.

**Testing**: pytest.
- `make test`: `test_summarization.py` and `test_interface.py` gain the tests of R8, on real files,
  real SQLite, embedded ChromaDB and fake models, as today.
- `make test-integration` doesn't change: no prompt, parser of model output or judge is touched.
- On the stack: a summary generated and downloaded in a browser (`quickstart.md`, § 4 to § 6).

**Target Platform**: The Docker Compose stack on the owner's Linux machine, and a browser:
- `gpt-oss:20b`, the local LLM, in Ollama, as `config/models.yaml` sets it;
- today's app container, built from `main`, with the owner's library: one book, `book_001`,
  `02_a_era_das_revolucoes`, 831 chunks, and no saved summary.

**Project Type**: A single Python application, with a Gradio interface and a command line.

**Performance Goals**: A summary takes as long as before. Building the file is string work on a
summary of a few kilobytes, once per generation. The download makes no request.

**Constraints**:
- **The rules stay in the service** (Principle IV): the JavaScript turns a text it is given into a
  file under the name it is given, and decides nothing.
- **Nothing written, nothing sent**: the download calls no model, contacts no provider and writes
  no file on the server (FR-009).
- **How a summary is made doesn't change**: its prompts, citations, report and saved files
  (FR-011, FR-012).
- **No prompt, parser of model output, judge, metric or fingerprint input** changes (FR-016).
- **The history stays untouched**: `specs/001` to `specs/010`, the bug and assessment records
  (FR-019).
- **The release**: a `feat:` title, so v0.11.0 unless another release comes first.

**Scale/Scope**:
- **The application.** Two modules changed: `app/generation/summarization.py` (`SummaryFile`,
  `summary_file` and the helpers of its name) and `app/interface/summarization.py`.
- **The tests.** Two files changed.
- **The records.** `README.md` and `docs/decisions.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --------- | ----- | --------------- | ------------ |
| I. Local-first and model-independent | No inference call is added, and nothing is sent to a provider: the file is built from a summary already made, and the download doesn't reach the server (FR-009). No model is named in code: the note names the model the summary records, and tells local from cloud with `ModelChoices`, not with a model's name. No setting is added. | Pass | Pass: `contracts/summary-file.md`, R2, R4. |
| II. The library is never at risk | No operation on the books, the catalog or the index is added or changed, and the tab stops writing into the library: one write fewer. The download writes nothing on the server (FR-009, FR-010). No volume or mount. The quickstart's `make up` recreates the app container, and the quickstart says what that deletes: the owner's library (`book_001`, `02_a_era_das_revolucoes`), its logs, a summary saved for the check, and the reranker's weights. It copies the book's original out first, runs `reset-everything`, confirmed in the service with `DELETE EVERYTHING`, and adds the book back. | Pass | Pass: `quickstart.md`, § 2 and § 3. |
| III. Index integrity | No embedding or chunking setting, template, tokenizer or metadata field changes. The fingerprint stays, and no reindex is needed (FR-016). | Pass | Pass: `data-model.md`, Unchanged. |
| IV. One service layer | The file's name and text are built by a service method, `ChapterSummarizer.summary_file`, which the tab calls once per generation (FR-015). The tab reads input, calls the service and hands what it returns to the browser. Its JavaScript turns a given text into a file under a given name, and checks, decides and writes nothing on the server. The command line keeps its own way to keep a summary, `summarize --save`, through the same service. | Pass | Pass: R3, R6, `contracts/summarization-tab.md`. |
| V. Verified on real models and real books | No prompt, parser of model output, judge or ingestion code changes. The file carries the output that the summary's parsers already produced, unchanged. The check downloads a real summary, written by `gpt-oss:20b` from the owner's real book, in a real browser, and compares it with the tab (SC-001, SC-002). | Pass | Pass: `quickstart.md`, § 4. |
| VI. Measured, not assumed | No improvement is claimed and no default changes, so no benchmark has anything to decide. No metric or judge changes. Ingestion doesn't change, so no workspace has to be deleted. | Pass | Pass. |
| VII. Every answer traceable | Summaries are made as before, and their citations and references reach the file unchanged, so every claim the tab could trace, the file can (FR-006). The summary benchmark's uncited count is computed by code this change doesn't touch. The note adds the model that wrote it, so a downloaded summary still says where it came from once it leaves the app. Answers, the no-evidence path and the Chat tab don't change (FR-014). | Pass | Pass: `contracts/summary-file.md`. |
| VIII. Decisions are recorded | Tasks update `README.md` (the Summarization row, Summaries) and `docs/decisions.md` (Generation: why the tab downloads instead of saving, why the browser makes the file, why the note names one model, and its form) (R10). `docs/decisions.md` was read first: its cache sweep (Infrastructure) is why the file isn't served from the server (R1), and "A summary is written by one model" (Cloud models) why the note names only the model that wrote it (R4). The delivered specs and the records aren't edited. | Pass | Pass: R10. |

No violation: Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/011-summary-download/
├── spec.md
├── plan.md                    # this file
├── research.md                # R1–R10
├── data-model.md              # SummaryFile, the tab's values, what stays
├── quickstart.md              # tests, the book copied out, rebuild, the browser check, --save, records
├── contracts/
│   ├── summary-file.md        # the file's text and name, with examples
│   └── summarization-tab.md   # the button, the events, the API
├── checklists/
│   └── requirements.md
└── tasks.md                   # /speckit-tasks
```

### Source Code (repository root)

```text
app/generation/summarization.py   # SummaryFile; ChapterSummarizer.summary_file; the title, type line, note and name
app/interface/summarization.py    # the download button, two hidden boxes, summarize's outputs, the JavaScript; no on_save, no state

tests/unit/
├── test_summarization.py         # the file's text and name in every case of R8; nothing read or written
├── test_interface.py             # the button, the events, the API names, summarize's new outputs; nothing saved
└── test_provider_kinds.py        # its summarize call reads the five outputs (spec.md, Corrections during implementation)

README.md, docs/decisions.md
```

**Structure Decision**: The existing application. No module, command or setting is added: the
file's rules join the summaries' service, where `save` and `summarize` are, and the tab changes
where its button is. `app/main.py`, `app/services`, `app/storage`, `config/` and the other tabs
don't change (R7).

## Complexity Tracking

None.
