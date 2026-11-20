# Data model: Removing the chapter quiz

What goes, what changes shape, and what stays. Each entry says where it lives and which
requirement or decision it follows (`research.md`, R1 to R16).

## Stored, and unchanged

| Entity | Where | Why it doesn't change |
| ------ | ----- | --------------------- |
| Catalog `books`, `indexes` and journal rows | `app/storage/catalog.py` | The quiz read the catalog and wrote nothing to it (FR-010, R9). No migration. |
| Index record and its fingerprint | catalog, `IndexService.current_configuration` | None of its inputs changes: embedding model and digest, dimensions, templates, tokenizer, chunking, `METADATA_SCHEMA_VERSION` (SC-006, R9). |
| ChromaDB collections | `book_chunks_v*` | No chunk or metadata field changes. |
| Originals, processed documents, saved summaries | `data/original_books`, `data/processed`, `data/summaries` | Untouched. |
| Benchmark dataset | `specs/005-markdown-only/benchmarks/datasets/`, the host's `benchmarks/datasets` | Untouched. Its one "quiz" is 19th-century Portuguese ("não quiz fitar"). |

## Removed

### `data/quiz_downloads` (the app container)

The folder where `QuizService.export()` wrote a result for its download, emptied at each start and
each new quiz. Nothing creates, reads or empties it any more (FR-002). The one in the running
container goes when `make up` recreates it (R15).

### `generation.quiz` (`config/generation.yaml`, `QuizConfig` and `QuizCheckConfig`)

| Key | Was |
| --- | --- |
| `temperature`, `max_tokens` | the writer's sampling and reply limit |
| `words_per_question`, `default_max`, `max_questions` | the default length and the most questions |
| `attempts_per_passage` | tries at a passage before another |
| `check.enabled`, `check.model`, `check.reasoning`, `check.max_tokens` | the key check |

The section goes with its two startup checks: that `check.model` has a profile, and that both
token limits leave room for a prompt. A configuration that still holds it, or any key under it,
stops loading: "Invalid configuration in <dir>: …", naming `generation.quiz` (FR-003, R7).

### Experiment fields (`app/evaluation/benchmark.py`, `Experiment`)

| Field | Was |
| ----- | --- |
| `local_books` (`LocalBook`: key, title, language, filename, sha256) | books outside the dataset, indexed beside it, for the quiz's runs |
| `targets` (`QuizTarget`: book, chapter, questions) | the chapters or books a `quiz` run prepares quizzes on |
| `seed` | fixed passages, letters and order, so variants pair up |
| `known_cases`, `case_set` | the key check's known cases, and which set to run |

An experiment that still sets any of them is refused when it loads, with the fields named
(FR-011, R5).

### Experiment kinds

`quiz` and `quiz_check` go. An experiment of either is refused when it loads, with the allowed
kinds named. A result of either is refused by `benchmark-report` (FR-012, R6).

### Benchmark result files of the quiz

`reading.csv`, which a `quiz` run wrote beside its `results.json` for a person to mark, and which
`benchmark-report` read. Nothing writes or reads it any more (FR-011).

### Errors (`app/errors.py`)

`QuizAlreadyGradedError` and `NothingToAskError`, raised only by `QuizService` (FR-004, R2).

## Changed

### `ExperimentKind` (new: `app/evaluation/kinds.py`)

| Name | Value |
| ---- | ----- |
| `ExperimentKind` | `Literal["retrieval", "generation", "summarization", "performance"]` |
| `EXPERIMENT_KINDS` | the same four, as a tuple |

`Experiment.kind` is an `ExperimentKind`, and `render()` refuses a result whose kind isn't in
`EXPERIMENT_KINDS`. The module imports nothing from the application, so `benchmark-report` stays
light (R6).

### `Experiment` (`app/evaluation/benchmark.py`)

| Field | Before | After |
| ----- | ------ | ----- |
| `name`, `description`, `variants`, `judge`, `runs`, `max_tokens`, `prompt_book` | | unchanged |
| `kind` | six kinds | `ExperimentKind`, four kinds |
| `local_books`, `targets`, `seed`, `known_cases`, `case_set` | | removed (above) |

`extra="forbid"` stays, which is what refuses an old quiz experiment's fields.

### `results.json` (`benchmarks/results/<experiment>_<time>/`)

Same shape for the four kinds. `environment.book_sha256` records the dataset's books only, since
no experiment has local books (R5).

### `GenerationConfig` (`app/config/settings.py`)

| Field | After |
| ----- | ----- |
| `question_answering`, `summarization`, `context`, `response_languages` | unchanged |
| `quiz` | removed |

### `Container` (`app/container.py`)

`quizzes` goes. Every other field, and how it is built, stays.

### `create_llm_provider` (`app/generation/factory.py`)

`create_llm_provider(settings, runtime)`: the provider for `llm.model`, with its profile from
`llm_profiles` and `settings.llm` as its configuration. The `model` and `reasoning` parameters go
(FR-004, R3). A benchmark variant or judge on another model or reasoning level gets it through
`apply_overrides`, as today.

### `render()` (`app/evaluation/report.py`)

`render(results, baseline=None)`. The `reading` parameter goes, and a kind outside
`EXPERIMENT_KINDS` raises `ConfigurationError` before any line is written (FR-012, R6).

## Unchanged, though the quiz used them

| What | Where | Still used by |
| ---- | ----- | ------------- |
| `generation.response_languages` | `config/generation.yaml` | the Chat and Summarization tabs' language lists |
| `generation.context.safety_margin` | `config/generation.yaml` | question answering and summaries |
| `format_passage`, the language rules | `app/generation/prompts.py` | every remaining prompt |
| `_identifier(restricted=True)`, `reply_language` | `app/ingestion/language.py` | the generation benchmark's language metric |
| `CACHE_SWEEP`, `stop_on_sigterm` | `app/interface/gradio_app.py` | uploaded books' copies, every restart (R4) |
| `BenchmarkJudgeError` | `app/errors.py` | RAGAS's adapter |
| `_SEED` | `app/evaluation/benchmark.py` | generation and judging |
