# Research: Cloud models for chat and summaries, opt-in

The decisions behind `plan.md`, R1 to R18. Each says what was decided, why, and what else was
weighed. The facts about the Claude API come from the Claude API reference that ships with Claude
Code (its model table cached on 2026-11-03), and `quickstart.md` checks them on the real models.

## R1. Two settings per provider, read apart from the rest

**Decision.** A provider is configured by `<PROVIDER>_API_KEY` and `<PROVIDER>_MODELS` in `.env`,
the prefix being its name in `cloud_profiles` (R2): `ANTHROPIC_API_KEY` and `ANTHROPIC_MODELS`.
`docker-compose.yml` passes both to the app's container, empty by default
(`${ANTHROPIC_API_KEY:-}`). They are read once, when the container is assembled, into one
`ProviderCredentials` per provider:
- the key as a `SecretStr`, None when unset or empty;
- the models as a tuple, split on commas, each name stripped, empty entries dropped, and a name
  given twice kept once, in the order listed (FR-001).

Neither `Settings` nor `EnvironmentSettings` holds them.

**Rationale.**
- The owner asked for environment variables, and the fewest settings: two per provider, and
  nothing in `config/` to edit to turn one on.
- Kept out of `Settings` and `EnvironmentSettings`, the key stays out of everything that records
  or copies them: benchmark results hold `Settings.model_dump()` and its hash, and the runner
  copies `EnvironmentSettings` for each workspace. `SecretStr` masks it in any representation, and
  only the SDK client receives the plain value (FR-004).
- Names derived from the provider's name mean that a provider added later needs no new field
  (FR-026).

**Alternatives.**
- *Two fields on `EnvironmentSettings` per provider*: every provider adds fields, and the key
  would travel wherever that object does.
- *The allow-list in `config/models.yaml`*: model names in configuration, as Principle I said
  before 3.0.0, but a change would take a rebuild, which empties the library, and the owner asked
  for the environment. Constitution 3.0.0 puts cloud model names in the environment.
- *The key typed in the interface*: no key on disk, but a key per page, and the commands would
  need another way. Set aside when the spec was written.
- *Every model the key can use*, from the Models API: no list to write, but the API also lists
  older models that take other parameters than the profile sends, and the app would have to
  contact the provider at startup, which the clarify session ruled out.

## R2. One profile per provider, in `cloud_profiles`

**Decision.** `config/models.yaml` gains a top-level key, `cloud_profiles`, keyed by provider name
and validated by a `CloudProfile` model that refuses unknown keys, like the rest of `config/`.
Anthropic's:

```yaml
cloud_profiles:
  anthropic:
    tokenizer: {kind: tiktoken, name: o200k_base}
    context_size: 65536
    reasoning: low
    reasoning_tokens: 4000
    check_abstentions: false
    request_timeout_seconds: 120
```

- `tokenizer`: counts tokens to fit prompts, an approximation (R5).
- `context_size`: the window the app works with, far below the models' own million tokens. It
  caps what one request sends, and so what it costs (R5).
- `reasoning`: sent as the request's effort, `low`, `medium`, `high`, `xhigh` or `max`, or null to
  send none.
- `reasoning_tokens`: added to every request's `max_tokens`, since reasoning counts against it,
  and set aside from `context_size` (R5).
- `check_abstentions`: as in `llm_profiles`, whether the model reads its own reply again for an
  abstention written only in words.
- `request_timeout_seconds`: how long the provider may send nothing before the request counts as
  timed out (R4).

The names that `cloud_profiles` accepts are those of the provider kinds the app implements, which
the factory holds in one mapping, `CLOUD_PROVIDERS` (`anthropic` now). `Settings` validates each
profile's fields, and the factory checks the names when the container is assembled, at startup: a
profile under any other name stops the app there, as an unknown key does (FR-003). Keeping the
names in the factory's mapping alone means that a provider kind is registered in one place, which
SC-009's fake provider uses too. A rule across files, like the one for `llm.context_size`, checks
that each task's `max_tokens`, plus `reasoning_tokens`, leaves room for a prompt in
`context_size`. An allowed model whose provider has no profile stops the app at startup (FR-003).
Without the key, `cloud_profiles` is empty, and no provider can be offered.

**Rationale.** Principle I: what differs between models lives in profiles, validated at startup.
One profile per provider, not per model, is constitution 3.0.0's rule, and keeps allowing a model
to one name in `.env`. The values are a starting point: `quickstart.md` checks them on the real
models (§ 6 to § 8), and `docs/decisions.md` records what was kept.

`reasoning: low`, because the tasks are reading passages and writing a short answer or a summary,
which the API reference says do well at low effort; Claude Opus 5.5's own default is `medium`.
Lower effort costs less and answers sooner. `reasoning_tokens: 4000` leaves the reasoning room
beside the task limits, which were set for `gpt-oss` at `low` (1500 for an answer, 900 for a
summary's partial step).

**What keeps each value** (checked on the real models, `quickstart.md` § 5 to § 8 and § 13):
- `reasoning: low` stays while every case of SC-003 passes on each allowed model; a failed case
  that a higher effort passes raises it, for every model, with the measurement recorded.
- `reasoning_tokens: 4000` stays while no reply in those checks stops at its limit without text;
  one that does raises it.
- `context_size: 65536` stays while a whole chapter of *On Liberty* is summarized in one step; it
  is a cap on cost, not a quality setting.
- `request_timeout_seconds: 120` stays unless a request that succeeds ever goes that long without
  a word.
- `check_abstentions: false`, because the current Claude models follow an instruction to open a
  reply with a marker, and because a check costs a call per answer. It stays while SC-003's three
  unanswerable questions each get the marker. A reply that abstains in words instead turns it on,
  as it is on for `gemma4:12b` and `qwen3.5:9b`, and `docs/decisions.md` records the reply.

**Alternatives.**
- *A profile per model*: what Principle I asks of local models, but each allowed model would need
  an entry in `config/models.yaml`, so allowing one would take a rebuild. Constitution 3.0.0 chose
  one per provider.
- *The provider's own `max_tokens` for each task*: more settings, kept in step with
  `config/generation.yaml` by hand. An allowance added to every request keeps the task limits'
  meaning: the room for what the model writes.

## R3. The provider interface gains two attributes and a provider kind

**Decision.**
- `LLMProvider` (`app/generation/base.py`) gains `provider`, its provider's name (`ollama`,
  `anthropic`), and `check_abstentions`, from its profile. `check_abstention()` reads the flag
  from the provider instead of `settings.llm_profile`, so that a cloud model follows its own
  provider's profile, and loses its `settings` argument.
- `Generation` gains `thinking_summarized`: true when `thinking` is a summary of the reasoning,
  not the reasoning itself (FR-025).
- `GenerationStats.load_seconds` and `prompt_seconds` become `float | None`, None meaning that the
  provider doesn't report it (FR-025). Ollama always sets them, so the benchmarks, which run local
  models only, read numbers as before.
- A new protocol, `CloudProvider` (`app/generation/cloud.py`), is a provider kind. Built once from
  its credentials and its profile, it has a `name` and a `label` (`Anthropic`), builds the
  `LLMProvider` of each allowed model, and checks its key and models (R12).
- `create_llm_provider()` keeps its signature, so the benchmarks and `devtools/default_llm.py`,
  which wraps it, keep working. A new `create_cloud_providers()` builds the configured kinds.

**Rationale.** Above the provider nothing changes: the services see the same `stream()` and
`generate()`, and the new attributes say only what they need. `app/container.py` and the factory
stay the only places that know the concrete classes (Principle I).

**Alternatives.**
- *An OpenAI-compatible endpoint for every provider*: one client, but the lesson behind Principle V
  is that such shims drop settings silently, as Ollama's dropped `num_ctx`. Each provider's own
  SDK is the documented way in.
- *LlamaIndex's Anthropic integration*, as the Ollama provider uses LlamaIndex: it would stand
  between the app and the parameters that matter here (effort, the reasoning's display, stop
  reasons), which the SDK exposes directly.

## R4. The Anthropic provider

**Decision.** `app/generation/anthropic_provider.py`, on Anthropic's official SDK, added with
`uv add --raw anthropic`:
- **One client per provider**, `anthropic.Anthropic(api_key=..., timeout=request_timeout_seconds,
  max_retries=0)`. Building it contacts nothing.
- **Retries, bounded** (FR-017): the SDK would retry a timeout too, which turns 120 s of silence
  into six minutes. So its own retries are off, and the provider tries a request again itself, at
  most twice, after a rate limit, an overload or a lost connection only, waiting 2 s, then 6 s, or
  the API's `retry-after` when it is shorter than 10 s. A timeout is never tried again. A retry
  only happens before the stream has yielded anything: once text has arrived, a failure is final.
- **The prompt**: the app's `system` messages become the request's `system` text, and the others
  its `messages`, in order. The prompts don't change.
- **The request**: `client.messages.stream(model, max_tokens, system, messages, thinking,
  output_config)`, with `max_tokens` the task's plus `reasoning_tokens`, `thinking` set to
  `{"type": "adaptive", "display": "summarized"}`, and `output_config` to `{"effort": reasoning}`
  when the profile sets one.
  - No `temperature`: the current Claude models refuse any sampling setting with a 400.
  - No seed: the API has none, and benchmarks don't run cloud models.
  - No server-side `fallbacks`: a model outside the sequence would answer (FR-016).
- **The stream**: a `content_block_delta` event with a `text_delta` becomes a `TextDelta`, and a
  `thinking_delta` is kept as the reasoning. The time to first token is the first delta of either
  kind.
- **The end**: `get_final_message()` gives `usage.input_tokens` and `usage.output_tokens`, the
  model that answered (`model`), and `stop_reason`. `max_tokens` maps to `length`, which the
  services already read. `refusal` raises a failure, `declined`, with `stop_details.category` when
  there is one.
- **Failures** raise `ModelFailedError` with a reason (R7). Most specific first, as the API
  reference advises:

  | From the SDK                                   | Reason          |
  | ---------------------------------------------- | --------------- |
  | `AuthenticationError` (401), 402, `PermissionDeniedError` (403) | `key refused` |
  | `NotFoundError` (404)                          | `unknown model` |
  | `RateLimitError` (429)                         | `rate limited`  |
  | `APITimeoutError`                              | `timed out`     |
  | `APIConnectionError`                           | `unreachable`   |
  | `InternalServerError` (500 and over, 529 included) | `outage`    |
  | any other status, such as a 400 for a setting the model doesn't take | `rejected` |
  | `stop_reason` `refusal`                        | `declined`      |

- **Stats**: the tokens from `usage`; `load_seconds` and `prompt_seconds` None; `generation_seconds`
  the time from the first delta to the end, which the app measures.
- **Logs**: the "generation finished" event that Ollama's provider writes, on the inference logger.

**Rationale.** From the API reference: streaming for anything long, which also keeps a long
summary's reply clear of the SDK's guard against long requests without it; adaptive reasoning with
an effort on the current models; `display: "summarized"` for a reasoning that can be read, the
default returning an empty one, billed the same; the typed errors, the timeout before the
connection error, of which it is a kind. The owner chose 120 seconds as the longest a model may
stay silent before the next one starts (the checklist's CHK013), which the SDK's own retries would
triple.

**The SDK beside the project's other packages.** The SDK's 1.x line runs on `httpx2`, apart from
the `httpx` that Ollama's client and LlamaIndex use, so neither constrains the other. The tests'
`respx` mocks `httpx` only, so the provider's unit tests use a fake client instead (R16). The
first task adds the SDK with `uv add --raw anthropic` and runs `make test` unchanged: if uv can't
resolve it beside the lock, or a test breaks, the tasks stop there.

**Alternatives.**
- *The server-side `fallbacks`*, which the API reference advises turning on by default for Claude
  Opus 5.5 and Sonnet 5.5: left off, since it would answer a declined request with a model that the
  user didn't put in the sequence. The sequence's next model takes it instead (FR-017).
- *Requests without streaming*: simpler, but the Chat tab needs the stream (FR-013), and long
  summaries would meet the SDK's guard.
- *`count_tokens` before each request*: exact, but R5.

## R5. Fitting prompts to a cloud model

**Decision.** A cloud model counts tokens with its profile's tokenizer, `o200k_base`, an
approximation like `gemma4:12b`'s, whose error `generation.context.safety_margin` absorbs. Its
`context_size()` is the profile's `context_size` minus `reasoning_tokens`: what the prompt and the
reply may take, with the reasoning's room set aside. The services fit prompts as they do today,
with the same arithmetic. `pull-models` also downloads each cloud profile's tokenizer, so that a
first cloud request doesn't fetch it.

**Rationale.** Principle V's rule exists because Ollama cuts a prompt silently. The Claude API
refuses a prompt larger than the model's window with a 400 (`prompt is too long`), and the
profile's window, 64K tokens, is far below the models' million, so a miscount can't drop passages
unseen: it only sends a little more or less than planned. The API reference counts Claude's tokens
with `count_tokens`, which would cost a request for each passage fitted, to correct an error that
the margin already covers. With the reranker's five passages, an answer's prompt is a few thousand
tokens either way. For summaries, a 64K window holds most chapters in one step.

**Alternatives.**
- *The models' whole window*: no map-reduce, but one request could send a million tokens, and the
  profile would cap nothing.
- *The local window, 8K*: the same steps as the local model, but more requests per summary.

## R6. The choices, and the rules of a sequence

**Decision.** `ModelChoices` (`app/generation/choices.py`), assembled in the container, holds the
local model and each offered cloud model:
- `offered()`: the local model first, then each allowed model, in its provider's list's order.
  Each is a `ModelOption`: its name, its provider's name and label, and whether it is local.
- `sequence(model, fallbacks)`: the providers that a request goes to, in order. No model, or the
  local one, gives the local model alone, and refuses any fallback. A cloud model gives that
  model, its fallbacks in order, then the local model. `ModelChoiceError`, which lists the names
  offered, refuses a name that isn't offered, a name given twice, the picked model among its own
  fallbacks, and the local model among them (FR-007, FR-008). The services call it before they
  search or send anything.
- `describe(model, fallbacks)`: the same sequence as options, for the tabs' notice, building no
  provider.
- `check()` and `setting_problems()`: R12.
- `local_only(llm)`: the choices of a setup without cloud models, which the benchmarks' and the
  tests' services use.

**Rationale.** Principle IV: the rules live where both interfaces reach them. The services take
names, as the tabs and the commands give them, and the choices turn them into providers or refuse
them. `ModelChoices`, not a catalog: `BookCatalog` already has that word.

**Alternatives.** *The tabs and the commands building the sequence*: two copies of the rules.

## R7. The sequence of an answer

**Decision.** `QuestionAnsweringService.stream()` takes `model` and `fallbacks`:
1. It resolves the sequence (R6) and searches once, yielding the `RetrievalResult` as today. Every
   model of the sequence gets these passages, in this order (FR-011). Without any, no model is
   called, as today.
2. For each model in turn, it fits the passages to that model's context, builds the prompt,
   streams the reply through the same marker and citation filters, reads it, and checks it for an
   abstention in words when the model's profile asks.
3. When a model other than the last fails, with a `ModelFailedError` from its provider or a
   `GenerationError` from reading its reply (the reason `no answer`), the service logs it, yields
   `AttemptFailed` with the failure and the next model, and starts again with that model
   (FR-017). `no answer` is a reply with no text, which is when reading raises today. A reply cut
   off by its limit with text in it is an answer, shown as a local one is, and so is an
   abstention: the owner's answer to the checklist's CHK011.
4. When the last model, the local one, fails, its error is raised as today if nothing failed
   before it. Otherwise an `AllModelsFailedError` lists every failure, in order (FR-018).
5. The `Answer` holds the model that answered, its provider, and the failures before it (FR-016).

A `ModelFailedError`'s reason is one of `key refused`, `unknown model`, `rate limited`,
`timed out`, `unreachable`, `outage`, `declined`, `rejected` and `no answer`. Its message names the
provider and the model, and never holds the key.

**Rationale.** The search runs once, since retrieval doesn't depend on the model, and each model
gets the request whole, from its start. The local model's own errors stay as they are, so a
session without cloud settings sees what it sees on `main` (SC-001).

## R8. The sequence of a summary

**Decision.** `ChapterSummarizer.summarize()` takes `model` and `fallbacks`. It resolves the
sequence and loads the chapter's chunks once, then has each model make the whole summary in turn,
until one finishes. When a step fails, it says so through `on_progress`, and starts again from the
first step with the next model (FR-019). The run object carries its model: every budget, count and
step reads the run's model instead of the summarizer's. It also adds up the tokens that its
finished steps read and generated, so a failed attempt keeps the count of what it spent, which was
billed too (the owner's answer to CHK017). The `ChapterSummary` holds the provider, the failed
attempts, each with its tokens, and the two counts of the attempt that finished.

**Rationale.** A summary written by two models would make its record false: "no summary is
written by two models", in the spec's edge cases. A failure late in a long summary wastes what it
had spent, which the spec's Assumptions accept for that.

## R9. Withdrawing what a failed model wrote

**Decision.**
- **The Chat tab** empties the answer area on `AttemptFailed`, and its status line says which
  model failed, why, and which one it asks next. The next model's text starts from nothing
  (SC-008).
- **`ask`** writes the answer to standard output as it streams, and a terminal can't take text
  back. It writes the failure to standard error, in a line that says that the text above is
  discarded, and which model answers from the start; then the next answer streams. The sources
  and the last lines are those of the model that answered.
- **A summary** shows nothing before its end, so nothing is withdrawn: its progress messages say
  what happened.

**Rationale.** FR-017 asks that a failed model's text not stand as an answer. The tab removes it;
the command can only mark it, so it marks it where a reader of the terminal sees it.

**Alternatives.** *Holding back a cloud answer in `ask` until it is whole*: nothing to withdraw,
but no streaming, against FR-013.

## R10. What the records hold

- **`Answer`**: `model` and `provider`, those of the model that answered or, when none was called,
  of the first in the sequence; `attempts`, the failures before it.
- **`ChapterSummary`**: `provider`, `attempts`, `prompt_tokens` and `completion_tokens`. An
  attempt of a summary carries the tokens of the steps it finished.
- **A saved summary's JSON file**: `provider` always; `failed_attempts`, a list, empty when none
  failed, each entry with its `tokens` when its model is a cloud one; and `tokens` (`read`,
  `generated`) when a cloud model wrote it (FR-022). The Markdown file doesn't change.
- **The reasoning** stays in the `Answer`, for the Research tab, and nowhere else: no log event
  and no saved record holds it (FR-020).
- **Logs**: "model failed", with the provider, the model, the reason and the attempt's position;
  and the provider and the count of failures in "question answered" and "chapter summarized".
  As today, no event carries a book's text or a question, and none carries the key (FR-020).

## R11. `reindex-all` leaves a cloud summary as it was

**Decision.** `_regenerate_summaries()` reads each saved summary's `provider`. When it names a
cloud provider, one that `cloud_profiles` can hold, the summary stays as it is, whether or not
that provider is configured now, and `ReindexReport.summaries_kept` lists it with its model. A
summary that names no provider, saved before this feature, or the local one, is written again
with the local model, as today (FR-023). The command and the Library tab show the list, and say
that a kept summary's references may name sections that the rebuild changed, and that summarizing
the chapter again refreshes it.

**Rationale.** The spec and its clarifications: regenerating never calls a cloud model, and no
cloud summary is rewritten by another model behind the owner's back.

## R12. When a provider is contacted

**Decision.** `HealthService.run()` takes `providers`, false by default:
- **`providers=False`**, the Research tab's own checks after each answer: no row about a
  provider, and no request (FR-021).
- **`providers=True`**, `doctor` and the Research tab's "Check again":
  - for a provider with one setting only, a failing row that says which is missing, with no
    request (FR-002);
  - for a configured provider, `client.models.retrieve()` for each allowed model, which sends the
    key and the model's name and runs no inference. A refused key is one failing row. Each model
    has a row: found, with its window, or unknown. A model whose `capabilities` don't take the
    profile's effort or adaptive reasoning, or whose window is smaller than the profile's, fails
    its row, saying which. Such a model also fails every request, as `rejected`; nothing warns at
    startup, which contacts no provider.
- **At startup**, the container reads the settings and builds the clients, which contacts
  nothing, and logs a provider with one setting as not offered.

**Rationale.** The clarify session's answer A: a check sends the key and the allowed models'
names, nothing from the library, only when asked for, and the app starts without a network.
Reading `capabilities` catches an allowed model that a single provider profile can't serve, before
a request finds out.

## R13. The tabs

**Decision.** A shared builder, `app/interface/model_choice.py`, gives the Chat tab and the
Summarization tab each their own components (FR-009):
- **"Model"**: a dropdown of `offered()`, labeled `gpt-oss:20b · local` and
  `claude-sonnet-5-5 · Anthropic`, whose value is the local model. Hidden when no cloud model is
  offered (FR-006).
- **"If it fails, then"**: a multiselect of the other cloud models, in the order chosen, shown
  while a cloud model is picked. Its note says that the local model answers last (FR-007).
- **A notice**, shown while a cloud model is picked: "The question and the passages found go to
  Anthropic: claude-sonnet-5-5, then claude-opus-5-5. If they fail, gpt-oss:20b answers,
  locally." In the Summarization tab, "The chapter's text goes to…" (FR-010).

A page load gives each component the value it was built with, so both tabs start on the local
model, with no fallbacks. Gradio keeps a component's value per page, so each tab's choice is its
own.

- **The Chat tab** passes the choice to the service, empties the answer on `AttemptFailed` (R9),
  and its status line names the model that answered when it is a cloud model or another one
  failed first. A local answer without failures reads as today.
- **The Summarization tab**: its progress messages carry the failures, and its report adds the
  provider, the failures and, for a cloud model, the tokens (FR-022).
- **The Research tab** (FR-024, FR-025): the LLM row reads the answer's model and provider
  instead of `settings.llm.model`; a row for each failed attempt; "unavailable" for a measure
  that is None; "(measured by the app)" beside the generation's seconds and speed of a cloud
  model, which include the network; the reasoning, labeled a summary when `thinking_summarized`,
  or "None came back"; its own checks with `providers=False`, and "Check again" with
  `providers=True`.
- **The Library tab** lists the summaries that `reindex-all` kept (R11).

**Rationale.** Thin handlers, as Principle IV asks: they read the components and show what the
services return.

**The order of the fallbacks.** FR-007's "in the order chosen" rests on Gradio's multiselect
keeping the order of selection, which its value appears to do and `quickstart.md` § 9 checks. If
it doesn't, three single dropdowns replace it, "Then", "Then" and "Then", each offering the cloud
models not yet chosen, with the same rules and the same notice. The handlers would read three
values instead of a list, and the services wouldn't change.

## R14. The commands

**Decision.** `ask` and `summarize` take `--model NAME`, and `--fallback NAME`, repeated, in
order.
- With a cloud model named, each first writes the tab's notice to standard error, before anything
  is sent: "The question and the passages found go to Anthropic: claude-sonnet-5-5. If it fails,
  gpt-oss:20b answers, locally." (the owner's answer to CHK006, FR-008).
- `ask` writes each failure to standard error as it happens (R9), and ends by naming the model that
  answered when it is a cloud model or another one failed first.
- `summarize` writes its progress, failures included, to standard error, and its last line adds
  the provider and, for a cloud model, the tokens.
- `doctor` runs the provider checks (R12). `reindex-all` lists the summaries it kept (R11).
- Without `--model`, and without failures, every command prints what it prints on `main`.

## R15. Benchmarks stay local, with no new rule

**Decision.** The benchmark runner gains no rule. An experiment's variant that names a cloud model
as `llm.model` fails validation when the runner applies its overrides, before anything runs: the
model has no entry in `llm_profiles`. A judge that names one fails when the runner describes the
environment, which asks Ollama for the model, before the run. The tests prove both (SC-010). The
runner builds its models with `create_llm_provider()`, which builds Ollama providers only, and
never reaches the choices. One of its lines changes, for `check_abstention()`'s new signature
(R3).

The workspaces' containers hold no cloud provider at all: `assemble()` reads the providers'
settings only from the environment it is given, `build_container()` gives it the process's, and
the runner, which calls `assemble()` for each workspace, gives it none.

**Rationale.** Principle I keeps benchmarks and judges local, and the runner already refuses
anything else. The README says it.

## R16. Tests

**Unit tests** (`make test`), on fakes as today:
- `tests/fakes.py`: `FakeLLM` gains `provider` and `check_abstentions`, and can fail with a given
  reason after a given text. A `FakeCloud`, a second provider kind, proves FR-026 (SC-009).
- New: `test_anthropic_provider.py`, on a fake client that has only the documented attributes: the
  request (system text, no temperature, effort, reasoning, `max_tokens`), the stream, the stats,
  each stop reason and each SDK error. `test_model_choices.py`: options, sequences, refusals,
  checks, and settings with one, both or neither.
- Changed: `test_config.py`, `test_question_answering.py`, `test_summarization.py`,
  `test_library_rebuild.py`, `test_health_service.py`, `test_interface.py`, `test_commands.py`,
  `test_container.py`, `test_logging.py` (no trace of a fake key, SC-011), `test_llm_provider.py`
  and `test_benchmark.py` (SC-010).
- **No request, counted** (SC-001, SC-002): the provider kinds of the tests take a client whose
  every method counts its calls. A session of questions and summaries without the settings, or
  with them and the local model only, ends with the count at zero; so does assembling the
  container.
- **A second provider** (SC-009): `FakeCloud` is registered only in the factory's mapping of
  provider kinds, `CLOUD_PROVIDERS`, as a real one would be, with a profile under its name; no
  service, tab or command names it.

**Integration tests** (`make test-integration`): `tests/integration/test_cloud_generation.py`,
skipped unless both Anthropic settings are in the environment, runs every model of
`ANTHROPIC_MODELS` for real (SC-003, FR-033). Its cases are in
`tests/integration/cloud_cases.yaml`: an excerpt written for the test, five questions that the
excerpt answers, three that it doesn't, and a short chapter. Each answer has to cite in a form the
app recognizes, every citation resolving; each unanswerable question has to get the marker; the
summary has to cite by lookup; and the stats, the reasoning and the key check are read. A form of
citation that the app doesn't recognize fails the case, rather than leaving an uncited answer
unnoticed. It spends a few cents per model.

**Rationale.** Principle V: how a new model family's output is read is checked on the real
models. The SDK's errors are built in the tests with a minimal `httpx2` response, which their
constructors take.

## R17. Records

- **`README.md`**: its opening line; a "Cloud models" section (the settings, what each request
  sends, that the provider's terms for API data apply and where to read them, fallbacks, the
  Research tab, `doctor` and "Check again", costs, the key, and running the integration tests on
  a model before trusting it); the Interface, Questions, Summaries and Configuration sections,
  the last saying that `config/generation.yaml`'s temperature doesn't apply to a cloud model and
  that its settings are its profile; the Deployment notes (the key, which anyone who can open the
  interface or call its API can use, and `GRADIO_BIND_ADDRESS`); the Layout.
- **`docs/decisions.md`**: a "Cloud models" section with FR-030's decisions, the plan's own
  (R4's absent fallbacks, temperature and SDK retries, R5's tokenizer, R2's values and what kept
  them, R9's withdrawal in a terminal), and what the real models showed.
- **`docs/benchmark-results.md`** doesn't change: no benchmark runs.
- **The release**: a `feat:` title, so v0.8.0 unless another release comes first.

## R18. The check on the stack

The stack runs v0.7.0's image, and the library is empty, by the owner's choice. `quickstart.md`
rebuilds the image with `make up`, which recreates the app container and deletes what it held:
the library, empty now, its logs, the tokenizers and the reranker's weights it downloaded, and its
copy of `benchmarks/`. ChromaDB keeps its collections, so `reset-everything` comes next, as in
`specs/007`. Setting `.env` takes the same recreation. `quickstart.md` says all of this before the
commands that do it (Principle II). A benchmark book is added for the check, and the owner adds
their own book back afterwards.
