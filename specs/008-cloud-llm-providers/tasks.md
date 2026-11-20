---

description: "Task list for cloud models in chat and summaries, opt-in"
---

# Tasks: Cloud models for chat and summaries, opt-in

**Input**: Design documents from `specs/008-cloud-llm-providers/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. SC-012 lists the unit tests, FR-033 and SC-003 the integration tests, and
research.md R16 says how each is built. Each phase writes its tests first and sees them fail, and
its implementation makes them pass. Two kinds of test:
- **New-behavior tests** check what the feature adds, and fail until their phase's implementation.
- **Guard tests** keep `main`'s behavior: the existing tests of the commands, the tabs, the services
  and the benchmark, which keep passing unchanged where no constructor's arguments change (T029,
  T041), and SC-001's comparisons.

**Organization**: By user story, in priority order, after a foundational phase that every story
needs: the settings and the profile, the provider interface, the Anthropic provider, the choices
and the container (Phase 2).
- **US1** (P1): a question answered by Claude, with the local model as its fallback, in the Chat
  tab and `ask`, and `doctor`'s checks. The MVP.
- **US2** (P2): a chapter summarized by Claude, in the Summarization tab and `summarize`; saved
  summaries and `reindex-all`.
- **US3** (P3): the fallbacks the owner orders, in both tabs and both commands.
- **US4** (P4): the Research tab.

Their checks on the stack share two rebuilds, which delete what the app container holds, so they
come together after the four stories (Phase 7).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: a different file, and no dependency on an unfinished task.
- **[Story]**: the user story the task belongs to (US1 to US4).

## Path Conventions

A single Python project, with `app/`, `config/`, `devtools/` and `tests/` at the repository root
(plan.md, Project Structure). Line numbers, where given, are `main`'s at `16eeda4`, for
orientation: names decide.

- **In the Bash tool**, run
  `export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"` before `make` or
  `uv`.
- **`$SCRATCH`** is the session's scratchpad: `main`'s outputs, throwaway scripts and their
  outputs stay there, out of the repository.
- **The key is the owner's.** The owner writes it into `.env` (T065). No task prints it, writes it
  anywhere else or commits `.env`, which git ignores; a command that needs it reads it from `.env`
  in its own process (FR-004).
- **Paid calls** to Anthropic, the integration tests and the stack's checks with a Claude model,
  run only after the owner says so (quickstart.md § 0).
- **`make up` recreates the app container**, which deletes the library, empty now by the owner's
  choice, its logs, the tokenizers and the reranker's weights it downloaded, and its copy of
  `benchmarks/` (Principle II, research.md R18). Only T064 and T065 run it, each once the owner has
  confirmed, and `reset-everything` follows each.
- **Commits** happen only when the owner asks.

---

## Phase 1: Setup

**Purpose**: A known starting point, the SDK in place before anything relies on it, and `main`'s
outputs for SC-001's comparisons.

- [X] T001 Check the starting point. The branch is `feat/cloud-llm-providers`, with only `docs:`
  commits on top of `main` (`16eeda4`), from the constitution's amendment (`31811d9`) to this task
  list. `git status --short` is empty, and `uv.lock` is `main`'s. With asdf's paths,
  `make lint-check` and `make test` pass. Note the number of unit tests, for the results (T069).
- [X] T002 Add Anthropic's SDK (research.md R4, "The SDK beside the project's other packages"):
  `uv add --raw anthropic`, which adds it to `pyproject.toml`'s dependencies and to `uv.lock`. Then:
  - `uv run python -c "import anthropic, httpx2; print(anthropic.__version__)"` prints a 1.x
    version;
  - `uv.lock`'s `httpx` entry is unchanged, and `httpx2` is new;
  - `make test` passes, with T001's count.

  If uv can't resolve it beside the lock, or a test breaks, stop and tell the owner: every later
  task relies on it. Write to `$SCRATCH/sdk-surface.md` the installed SDK's signatures that the
  provider and its tests use, read from the package itself: `Anthropic(api_key=..., timeout=...,
  max_retries=...)`; `messages.stream(...)`, its events and `get_final_message()`;
  `models.retrieve(...)`; and the constructors of `APIStatusError`'s subclasses,
  `APIConnectionError` and `APITimeoutError` (contracts/providers.md, Failures).
- [X] T003 [P] Record `main`'s outputs on the running stack, before any rebuild (SC-001;
  quickstart.md § 2). The app container runs v0.7.0's image, whose `app/` is `main`'s: check it
  with `docker compose ps`, and if it is stopped, start it with `docker compose start`, never
  `make up`. Write to `$SCRATCH` the output of `docker compose exec -T app book-rag doctor`, with
  its exit status, and the `--help` of `ask`, `summarize` and `reindex-all`. The library is empty,
  so no question or summary can be compared on the stack: the unit tests' guards do that (T022,
  T036).

**Checkpoint**: The SDK is in `uv.lock`, `make test` passes, and `$SCRATCH` holds `main`'s
`doctor` output and three `--help` outputs.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: What every story needs: the settings and the provider profile, the interface's two
attributes, the errors, the Anthropic provider, the choices, the factory and the container
(research.md R1 to R6). No service, tab or command changes yet, so `main`'s behavior holds.

**⚠️ CRITICAL**: No user story can begin until this phase is complete.

### Test support and tests (write first, and see them fail)

- [X] T004 In `tests/fakes.py` (research.md R16):
  - `FakeLLM` gains `provider="ollama"`, `check_abstentions=False`, `thinking=""` and
    `thinking_summarized=False` arguments, and a way to fail: `fail=`, a `ModelFailedError` or a
    `GenerationError`, raised after the deltas of `text_before_failure`, or at once. With
    `cloud=True`, its stats' `load_seconds` and `prompt_seconds` are None. What it does today
    doesn't change.
  - `FakeAnthropicClient`: the part of the SDK's client that the provider uses, as T002 noted it.
    `messages.stream(**kwargs)` records its arguments and returns a context manager that yields
    scripted events (`content_block_delta` with a `text_delta` or a `thinking_delta`), whose
    `get_final_message()` returns a message with `model`, `usage`, `stop_reason` and
    `stop_details`; it can raise a given SDK error before its first event or after one.
    `models.retrieve(name)` returns a model with `display_name`, `max_input_tokens` and
    `capabilities`, or raises. Every method counts its calls.
  - `FakeCloud`: a `CloudProvider` (contracts/providers.md) named `fakecloud` and labeled
    `FakeCloud`, whose `model(name)` returns a `FakeLLM` with `provider="fakecloud"`, scripted per
    model, and whose `check()` returns scripted rows. It counts its calls.
- [X] T005 [P] In `tests/unit/test_config.py`, the profile and the settings (FR-001, FR-003;
  `data-model.md`, `CloudProfile.tokenizer`, `.context_size`, `.reasoning`, `.reasoning_tokens`,
  `.check_abstentions` and `.request_timeout_seconds`, and Provider credentials `.name`,
  `.api_key` and `.models`):
  - the repository's `config/models.yaml` loads, and `cloud_profiles.anthropic` holds research.md
    R2's values;
  - without `cloud_profiles`, `Settings.cloud_profiles` is empty;
  - refused, naming the field: an unknown key in a profile, a `reasoning` outside the five levels,
    a negative `reasoning_tokens`, a `context_size` or `request_timeout_seconds` of 0;
  - refused with contracts/configuration.md's message: a task's `max_tokens` plus
    `reasoning_tokens` not smaller than `context_size`;
  - `read_provider_credentials("anthropic", environ)`: both settings, one, or neither; spaces
    around names and empty entries dropped; a name given twice kept once, in order; `Claude-X` kept
    apart from `claude-x`; an empty key read as None; the key's representation hides it.
- [X] T006 [P] In `tests/unit/test_anthropic_provider.py`, new (research.md R4;
  contracts/providers.md, The Anthropic provider), with `FakeAnthropicClient` given to
  `AnthropicCloud` as its client factory:
  - **the client**: built with the key's value, `timeout=request_timeout_seconds` and
    `max_retries=0`; building it, and `model()`, call nothing;
  - **the request**: `system` is the system messages' contents joined by a blank line; `messages`
    the others, in order; `max_tokens` the task's plus `reasoning_tokens`; `thinking` adaptive and
    summarized; `output_config` the profile's effort, absent when `reasoning` is null; no
    `temperature`, `top_p`, `seed`, `fallbacks` or `tools`;
  - **the stream**: a `TextDelta` per `text_delta`, in order; the `thinking_delta`s joined into
    `Generation.thinking`; `thinking_summarized` true; the stats' tokens from `usage` and `model`
    from the final message; `load_seconds` and `prompt_seconds` None; a positive time to first
    token; `generation_seconds` from the first delta;
  - **stop reasons**: `end_turn` gives `stop`; `max_tokens` gives `length`, keeping the text;
    `refusal` raises `ModelFailedError`, `declined`, its detail the category;
  - **failures**: each row of contracts/providers.md's table raises its reason, with the message
    "claude-x (Anthropic) failed: …", and no message holds the key;
  - **retries** (FR-017), with an injected sleep that records its waits: a 429, a 529 and a lost
    connection are tried again twice, waiting 2 s then 6 s, or a `retry-after` under 10 s, and then
    fail; a timeout is never tried again; nothing is tried again once a delta has arrived;
  - **the rest**: `context_size()` is `context_size` minus `reasoning_tokens`; `count_tokens()` uses
    the profile's tokenizer; `provider` is `anthropic`; `check_abstentions` is the profile's;
  - **the check** (research.md R12): one `models.retrieve` per model, and nothing else. A found
    model's row gives its display name and window; an unknown one fails its row; a refused key
    gives one failing row and stops; a model whose `capabilities` don't take the profile's effort
    or adaptive reasoning, or whose `max_input_tokens` is under `context_size`, fails its row,
    saying which.
- [X] T007 [P] In `tests/unit/test_model_choices.py`, new (research.md R6; `data-model.md`,
  `ModelOption.name`, `.provider`, `.provider_label` and `.local`, and Sequence), with a local
  `FakeLLM` and `FakeCloud`:
  - `offered()` gives the local model first, then the allowed models in their list's order;
    `has_cloud()`;
  - `sequence()`: no model, or the local one, gives the local model alone; a cloud model gives it,
    then the local model; fallbacks come in order between them;
  - refused with `ModelChoiceError`, which lists the names offered: an unknown name, a name given
    twice, the picked model among its fallbacks, the local model among them, a fallback with the
    local model picked, a name that differs only in case;
  - `describe()` returns the same options and builds no provider (`FakeCloud`'s count);
  - `is_cloud_provider()` is true for every key of `CLOUD_PROVIDERS`, configured or not, and false
    for the local provider and None; `label_of()`;
  - `check()` gathers the providers' rows; `setting_problems()` gives a failing row for a provider
    with one setting, naming the missing one, and contacts nothing; `local_only(llm)`.
- [X] T008 [P] In `tests/unit/test_container.py` (research.md R1, R15; contracts/services.md, The
  container), with `FakeAnthropicClient` patched in as Anthropic's client:
  - `assemble()` without an environment offers no cloud model;
  - with both settings, `models.offered()` holds the allowed models, and no client method was
    called;
  - a profile under a name outside `CLOUD_PROVIDERS`, and `ANTHROPIC_MODELS` without a profile,
    each raise `ConfigurationError` with contracts/configuration.md's message (FR-003);
  - one setting: nothing offered, and one "cloud provider not offered" event naming the missing
    setting (FR-002), whose fields hold no key;
  - `build_container()` passes the process's environment.
- [X] T009 [P] In `tests/unit/test_llm_provider.py`: `OllamaLLMProvider.provider` is `ollama`, its
  `check_abstentions` is its profile's, and its stats' fields are floats, as today. In
  `tests/unit/test_question_answering.py`, the `checking(settings)` helper gives way to a `FakeLLM`
  with `check_abstentions=True`, for `check_abstention()`'s new signature (research.md R3).

### Implementation

- [X] T010 [P] `app/config/settings.py` (research.md R1, R2):
  - `CloudProfile`, a `ConfigModel` with `data-model.md`'s `CloudProfile.tokenizer`,
    `.context_size`, `.reasoning`, `.reasoning_tokens`, `.check_abstentions` and
    `.request_timeout_seconds`;
  - `Settings.cloud_profiles` (`data-model.md`, `Settings.cloud_profiles`), a
    `dict[str, CloudProfile]`, empty by default, and the rule across files in
    `check_rules_across_files`;
  - `ProviderCredentials`, frozen, with `data-model.md`'s Provider credentials `.name`, `.api_key`
    (a `SecretStr`) and `.models`, and `read_provider_credentials(name, environ)`, which reads
    `<NAME>_API_KEY` and `<NAME>_MODELS` as FR-001 says.

  `EnvironmentSettings` doesn't change.
- [X] T011 [P] `app/errors.py` (`data-model.md`, Events and errors): `ModelChoiceError`;
  `ModelFailedError`, with `model`, `provider`, `reason` and `detail`, whose message reads "<model>
  (<label>) failed: <words>" in contracts/providers.md's words; `AllModelsFailedError`, which holds
  the attempts and lists them in order. All three are `BookRagError`s.
- [X] T012 [P] `app/generation/base.py` (research.md R3):
  - `LLMProvider.provider` and `.check_abstentions`;
  - `Generation.thinking_summarized`, false by default (`data-model.md`,
    `Generation.thinking_summarized`);
  - `GenerationStats.load_seconds` and `.prompt_seconds` as `float | None` (`data-model.md`,
    `GenerationStats.load_seconds`, `.prompt_seconds`);
  - `FailureReason`, a string enum of `data-model.md`'s nine values (`FailureReason`);
  - `Attempt`, with `data-model.md`'s `Attempt.model`, `.provider`, `.reason`, `.detail`,
    `.prompt_tokens` and `.completion_tokens`, the last two None by default;
  - `AttemptFailed`, which holds the attempt and the next model's name and provider
    (`data-model.md`, Events and errors).
- [X] T013 Depends on T012. `app/generation/ollama_provider.py`: `provider = "ollama"`, and
  `check_abstentions` from its profile. `app/generation/question_answering.py`:
  `check_abstention(llm, question, reply, parameters)` reads `llm.check_abstentions`. Its two
  other callers follow: `app/evaluation/benchmark.py` (line 407) and
  `tests/integration/test_generation.py` (line 111). T009 passes.
- [X] T014 Depends on T012. `app/generation/cloud.py`, new: the `CloudProvider` protocol, and
  `ProviderCheck` with `data-model.md`'s Checks `ProviderCheck.name`, `.ok` and `.detail`.
- [X] T015 Depends on T010, T011, T012, T014. `app/generation/anthropic_provider.py`, new
  (research.md R4, R5; contracts/providers.md, The Anthropic provider): `AnthropicCloud`, named
  `anthropic` and labeled `Anthropic`, built from a `ProviderCredentials`, a `CloudProfile` and a
  client factory that defaults to `anthropic.Anthropic`, with its `model()` and `check()`; and
  `AnthropicLLMProvider`, one per model, whose request, stream, stop reasons, failures
  (`data-model.md`, `FailureReason`) and bounded retries are the contract's (FR-013 to FR-015,
  FR-017). Its stats follow `data-model.md`'s `GenerationStats.load_seconds` and `.prompt_seconds`
  (None), `GenerationStats.generation_seconds` (measured from the first delta) and
  `GenerationStats.model` (the model the final message names); its `Generation.thinking_summarized`
  is true; and it writes `data-model.md`'s Logs event "generation finished" on the inference logger,
  with the fields Ollama's provider gives it. T006 passes.
- [X] T016 Depends on T011, T014. `app/generation/choices.py`, new (research.md R6;
  contracts/providers.md, `ModelChoices`): `ModelOption`, with `data-model.md`'s
  `ModelOption.name`, `.provider`, `.provider_label` and `.local`; and `ModelChoices`, with
  `offered()`, `has_cloud()`, `describe()`, `sequence()` under `data-model.md`'s Sequence rules,
  `is_cloud_provider()`, `label_of()`, `check()`, `setting_problems()` and `local_only()`. T007
  passes.
- [X] T017 Depends on T010, T014. `app/generation/factory.py` (contracts/providers.md, Factory):
  `CloudSetup`, and `create_cloud_providers(settings, environ, kinds)`, which reads each given
  kind's credentials, builds each configured kind with its profile, records the setting problems,
  and raises for a profile name that isn't a key of `kinds`, and for allowed models without a
  profile (FR-003). It imports no concrete class (Principle I). `create_llm_provider()` doesn't
  change.
- [X] T018 Depends on T015, T017. `app/container.py` (contracts/services.md, The container):
  - `CLOUD_PROVIDERS = {"anthropic": AnthropicCloud}`, the only place that names a cloud class
    (Principle I);
  - `Container` gains `models: ModelChoices`;
  - `assemble(settings, environment, collection_prefix, environ=None)` builds the choices from the
    local provider and `create_cloud_providers(settings, environ or {}, CLOUD_PROVIDERS)`, and
    logs `data-model.md`'s Logs event "cloud provider not offered", with its fields `provider` and
    `missing`, for each setting problem;
  - `build_container()` passes `os.environ`.

  It keeps calling `create_llm_provider` through the module's own name, which
  `devtools/default_llm.py` replaces, so `tests/unit/test_default_llm_devtool.py` keeps passing.
  The services still take the local provider: US1 and US2 change them. T008 passes.
- [X] T019 [P] Depends on T010. The settings' homes (contracts/configuration.md):
  - `config/models.yaml`: `cloud_profiles.anthropic`, with the contract's values and comments,
    after `embedding_profiles`;
  - `docker-compose.yml`: the app service's `ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}` and
    `ANTHROPIC_MODELS: ${ANTHROPIC_MODELS:-}`, in no other service;
  - `devtools/.env.sample`: the contract's block, both settings empty (FR-005).
- [X] T020 [P] Depends on T010. `app/main.py`, `_pull_models`: also download each cloud profile's
  tokenizer, printing "tokenizer o200k_base: ready" as it does for the others (research.md R5),
  with no request to a provider. A test in `tests/unit/test_commands.py` checks the line.
- [X] T021 Checkpoint: `make lint-check` and `make test` pass (SC-012), T005 to T009 included,
  and T001's tests unchanged. `git diff --name-only` lists Phase 2's files and Phase 1's
  `pyproject.toml` and `uv.lock`. Only `pull-models` prints anything new.

**Checkpoint**: The app starts as before, with or without the settings, and the choices exist,
unused.

---

## Phase 3: User Story 1 - A question answered by Claude (Priority: P1) 🎯 MVP

**Goal**: The Chat tab and `ask` answer with a Claude model picked for the question, and the local
model answers when it fails, saying why; `doctor` checks the key and the models; without the
settings, nothing changes (FR-002, FR-004, FR-006, FR-008, FR-010 to FR-018, FR-020, FR-021).

**Independent Test**: User Story 1's test in spec.md. In this phase, `make test`; on the stack,
T064 to T066 (quickstart.md § 2 to § 7).

### Tests for User Story 1 (write first, and see them fail)

- [X] T022 [P] [US1] In `tests/unit/test_question_answering.py` (research.md R7;
  contracts/services.md, `QuestionAnsweringService`), with the service built on `ModelChoices` of
  a local `FakeLLM` and `FakeCloud`:
  - without `model`, the events and the `Answer` are today's, the `Answer` naming the local model
    and its provider (`data-model.md`, `Answer.model`, `.provider` and `.attempts`);
  - with a cloud model: the same passages, in the same order, as the local model gets (SC-004), and
    the same prompt; the `Answer` names the model that the provider reported;
  - each `FailureReason` from the cloud model, at once: one `AttemptFailed` naming the next model,
    then the local model's answer, which lists the attempt (FR-017, FR-018), a refused key's
    included (SC-002);
  - a reply with no text is `no answer`, and moves on; a reply cut off at its limit with text, and
    an abstention, are answers (FR-017);
  - a failure after two deltas: the deltas, then `AttemptFailed`, then the local model's deltas,
    and an `Answer` whose text is the local model's alone (SC-008);
  - the local model failing after the cloud one: `AllModelsFailedError`, the local failure last;
    the local model failing alone: its own error, as today (SC-001);
  - a refused sequence raises `ModelChoiceError` before the retrieval is called;
  - with nothing retrieved, no model is called, the cloud one included;
  - a cloud model whose profile asks for the check reads its own reply again;
  - the "model failed" and "question answered" events carry `data-model.md`'s Logs fields, and
    none holds the question.
- [X] T023 [P] [US1] In `tests/unit/test_interface.py`, the Chat tab (research.md R13;
  contracts/interface.md, The model choice and The Chat tab):
  - with local-only choices, no Model dropdown or notice is visible, and the handlers' outputs are
    today's (FR-006, SC-001);
  - with `FakeCloud`, the dropdown's choices are labeled as the contract says, the local model is
    its value, and picking a cloud model shows the notice;
  - `ask` passes the model to the service; on `AttemptFailed`, the answer area empties and the
    status line names the failure; a cloud answer's last status line names its model, and a local
    one without failures reads as today.
- [X] T024 [P] [US1] In `tests/unit/test_commands.py`, `ask` and `doctor` (research.md R14;
  contracts/interface.md, The commands):
  - without `--model`, the output is today's, line for line (SC-001);
  - with `--model` and a cloud model: the notice on standard error before anything else, the
    answer on standard output, and "Answered by … (FakeCloud)";
  - a failure: the contract's line on standard error, then the local answer;
  - a refused name: the error, with the names offered, and exit status 1;
  - `doctor` prints the providers' rows, and fails on a failing one.
- [X] T025 [P] [US1] In `tests/unit/test_health_service.py` (research.md R12): `run()` adds no row
  and calls no provider; `run(providers=True)` adds the setting problems' rows and the checks';
  with no provider set at all, `run(providers=True)` gives today's rows (FR-021, FR-002).
- [X] T026 [P] [US1] In `tests/unit/test_logging.py` (SC-011, FR-004): with a sentinel key, a
  session of cloud questions, failures and refusals included, leaves the sentinel in no log
  record, no error message and no `Answer` field.

### Implementation for User Story 1

- [X] T027 [US1] `app/services/health_service.py` (contracts/services.md, `HealthService`):
  `HealthService(settings, runtime, chroma, indexes, models=None)`, and
  `run(inference=False, providers=False)`, which adds the rows of `models.setting_problems()` and
  `models.check()` when `providers` is true. T025 passes.
- [X] T028 [US1] `app/generation/question_answering.py` (research.md R7; contracts/services.md):
  `QuestionAnsweringService(settings, retrieval, models)`, and `stream()` and `answer()` with
  `model` and `fallbacks`:
  - the sequence resolved first, then one search whose passages every model gets (FR-011), then
    each model in turn, streaming (FR-013), fitting the passages to its context (FR-014) and
    sending only what FR-015 lists, with `AttemptFailed` between them;
  - the `Answer`'s `data-model.md` `Answer.model`, `.provider` and `.attempts`, the model the
    provider reported (FR-016);
  - `data-model.md`'s Logs events "model failed", with its fields `provider`, `model`, `reason`
    and `position`, and "question answered", with `provider` and `failed_attempts`;
  - `AllModelsFailedError` once every model failed, the local one last (FR-018).

  Labels come from `ModelChoices.label_of()`.
- [X] T029 [US1] Every construction follows: `app/container.py` passes the choices to
  `QuestionAnsweringService` and `HealthService`; `tests/unit/test_interface.py`,
  `tests/unit/test_question_answering.py`, `tests/unit/test_benchmark.py` and
  `tests/unit/test_commands.py` wrap their `FakeLLM` in `ModelChoices.local_only()`, and pass
  `models` to any `Container` they build. T022 passes.
- [X] T030 [US1] `app/interface/model_choice.py`, new (research.md R13; contracts/interface.md, The
  model choice): for one tab, the Model dropdown, hidden without cloud models, its value the local
  model, and the notice, worded for a question or for a chapter, from `models.describe()`. A
  refusal from `describe()` shows in place of the notice (FR-006, FR-010). The fallbacks come in
  US3.
- [X] T031 [US1] `app/interface/formatting.py` (contracts/interface.md, The Chat tab): the notice's
  text; the status line of a failure; `timing_markdown()` naming the model that answered when it is
  a cloud model or a failure came first, with a line per failure, and today's text otherwise
  (FR-010, FR-018).
- [X] T032 [US1] `app/interface/chat.py`: the tab's own model choice (T030); `on_ask` passes the
  model; `AttemptFailed` empties the answer and sets the status line; the last status line comes
  from `timing_markdown()`. The handlers read their components and show what the service returns,
  and hold no rule (FR-032). T023 passes.
- [X] T033 [US1] `app/main.py` (research.md R9, R14): `ask --model NAME`; the notice on standard
  error before the service is called, from T031's function in `app/interface/formatting.py`, which
  `main.py` already imports, so that it reads as the tab's (FR-008); each failure's line on
  standard error; "Answered by …" before the timing, when a cloud model answered or a model
  failed; and `doctor` with
  `health.run(inference=..., providers=True)`. T024 passes.
- [X] T034 [US1] `tests/integration/test_cloud_generation.py` and
  `tests/integration/cloud_cases.yaml`, new (research.md R16; SC-003, FR-033):
  - the cases: an excerpt written for the test, in a few paragraphs, five questions that it
    answers, and three that it doesn't;
  - skipped unless `ANTHROPIC_API_KEY` and `ANTHROPIC_MODELS` are set; parametrized over
    `ANTHROPIC_MODELS`, building `AnthropicCloud` with the repository's profile;
  - for each model, reading replies as the benchmark's generation does:
    `question_answering_messages()` on `Chunk`s built from the excerpt, `generate()`, then
    `read_reply()`. Each answerable question gets citations that resolve, in a form the app
    recognizes, and no invented one; each unanswerable question gets the marker;
  - the stats: tokens and time to first token above zero, `load_seconds` and `prompt_seconds`
    None, `thinking_summarized` true;
  - `AnthropicCloud.check()` passes for the model.

  It runs at T068, with the owner's go-ahead.
- [X] T035 [US1] Checkpoint: `make lint-check` and `make test` pass (SC-012), `tests/unit/`'s
  T022 to T026 included.

**Checkpoint**: Claude can answer a question in the tab and in `ask`, the local model taking over on
any failure; `doctor` checks the provider. Without the settings, the tab and the commands are as on
`main`.

---

## Phase 4: User Story 2 - A chapter summarized by Claude (Priority: P2)

**Goal**: The Summarization tab and `summarize` make a chapter's summary with a Claude model picked
for it, starting again with the local model when a step fails. Saved summaries record the
provider, the failures and the tokens, and `reindex-all` leaves a cloud summary as it was (FR-012,
FR-019, FR-022, FR-023).

**Independent Test**: User Story 2's test in spec.md. In this phase, `make test`; on the stack,
T066 (quickstart.md § 8).

### Tests for User Story 2 (write first, and see them fail)

- [X] T036 [P] [US2] In `tests/unit/test_summarization.py` (research.md R8; contracts/services.md,
  `ChapterSummarizer`), with `ModelChoices` of a local `FakeLLM` and `FakeCloud`:
  - without `model`, today's summary, naming the local provider (`data-model.md`,
    `ChapterSummary.provider`, `.attempts`, `.prompt_tokens` and `.completion_tokens`);
  - with a cloud model, its summary, with the tokens added up over its steps. The run's model sets
    the budgets, so a chapter that a large cloud window holds takes one step, where the local
    model's small window takes several (FR-012);
  - a cloud model that fails at its second step (SC-007): `on_progress` gets the contract's line,
    the local model makes the whole summary from its first step, and the summary lists the
    attempt with its first step's tokens (FR-022);
  - `save()` writes `data-model.md`'s A saved summary's JSON file keys `provider`,
    `failed_attempts` and `tokens`, the last for a cloud model's only;
  - a refused sequence raises before the chapter is read; every model failing raises
    `AllModelsFailedError`, the local model's failure last;
  - the "chapter summarized" event carries `data-model.md`'s Logs fields, and no log holds a
    step's text or a model's reasoning (FR-020).
- [X] T037 [P] [US2] In `tests/unit/test_library_rebuild.py` (research.md R11; SC-005, FR-023): with
  saved summaries whose `provider` is `anthropic`, `ollama`, or absent, `reindex-all` with
  regeneration leaves the first byte for byte and lists it in `summaries_kept` with its model
  (`data-model.md`, `ReindexReport.summaries_kept`), even without Anthropic's settings. It writes
  the other two again with the local model, and calls no cloud model.
- [X] T038 [P] [US2] In `tests/unit/test_interface.py`, the Summarization and Library tabs
  (contracts/interface.md): the tab's own model choice and its notice for a chapter; `generate`
  passes the model; the report's first line names the provider; a cloud summary's tokens line; a
  failed attempt's line with its tokens; a local summary's report as today; the Library tab's
  notice of the summaries kept, with its line on their references.
- [X] T039 [P] [US2] In `tests/unit/test_commands.py`, `summarize` and `reindex-all`
  (contracts/interface.md): with `summarize --model`, the notice on standard error, the progress
  with a failure, and the last line with the provider and the tokens; without `--model`, today's
  output; `reindex-all`'s two lines about the summaries kept.

### Implementation for User Story 2

- [X] T040 [US2] `app/generation/summarization.py` (research.md R8; contracts/services.md):
  - `ChapterSummarizer(settings, models, catalog, chunks, documents, locator)`;
  - `summarize()` with `model` and `fallbacks`: the sequence resolved before the chapter is read,
    then the whole summary with each model in turn, made as a local one is (FR-012) and by one
    model only (FR-019), the run carrying its model and adding up its finished steps' tokens;
  - `ChapterSummary`'s `data-model.md` `ChapterSummary.provider`, `.attempts`, `.prompt_tokens` and
    `.completion_tokens`, each failed attempt with its tokens (`data-model.md`,
    `Attempt.prompt_tokens`, `.completion_tokens`);
  - `save()`, writing `data-model.md`'s A saved summary's JSON file keys `provider`,
    `failed_attempts` and `tokens`;
  - `data-model.md`'s Logs event "chapter summarized", with its fields `provider` and
    `failed_attempts`, and, for a cloud model, `prompt_tokens` and `completion_tokens`;
  - `cloud_written(provider)`, which tells `reindex-all`, through
    `ModelChoices.is_cloud_provider()`, whether a saved summary's provider is a cloud one.
- [X] T041 [US2] Every construction follows: `app/container.py` passes the choices to
  `ChapterSummarizer`; `tests/library.py` and `tests/unit/test_summarization.py` wrap their
  `FakeLLM` in `ModelChoices.local_only()`. T036 passes.
- [X] T042 [US2] `app/services/library_service.py` (research.md R11): `ReindexReport.summaries_kept`
  (`data-model.md`, `ReindexReport.summaries_kept`). `_regenerate_summaries()` leaves each saved
  summary whose provider `cloud_written()` calls a cloud one, and lists it with its model; it
  writes the others again as today. T037 passes.
- [X] T043 [US2] `app/interface/formatting.py` (contracts/interface.md, The Summarization tab and
  The Library tab): `summary_report()` with the provider, a cloud summary's tokens, and a line per
  failed attempt with its tokens, and today's text for a local summary without failures; the
  notice of the summaries kept.
- [X] T044 [US2] `app/interface/summarization.py`: the tab's own model choice (T030), worded for a
  chapter; `on_generate` passes the model, and its progress shows the failures, with no rule of
  its own (FR-032).
  `app/interface/library.py`: a `gr.Info` with the summaries kept. T038 passes.
- [X] T045 [US2] `app/main.py`: `summarize --model NAME`, its notice, from the same function as
  `ask`'s, and its last line;
  `reindex-all`'s lines about the summaries kept. T039 passes.
- [X] T046 [US2] `tests/integration/test_cloud_generation.py` and `cloud_cases.yaml`: a short
  chapter in the cases, summarized by each allowed model through `ChapterSummarizer` over the
  excerpt's `Chunk`s, with a locator that finds a statement's passage by its words, in
  `tests/fakes.py`. Its statements are cited by lookup, and its tokens are above zero. It runs at
  T068.
- [X] T047 [US2] Checkpoint: `make lint-check` and `make test` pass (SC-012), `tests/unit/`'s
  T036 to T039 included.

**Checkpoint**: Claude can summarize a chapter; the summary records its provider, failures and
tokens, and `reindex-all` keeps it.

---

## Phase 5: User Story 3 - A sequence of fallbacks that the owner defines (Priority: P3)

**Goal**: Both tabs and both commands let the owner order fallbacks after a cloud model, the local
model ending the sequence (FR-007 to FR-010). The services take any sequence since US1 and US2;
this story adds the controls, the flags and the tests of whole sequences.

**Independent Test**: User Story 3's test in spec.md. In this phase, `make test`; on the stack,
T066 and T067 (quickstart.md § 7 and § 9).

### Tests for User Story 3 (write first, and see them fail)

- [X] T048 [P] [US3] In `tests/unit/test_question_answering.py` and
  `tests/unit/test_summarization.py` (SC-006), guards that pass as soon as T028 and T040 are in,
  since the services take any sequence from then on: a failing cloud model, then a working one: the
  second answers, and the local model
  isn't called; two failing ones: the local model answers, both attempts listed in order; the same
  for a summary.
- [X] T049 [P] [US3] In `tests/unit/test_interface.py` (research.md R13; contracts/interface.md):
  the fallbacks' multiselect is hidden until a cloud model is picked; it offers the other cloud
  models; its value's order reaches the service as given; the notice lists the sequence in that
  order, the local model last; a choice in one tab leaves the other's as it was (FR-009); a refused
  list shows its refusal in place of the notice.
- [X] T050 [P] [US3] In `tests/unit/test_commands.py`: `--fallback`, repeated, in order, for `ask`
  and `summarize`, in the notice and in the sequence; refused, with exit status 1 and the names
  offered: an unknown name, one given twice, the local model as a fallback, and a fallback after
  the local model (FR-008).

### Implementation for User Story 3

- [X] T051 [US3] `app/interface/model_choice.py` (research.md R13; FR-007, FR-010): the "If it
  fails, then" multiselect, shown while a cloud model is picked and offering the other cloud
  models, with its note that the local model answers last; the notice over the whole sequence.
- [X] T052 [US3] `app/interface/chat.py` and `app/interface/summarization.py`: each handler passes
  its own tab's fallbacks with the model (FR-009). T049 passes, and T048 still does.
- [X] T053 [US3] `app/main.py`: `--fallback NAME`, repeated, for `ask` and `summarize`. T050 passes.
- [X] T054 [US3] Checkpoint: `make lint-check` and `make test` pass (SC-012), `tests/unit/`'s
  T048 to T050 included.

**Checkpoint**: Any sequence the owner orders runs in both tabs and both commands.

---

## Phase 6: User Story 4 - The Research tab shows a cloud answer from the inside (Priority: P4)

**Goal**: The Research tab names the model that answered and the ones that failed, shows a cloud
model's measures with their caveats and its reasoning as Anthropic returned it, and checks the
providers on "Check again" only (FR-021, FR-024, FR-025).

**Independent Test**: User Story 4's test in spec.md. In this phase, `make test`; on the stack,
T067 (quickstart.md § 10).

### Tests for User Story 4 (write first, and see them fail)

- [X] T055 [P] [US4] In `tests/unit/test_interface.py` (research.md R13; contracts/interface.md, The
  Research tab):
  - for a cloud answer: the LLM row's model and provider; a "Failed first" row per attempt; model
    loading and prompt processing "unavailable"; "(measured by the app)" beside the generation's
    speed and seconds; the reasoning under its summary label, or "None came back.";
  - for a local answer without failures, `main`'s markdown, byte for byte;
  - with nothing retrieved, the LLM row names the model picked for the question, and no
    generation's row shows (FR-024);
  - the checks after an answer run without the providers, and "Check again" with them (FR-021,
    FR-024, FR-025).

### Implementation for User Story 4

- [X] T056 [US4] `app/interface/formatting.py` (FR-024, FR-025): `run_markdown()` reads the
  answer's model, provider and attempts instead of a configured name, and, when no model was
  called, the model picked, with no generation's rows; `_generation_rows()` shows None as
  "unavailable" and labels the app's own measures; the reasoning's label.
- [X] T057 [US4] `app/interface/diagnostics.py`: `on_answer` passes the answer alone to the
  formatting; the checks after an answer call `health.run()`, and "Check again" calls
  `health.run(providers=True)` (FR-021). T055 passes.
- [X] T058 [US4] Checkpoint: `make lint-check` and `make test` pass (SC-012), `tests/unit/`'s T055
  included.

**Checkpoint**: The four stories work, and are unit-tested; the checks on the stack come next.

---

## Phase 7: Polish & Cross-Cutting Concerns (cross-story tests, the records, the stack)

**Purpose**: The tests that span the stories, the records, and the checks on the real stack and
the real models.

- [X] T059 [P] `tests/unit/test_provider_kinds.py`, new (SC-009, FR-026; research.md R16): with
  `FakeCloud` added to `app.container.CLOUD_PROVIDERS` by `monkeypatch`, a profile
  `cloud_profiles.fakecloud`,
  and `FAKECLOUD_API_KEY` and `FAKECLOUD_MODELS` in the environment given to `assemble()`. The fake
  shows in both tabs' choices, in `--model` and `--fallback`, and in `doctor`'s rows; it joins a
  sequence, answers and summarizes; and the Research tab reports it. `git grep -n -i fakecloud --
  app/` finds nothing.
- [X] T060 [P] In `tests/unit/test_benchmark.py` (SC-010, FR-027; research.md R15): an experiment
  whose variant's `llm.model` is a cloud model's name, and one whose judge's `model` is, are each
  refused before the run starts; a workspace's container offers no cloud model.
- [X] T061 `README.md` (FR-029; research.md R17): its opening line; a "Cloud models" section with
  everything that FR-029 lists: the settings and the recreation they take, what each request
  sends, the provider's terms and where to read them, fallbacks, the notices, `doctor` and "Check
  again", costs, the key and who can use it, the integration tests to run before trusting a model,
  and what stays local. Also the Interface, Questions, Summaries and Configuration sections, the
  last saying which generation settings don't apply to a cloud model; the Deployment notes; and
  the Layout's new modules.
- [X] T062 `docs/decisions.md` (FR-030; research.md R17): a "Cloud models" section with each
  decision that FR-030 lists and its reason, and the plan's own choices: no server-side fallbacks,
  no temperature, the bounded retries, the approximate tokenizer, the profile's values, a
  command's withdrawal. It also says that benchmark results recorded from now on hold
  `cloud_profiles` in their configuration, so their `configuration_sha256` differs from earlier
  runs of the same local setup, which nothing in the code compares. T068 adds what the real models
  showed.
- [X] T063 Checkpoint: `make lint-check` and `make test` pass (SC-012), T059 and T060 included.
  `git diff main --name-only` lists plan.md's Project Structure files, `README.md`,
  `docs/decisions.md` and this spec's folder, and no file of the delivered specs (FR-031). None
  is in `app/retrieval`, `app/ingestion`, `app/storage` or `app/generation/prompts.py`, and in
  `config/` only `models.yaml` changed (FR-028).
- [ ] T064 With the owner's go-ahead, the rebuild without the settings (quickstart.md § 2; SC-001):
  `.env` without `ANTHROPIC_*`; `make up`, which deletes what Path Conventions lists;
  `reset-everything --confirm "DELETE EVERYTHING"`; then `doctor`, the same rows as T003's. The
  owner sees no model choice in the tabs.
- [ ] T065 The owner writes the key into `.env`, with `ANTHROPIC_MODELS` set to
  `claude-haiku-5-5,claude-sonnet-5-5,claude-no-such-model` (quickstart.md § 3; SC-002). With their
  go-ahead: `make up`, which deletes what Path Conventions lists; `reset-everything`; and *On
  Liberty* added from `benchmarks/books/on-liberty.md`. Then quickstart.md § 4: `doctor`'s three
  rows, and its run with a wrong key in its own process.
- [ ] T066 With the owner's go-ahead for the paid calls, `quickstart.md` § 5 to § 8, § 11 and § 12,
  by command: the same passages, the abstention, the fallbacks, the summaries and `reindex-all`, no
  trace of the key, and the benchmark's refusal. Each section's outputs go to `$SCRATCH`.
- [ ] T067 The owner, in the browser: quickstart.md § 9 and § 10. If the multiselect doesn't keep
  the order of selection, research.md R13's three dropdowns replace it in
  `app/interface/model_choice.py`, T049 adapts, and the change reaches the stack without a
  rebuild, which would empty the library: check that the container runs the app from `/app/app`
  (`docker compose exec app python -c "import app; print(app.__file__)"`, uv's editable install),
  copy the module in with `docker compose cp`, and run `docker compose restart app`, which keeps
  the container and its library. Then § 9 runs again.
- [ ] T068 With the owner's go-ahead, quickstart.md § 13: `make test-integration` with the settings
  exported and `ANTHROPIC_MODELS=claude-haiku-5-5,claude-sonnet-5-5`. Then `docs/decisions.md`
  gains what the real models showed, and whether research.md R2's values held; a value that didn't
  changes in `config/models.yaml`, with its reason.
- [ ] T069 Results: a "Results of the implementation" section in spec.md, as `specs/007` has, with
  one line per success criterion and its evidence, and the test counts against T001's. The owner
  adds their own book back, or empties the settings and runs `make up` (quickstart.md § 14).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none. T002 comes before anything that imports `anthropic`; T003 before any
  rebuild.
- **Foundational (Phase 2)**: after Setup. It blocks every story.
- **US1 (Phase 3)**: after Phase 2.
- **US2 (Phase 4)**: after Phase 2, and after T030, whose shared component its tab uses. If US2
  runs first, T030 moves into it.
- **US3 (Phase 5)**: after US1 and US2: it extends both tabs' choices and both commands.
- **US4 (Phase 6)**: after US1, whose answers it reads. It doesn't need US2 or US3.
- **Polish (Phase 7)**: after the stories. T064 to T068 run in order, each on the stack that the
  one before left; T059 to T063 before them.

### Within Each User Story

- Tests first, failing; then the service, then the tabs and the commands; the checkpoint last.
- A file shared by several tasks, such as `app/interface/formatting.py`, `app/main.py` or
  `tests/unit/test_interface.py`, takes them one at a time.

### Parallel Opportunities

- Phase 2: T005 to T009, once T004 is done; T010, T011 and T012; T019 and T020 after T010.
- US1: T022 to T026. US2: T036 to T039. US3: T048 to T050.
- Polish: T059 and T060.
- US4 can run beside US2 and US3, once US1 is done.

---

## Parallel Example: Phase 2

```bash
# Once T004's fakes exist, the five test files are independent:
Task: "T005 profile and settings tests in tests/unit/test_config.py"
Task: "T006 Anthropic provider tests in tests/unit/test_anthropic_provider.py"
Task: "T007 choices tests in tests/unit/test_model_choices.py"
Task: "T008 container tests in tests/unit/test_container.py"
Task: "T009 provider attributes in tests/unit/test_llm_provider.py"

# Three foundations that import nothing new from each other:
Task: "T010 CloudProfile and ProviderCredentials in app/config/settings.py"
Task: "T011 the three errors in app/errors.py"
Task: "T012 the interface's attributes and the failure types in app/generation/base.py"
```

## Parallel Example: User Story 1

```bash
Task: "T022 sequences of an answer in tests/unit/test_question_answering.py"
Task: "T023 the Chat tab in tests/unit/test_interface.py"
Task: "T024 ask and doctor in tests/unit/test_commands.py"
Task: "T025 the providers' checks in tests/unit/test_health_service.py"
Task: "T026 no trace of the key in tests/unit/test_logging.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1, then Phase 2: the SDK, the profile, the provider, the choices and the container, with
   nothing visible changing.
2. Phase 3: a question answered by Claude, falling back to the local model, in the tab and in
   `ask`.
3. **Stop and validate**: `make test`, and, with the owner's go-ahead, quickstart.md § 4 to § 7 on
   the stack.

### Incremental Delivery

1. US1: questions (the MVP).
2. US2: summaries, saved and kept through `reindex-all`.
3. US3: ordered fallbacks.
4. US4: the Research tab.
5. Phase 7: the cross-story tests, the records, the checks on the stack and the real models, and
   the results.

Each story leaves `make test` passing, and the app without the settings as on `main`.

---

## Notes

- [P] tasks touch different files and depend on no unfinished task.
- [Story] labels map tasks to spec.md's user stories, for traceability.
- See each phase's tests fail before implementing it.
- No task prints the key or writes it outside `.env`; the paid calls and the rebuilds wait for the
  owner's go-ahead.
- Commit only when the owner asks; stop at any checkpoint to validate a story on its own.
