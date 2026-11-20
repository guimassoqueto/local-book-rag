# Data model: OpenAI models for chat and summaries, opt-in

What this feature adds to the data of `specs/008-cloud-llm-providers/data-model.md`. Everything
else there holds as it is: credentials, choices, sequences, attempts, answers, saved summaries,
check rows and log events.

## OpenAI's settings

Read by `read_provider_credentials("openai", environ)`, as Anthropic's are (008 R1):

| Setting | Read as | Rules |
| --- | --- | --- |
| `OPENAI_API_KEY` | `ProviderCredentials.api_key`, a `SecretStr`; `None` when unset or empty | never written anywhere (FR-004) |
| `OPENAI_MODELS` | `ProviderCredentials.models`, a tuple in the order listed | stripped, empty entries dropped, a repeat kept once, case kept (FR-001) |

Both set: OpenAI's models are offered. One set: none is offered, the startup log and `doctor` name
the missing one. Neither: as on `main` (FR-002).

## The profile

`CloudProfile`, unchanged in its fields; `cloud_profiles.openai` holds OpenAI's values (research.md
R6, `contracts/configuration.md`).

| Field | Change |
| --- | --- |
| `reasoning` | its allowed names widen to `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, or null; each provider kind accepts only its own (below) |

## Provider kinds

`CloudProvider` gains one class attribute:

| Attribute | Type | Anthropic | OpenAI |
| --- | --- | --- | --- |
| `name` | `str` | `anthropic` | `openai` |
| `label` | `str` | `Anthropic` | `OpenAI` |
| `efforts` | `frozenset[str \| None]` | `low`, `medium`, `high`, `xhigh`, `max`, and null (no effort sent) | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`; not null, since its profile must name one |

`CLOUD_PROVIDERS` holds both, Anthropic first: the order the tabs offer their models in (FR-007).

## Startup rules

`create_cloud_providers()` raises `ConfigurationError` before anything is offered when:

| Rule | Message names | Requirement |
| --- | --- | --- |
| a profile names a kind the app doesn't implement | the kind, the implemented ones | 008 FR-003 |
| a provider's models are allowed without its profile | the setting, the provider | 008 FR-003 |
| a profile's effort isn't one its kind accepts, null included for OpenAI | `cloud_profiles.<name>.reasoning`, the value, the kind's efforts | FR-003 |
| a name is offered by two providers, or is offered and is `llm.model` | the name, and each setting or `llm.model` it appears in | FR-006 |

A provider offers its models only with both its settings set; a list without its key clashes with
nothing. When every rule passes, startup logs nothing new.

## Failure reasons

`FailureReason` gains one member; the others are 008's.

| Member | Value | Words | Tried again |
| --- | --- | --- | --- |
| `OUT_OF_CREDIT` | `out of credit` | "its account is out of credit or over a spending or usage limit (`<code>`)" | never |

Recorded like any reason: in an `Attempt`, a saved summary's `failed_attempts`, the Research tab,
standard error and the logs (`reason: out of credit`).

## What an OpenAI model's work records

Nothing new in the records' shape. Their values, for OpenAI:

| Record | Field | Value |
| --- | --- | --- |
| answer, Research tab | provider | `openai`, shown as `OpenAI` |
| answer, Research tab | model | `response.model`, as OpenAI reports it (FR-013) |
| answer, Research tab | prompt tokens, generated tokens | `usage.input_tokens`, `usage.output_tokens` (the reasoning included) |
| answer, Research tab | load, prompt processing | unavailable (`None`) |
| answer, Research tab | reasoning | the reasoning summary, marked as a summary; empty when none came back (FR-015) |
| saved summary JSON | `provider` | `openai` |
| saved summary JSON | `tokens` | read and generated, per cloud attempt (008 FR-022) |
| `reindex-all` | `summaries_kept` | "book_001, chapter_04_standard (gpt-6.2-sol, OpenAI)" |
| check row | name | `openai`, or `openai <model>` |
| inference log | `generation finished` | model, tokens, timings, finish reason; never the text or the reasoning |
| nowhere | the encrypted reasoning that an unstored response carries | dropped by the provider: neither shown, logged nor recorded (FR-016) |
| nowhere | OpenAI's error messages | read to recognize a verification refusal, never shown or logged (FR-004) |

## Unchanged

The catalog, ChromaDB, the processed documents, the index and its fingerprint, the prompts, the
local model's profile, Anthropic's profile, and the layout of a saved summary (FR-021).
