# Contract: the retrieval row, and what reads it

## Fields, in order

`variant`, `question`, `book`, `category`, `relevant_chapters`, `relevant_chunks`, `recall_at_5`,
`recall_at_10`, `mrr`, `ndcg_at_10`, `context_precision`, `context_recall`, `retrieval_seconds`,
`rerank_seconds`, `ranking`, `context`.

The first fourteen are today's, in today's order, and hold what they hold today (FR-005).
`ranking` and `context` come last (`research.md`, R2).

## `rows.jsonl`

One JSON object per line, appended as soon as the question is scored, so a run that dies keeps
both lists in the rows already written. An example, abridged (`…`), with illustrative IDs:

```text
{"variant": "default", "question": "think_python_multi_section_05", "book": "think_python",
 "category": "multi_section", "relevant_chapters": "…",
 "relevant_chunks": "book_002_chapter_05_chunk_0061; book_002_chapter_05_chunk_0062",
 "recall_at_5": 1.0, "recall_at_10": 1.0, "mrr": 1.0, "ndcg_at_10": 1.0,
 "context_precision": 1.0, "context_recall": 1.0, "retrieval_seconds": 0.21, "rerank_seconds": 3.9,
 "ranking": ["book_002_chapter_05_chunk_0061", "book_002_chapter_05_chunk_0062",
             "book_002_chapter_09_chunk_0118", "book_002_chapter_04_chunk_0049",
             "book_002_chapter_05_chunk_0060", "book_002_chapter_12_chunk_0170", …],
 "context": ["book_002_chapter_05_chunk_0061", "book_002_chapter_05_chunk_0062",
             "book_002_chapter_09_chunk_0118", "book_002_chapter_04_chunk_0049",
             "book_002_chapter_05_chunk_0060"]}
```

The file holds each row on one line; the example is wrapped to be read.

## `results.json`

`rows` holds the same objects. The file is written with `indent=1`, as today, so each ID of a list
is on a line of its own.

## `rows.csv`

The header gains two columns at its end:

```text
variant,question,book,category,relevant_chapters,relevant_chunks,recall_at_5,recall_at_10,mrr,ndcg_at_10,context_precision,context_recall,retrieval_seconds,rerank_seconds,ranking,context
```

Each list is one cell, its IDs in order, joined with "; ", as `relevant_chunks` is (FR-004):

```text
…,0.21,3.9,book_002_chapter_05_chunk_0061; book_002_chapter_05_chunk_0062; book_002_chapter_09_chunk_0118; …,book_002_chapter_05_chunk_0061; …
```

A list is the only value written this way, and only retrieval rows hold lists (R3).

## Which lists, by configuration

| Configuration | `ranking` | `context` |
| ------------- | --------- | --------- |
| Reranking on, the default | every candidate, in the reranker's order: up to `dense.top_k` + `bm25.top_k`, 30 | its first `reranker.top_k`, 5 |
| Reranking off | every candidate, in the retriever's order: fusion's for `hybrid`, otherwise dense search's or BM25's | its first `reranker.top_k`, 5 |
| A chapter-specific question | as above, within its chapter, so it can hold fewer than ten, or five | as above, or the whole ranking when shorter |

## What the lists satisfy (SC-002)

For a row, take its question's evidence `E` as the runner does: one set of chunk IDs per quote,
from `relevant_chunks(question, chunks)` over the run's chunks of the book. Then:

| Field | Equals |
| ----- | ------ |
| `recall_at_5` | `recall_at_k(ranking, E, 5)` |
| `recall_at_10` | `recall_at_k(ranking, E, 10)` |
| `mrr` | `reciprocal_rank(ranking, E)` |
| `ndcg_at_10` | `ndcg_at_k(ranking, E, 10)` |
| `context_precision` | `context_precision(context, E)` |
| `context_recall` | `context_recall(context, E)` |

And `context` is `ranking[:5]` with the default configuration.

## What reads the rows

| Reader | What it reads | With this change |
| ------ | ------------- | ---------------- |
| `summarize` | the six metrics | unchanged |
| `book-rag benchmark-report RESULTS [--baseline V]` | the summaries and, from the rows, `variant`, each metric and `question` | unchanged. It prints nothing of the lists: the same bytes for a run with them as for the same run without them (FR-006, FR-013) |
| `devtools/compare_runs.py` | the rows and their environment, as today, and now `ranking` | the new table (`contracts/compare-runs.md`) |
| A reader of `rows.csv` or `rows.jsonl` | everything | two more fields |

## Results written before this change

Their rows have neither `ranking` nor `context`. They stay valid as they are:
- **`benchmark-report`** renders them exactly as `main` does, with or without `--baseline`
  (FR-013).
- **`devtools/compare_runs.py`** pairs them with each other and with new results, and says
  `not recorded` where a run has no ranking (FR-014).
- **Nothing rewrites, completes or migrates them** (FR-015).

## Other kinds

The rows of the `generation`, `summarization` and `performance` kinds, and their `rows.csv`, don't
change. The search that the `generation` kind runs once, before its models answer, records nothing
(FR-007).
