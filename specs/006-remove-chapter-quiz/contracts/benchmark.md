# Contract: the benchmark without the quiz's kinds

## Experiment kinds

`retrieval`, `generation`, `summarization` and `performance`, defined once as `ExperimentKind` in
`app/evaluation/kinds.py` (R6). Each runs as on `main`, and its result records the same fields
(US3).

## Experiment files

| Field | After |
| ----- | ----- |
| `name`, `kind`, `description`, `variants`, `judge`, `runs`, `max_tokens`, `prompt_book` | unchanged; `kind` takes the four above |
| `local_books`, `targets`, `seed`, `known_cases`, `case_set` | removed (FR-011) |

Unknown fields are still refused (`extra="forbid"`).

## Commands

| Command | Change |
| ------- | ------ |
| `book-rag benchmark EXPERIMENT [--limit N] [--commit C]` | An experiment of kind `quiz` or `quiz_check`, or of any kind with a removed field, is refused when it loads, before any workspace is opened or any model is called: `error: Invalid experiment <path>: …`, naming the four allowed kinds and each field the model doesn't know. The dataset is read first, as today, so a missing dataset is reported before the experiment. Otherwise unchanged |
| `book-rag benchmark-report RESULTS [--baseline V]` | Refuses a result whose kind isn't one of the four (below). Never reads `reading.csv`. Renders the four kinds as on `main`, byte for byte, with or without `--baseline` |
| `book-rag validate-benchmark` | unchanged |
| `make benchmark EXPERIMENT=… [LIMIT=…]` | unchanged |

## `benchmark-report` on a removed kind

| Result's kind | Outcome |
| ------------- | ------- |
| `retrieval`, `generation`, `summarization`, `performance` | rendered as on `main` |
| `quiz`, `quiz_check`, `extraction`, or any other | exit status 1, nothing on standard output, and on standard error: `error: This is a result of the '<kind>' kind, which the benchmark no longer has. benchmark-report renders retrieval, generation, summarization and performance runs.` |

`extraction` results were renderable after `specs/005`. None exists any more (R6).

## `results.json`

Same shape for the four kinds. `environment.book_sha256` holds the dataset's books only, since
experiments have no local books (R5). `environment.commit` is still the `--commit` value.

## The host's `benchmarks/`

| Path | After |
| ---- | ----- |
| `experiments/quiz.yaml`, `quiz_models.yaml`, `quiz_check.yaml`, `key_cases.yaml` | deleted (FR-013) |
| `results/quiz_*`, `results/quiz_models_*`, `results/quiz_check_*` (seven folders) | deleted (FR-013) |
| the dataset, the books, the other experiments and results | unchanged |

`specs/003-chapter-quiz/benchmarks/` and `key_cases.yaml` stay in the repository, as history
(FR-017). The application refuses them, and the README no longer says how to run them.
