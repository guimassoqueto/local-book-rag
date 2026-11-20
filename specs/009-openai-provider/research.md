# Research: OpenAI models for chat and summaries, opt-in

The decisions behind `plan.md`. Each one says what was chosen, why, and what else was weighed.
`specs/008-cloud-llm-providers/research.md` (R1 to R18 there) holds the structure this feature
builds on, and is cited as "008 R*n*".

Sources read on 2026-11-20: OpenAI's guides *Reasoning models*, *Streaming API responses*, *Error
codes*, *Data controls in the OpenAI platform*, *Counting tokens*, *Using GPT-6.2*, *Model
selection* and *API credits for ChatGPT subscribers*, and the model pages of `gpt-6-luna`,
`gpt-6.1-terra` and `gpt-6.2-sol` (developers.openai.com/api/docs); and the installed `openai`
package, 3.3.0, already in `uv.lock` through RAGAS.

## R1. Which of OpenAI's APIs: Responses, streamed

**Decision**: The provider calls the Responses API (`client.responses.create(..., stream=True)`)
through OpenAI's official SDK for Python, `openai`, added as a direct dependency with
`uv add --raw openai`. It iterates the raw event stream itself.

**Rationale**:
- **The reasoning.** The Research tab shows the reasoning when the provider returns it (FR-018).
  The Responses API returns a summary of it when the request asks (`reasoning.summary`); Chat
  Completions returns none for OpenAI's models.
- **OpenAI's own advice.** "Reasoning models work better with the Responses API", and the three
  models the owner allows support it.
- **The raw stream, not the SDK's `responses.stream()` helper.** The helper's
  `get_final_response()` raises unless a `response.completed` event arrived, while a reply cut off
  by its token limit ends with `response.incomplete`, which FR-014 keeps as an answer when it holds
  text. Iterating the events of `create(stream=True)` keeps the terminal event whatever it is:
  `response.completed`, `response.incomplete` or `response.failed`, each carrying the response.
- **Not Ollama's OpenAI-compatible endpoint** (FR-023, Principle V): the client is OpenAI's, with
  OpenAI's address pinned (R10).
- **The SDK's version.** The constitution adds dependencies unpinned, so `uv.lock` alone holds
  3.3.0. The unit tests' fakes are built from the installed SDK's own types (its event and response
  models, validated from dictionaries, and its error classes), so an SDK release that changes
  what the provider reads fails `make test` when `make update` brings it, before it reaches the
  app.

**Alternatives considered**:
- *Chat Completions*: no reasoning to show, and OpenAI steers reasoning models away from it.
- *Non-streamed requests*: an answer must stream (FR-010), and the bound on a silent model needs a
  stream (Clarifications, Session 2026-11-20).
- *Counting each prompt exactly with `responses.input_tokens.count`*: a request per fitting, as
  008 R5 found for Claude's equivalent. It serves the measurement of R6 only.

## R2. What a request carries

**Decision**: Each request sends exactly:

| Argument | Value | Why |
| --- | --- | --- |
| `model` | the allowed name | |
| `input` | the prompt's messages in order, each with its own role and text, `system` included | the local model's prompt, byte for byte and role for role (FR-008), which the Responses API takes as it is |
| `max_output_tokens` | the task's `max_tokens` plus the profile's `reasoning_tokens` | reasoning counts against the limit, as for Claude (008 R4) |
| `reasoning` | `{"effort": <profile>, "summary": "auto"}`; no `effort` when the profile's is null | FR-003; `auto` is "the most detailed summarizer available for a model" |
| `store` | `false` | FR-012: OpenAI keeps no response for later retrieval |
| `truncation` | `"disabled"`, its default, sent explicitly | a prompt too long fails with a 400 instead of losing its first items, which would drop the instructions silently (Principle V) |
| `stream` | `true` | FR-010 |

Nothing else: no `tools`, so no web search or file search (FR-012); no `temperature` or `top_p`,
which the GPT-6 models refuse; no seed, which the API lacks; no `metadata`, `user`,
`safety_identifier` or `prompt_cache_key`, which would identify the user or the library; no
`service_tier`, `background`, `previous_response_id` or `conversation`. `include` stays empty:
with `store: false`, reasoning items come back with an encrypted copy, which the provider ignores.

**Rationale**: FR-012 and Principle I allow what the request needs and nothing more. Each argument
left out is one that would send more, change what the model reads, or keep the request at OpenAI.

**Prompt caching** isn't an argument: OpenAI caches the start of a prompt on its own, for about 30
minutes by default, to bill a repeat less. No argument above turns it off; the owner accepted it,
and the README says so (spec, Clarifications).

**Alternatives considered**:
- *The `developer` role, or `instructions`, for the system message*: OpenAI's GPT-6 guide moves
  stable instructions into a `developer` message. It would make the prompt differ from the local
  model's by a role, which FR-008 rules out; the system role is OpenAI's older name for the same
  thing, and the integration tests check what the models do with it.
- *`reasoning.mode: "pro"`*: more model work at a higher cost, for "difficult tasks"; not for
  reading passages.

## R3. Reading the stream

**Decision**: The provider reads these events, and ignores the others:

| Event | What the provider does |
| --- | --- |
| `response.output_text.delta` | yields the text, notes the first token's time |
| `response.reasoning_summary_text.delta` | keeps it as the reasoning, notes the first token's time |
| `response.refusal.delta` | marks the reply as declined |
| `response.completed`, `response.incomplete`, `response.failed` | keeps the response it carries, and ends |
| `error` | the SDK raises `APIError` with the error's body (R4) |

Then:
- **A refusal** fails as `DECLINED`, whatever text came with it (FR-014). OpenAI gives no
  category for a refusal; the detail stays empty.
- **`response.failed`** fails by its `error.code` (R4).
- **`response.incomplete`** with `incomplete_details.reason == "content_filter"` fails as
  `DECLINED` (`content_filter`). With `"max_output_tokens"`, it ends as a generation whose
  `finish_reason` is `length`: kept as an answer when it holds text, as for every model, and a
  failure without text, through the shared rule that a reply with no text fails (`choices.py`,
  `moves_on`; 008 R7).
- **`response.completed`** ends as a generation whose `finish_reason` is `stop`.
- **The stats** come from the terminal response: `model`, as OpenAI reports it (FR-013),
  `usage.input_tokens`, and `usage.output_tokens`, which counts the reasoning (FR-018). The first
  token's time is the first text or reasoning delta, as for Claude; model loading and prompt
  processing are `None`, shown as unavailable.
- **The reasoning** is the concatenated summary text, marked as a summary
  (`thinking_summarized=True`); empty when none came back (FR-015).
- **A stream that ends without a terminal event** fails as `UNREACHABLE` (a lost connection).

**Rationale**: The same `Generation`, `GenerationStats` and `ModelFailedError` that the Anthropic
provider produces, so that nothing above the provider changes (FR-022).

## R4. Failures, and how each is said

**Decision**: Every SDK error and failed response maps to a `FailureReason`, the most specific
first; the detail is OpenAI's error code, with the parameter it names when it names one, and never
OpenAI's message, which for a refused key quotes part of it (FR-004).

| What OpenAI returns | Reason | Detail |
| --- | --- | --- |
| `APITimeoutError` | `TIMED_OUT` | `120 s` |
| `APIConnectionError`; a stream without a terminal event | `UNREACHABLE` | |
| 401 `AuthenticationError` | `KEY_REFUSED` | the code |
| 403 `PermissionDeniedError`: a model the project may not use, a country not served, anything else forbidden | `REJECTED` | the code, and the parameter |
| 404 `NotFoundError`, or code `model_not_found` | `UNKNOWN_MODEL` | |
| 429 with code `insufficient_quota`, `credit_balance_exhausted`, `organization_spend_limit_exceeded`, `project_spend_limit_exceeded` or `organization_usage_limit_exceeded` | `OUT_OF_CREDIT` (R5) | the code |
| any other 429 (`rate_limit_exceeded`, `slow_down`) | `RATE_LIMITED` | the code |
| 500, 503 `server_is_overloaded`; failed response `server_error` | `OUTAGE` | status or code |
| failed response `rate_limit_exceeded` | `RATE_LIMITED` | |
| failed response `invalid_prompt`, `bio_policy`; incomplete `content_filter`; a refusal | `DECLINED` | the code, empty for a refusal |
| a 400 or 403 whose error concerns organization verification for streaming | `REJECTED` | "OpenAI streams this model only to a verified organization" |
| a 400 naming `reasoning.summary` | asked again once, at once, without the summary (below) | |
| any other 400, or a failed response with another code, such as `data_residency_mismatch` or an image code | `REJECTED` | the code, and the parameter: "it rejected the request: `<code>` (`<param>`)" |

A refusal or a decline that comes after text has streamed is still a decline: the provider raises
it, and the services withdraw the text, as for every failure after part of an answer (008 FR-017).
Silence is measured by the client's read timeout, the profile's 120 seconds between any two bytes
of the stream, events included, as for Claude's SDK.

- **Tried again**: `RATE_LIMITED`, `OUTAGE` and `UNREACHABLE`, before any text or reasoning has
  arrived, after 2 then 6 seconds, or after OpenAI's `retry-after` when it is shorter than 10
  seconds: the waits and the rule of Claude's (008 R4), shared now (R9). `TIMED_OUT` and
  `OUT_OF_CREDIT` never: waiting fixes neither.
- **A reasoning summary refused** (a 400 whose `param` is `reasoning.summary`): the same request is
  sent again at once without `summary`, once, and its answer stands with no reasoning (FR-015).
  The retry is logged with the model and the reason, never the text. This is the one case where a
  request is sent again with other arguments, and it changes only what comes back beside the
  answer, never how the answer is written or streamed. It counts against none of the retries
  above: a rate limit on the second request is still tried twice.
- **A stream refused to an unverified organization** fails at once, and is never asked again
  without streaming (Clarifications). OpenAI's documentation doesn't say which code it uses, so
  the provider recognizes it by its `param` (`stream`) or by the words "verified" or
  "verification" in the error, read but never shown, and falls back to the code otherwise, as
  "it rejected the request: `<code>` (`<param>`)"; `quickstart.md` § 2 records what the owner's
  organization gets, and `docs/decisions.md` keeps it.
- **SDK retries off** (`max_retries=0`), as for Claude: they would try a timeout again too.
- **The error is raised without its cause** (`from None`): the SDK's error holds the request, whose
  headers hold the key (FR-004), as in the Anthropic provider.

**Rationale**: FR-014's reasons are 008's, with one added. OpenAI answers an exhausted account with
the status of a rate limit (429), so the code, not the status, tells them apart; trying an
exhausted account again twice would wait 8 seconds for nothing and say "rate limited", which is
wrong.

**Alternatives considered**:
- *Showing OpenAI's message*: more precise, but a 401's message quotes the key's last characters.
- *Asking again without streaming for an unverified organization*: the owner chose not to
  (Clarifications).
- *A profile setting to turn the reasoning summary off*: it would fail every request until the
  owner changed `config/`; the automatic retry costs one rejected request, which OpenAI rejects
  before any inference.

## R5. A new reason: out of credit

**Decision**: `FailureReason.OUT_OF_CREDIT = "out of credit"`, said as "its account is out of
credit or over a spending or usage limit (`<code>`)". It is not tried again.

**Rationale**: FR-014 asks that an exhausted account be said as such. The reason is the provider's
category, not OpenAI's name, so it serves every provider (FR-022), and the interfaces already show
any reason through `describe()`, so no tab or command changes.

**Alternatives considered**:
- *Map it to `KEY_REFUSED`*, as Anthropic's provider does with its `billing_error`: the key is fine;
  the account isn't. Anthropic's mapping stays as it is, since the spec keeps Claude unchanged
  (FR-021); moving it to the new reason is a follow-up for the owner to choose.
- *Map it to `REJECTED` with the code*: true, but it hides the one thing the owner has to act on.

## R6. The profile

**Decision**: `cloud_profiles.openai` in `config/models.yaml`:

| Setting | Value | Why |
| --- | --- | --- |
| `tokenizer` | `tiktoken`, `o200k_base` | the encoding of OpenAI's recent models (tiktoken maps `gpt-5`, `gpt-4.1` and `gpt-4o` to it); tiktoken has no entry for GPT-6 yet, so SC-009 measures it |
| `context_size` | `65536` | the cap is about what one request sends and costs, not about the tokenizer: far below the models' 922,000 input tokens, one request costs at most about $0.13 on `gpt-6.2-sol`, and every chapter of *On Liberty* fits one summary step, as for Claude. With an exact estimate it caps 64K of OpenAI's tokens, where Claude's caps about 100K of Claude's |
| `reasoning` | `low` | all three allowed models take it; OpenAI advises `low` over `none` or `minimal`, and `gpt-6.2-sol` refuses `none`; the tasks read passages and write a short answer or a summary, as for Claude |
| `reasoning_tokens` | `4000` | Claude's room. The integration run prints each reply's reasoning tokens (`usage.output_tokens_details.reasoning_tokens`). A reply has run out when it ends incomplete for `max_output_tokens` with no text; then the value doubles, to 8,000, and the run is repeated, until no case runs out |
| `check_abstentions` | `false` until the integration run says otherwise | 008 R2's rule: if any of the three models abstains in words, without the marker, on any case of the integration run, it turns on for the whole profile, since every model shares it, and the run is repeated until every case of every model passes. It costs one short call per answer without the marker |
| `request_timeout_seconds` | `120` | the owner's bound for Claude (008), for the same reasons |

**Efforts are checked per provider.** `CloudProfile.reasoning` takes the union of the providers'
names (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`) or null, and each provider kind
declares the efforts its profile may hold (`efforts`, a class attribute): Anthropic's `low` to
`max`, and null, which sends no effort, as 008 allowed; OpenAI's `none` to `max`, and not null,
since its profile must name one (FR-003). `create_cloud_providers()` refuses, at startup, a
profile whose effort its kind doesn't accept, configured or not. When every rule passes, startup
prints nothing new, so SC-001's output stays as on `main`.

**Rationale**: FR-003 asks that a value its provider doesn't take stop the app. A single `Literal`
can't say which names belong to which provider; the kind knows, and the factory already checks
profiles against kinds.

**Alternatives considered**:
- *A profile class per provider*: the profile's fields are the same for both; only an effort's
  allowed names differ.
- *Counting with the token counting endpoint*: R1.

## R7. A name that two providers allow

**Decision**: `create_cloud_providers()` raises `ConfigurationError` at startup when a configured
provider allows a name that another configured provider allows too, or that is the local model's
(`llm.model`), naming the name and the settings it appears in (FR-006). A provider with one setting
only isn't offered, so its names count for nothing. The rule covers `ANTHROPIC_MODELS` too: a
Claude name equal to the local model's was already ambiguous, and no real one is.

**Rationale**: `ModelChoices` keys the cloud models by name, and keeps the first provider's on a
clash (`setdefault`): a request for the name would go to Anthropic when the owner may have meant
OpenAI, which Principle I forbids.

**Alternatives considered**:
- *Naming a model with its provider* (`openai/gpt-6.2-sol`): it would change `--model`,
  `--fallback`, the tabs and the records for a clash that real names don't have.

## R8. Registration, settings and order

**Decision**: `CLOUD_PROVIDERS = {"anthropic": AnthropicCloud, "openai": OpenAICloud}` in
`app/container.py`. `docker-compose.yml` passes `OPENAI_API_KEY` and `OPENAI_MODELS` to the app
container, as it passes Claude's; `devtools/.env.sample` lists them, empty, explained. The kind's
`name` is `openai` (its settings' prefix and its profile's key) and its `label` `OpenAI`.

**Rationale**: The dictionary's order is the order the tabs offer the providers' models (FR-007),
since `ModelChoices` walks the setup in it. Nothing else names the class.

## R9. Shared waits

**Decision**: The retry waits and their rule (`_RETRY_WAITS`, `_RETRIED`, `_LONGEST_RETRY_AFTER`,
`_retry_wait()`) move from `anthropic_provider.py` to `app/generation/cloud.py` as `RETRY_WAITS`,
`RETRIED` and `retry_wait(headers, reason, waits)`, which both providers call. The Anthropic
provider behaves byte for byte as before; its unit tests are the proof.

**Rationale**: FR-014 asks for the same retries; one copy can't drift.

**Alternatives considered**:
- *A copy in the OpenAI provider*: two copies of a rule the spec states once.

## R10. The check, and the key elsewhere

**Decision**:
- **The check** reads each allowed model with `client.models.retrieve(name)`, which sends the key
  and the name and runs no inference (FR-017). A refused key (401), OpenAI unreachable or a
  timeout ends the check with one row; a model OpenAI doesn't know, or a 403 for a model the
  project may not use, is a failing row with its reason, and the check goes on; a found one passes
  with its `id` and `owned_by`. OpenAI's description of a model holds no window and no settings,
  so the check can't compare them with the profile; the README says so (FR-024).
- **The client is built with the key and OpenAI's address** (`https://api.openai.com/v1`) given
  explicitly, `max_retries=0` and the profile's timeout, so that neither `OPENAI_BASE_URL` nor
  anything else in the environment can send the key elsewhere (FR-023). The same holds for every
  client of OpenAI's library in `app/`: a unit test reads `app/` and checks that each construction
  of `OpenAI(` or `AsyncOpenAI(` passes `api_key=` and `base_url=` (FR-020, SC-008).
- **The judges** build `AsyncOpenAI(base_url=<Ollama>/v1, api_key="local")`
  (`app/evaluation/generation_metrics.py`), which reads neither `OPENAI_API_KEY` nor
  `OPENAI_BASE_URL`. A unit test sets both in the environment and checks that the judges' client
  still points at Ollama with its own key (SC-008). RAGAS and LangChain get that client, and the
  app's own LLM, never a client of their own; `ragas/cli.py` reads `OPENAI_API_KEY`, but the app
  doesn't run it.

## R11. Tests

**Decision**:
- **Unit** (`make test`):
  - `tests/unit/test_openai_provider.py`, new: the request of R2, argument by argument; the stream
    of R3; each row of R4; the retries, the summary retry and the verification refusal; stats;
    the check's rows; the key absent from every error.
  - `tests/fakes.py`: OpenAI's SDK as far as the provider reads it: events, terminal responses,
    errors with codes, a model's description, as the Anthropic fakes do. `tests/conftest.py`: a
    fixture that patches the client the provider builds, so that the container's `OpenAICloud`
    gets a fake.
  - `tests/unit/test_config.py`: the widened efforts, each refused for the provider that doesn't
    name it.
  - `tests/unit/test_model_choices.py`: a name allowed by two providers, or equal to the local
    model's, stops the setup; OpenAI's models offered after Anthropic's, in the choice, the
    fallbacks and the notices.
  - `tests/unit/test_generation_metrics.py`, where `RagasJudge` is tested: the judges' client
    with `OPENAI_API_KEY` and `OPENAI_BASE_URL` set, and every construction of a client of
    OpenAI's library in `app/` given a key and an address (SC-008).
  - `tests/unit/test_benchmark.py`: an experiment or a judge naming an OpenAI model refused
    before it runs (FR-019).
  - `tests/unit/test_provider_kinds.py`: no file in `app/services`, `app/interface` or
    `app/main.py` names OpenAI, as the fake kind's test does. It guards later changes; SC-011's
    own measure is `git diff main --stat` when the pull request opens, which lists none of them.
    Also, no file under `app/` names one of OpenAI's models (Principle I).
  - The stories' tests, through 008's code with a fake client: `test_commands.py`,
    `test_question_answering.py`, `test_summarization.py`, `test_library_rebuild.py` and
    `test_interface.py`.
  - `tests/unit/test_anthropic_provider.py`: passes after R9 with no change to the file, which
    `git diff main -- tests/unit/test_anthropic_provider.py` shows empty (FR-021, SC-012).
- **Integration** (`make test-integration`): `tests/integration/test_cloud_generation.py` runs every
  implemented provider whose two settings are exported, each model of its list, on the cases of
  `cloud_cases.yaml`, building the kind from `CLOUD_PROVIDERS` so that the test names no class.
  Each provider is skipped on its own without its settings (FR-026). For SC-009, the same run
  prints, for each model, the app's estimate (`count_tokens` over each prompt's messages) beside
  the `input_tokens` that the provider reported, for the eight questions and the short summary,
  and the largest ratio; above 1 / (1 − `safety_margin`), about 1.11, the README and the profile
  say what the window caps. It prints each reply's reasoning tokens too (R6).

## R12. Records

**Decision**:
- **`README.md`**: the opening names OpenAI beside Anthropic; "Cloud models" becomes about both
  providers, with OpenAI's settings, what a request sends and that it isn't stored, OpenAI's data
  terms (abuse-monitoring logs up to 30 days, its own caching of a prompt's start for about 30
  minutes, no training on API data unless the organization opts in to share it, which the owner
  checks in OpenAI's dashboard and the app can't change), the reasoning possibly in another
  language than the answer, API credits and ChatGPT plans, organization verification, the efforts
  it takes, what the check can't tell, and the integration tests; the Deployment notes and
  Configuration sections name the two settings.
- **`docs/decisions.md`**, "Cloud models": why OpenAI came through 008's structure and what that
  structure needed (R5, R6, R7, R9); the Responses API and its arguments (R1, R2); out of credit
  told from a rate limit (R4, R5); the token estimate as measured; the profile's values and what
  kept each; the real models' behavior; the verification error as the owner's organization got
  it; any model dropped from `OPENAI_MODELS`, with OpenAI's reason; and the follow-up of moving
  Anthropic's billing error to "out of credit" (R5).

## R13. The stack

**Decision**: `quickstart.md` runs the unit and integration tests first, with the settings
exported in the shell only, which needs no new container. Only then does it recreate the app
container with the settings in `.env`, which empties the library, *História* included, and says
so before the command; it adds *On Liberty* for the checks, removes it afterwards, and leaves
adding *História* again to the owner, as 008's quickstart did.

**Rationale**: Principle II: whatever recreates a container says what that deletes. Running the
paid checks first means a wrong model name or a refused stream shows up before the library is
emptied.
