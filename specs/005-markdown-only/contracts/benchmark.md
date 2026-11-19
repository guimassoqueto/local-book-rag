# Contract: the benchmark on Markdown books

## The dataset's books

`benchmarks/datasets/books.yaml` takes the schema in `data-model.md` (`BenchmarkBook`). The three
Markdown files sit in `benchmarks/books` under the names `filename` gives. The owner converts them
with the MarkItDown setup they use for their own books, and records it in `conversion`.

Before `run` does anything, and before `validate` reads a book, each dataset book and each of the
experiment's local books is checked:

| Finding | Outcome |
| ------- | ------- |
| the file is missing | stops: "<key>: benchmarks/books/<filename> is missing. The benchmark's books are Markdown conversions that the owner makes: see README, Benchmarks." |
| its sha256 differs | stops: "<key>: <path> isn't the file the dataset names: its sha256 is <x>, not <y>. Its evidence quotes may not be found in it." |
| `books.yaml` has a key the schema doesn't know, such as the old `url` | `load_dataset` refuses the dataset, naming the key |

## Commands

| Command | Change |
| ------- | ------ |
| `book-rag fetch-benchmark-books` | removed: argparse refuses it as an unknown command |
| `book-rag validate-benchmark` | unchanged, after the check above. It lists every quote not found exactly and every chapter name not found, and exits non-zero while any is left |
| `book-rag benchmark EXPERIMENT` | unchanged, after the check above. An experiment of kind `extraction` is refused when it loads, with the allowed kinds named |
| `book-rag benchmark-report RESULTS [--baseline V]` | unchanged. It still renders an older extraction run's `results.json` |

## `devtools/dump_chunks.py`

```text
python -I /tmp/devtools/dump_chunks.py --out DIRECTORY FILE.md...
```

It runs in the app container, on `main`'s image and on the branch's, with the container's
`config/`. For each file it writes `DIRECTORY/<file name>.json`:

```json
{
  "chapters": [{"number": 1, "title": "…", "sections": ["…", null]}],
  "chunks": [{"chapter_number": 1, "chapter_title": "…", "section_title": "…", "text": "…"}]
}
```

The keys are sorted and the order is the book's. It holds no title, author, page, book ID or chunk
ID. It writes nothing outside `DIRECTORY`, and touches neither the library nor the index: it calls
the pipeline only. The two runs' directories are identical (`cmp` on each file), or SC-002 fails.

## `devtools/compare_runs.py`

```text
uv run python devtools/compare_runs.py BASELINE_RESULTS CHANGED_RESULTS --labels originals markdown
```

It runs on the host, on the branch's code. It reads `results.json` from two retrieval results
directories, each with one variant. It leaves out every question whose `relevant_chunks` is empty
in either run, because none of its evidence resolved to a chunk, and counts them (FR-020). Then it
writes Markdown to standard output:
1. Each run's environment line: the commit, the dataset's sha256, each book's sha256, the date.
   Then the questions left out, by ID, with the run where their evidence resolved nowhere.
2. Both runs' summaries side by side, from `app.evaluation.report`'s rendering.
3. The paired difference of each metric, `markdown − originals`, with its 95% interval from
   `paired_difference`: 4,000 resamples, pairs by question ID. An interval that leaves zero out is
   in bold.
4. Every question whose Recall@5, MRR or nDCG@10 changed, with its book, category, both values and
   both runs' `relevant_chunks`, for reading what each retrieved.

It stops with an error when the two runs share no question, have more than one variant, or are
not retrieval runs.

## Where the files live

| File | On the host | Recorded in the repository (`research.md`, R19) |
| ---- | ----------- | ------------------------------------------------ |
| `datasets/books.yaml`, `questions.jsonl`, `chapter_key_points.jsonl` | `benchmarks/datasets/` | `specs/005-markdown-only/benchmarks/datasets/`, as validated |
| `experiments/markdown_books.yaml` | `benchmarks/experiments/` | `specs/005-markdown-only/benchmarks/experiments/` |
| `experiments/quiz.yaml`, `quiz_models.yaml`, `quiz_check.yaml` | `benchmarks/experiments/`, untouched: the next feature removes the quiz | unchanged in `specs/003-chapter-quiz/benchmarks/` |
| the other experiments | `benchmarks/experiments/`, `extraction.yaml` deleted | unchanged at `c7bb785` |
| the three Markdown books, the owner's História | `benchmarks/books/` | never: the checksums and provenance identify them |

## `benchmarks/experiments/markdown_books.yaml`

```yaml
name: markdown_books
kind: retrieval
description: >-
  The default configuration, run on main with the original PDF and EPUBs and on the branch with
  their Markdown conversions, to compare question by question (specs/005-markdown-only).

variants:
  - name: default
```
