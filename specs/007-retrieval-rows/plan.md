# Implementation Plan: What the retrieval benchmark retrieved

**Branch**: `feat/retrieval-rows` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-retrieval-rows/spec.md`

## Summary

Each retrieval row records the two lists that its scores were computed from, and the comparison of
two runs reads them:
- **The rows.** `_run_retrieval` already builds the ranking (`result.candidates`) and the context
  (`result.passages`) as chunk IDs, scores them, and drops them. It keeps them now, as `ranking`
  and `context`, last in the row. They are JSON arrays in `rows.jsonl` and `results.json`, and one
  cell each in `rows.csv`, joined with "; " as `relevant_chunks` is (R1 to R3).
- **The comparison.** `devtools/compare_runs.py` adds a table after "Questions that moved". For
  each question that moved, and each run, it shows the ranks the evidence took, and the chunks
  that ranked above it, down to the lowest-ranked evidence among the first ten (R5, R6). A run
  written before this change says that it didn't record its ranking (R7).
- **The records.** `README.md` (Benchmarks), `docs/decisions.md` (Evaluation) and
  `docs/benchmark-results.md`, which records the runs that check the change (R12).

**How.**
- **Nothing is computed differently.** The scores come from the same two lists, which are now also
  written down. The search, the resolution of the evidence, the metrics, `summarize` and
  `app/evaluation/report.py` don't change, so the averages, `summary.csv` and `benchmark-report`'s
  output can't (R4).
- **One change in the shared writer.** `rows.csv` writes a list as one cell. No row of another kind
  holds a list, so their files don't change (R3).
- **Checked on the stack** against the publisher-back-matter fix's run: the same 75 rows, and the
  same `summary.csv`, byte for byte (R8). A second run, with reranking off, gives the comparison
  questions that moved. Its experiment is kept with this spec (R9).

`research.md` holds the 13 decisions behind this.

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed with uv.

**Primary Dependencies**: Unchanged. The change needs only the standard library's `json` and
`csv`, which the runner and the devtool already use. No package is added or removed.

**Storage**:
- **A retrieval run's files**: each row gains `ranking` and `context`, about 1.2 KB with the
  default configuration, so a 75-question run's three files grow by about 0.3 MB in all (R4).
  `summary.csv` doesn't change.
- **The catalog, ChromaDB, the library and the workspaces**: unchanged (FR-008).
- **The host's `benchmarks/results`**: two new runs (SC-001, SC-005). The fix's two folders are
  read, never written (FR-015).

**Testing**: pytest.
- `make test`: `test_benchmark.py`, `test_compare_runs.py` and `test_report.py` gain the tests of
  R11, on real files, embedded ChromaDB and fake models, as today.
- `make test-integration` doesn't change: no prompt, parser or judge is touched.
- On the stack: two benchmark runs, and throwaway checks of their rows (`quickstart.md`, § 4 to
  § 8).

**Target Platform**: The Docker Compose stack on the owner's Linux machine:
- an RTX 5060 Ti with 16 GB;
- qwen3-embedding:0.6b in Ollama, and Qwen3-Reranker-0.6B on the CPU, as `config/models.yaml` sets
  it. Retrieval runs no LLM;
- today's app container: v0.6.1's image, whose `app/` is `main`'s, with the owner's library
  (*História econômica global*).

**Project Type**: A single Python application, with development tools that run on the host.

**Performance Goals**: A run takes as long as before. The lists are already built, and writing
them adds about a kilobyte per question. `devtools/compare_runs.py` reads two result files, as
today.

**Constraints**:
- **The same scores**, row for row, for the same configuration, dataset, books and models
  (FR-005, SC-001, SC-002).
- **`benchmark-report` prints the same**, for old and new results (FR-006, FR-013, SC-003).
- **Results written before stay as they are**, and render as before (FR-013 to FR-015).
- **No metric, judge, prompt, parser of model output or fingerprint input** changes (FR-021).
- **The history stays untouched**: `.specify/bugs/publisher-back-matter/` and `specs/001` to
  `specs/006` (FR-019).
- **The release**: a `feat:` title, so v0.7.0 unless another release comes first.

**Scale/Scope**:
- **The application.** One module changed, `app/evaluation/benchmark.py`: two keys in a row, and a
  list written as one CSV cell.
- **The development tool.** `devtools/compare_runs.py`: the reading of one run's row, one table,
  and its docstring.
- **The tests.** Three files changed.
- **The records.** `README.md`, `docs/decisions.md` and `docs/benchmark-results.md`, and one
  experiment file in this spec's folder.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --------- | ----- | --------------- | ------------ |
| I. Local-first and model-independent | No inference call is added, and no model is named in code. No setting is added: every retrieval row records the lists. The only models that run are the embedding model and the reranker, local, in the stack, as in every retrieval run. | Pass | Pass: `contracts/retrieval-rows.md`. |
| II. The library is never at risk | No operation on the books, the catalog or the index is added or changed. The benchmark writes the lists into its run's results folder only, and still reaches nothing but `benchmarks/workspace` and the `bench_*` collections (FR-020). `devtools/compare_runs.py` reads two `results.json` files and prints, so it can't rewrite an old result (FR-015). The quickstart's `make up` recreates the app container, and the quickstart says what that deletes: the owner's library (*História econômica global*), its logs, the reranker's downloaded weights and the container's copy of `benchmarks/`. It says that `reset-everything`, confirmed in the service with `DELETE EVERYTHING`, then deletes every `book_chunks_v*` collection, and that the owner adds their book back. No volume or mount. | Pass | Pass: `quickstart.md`, § 3 and § 10; R10. |
| III. Index integrity | No embedding or chunking setting, template, tokenizer or metadata field changes. So the fingerprint stays, and no reindex is needed (FR-008, FR-021). A workspace built before this change stays valid. | Pass | Pass: `data-model.md`, Unchanged. |
| IV. One service layer | No operation is added. The runner in `app/evaluation` records two more fields, and the devtool runs on the host, outside the application. `app/main.py`, `app/services` and `app/interface` don't change. | Pass | Pass. |
| V. Verified on real models and real books | No prompt, parser of model output, judge or ingestion code changes. The check runs the real embedding model and reranker on the dataset's three real books (SC-001), and reads the rows (`quickstart.md`, § 5 to § 8). | Pass | Pass: `quickstart.md`, § 4. |
| VI. Measured, not assumed | No improvement is claimed and no default changes, so no baseline variant has anything to decide. SC-001 checks, row for row, that the scores didn't move from the last run before the change. No metric or judge changes: the same functions compute the six scores from the same lists. A result still records everything that gives its numbers a meaning, and now also what it retrieved, which Principle VI's reading of rows needs. Ingestion doesn't change, so no workspace has to be deleted; the rebuild gives a fresh one anyway. | Pass | Pass: R4 and R8. |
| VII. Every answer traceable | Answers, citations, the no-evidence path and summaries don't change. The generation kind's search records nothing new, and its rows don't change (FR-007), so citation accuracy, abstention quality and `evidence_in_context` are computed as before. | Pass | Pass. |
| VIII. Decisions are recorded | Tasks update `README.md` (Benchmarks), `docs/decisions.md` (Evaluation: why the rows record the lists, why IDs, why that depth) and `docs/benchmark-results.md` (the check's runs) (R12). `docs/decisions.md` was read first. "Relevance is stored as evidence quotes, not chunk IDs" still holds, since a ranking's IDs are read only within their run. "Context recall equals Recall@5 here" is what the recorded context will show: the ranking's first five. The delivered specs and the fix's record aren't edited. | Pass | Pass: R12. |

No violation: Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/007-retrieval-rows/
├── spec.md
├── plan.md                 # this file
├── research.md             # R1–R13
├── data-model.md           # the row, the two lists, the comparison's reading, what stays
├── quickstart.md           # tests, main's outputs, rebuild, two runs, checks, records, library
├── contracts/
│   ├── retrieval-rows.md   # the row in rows.jsonl, results.json and rows.csv; what reads it
│   └── compare-runs.md     # the comparison's output and its new table; old runs
├── benchmarks/
│   └── experiments/
│       └── no_reranking.yaml   # SC-005's second run: the default with reranking off (R9)
├── checklists/
│   └── requirements.md
└── tasks.md                # /speckit-tasks
```

### Source Code (repository root)

```text
app/evaluation/benchmark.py      # _run_retrieval keeps ranking and context in the row; _write_csv writes a list as one cell
devtools/compare_runs.py         # the reading of FR-009 and FR-010, the table after "Questions that moved", the docstring

tests/unit/
├── test_benchmark.py            # the lists in the three files, the scores again, reranking on and off, other kinds unchanged
├── test_compare_runs.py         # each case of FR-009 and FR-010; runs without the lists, alone and with a new one
└── test_report.py               # the lists change nothing that benchmark-report prints

README.md, docs/decisions.md, docs/benchmark-results.md
```

**Structure Decision**: The existing application and its development tools. No module, command or
setting is added. The reading of what ranked above the evidence lives in the devtool, its only
reader, and `benchmark-report` stays as it is (FR-006). The checks on the stack use throwaway
scripts, as `specs/006` did, and the unit tests keep the rules (R11, R13).

## Complexity Tracking

None.
