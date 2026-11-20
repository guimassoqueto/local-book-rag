# Contract: services

What the tabs and the commands call, and what each returns or raises (FR-006 to FR-025,
FR-032; `research.md`, R6 to R12). Every rule lives here, not in the interface (Principle IV).

## The container (`app/container.py`)

`Container` gains `models: ModelChoices`. `assemble(settings, environment, collection_prefix,
environ=None)` builds the local provider as today, with `create_llm_provider()`, the cloud
providers with `create_cloud_providers(settings, environ)`, and the choices from both. Only
`build_container()` passes an environment, the process's; without one, as the benchmarks'
workspaces are assembled, there is no cloud provider. It passes the choices to
`QuestionAnsweringService`, `ChapterSummarizer` and `HealthService`. It logs each provider that has
one setting only, and contacts no provider.

## `QuestionAnsweringService` (`app/generation/question_answering.py`)

```python
QuestionAnsweringService(settings: Settings, retrieval: RetrievalService, models: ModelChoices)

def stream(
    self,
    question: str,
    filters: RetrievalFilters,
    language: str | None = None,
    retrieval_config: RetrievalConfig | None = None,
    model: str | None = None,
    fallbacks: Sequence[str] = (),
) -> Iterator[RetrievalResult | TextDelta | AttemptFailed | Answer]: ...

def answer(...same arguments...) -> Answer: ...
```

The events, in order:
1. `ModelChoiceError`, raised before anything else, for a refused sequence.
2. One `RetrievalResult`.
3. For each model of the sequence until one answers: its `TextDelta`s, then, if it fails and
   isn't the last, one `AttemptFailed`. The `TextDelta`s that came before an `AttemptFailed` are
   withdrawn.
4. One `Answer`, or, when the last model fails: its own error if nothing failed before it, or
   `AllModelsFailedError`.

With no passage retrieved, the `Answer` comes right after the `RetrievalResult`, and no model is
called. Without `model` and `fallbacks`, the events are today's, and so is the `Answer`, which also
names the local model and its provider.

## `ChapterSummarizer` (`app/generation/summarization.py`)

```python
ChapterSummarizer(settings, models: ModelChoices, catalog, chunks, documents, locator)

def summarize(
    self,
    book_id: str,
    chapter_number: int,
    summary_type: str,
    language: str | None = None,
    on_progress: Callable[[str], None] | None = None,
    model: str | None = None,
    fallbacks: Sequence[str] = (),
) -> ChapterSummary: ...

def save(self, summary: ChapterSummary) -> str: ...
```

- The sequence is resolved before the chapter is read; a refused one raises `ModelChoiceError`.
- Each model makes the whole summary. A failure of any step, by a model that isn't the last, sends
  `"claude-sonnet-5-5 (Anthropic) failed: it limited the rate. Starting again with gpt-oss:20b."`
  to `on_progress`, and the summary starts again with the next model. The failed attempt keeps
  the tokens of the steps it finished.
- The last model's failure raises as `QuestionAnsweringService` does, the local model's failure
  listed last.
- `save()` writes the JSON keys of `data-model.md`.

## `LibraryService.reindex_all()` (`app/services/library_service.py`)

Unchanged signature. With `regenerate_summaries`, a saved summary whose `provider` names a cloud
provider, configured now or not, is left as it was, and `ReindexReport.summaries_kept` lists it.
The others are written again with `summarize(...)`, without `model`, so with the local model. No
cloud model is called, and no provider is contacted (FR-023, SC-005).

## `HealthService` (`app/services/health_service.py`)

```python
HealthService(settings, runtime, chroma, indexes, models: ModelChoices)

def run(self, inference: bool = False, providers: bool = False) -> list[CheckResult]: ...
```

- `providers=False`: today's checks, and no request to a provider.
- `providers=True`: today's checks, then the rows of `models.setting_problems()` and
  `models.check()`. With no provider set at all, there are no more rows than today (FR-021).
- `inference=True` runs the local model's inference, as today, and never a cloud model's.

## Errors (`app/errors.py`)

| Error | Raised when | Its message |
| ----- | ----------- | ----------- |
| `ModelChoiceError` | a sequence is refused | what was refused, then "Offered: gpt-oss:20b (local), claude-sonnet-5-5 (Anthropic)." |
| `ModelFailedError` | a cloud model fails | "claude-sonnet-5-5 (Anthropic) failed: it limited the rate." |
| `AllModelsFailedError` | the local model fails after others did | each failure in order, the local model's last |

All three are `BookRagError`s, so the tabs show them as they show any other, and the commands
print them.
