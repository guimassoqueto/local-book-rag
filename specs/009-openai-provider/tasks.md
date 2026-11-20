---

description: "Task list for OpenAI models in chat and summaries, opt-in"
---

# Tasks: OpenAI models for chat and summaries, opt-in

**Input**: Design documents from `specs/009-openai-provider/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. SC-012 lists the unit tests, FR-026 and SC-003 the integration tests, and
research.md R11 says how each is built. Each phase writes its tests first and sees them fail, and
its implementation makes them pass. Two kinds of test:
- **New-behavior tests** check what the feature adds, and fail until their phase's implementation.
- **Guard tests** keep `main`'s behavior: `tests/unit/test_anthropic_provider.py`, which passes
  with no change to it (FR-021), and the existing tests of the services, the tabs and the
  commands, which pass unchanged since none of those files changes (SC-011).

**Organization**: The provider and the shared changes come first, since every story reaches
OpenAI through them (Phase 2). The stories then add the tests that prove each one works through
008's interfaces, which need no change:
- **US1** (P1): a question answered by an OpenAI model, and the real models checked. The MVP.
- **US2** (P2): a chapter summarized by an OpenAI model; saved summaries and `reindex-all`.
- **US3** (P3): sequences across providers.
- **US4** (P4): the Research tab and the checks.

The stack's checks recreate the app container, which deletes the library with the owner's
*História*, so they come together at the end, after the owner says go (Phase 7).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel: a different file, and no dependency on an unfinished task.
- **[Story]**: the user story the task belongs to (US1 to US4).

## Path Conventions

The existing application, as `plan.md` lays it out: `app/` for the code, `config/` for the
configuration, `tests/unit/` and `tests/integration/` for the tests, at the repository's root.

---

## Phase 1: Setup

**Purpose**: The dependency and the deployment's two settings.

- [X] T001 Add OpenAI's SDK as a direct dependency with `uv add --raw openai`, which changes `pyproject.toml` and `uv.lock`; check that the lock keeps `openai` at 3.3.0 or newer and that nothing else moves beyond what that pulls (research.md R1)
- [X] T002 [P] Pass `OPENAI_API_KEY` and `OPENAI_MODELS` to the app service in `docker-compose.yml`, after Claude's two settings, empty by default, with no other service getting them (contracts/configuration.md, "docker-compose.yml"; FR-005)
- [X] T003 [P] Add OpenAI's block to `devtools/.env.sample`, after Anthropic's, both settings empty, with the comments of contracts/configuration.md, ".env" (FR-005)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared changes that serve every provider (FR-022) and the OpenAI provider itself.
Every story needs them.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Test support and tests (write first, and see them fail)

- [X] T004 [P] Extend `tests/fakes.py`:
  - `FakeCloud.efforts`, every effort name and `None`, so that the factory's new check (T012) accepts the fake kind's profile.
  - OpenAI's SDK, as far as the provider reads it, built from the installed SDK's own types so that an SDK change fails the tests (research.md R1):
    - error builders for `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `RateLimitError`, `BadRequestError`, `InternalServerError`, `APIConnectionError` and `APITimeoutError`, each with an error body holding a `code`, a `param` and a `message`, and headers such as `retry-after`; an `APIError` such as the SDK raises for an `error` event;
    - event builders for `response.created`, `response.in_progress`, `response.output_text.delta`, `response.reasoning_summary_text.delta`, `response.refusal.delta`, and `response.completed`, `response.incomplete` and `response.failed` carrying a response with `model`, `usage` (input, output and reasoning tokens), `status`, `incomplete_details` and `error`, and a reasoning item with an encrypted copy;
    - a model's description (`id`, `owned_by`);
    - `FakeOpenAIClient`, which records every `responses.create(...)` and `models.retrieve(...)` call with its arguments, plays scripted event streams or raises scripted errors, including an error raised after some events, and a stream that ends with no terminal event.
  - A fixture `openai_client` in `tests/conftest.py`: it patches the SDK client's constructor that `app/generation/openai_provider.py` calls so that the container, which builds `OpenAICloud` from its credentials and profile alone, gets a `FakeOpenAIClient`. It records the constructor's arguments and yields the fake for the test to script. Every task below that says "with a `FakeOpenAIClient`" uses this fixture.
- [X] T005 [P] Tests in `tests/unit/test_config.py`: `cloud_profiles.<name>.reasoning` accepts every name of data-model.md, The profile, `CloudProfile.reasoning` (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`) and null, and refuses any other name at load.
- [X] T006 Tests in `tests/unit/test_model_choices.py`, on `create_cloud_providers()` and `ModelChoices` (data-model.md, Startup rules), after T004:
  - OpenAI's settings read as data-model.md, OpenAI's settings, `ProviderCredentials.api_key` and `ProviderCredentials.models` define them: both, one or neither set; spaces; empty entries; a name listed twice; a name in another case kept as written (FR-001, FR-002, SC-012). One setting alone offers nothing, and is a failing row naming the missing setting.
  - A profile whose effort its kind doesn't accept stops the setup, per data-model.md, Provider kinds, `CloudProvider.efforts`: `minimal` in Anthropic's profile; null in OpenAI's; checked whether the provider is configured or not; with the messages of contracts/configuration.md.
  - A name offered by two providers, or offered and equal to `llm.model`, stops the setup with the messages of contracts/configuration.md, Claude's list included (FR-006). A list whose provider has one setting only clashes with nothing.
  - With both providers configured, the choices list the local model, Anthropic's models, then OpenAI's, each in its list's order (FR-007).
  - When every rule passes, the setup logs nothing new (SC-001).
  - `FailureReason.OUT_OF_CREDIT` reads as data-model.md, Failure reasons, `FailureReason.OUT_OF_CREDIT` gives it, with and without a code.
- [X] T007 New `tests/unit/test_openai_provider.py`, on `OpenAICloud` and `OpenAILLMProvider` with `FakeOpenAIClient` (contracts/providers.md; research.md R1 to R4, R10), after T004:
  - **Building**: the client gets the key from data-model.md, OpenAI's settings, `ProviderCredentials.api_key`, `base_url="https://api.openai.com/v1"`, the profile's timeout and `max_retries=0`, even with `OPENAI_BASE_URL` set in the environment; building the kind or a model contacts nothing.
  - **The request** (research.md R2): the model; the prompt's messages with their own roles and text, `system` included; `max_output_tokens` as the task's limit plus the profile's `reasoning_tokens`; `reasoning` with the profile's effort and `summary: "auto"`; `store=False`; `truncation="disabled"`; `stream=True`. None of the arguments that contracts/providers.md says are never sent.
  - **The stream** (research.md R3): text deltas are yielded as they come; reasoning summary deltas become the reasoning, marked as a summary; reasoning items and their encrypted copy are dropped.
  - **Stats**: the stats of data-model.md, "What an OpenAI model's work records", from the terminal response: the model as OpenAI reported it, a dated name included; input and output tokens; the time to first token from the first text or reasoning delta; load and prompt processing as `None`; finish reason `stop` when completed, `length` when incomplete for `max_output_tokens`, with or without text.
  - **The log**: the inference log's `generation finished` event, with no text, reasoning or key.
  - **Failures**: every row of contracts/providers.md, Failures, mapped to its reason and detail. Only a 401 is a refused key; a 403 is a rejection with its code. Each credit code is `OUT_OF_CREDIT`, tried once. A refusal, before or after text, is a decline. `content_filter` and the declining codes are declines. Any other code is a rejection worded as contracts/providers.md gives it. A stream with no terminal event is unreachable.
  - **The verification refusal**: recognized by `param` or by its words, said as "OpenAI streams this model only to a verified organization", with the code's wording when it isn't recognized; one request only, never followed by one without streaming.
  - **Retries**: a rate limit, an outage or a lost connection is tried twice before any text or reasoning, after 2 then 6 seconds or a `retry-after` under 10 (a fake `sleep`), and not after text has arrived. A timeout is never tried again.
  - **The reasoning summary refused**: a 400 naming `reasoning.summary` is followed at once by the same request without `summary`, once, still streamed; its answer stands with an empty reasoning; a rate limit on that second request is still tried twice (FR-015). The retry is logged with the provider, the model and the reason, and the log record holds no text, question, reasoning or key (FR-016).
  - **The key**: no `ModelFailedError` carries the key, OpenAI's message, or a cause or context holding the SDK's request.
  - **The check** (research.md R10): one row per model, found with its `id` and `owned_by`; unknown, or forbidden (403), on its own row while the check goes on; a refused key (401), OpenAI unreachable or a timeout ends it with one row. It sends only `models.retrieve` calls.

### Implementation

- [X] T008 [P] Widen data-model.md, The profile, `CloudProfile.reasoning` in `app/config/settings.py` to `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` or null, and update its docstring: each provider kind says which it accepts (research.md R6). T005 passes.
- [X] T009 [P] Add data-model.md, Failure reasons, `FailureReason.OUT_OF_CREDIT` in `app/generation/base.py`, with its words in `describe()` (research.md R5).
- [X] T010 Extend `app/generation/cloud.py` (contracts/providers.md, "app/generation/cloud.py"):
  - `CloudProvider.efforts`, as data-model.md, Provider kinds, `CloudProvider.efforts` defines it;
  - `RETRY_WAITS`, `RETRIED` and `retry_wait(headers, reason, waits)`, moved from `app/generation/anthropic_provider.py` with their behavior unchanged (research.md R9).
- [X] T011 Update `app/generation/anthropic_provider.py`:
  - `AnthropicCloud.efforts` is Anthropic's efforts and `None` (data-model.md, Provider kinds, `CloudProvider.efforts`);
  - its streaming loop calls the shared `retry_wait()` in place of its private copies, which go;
  - nothing else changes. `tests/unit/test_anthropic_provider.py` passes with no change to the file (FR-021).
- [X] T012 Extend `create_cloud_providers()` in `app/generation/factory.py` (data-model.md, Startup rules; contracts/configuration.md, "What startup does"):
  - every profile's effort is checked against its kind's `efforts`, configured or not, and refused with the messages of the contract (FR-003);
  - once the configured providers are known, a name offered by two of them, or offered and equal to `settings.llm.model`, raises `ConfigurationError` with the contract's messages (FR-006, research.md R7);
  - nothing is logged when every rule passes. T006 passes.
- [X] T013 New `app/generation/openai_provider.py`: `OpenAICloud` and `OpenAILLMProvider` as contracts/providers.md gives them. The module docstring says that nothing contacts OpenAI until a request streams or a check runs, and that the key reaches the SDK's client only.
  - `name = "openai"` and `label = "OpenAI"`, per data-model.md, Provider kinds, `CloudProvider.name` and `CloudProvider.label`; `efforts` without `None`.
  - The client is built as T007 says, from the key of data-model.md, OpenAI's settings, `ProviderCredentials.api_key`, read with `get_secret_value()` only there. Each model's provider has the profile's `check_abstentions`, `context_size() = context_size - reasoning_tokens`, and `count_tokens()` with the profile's tokenizer.
  - `stream()` sends the request of research.md R2 through `client.responses.create(..., stream=True)` and reads the raw events as research.md R3 says, not through the SDK's `responses.stream()` helper. It yields the `Generation` whose values data-model.md, "What an OpenAI model's work records", gives: the model as OpenAI reported it; prompt and generated tokens from `usage`; load and prompt processing as `None`; the reasoning summary marked as a summary, empty when none came back; and the provider `openai`, which the saved summary records.
  - No model's name appears in the module, in code, docstrings or comments (Principle I): the allowed names live in `OPENAI_MODELS` and the profile's comments only.
  - Failures map as research.md R4 says, through one `_failure()` function, the most specific case first. Retries go through `retry_wait()`. The reasoning-summary retry happens once.
  - Every `ModelFailedError` is raised `from None`.
  - `check()` follows research.md R10. T007 passes.
- [X] T014 Register `"openai": OpenAICloud` in `CLOUD_PROVIDERS` in `app/container.py`, after Anthropic, and update the comment above it to name both providers' settings (research.md R8).
- [X] T015 Add `cloud_profiles.openai` to `config/models.yaml`, after `anthropic`, as contracts/configuration.md gives it. The comments in angle brackets stay as placeholders until T023 measures them, and the comment above `cloud_profiles` names OpenAI's settings beside Anthropic's.
- [X] T016 Run `make lint` and `make test`. Every Phase 2 test passes, and so does every existing test, `tests/unit/test_anthropic_provider.py` with no change to it, which `git diff main -- tests/unit/test_anthropic_provider.py` shows empty.

**Checkpoint**: OpenAI is a configured provider kind; every story can now be proved through it.

---

## Phase 3: User Story 1 - A question answered by an OpenAI model (Priority: P1) 🎯 MVP

**Goal**: With both settings, the Chat tab and `ask` offer OpenAI's models after Claude's, say
what goes to OpenAI, stream its answer with resolving citations and abstentions, and fall back to
the local model when it fails. Without them, nothing changes.

**Independent Test**: The unit tests below with fake clients; then, on the real models, quickstart
§ 2, from the host, before the stack is touched.

### Tests for User Story 1 (write first, and see them fail)

- [X] T017 [P] [US1] Tests in `tests/unit/test_commands.py`, with the container built from an environment holding OpenAI's two settings and the provider's client patched to a `FakeOpenAIClient`:
  - `ask --model <an OpenAI name>` prints the notice naming OpenAI on standard error before any request, then the answer with its sources, and "Answered by <reported model> (OpenAI)".
  - With the fake failing (out of credit, refused key), the local model answers and standard error names the failure in contracts/providers.md's words.
  - A name that isn't offered is refused before any search, listing OpenAI's names with "(OpenAI)".
  - With neither OpenAI setting, `ask` and `doctor` print what they print on `main`, with Claude's settings set and without them (SC-001).
- [X] T018 [P] [US1] Tests in `tests/unit/test_question_answering.py`, through `QuestionAnsweringService` with an OpenAI model whose client is a `FakeOpenAIClient`:
  - the search returns the same passages, in the same order, as for the local model;
  - the request's `input` is exactly the prompt the local model gets, roles included (FR-008), and exactly the answer's `messages`, the final context that the Research tab shows (SC-004);
  - citations resolve, an invented one is reported, and the marker is shown as an abstention;
  - a decline after text has streamed emits the failure, the text is withdrawn, and the local model answers;
  - in a session of local and Claude answers, the client counts no request (SC-002).
- [X] T019 [P] [US1] Tests in `tests/unit/test_generation_metrics.py` (SC-008, FR-020):
  - with `OPENAI_API_KEY` and `OPENAI_BASE_URL` set in the environment, building `RagasJudge`'s metrics, with `openai.AsyncOpenAI` patched to record its arguments, gives the judges' client Ollama's address and its own key;
  - a test reads every `.py` file under `app/` and checks that each construction of `OpenAI(` or `AsyncOpenAI(` passes both `api_key=` and `base_url=`.
- [X] T020 [P] [US1] Tests in `tests/unit/test_benchmark.py`: an experiment whose variant names an OpenAI model, and one whose judge does, are each refused before the run starts, with no request to the provider (FR-019, SC-008), as the Claude case is.
- [X] T021 [P] [US1] Tests in `tests/unit/test_provider_kinds.py`, beside the fake kind's:
  - no file in `app/services/`, `app/interface/` or `app/main.py` names OpenAI, case ignored (SC-011's guard);
  - no `.py` file under `app/` names one of OpenAI's models: it holds neither `gpt-5` nor `gpt-6`, case ignored (Principle I: a model is named in configuration). The local model's workaround comments, which name `gpt-oss`, stay allowed.

### Implementation for User Story 1

- [X] T022 [US1] Generalize `tests/integration/test_cloud_generation.py` (research.md R11, FR-026):
  - The module docstring covers every provider.
  - Credentials are read for every name in `app.container.CLOUD_PROVIDERS`. Each `(provider, model)` pair of the providers whose two settings are exported is a parameter; a provider without its settings is skipped on its own, with a reason naming its two settings.
  - The kind is built from `CLOUD_PROVIDERS[name]` with `settings.cloud_profiles[name]`, so the test names no class. The summary's `CloudSetup` uses the kind's own label.
  - The existing cases run unchanged for every provider.
  - New, for SC-009: for each pair, the app's estimate (`count_tokens` over each prompt's messages) beside the input tokens the provider reported, for the eight question prompts and the summary's, and the largest ratio; and each reply's reasoning tokens, when the provider reports them. All are printed, shown with `-s`.
- [X] T023 [US1] Run quickstart § 2 from the host: `set -a; . ./.env; set +a`, then `uv run pytest -m integration tests/integration/test_cloud_generation.py -s`. Never print the key. Then apply research.md R6's rules in quickstart § 2's order, running again after each change:
  - drop a model the organization can't use from `.env`'s `OPENAI_MODELS`, and note OpenAI's reason;
  - turn `check_abstentions` on after an abstention in words;
  - double `reasoning_tokens` after a reply ran out during its reasoning.

  Every case then passes on every model that remains (SC-003). Fill the angle-bracket comments of `cloud_profiles.openai` in `config/models.yaml`: the largest ratio, the date, and what it means for `context_size`. Keep the run's numbers, the replies' notable forms (citations, abstentions, reasoning) and any verification error for T035, T036 and T040.
- [X] T024 [US1] Run `make lint` and `make test`: T017 to T021 pass. None of `app/services/`, `app/interface/` or `app/main.py` changed to make them pass; if one had to, stop, and correct the spec first (SC-011).

**Checkpoint**: An OpenAI model answers questions in the app, and its output is read correctly on
the real models. This is the MVP.

---

## Phase 4: User Story 2 - A chapter summarized by an OpenAI model (Priority: P2)

**Goal**: The Summarization tab and `summarize` offer OpenAI's models, record the provider, the
model and the tokens, and `reindex-all` leaves an OpenAI summary as it was.

**Independent Test**: The unit tests below; the real-model summary case of T023; quickstart § 7
on the stack.

### Tests for User Story 2 (write first, and see them fail)

- [X] T025 [P] [US2] Tests in `tests/unit/test_summarization.py`, with an OpenAI model whose client is a `FakeOpenAIClient`:
  - A summary in one step and in several follows the local steps. Its record names provider `openai` and the reported model, with the tokens summed over its steps (data-model.md, "What an OpenAI model's work records": `provider`, `tokens`).
  - A step that fails with out of credit restarts the summary with the next model, and the failed attempt records its step and tokens.
- [X] T026 [P] [US2] Tests in `tests/unit/test_library_rebuild.py`: a saved summary whose provider is `openai` is left byte for byte by `reindex-all --regenerate-summaries`, with no request to the client, and is listed in `summaries_kept` as "…(<model>, OpenAI)" (data-model.md, "What an OpenAI model's work records": `summaries_kept`), whether or not OpenAI's settings are set.

### Implementation for User Story 2

- [X] T027 [US2] Run `make test`: T025 and T026 pass through 008's summary and regeneration code, with no change under `app/services/` (SC-011). If one fails, the fix belongs in `app/generation/openai_provider.py`, or in a shared module for every provider, never in a service.

**Checkpoint**: Summaries from OpenAI are made, saved and kept like Claude's.

---

## Phase 5: User Story 3 - Sequences across providers (Priority: P3)

**Goal**: A sequence may mix Claude's and OpenAI's models in any order, the local model last; the
notices name both providers in order; each failure moves on to the next provider's model.

**Independent Test**: The unit tests below; quickstart § 6 on the stack.

### Tests for User Story 3 (write first, and see them fail)

- [X] T028 [P] [US3] Tests in `tests/unit/test_model_choices.py`, with both providers configured:
  - a Claude model's fallback options hold OpenAI's models and the other Claude ones, in the order offered, and the reverse;
  - `describe()` of a Claude model with an OpenAI fallback, and of the reverse, ends with the local model;
  - a name given twice across providers is refused.
- [X] T029 [P] [US3] Tests in `tests/unit/test_interface.py`: `model_notice()` for a mixed sequence reads "The question and the passages found go to Anthropic: …, then OpenAI: …. If they fail, gpt-oss:20b answers, locally.", and the reverse order names OpenAI first (contracts/providers.md, "What the user sees").
- [X] T030 [P] [US3] Tests in `tests/unit/test_question_answering.py`, with an `AnthropicCloud` on a fake Anthropic client and an `OpenAICloud` on a `FakeOpenAIClient`:
  - a failing Claude model followed by an OpenAI one: OpenAI answers, and the local model isn't called;
  - the reverse;
  - both failing: the local model answers, and both failures are listed in order, each with its provider (SC-006).

### Implementation for User Story 3

- [X] T031 [US3] Run `make test`: T028 to T030 pass with no change to `app/generation/choices.py`, `app/interface/` or `app/services/`. A mixed sequence is 008's rules applied to two kinds.

**Checkpoint**: Fallbacks cross providers.

---

## Phase 6: User Story 4 - The Research tab and the checks see OpenAI (Priority: P4)

**Goal**: The Research tab names OpenAI and the reported model, its tokens, timings and reasoning
summary, or that none came back. `doctor` and "Check again" report OpenAI's key and models.

**Independent Test**: The unit tests below; quickstart § 4 and § 8 on the stack.

### Tests for User Story 4 (write first, and see them fail)

- [X] T032 [P] [US4] Tests in `tests/unit/test_interface.py`, for an answer from an OpenAI model:
  - the Research tab's model line names the reported model and "OpenAI";
  - the measures show load and prompt processing as unavailable;
  - the reasoning reads "A summary of the reasoning, as OpenAI returns it", or "None came back." when the summary was refused or absent (FR-015, FR-018).
- [X] T033 [P] [US4] Tests in `tests/unit/test_commands.py`, `doctor` with OpenAI's settings and a `FakeOpenAIClient`:
  - its rows follow Claude's;
  - a refused key is one failing row;
  - one setting alone is a failing row naming the missing one;
  - a 403 for one model fails that row only.

  The checks that run on their own after an answer make no request to the client (FR-017).

### Implementation for User Story 4

- [X] T034 [US4] Run `make test`: T032 and T033 pass with no change to `app/interface/`, `app/services/` or `app/main.py`.

**Checkpoint**: Every story is proved in the unit tests and on the real models.

---

## Phase 7: Polish & Cross-Cutting Concerns (the records, the stack)

**Purpose**: The records that make the feature done (Principle VIII), and the checks on the
stack, which delete the library.

- [X] T035 [P] Update `README.md` (FR-024, research.md R12):
  - The opening names OpenAI beside Anthropic.
  - "Cloud models" covers both providers, with everything FR-024 lists:
    - the settings, with `OPENAI_MODELS` holding models that reason;
    - what a request sends, and that it isn't stored;
    - OpenAI's data terms and where to read them: the abuse-monitoring logs, its own caching of a prompt's start, and no training unless the organization opts in, which the owner checks in OpenAI's dashboard;
    - that the reasoning may come back in another language;
    - API keys versus ChatGPT plans and their API credits;
    - verifying the organization;
    - which `config/generation.yaml` settings don't apply;
    - what `doctor` can't tell about a model;
    - the window's cap, in OpenAI's tokens if T023's ratio exceeds 1.11;
    - the integration tests.
  - "Deployment notes" and "Configuration" name the two settings, and say that changing either recreates the container, emptying the library.
- [X] T036 [P] Update `docs/decisions.md`, "Cloud models" (FR-025, research.md R12), with T023's measurements:
  - why OpenAI came through 008's structure, and what it needed (research.md R5 to R7, R9);
  - the Responses API and its arguments;
  - out of credit told from a rate limit;
  - the token estimate as measured;
  - the profile's values and what kept each;
  - what the three models wrote differently from the local models and Claude;
  - the verification error, as the owner's organization got it;
  - any model dropped, with OpenAI's reason;
  - the follow-up of Anthropic's billing error.
- [X] T037 Run `make lint-check` and `make test`, then `git diff main --stat -- app/services app/interface app/main.py tests/unit/test_anthropic_provider.py`, which lists nothing (quickstart § 1; SC-011, SC-012, FR-021).
- [X] T038 **Ask the owner before this task.** It recreates the app container, which deletes the library: *História* and every summary saved from it, Claude's included (quickstart § 0). With the owner's go, and `.env` holding OpenAI's settings, run quickstart § 3 to § 7, § 9, § 10 and § 10a, and note each outcome against its success criterion:
  - `make up`, `reset-everything`, *On Liberty* added;
  - `make test-integration` on the running stack, with the settings exported, so that SC-003 holds for the whole suite: the cloud cases on every remaining model, and the local and stack tests as on `main` (quickstart § 10a);
  - `doctor` with the right key, then a wrong key, a missing setting and an unknown model, each in its own process;
  - questions, an abstention and a Portuguese answer;
  - fallbacks across providers;
  - a summary saved and kept by `reindex-all`;
  - the key nowhere;
  - an experiment and a judge naming an OpenAI model refused.
- [ ] T039 The owner checks the tabs in the browser (quickstart § 8):
  - the choice's order;
  - a mixed sequence's notice;
  - an answer streaming from `gpt-6.2-sol`;
  - the Research tab's model, measures and reasoning, and "Check again";
  - the Summarization tab's notice.
- [X] T040 Add a "Results of the implementation" section to `specs/009-openai-provider/spec.md`, as `specs/008` has, with:
  - each success criterion's outcome, and the numbers of T023 and T038;
  - any model dropped from `OPENAI_MODELS`;
  - any correction made during implementation.

  Then quickstart § 11: the owner removes *On Liberty* and adds *História* back.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none. T001 before T013, which imports the SDK.
- **Foundational (Phase 2)**: after Setup; blocks every story. Within it:
  - the tests T004 to T007 come first; T005 needs nothing else, while T006 and T007 need T004's fakes and fixture;
  - T008 and T009 before T010, T010 before T011 to T013, T013 before T014, and T014 and T015 before T016.
- **US1 (Phase 3)**: after Phase 2. T022 before T023. T023 needs the owner's key in `.env`, and no stack.
- **US2, US3, US4 (Phases 4 to 6)**: after Phase 2, each independent of the others and of US1's T022 and T023. Their tests share files with US1's (`test_question_answering.py`, `test_commands.py`, `test_interface.py`), so the same file's tasks run one after the other.
- **Polish (Phase 7)**: after every story. T035 and T036 need T023's numbers. T038 needs the owner's go. T039 is the owner's. T040 comes last.

### Within Each User Story

Tests first, and seen to fail where they test new behavior; then the run that makes them pass. The
stories need no application code of their own: if one does, the fix goes in `app/generation/` or
`app/config/`, never in a service, a tab or a command (SC-011).

### Parallel Opportunities

- Phase 1: T002 and T003.
- Phase 2: T004 and T005 together; then T006 and T007 together, once T004 is done (not marked `[P]`, since they need it); T008 and T009.
- US1: T017 to T021, five files.
- US2: T025 and T026. US3: T028, T029 and T030. US4: T032 and T033. Each set touches its own files, except where it shares a file with another story.
- Polish: T035 and T036.

---

## Parallel Example: Phase 2

```text
Task: "T004 OpenAI's SDK fakes and the openai_client fixture in tests/fakes.py and tests/conftest.py"
Task: "T005 Tests in tests/unit/test_config.py: the effort names"
Task: "T008 Widen CloudProfile.reasoning in app/config/settings.py"
Task: "T009 Add FailureReason.OUT_OF_CREDIT in app/generation/base.py"

# then, once T004 is done:
Task: "T006 Tests in tests/unit/test_model_choices.py: settings, efforts per kind, name clashes, order, OUT_OF_CREDIT"
Task: "T007 New tests/unit/test_openai_provider.py: request, stream, stats, failures, retries, check, key"
```

## Parallel Example: User Story 1

```text
Task: "T017 ask --model with an OpenAI model in tests/unit/test_commands.py"
Task: "T018 QuestionAnsweringService with an OpenAI model in tests/unit/test_question_answering.py"
Task: "T019 The judges' client and every OpenAI client in tests/unit/test_generation_metrics.py"
Task: "T020 Experiments naming an OpenAI model in tests/unit/test_benchmark.py"
Task: "T021 No service, tab or command names OpenAI in tests/unit/test_provider_kinds.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 and Phase 2: the provider, the shared changes, `make test` green, Claude unchanged.
2. Phase 3: the questions' tests, then the real models from the host (T023). Stop here and check:
   OpenAI answers in the unit tests and on the real models, before the library is touched.

### Incremental Delivery

1. US1: questions, and the real models.
2. US2: summaries, saved and kept.
3. US3: sequences across providers.
4. US4: the Research tab and the checks.
5. Polish: the README, the decisions, then the stack, with the owner's go, and the owner's browser
   check.

Each story adds tests only. 008's interfaces carry OpenAI through every service, tab and command,
which is what SC-011 measures.

---

## Notes

- `[P]` tasks touch different files and depend on no unfinished task.
- `[Story]` maps a task to its user story, for traceability.
- The key is read into the shell only for T023 and T038; never print it, and close the shell
  afterwards.
- Commit only when the owner asks; the pull request is titled `feat: …` (v0.9.0).
- `checklists/data-sharing-and-model-output.md` is resolved; its four owner defaults stand unless
  the owner says otherwise.
