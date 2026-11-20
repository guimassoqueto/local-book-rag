# Data model: What the retrieval benchmark retrieved

What changes shape, what is read, and what stays. Each entry says where it lives and which
requirement or decision it follows (`research.md`, R1 to R13).

## The retrieval row (changed)

One per variant and question, made by `BenchmarkRunner._run_retrieval`. It is written to
`rows.jsonl` as soon as the question is scored, and to `results.json` (`rows`) and `rows.csv` at
the run's end.

| Field | Type | Since | Meaning |
| ----- | ---- | ----- | ------- |
| `variant`, `question`, `book`, `category` | string | before | what the row is about |
| `relevant_chapters` | string, joined with "; " | before | the chapters that the evidence resolved to, in book order |
| `relevant_chunks` | string, joined with "; " | before | the chunks that the evidence resolved to, in book order: the union of each quote's chunks |
| `recall_at_5`, `recall_at_10`, `mrr`, `ndcg_at_10` | float | before | computed from `ranking` |
| `context_precision`, `context_recall` | float | before | computed from `context` |
| `retrieval_seconds`, `rerank_seconds` | float | before | timings, which vary from run to run |
| `ranking` | chunk IDs in rank order: an array in JSON, one cell joined with "; " in CSV | this change | every passage the search considered, in the order that the scores read (R1, R2) |
| `context` | chunk IDs in order: as `ranking` | this change | the passages kept after reranking (R1, R2) |

Rules:
- **The scores are the lists'**: computing the six scores again from `ranking`, `context` and the
  question's evidence gives the row's values (FR-003, SC-002).
- **The context is the ranking's first `top_k`** in the benchmark, five with the default
  configuration, or the whole ranking when it is shorter. Each question searches one book (R1).
- **The ranking holds no ID twice**: fusion merges the two searches' lists into one.
- **Lengths**: up to 30 IDs in the ranking with the default configuration. It is fewer when dense
  search and BM25 found the same chunks, and when a chapter-specific question's chapter holds fewer
  chunks.
- **An ID holds within its run**: every ID in a row is a chunk of that run's workspace, and the
  same ID in another run can name other text (FR-011).
- **A question whose evidence resolved to no chunk** has an empty `relevant_chunks`, as today, and
  still records both lists.
- **A row written before this change** has neither key. It stays valid, and is read as not having
  recorded them (FR-013 to FR-015).

## The chunk ID (unchanged)

`{book_id}_chapter_{NN}_chunk_{NNNN}`, as the chunker builds it, for example
`book_001_chapter_11_chunk_0021`: the book's ID in the workspace, its chapter's position, and the
chunk's position in the book. Up to 31 characters in the dataset's books. The comparison shows IDs
as their run recorded them, and never matches IDs across runs (FR-011).

## The comparison's reading of a run (new, never stored)

For each question that moved and each run, `devtools/compare_runs.py` reads the run's row (R5).
The reading is printed, not stored.

| Part | From the row |
| ---- | ------------ |
| The evidence | the IDs of `relevant_chunks`, split on "; " |
| The evidence's ranks | the positions, from 1, of `ranking`'s chunks that are evidence |
| The depth | the largest of those ranks that is 10 or less (the lowest-ranked evidence among the first ten), or, when none is, the smallest of them (the highest-ranked evidence) |
| The evidence shown | the evidence's ranks, up to the depth |
| The chunks above it | each chunk above the depth that isn't evidence, with its rank, in rank order |

Its four states, and what each prints (`contracts/compare-runs.md`):

| The row | Evidence at | Ranked above it |
| ------- | ----------- | --------------- |
| holds no `ranking` | `not recorded` | `not recorded` |
| its ranking holds none of the evidence | `not retrieved` | the ranking's first ten, or all of it when shorter |
| some evidence within the first ten | its ranks, up to the largest that is 10 or less | the other chunks above that rank |
| evidence only below the first ten | its smallest rank, the first piece's | every chunk above it |

## Added

| File | What |
| ---- | ---- |
| `specs/007-retrieval-rows/benchmarks/experiments/no_reranking.yaml` | One variant, `hybrid_rrf`: the default configuration with reranking off, for SC-005's second run (R9). The host's copy goes into `benchmarks/experiments/` to run. |

## Unchanged

| Entity | Where | Why it doesn't change |
| ------ | ----- | --------------------- |
| The summaries: `summary.csv`, and `summary`, `by_category` and `by_book` in `results.json` | `summarize` | They average the six metrics and count samples. No other field is read (R4). |
| The rest of `results.json`: `experiment`, `complete`, `sample_limit`, `environment` | `_write`, `_describe_environment` | Untouched. |
| `benchmark-report`'s output | `app/evaluation/report.py`, `app/main.py` | It reads the summaries and, from the rows, the variant, the metrics and the question (FR-006, FR-013). |
| The rows of the generation, summarization and performance kinds | `_run_generation`, `_run_summarization`, `_run_performance` | Untouched, and they hold no list, so `rows.csv` writes them as before (FR-007, R3). |
| The catalog, the index and its fingerprint, the ChromaDB collections, the workspaces | `app/storage`, `app/ingestion`, `benchmarks/workspace` | No ingestion, chunking or embedding change, and no reindex (FR-008). |
| The dataset and the existing experiments | the host's `benchmarks/`, `specs/005-markdown-only/benchmarks/`, commit `c7bb785` | FR-008. |
| Results written before this change | the host's `benchmarks/results/` | Read, never written (FR-015). |
