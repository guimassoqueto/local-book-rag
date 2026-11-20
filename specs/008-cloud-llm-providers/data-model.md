# Data model: Cloud models for chat and summaries, opt-in

What the feature adds or changes, by where it lives. The decisions behind each are in
`research.md`.

## Configuration

### Provider credentials (the environment, R1)

One per provider kind that the app implements, read when the container is assembled.

| Field     | Type                | From                | Rule |
| --------- | ------------------- | ------------------- | ---- |
| `name`    | `str`               | the provider kind   | `anthropic` |
| `api_key` | `SecretStr \| None` | `<NAME>_API_KEY`    | None when unset or empty. Only the SDK client sees its value. |
| `models`  | `tuple[str, ...]`   | `<NAME>_MODELS`     | Split on commas, each name stripped, empty entries dropped, a repeated name kept once, in order. |

| Key | Models | The provider |
| --- | ------ | ------------ |
| no  | no     | doesn't exist, for the app (FR-002) |
| yes | no     | not offered; logged at startup; `doctor` says `<NAME>_MODELS` is missing |
| no  | yes    | not offered; logged at startup; `doctor` says `<NAME>_API_KEY` is missing |
| yes | yes    | offered, with its models, if it has a profile; without one, the app doesn't start (FR-003) |

### `CloudProfile` (`config/models.yaml`, `cloud_profiles.<name>`, R2)

| Field                     | Type                                          | Rule |
| ------------------------- | --------------------------------------------- | ---- |
| `tokenizer`               | `TokenizerConfig`                             | as in `llm_profiles` |
| `context_size`            | positive int                                  | the window the app works with |
| `reasoning`               | `low`, `medium`, `high`, `xhigh`, `max` or null | the effort sent; null sends none |
| `reasoning_tokens`        | int, 0 or more                                | added to every request's `max_tokens`, and set aside from `context_size` |
| `check_abstentions`       | bool, default false                           | as in `llm_profiles` |
| `request_timeout_seconds` | positive float                                | how long the provider may send nothing |

`Settings.cloud_profiles` is a mapping from a provider kind's name to its profile, empty by
default. The names have to be those of the factory's `CLOUD_PROVIDERS` (`anthropic`), checked when
the container is assembled, at startup. Rule across files: for each profile, each task's
`max_tokens` (`question_answering`, `summarization`), plus `reasoning_tokens`, is smaller than
`context_size`.

## Choosing

### `ModelOption` (R6)

| Field            | Example                               |
| ---------------- | ------------------------------------- |
| `name`           | `gpt-oss:20b`, `claude-sonnet-5-5`    |
| `provider`       | `ollama`, `anthropic`                 |
| `provider_label` | `local`, `Anthropic`                  |
| `local`          | true for the local model only         |

`ModelChoices.offered()` lists the local model first, then each allowed model of each configured
provider, in its list's order.

### Sequence (R6)

The models that a request may go to, in order:

| Picked             | Fallbacks             | Sequence |
| ------------------ | --------------------- | -------- |
| none, or the local model | none            | the local model |
| a cloud model `A`  | none                  | `A`, the local model |
| a cloud model `A`  | `B`, `C`              | `A`, `B`, `C`, the local model |

Refused with `ModelChoiceError`, which lists the names offered, before anything is searched or
sent: a name that isn't offered; a name given twice; the picked model among its fallbacks; the
local model among the fallbacks; a fallback with the local model picked.

## Running

### `FailureReason` (R7)

`key refused`, `unknown model`, `rate limited`, `timed out`, `unreachable`, `outage`, `declined`,
`rejected`, `no answer`. R4 maps the SDK's errors to them, and `no answer` is a `GenerationError`
from reading a reply with no text. A reply cut off by its limit with text in it, and an
abstention, are answers.

### `Attempt`

A model's failed try at a request.

| Field               | Content |
| ------------------- | ------- |
| `model`             | the model that failed |
| `provider`          | its provider |
| `reason`            | a `FailureReason` |
| `detail`            | the provider's words, such as the category of a refusal or the API's error type, never the key |
| `prompt_tokens`     | for a summary's attempt, the tokens its finished steps read; None for an answer's |
| `completion_tokens` | likewise, the tokens they generated |

### Events and errors

- **`AttemptFailed`**, an event of `QuestionAnsweringService.stream()`: the `Attempt`, and the
  next model's name and provider label.
- **`ModelFailedError(BookRagError)`**: raised by a provider, with `model`, `provider`, `reason`
  and `detail`. Its message reads "claude-sonnet-5-5 (Anthropic) failed: it limited the rate."
- **`AllModelsFailedError(BookRagError)`**: raised when the local model fails after others did.
  It holds every attempt, the local one's last, and its message lists them in order.
- **`ModelChoiceError(BookRagError)`**: a refused sequence, with the names offered.

## What the records hold (R10)

### `Generation` and `GenerationStats`

| Field                           | Change |
| ------------------------------- | ------ |
| `Generation.thinking_summarized` | new: true when `thinking` is the provider's summary of the reasoning |
| `GenerationStats.load_seconds`  | `float \| None`: None when the provider doesn't report it |
| `GenerationStats.prompt_seconds` | `float \| None`: likewise |
| `GenerationStats.generation_seconds` | unchanged; for a cloud model, measured by the app from the first delta to the end |
| `GenerationStats.model`         | for a cloud model, the model that its provider says answered |

### `Answer`

| Field      | Content |
| ---------- | ------- |
| `model`    | the model that wrote the answer; when none was called, the first of the sequence |
| `provider` | its provider |
| `attempts` | the failed attempts before it, in order, empty when none failed |

### `ChapterSummary`

| Field               | Content |
| ------------------- | ------- |
| `provider`          | the provider of `model`, the model that wrote it |
| `attempts`          | the failed attempts before it |
| `prompt_tokens`     | the tokens its steps read, added up |
| `completion_tokens` | the tokens its steps generated, reasoning included, added up |

### A saved summary's JSON file

Next to the keys of today:

| Key               | When        | Content |
| ----------------- | ----------- | ------- |
| `provider`        | always      | `ollama`, `anthropic` |
| `failed_attempts` | always      | a list of `{model, provider, reason, detail}`, with `tokens` (`{read, generated}`) for a cloud attempt, empty when none failed |
| `tokens`          | cloud model | `{read, generated}`, the attempt that wrote it |

A file without `provider`, saved before this feature, is read as the local model's (FR-023). The
summary's Markdown file doesn't change.

### `ReindexReport`

`summaries_kept`, new: each saved summary that names a cloud provider, configured or not, left as
it was, described as `book_001, chapter_04_standard: written by claude-sonnet-5-5 (Anthropic)`.
Whatever shows the list adds that a kept summary's references may name sections that the rebuild
changed, and that summarizing the chapter again refreshes it.

## Checks (R12)

`ProviderCheck(name, ok, detail)`, which `HealthService` turns into its `CheckResult` rows:

| Situation | Row |
| --------- | --- |
| one setting only | `anthropic`, failing: "ANTHROPIC_MODELS is set and ANTHROPIC_API_KEY isn't: no Claude model is offered" |
| key refused | `anthropic`, failing: "Anthropic refused the API key" |
| model found | `anthropic claude-sonnet-5-5`, ok: its display name and window |
| model unknown | `anthropic claude-x`, failing: "Anthropic doesn't know this model" |
| model the profile can't serve | `anthropic claude-haiku-4-5`, failing: "doesn't take the effort `low`" |

## Logs (R10)

| Event | Fields added |
| ----- | ------------ |
| "model failed" (new) | `provider`, `model`, `reason`, `position` |
| "question answered" | `provider`, `failed_attempts` |
| "chapter summarized" | `provider`, `failed_attempts`; for a cloud model, `prompt_tokens` and `completion_tokens` |
| "generation finished" (inference logger) | written by the Anthropic provider too, with the same fields |
| "cloud provider not offered" (new, at startup) | `provider`, `missing` |

No event holds a book's text, a question, or the key.

## Unchanged

The catalog, the index and its fingerprint, the chunks, the processed documents, ChromaDB's
collections, the prompts, the retrieval, the benchmark rows and results, `config/generation.yaml`,
`config/retrieval.yaml`, `config/ingestion.yaml`, and every `llm_profiles` and `embedding_profiles`
entry.
