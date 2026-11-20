# Implementation Plan: Cloud models for chat and summaries, opt-in

**Branch**: `feat/cloud-llm-providers` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-cloud-llm-providers/spec.md`

## Summary

Answers and summaries can come from a Claude model that the user picks for a request, with
fallbacks that the user orders and the local model last. Without the two new settings, nothing
changes:
- **Configuration.** `ANTHROPIC_API_KEY` and `ANTHROPIC_MODELS` in `.env`, passed to the app's
  container, and read into their own object, away from everything that records the configuration
  (R1). One profile per provider in `config/models.yaml`, `cloud_profiles.anthropic` (R2).
- **Providers.** `LLMProvider` gains `provider` and `check_abstentions`. A new provider kind,
  `CloudProvider`, builds a model's provider and checks its key. The Anthropic provider streams
  through Anthropic's SDK, with adaptive reasoning at the profile's effort and no sampling
  settings, and maps every failure to a reason (R3, R4, R5).
- **Choices.** `ModelChoices` lists the models offered, and turns a picked model and its fallbacks
  into a sequence that ends with the local model, refusing what the rules don't allow (R6).
- **Services.** `QuestionAnsweringService` searches once, then tries each model of the sequence
  until one answers, yielding `AttemptFailed` between them (R7). `ChapterSummarizer` makes the
  whole summary with each model in turn (R8). `reindex-all` leaves a cloud summary as it was
  (R11). `HealthService` contacts a provider only for `doctor` and "Check again" (R12).
- **The interface and the commands.** Each tab gets its own model choice, fallbacks and notice;
  the Research tab names the model that answered and the ones that failed; `ask` and `summarize`
  take `--model` and `--fallback` (R9, R13, R14).
- **Records.** `README.md` and `docs/decisions.md` (R17).

**How.**
- **Nothing local changes.** The local model is built as today, the search runs as today, and the
  prompts don't change. The benchmarks build Ollama providers only, as today, and refuse a cloud
  model before they run (R15).
- **Checked on the real models.** The integration tests run a Claude model for real when the
  settings are there, and `quickstart.md` checks every story on the stack (R16, R18).

`research.md` holds the 18 decisions behind this.

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed with uv.

**Primary Dependencies**:
- **Added**: `anthropic`, Anthropic's official SDK for Python, whose 1.x line runs on `httpx2`,
  with `uv add --raw anthropic`. It reaches the Claude API: streaming messages, the Models API,
  typed errors.
- **Unchanged**: Gradio, pydantic and pydantic-settings, tiktoken, and Ollama's client with
  LlamaIndex for the local model.

**Storage**:
- **A saved summary's JSON file**: `provider` and `failed_attempts` always, and `tokens` for a
  cloud model's (R10). The Markdown file doesn't change.
- **The catalog, ChromaDB, the processed documents and the index**: unchanged (FR-028).
- **No volume and no mount**, as today.

**Testing**: pytest.
- `make test`: two new test files, `test_anthropic_provider.py` and `test_model_choices.py`, and
  eleven changed (R16), on fakes, real files, real SQLite and embedded ChromaDB, as today.
- `make test-integration`: `tests/integration/test_cloud_generation.py` runs a Claude model for
  real when both settings are exported, and is skipped otherwise. It spends a few cents.
- On the stack: `quickstart.md`.

**Target Platform**: The Docker Compose stack on the owner's Linux machine:
- an RTX 5060 Ti with 16 GB, `gpt-oss:20b` as the local model, `qwen3-embedding:0.6b` and
  Qwen3-Reranker-0.6B, as `config/models.yaml` sets them;
- the app container reaches `api.anthropic.com` over HTTPS, for a request that picked a Claude
  model or a check that the owner asked for, and at no other time;
- today's app container runs v0.7.0's image, with an empty library.

**Project Type**: A single Python application: a Gradio interface and the `book-rag` commands, over
one service layer.

**Performance Goals**:
- **The local model**: no added work beyond building the choices at startup, and no request to a
  provider.
- **A cloud answer** streams from Claude's first delta, as a local one streams from Ollama's.
- **A failure** costs the provider's time to fail, at most the profile's 120 s of silence and the
  SDK's two retries, before the next model starts.

**Constraints**:
- **Local by default**: every page load, command and regeneration uses the local model unless a
  cloud model is picked (FR-006 to FR-009, FR-023).
- **Nothing goes to a provider without a choice**, and a check sends the key alone (FR-015,
  FR-021).
- **The key is never written** to the logs, the library, a result, the interface or a message
  (FR-004).
- **The same search and the same prompts** for every model (FR-011, FR-028).
- **Benchmarks and judges stay local** (FR-027).
- **No change to the index, its fingerprint or the catalog**, and no reindex (FR-028).
- **The history stays untouched**: `specs/001` to `specs/007` (FR-031).
- **The release**: a `feat:` title, so v0.8.0 unless another release comes first.

**Scale/Scope**:
- **New modules**: `app/generation/cloud.py`, `app/generation/anthropic_provider.py`,
  `app/generation/choices.py` and `app/interface/model_choice.py`.
- **Changed modules**: seventeen, in `app/config`, `app/generation`, `app/services`,
  `app/interface`, `app/evaluation` (one line) and `app/main.py`, with `app/errors.py` and
  `app/container.py`.
- **Configuration and deployment**: `config/models.yaml`, `docker-compose.yml`,
  `devtools/.env.sample`, `pyproject.toml` and `uv.lock`.
- **Records**: `README.md` and `docs/decisions.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --------- | ----- | --------------- | ------------ |
| I. Local-first and model-independent | The plan sends nothing to a provider unless the user picked one of its models for the request, and then only the question and its passages, or the chapter and what was made from it; the one other contact is a check the user asks for, which sends the key alone (FR-015, FR-021). Embeddings, reranking, benchmarks and judges stay on local models: the benchmarks build Ollama providers only, and refuse a cloud model's name before they run (FR-027). Without the settings, the app works as if the provider didn't exist (FR-002, SC-001). The key lives in a `SecretStr`, apart from `Settings` and `EnvironmentSettings`, and no log, result or message holds it (FR-004). A local model stays named in `config/models.yaml` with its profile; a cloud model is named only in its provider's allow-list, and its provider has one profile, `cloud_profiles.anthropic`, validated at startup with the rest of `config/`. What differs between models is a profile setting: effort, reasoning room, window, timeout. What differs between providers lives in each provider's class, behind `LLMProvider` and `CloudProvider`, and `app/container.py` and the factory are the only places that know the concrete classes. No code names or branches on a model. | Pass | Pass: `contracts/configuration.md`, `contracts/providers.md`; R1 to R6, R12, R15. |
| II. The library is never at risk | No new operation on the books, the catalog or the index. `reindex-all` only skips writing again the summaries that a cloud model wrote, inside its journaled operation, and deletes nothing new (FR-023). A saved summary's JSON file gains keys, written as today. No volume or mount. Setting `.env` recreates the app container at `make up`, and the README says that this empties the library (FR-029). The quickstart's `make up` recreates it too, and says before each command what that deletes; `reset-everything`, confirmed in the service with `DELETE EVERYTHING`, then clears ChromaDB's old collections, as in `specs/007`. No benchmark code changes, so it still reaches nothing beyond `benchmarks/workspace` and the `bench_*` collections. | Pass | Pass: `quickstart.md`, § 0, § 2, § 3, § 14; R11, R18. |
| III. Index integrity | No embedding or chunking setting, document template, tokenizer of the index, or metadata field changes; a cloud profile's tokenizer counts a prompt's tokens only. The fingerprint stays, and no reindex is needed (FR-028). | Pass | Pass: `data-model.md`, Unchanged. |
| IV. One service layer | Every rule is in a service or in `ModelChoices`, which the services call: what is offered, a sequence's rules and refusals, the move to the next model, regeneration's skipping, the provider checks (FR-032). The tabs and the commands read the choice, pass names, and show what comes back. | Pass | Pass: `contracts/services.md`, `contracts/interface.md`. |
| V. Verified on real models and real books | A new parser of model output, the Anthropic provider's reading of Claude's stream and stop reasons, runs on the real Claude models through `make test-integration`, on the first allowed model (`claude-haiku-5-5` in the quickstart), with `claude-sonnet-5-5` checked on the stack. Expected: citations as `[n]` that resolve, the no-evidence marker as the app's, readable reasoning. The prompts, the judges and ingestion don't change, so no book or benchmark needs a run beyond the quickstart's functional checks on *On Liberty*. Every call that can be long goes through a provider in `app/generation`, with prompts fitted to its window first, and no OpenAI-compatible endpoint. | Pass | Pass: `quickstart.md`, § 5 to § 8, § 13; R4, R5, R16. |
| VI. Measured, not assumed | No improvement in quality or speed is claimed, and no default changes: the local model stays the default for every request. So no benchmark has anything to decide, and none runs. No judge or metric changes. Benchmarks keep recording what they record, and run local models only, which keeps them reproducible. | Pass | Pass: R15. |
| VII. Every answer traceable to its passages | A cloud answer is read by the same code as a local one: numbered citations resolved to book, chapter and section, invented ones reported, the no-evidence marker shown as an abstention (FR-011). A cloud summary cites by lookup and counts its uncited statements (FR-012). Every answer and summary records the model that wrote it and the ones that failed (FR-016, FR-022). The generation benchmark is unchanged, so its citation accuracy and abstention quality still watch the local model; for Claude, the integration tests and the quickstart check the citations and the abstention (SC-003). | Pass | Pass: `contracts/services.md`; R7, R8, R10. |
| VIII. Decisions are recorded | Tasks update `README.md` (its opening, a "Cloud models" section, the Interface, Questions, Summaries, Configuration, Deployment notes and Layout sections) and `docs/decisions.md` (a "Cloud models" section with FR-030's decisions and what the real models showed). `docs/decisions.md` was read first: its Ollama OpenAI-compatible endpoint entry is why the provider uses Anthropic's own SDK; its `gpt-oss` citation and abstention entries are why the reading of replies stays shared and checked on the real models. The delivered specs aren't edited. | Pass | Pass: R17. |

No violation: Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/008-cloud-llm-providers/
├── spec.md
├── plan.md                 # this file
├── research.md             # R1–R18
├── data-model.md           # credentials, profile, choices, sequence, failures, records, checks, logs
├── quickstart.md           # tests, the stack without and with the settings, every story, the key
├── contracts/
│   ├── configuration.md    # .env, Compose, cloud_profiles, what startup does
│   ├── providers.md        # LLMProvider, CloudProvider, ModelChoices, the Anthropic mapping
│   ├── services.md         # the services' signatures, events and errors
│   └── interface.md        # the tabs and the commands
├── checklists/
│   └── requirements.md
└── tasks.md                # /speckit-tasks
```

### Source Code (repository root)

```text
app/
├── config/settings.py          # CloudProfile, cloud_profiles and its rule; ProviderCredentials and their reading (R1, R2)
├── errors.py                   # ModelChoiceError, ModelFailedError, AllModelsFailedError
├── container.py                # builds the cloud providers and the choices; Container.models
├── generation/
│   ├── base.py                 # LLMProvider.provider and .check_abstentions; Generation.thinking_summarized; optional stats; FailureReason, Attempt, AttemptFailed
│   ├── cloud.py                # new: CloudProvider, ProviderCheck
│   ├── anthropic_provider.py   # new: the Anthropic kind and its models' provider (R4)
│   ├── choices.py              # new: ModelOption, ModelChoices (R6)
│   ├── factory.py              # create_cloud_providers()
│   ├── ollama_provider.py      # provider, check_abstentions
│   ├── question_answering.py   # the sequence of an answer; check_abstention() reads the provider (R7)
│   └── summarization.py        # the sequence of a summary; the run carries its model; tokens (R8)
├── services/
│   ├── library_service.py      # regeneration keeps a cloud summary; summaries_kept (R11)
│   └── health_service.py       # run(providers=...) (R12)
├── interface/
│   ├── model_choice.py         # new: each tab's model, fallbacks and notice (R13)
│   ├── chat.py                 # the choice; AttemptFailed empties the answer; the status line
│   ├── summarization.py        # the choice; failures in the progress; the report
│   ├── diagnostics.py          # the answer's model; failures; unavailable measures; "Check again"
│   ├── library.py              # the summaries kept
│   └── formatting.py           # the rows and lines above
├── evaluation/benchmark.py     # one call, for check_abstention()'s new signature (R15)
└── main.py                     # --model and --fallback; doctor; reindex-all; pull-models warms cloud tokenizers (R14)

config/models.yaml              # cloud_profiles.anthropic
docker-compose.yml              # the app's two settings
devtools/.env.sample            # the two settings, empty, explained
pyproject.toml, uv.lock         # anthropic

tests/
├── fakes.py                    # FakeLLM's provider, flag and failures; FakeCloud, a second provider
├── unit/
│   ├── test_anthropic_provider.py   # new: the request, the stream, the stats, stop reasons, errors
│   ├── test_model_choices.py        # new: options, sequences, refusals, checks, settings
│   ├── test_config.py, test_question_answering.py, test_summarization.py, test_library_rebuild.py,
│   ├── test_health_service.py, test_interface.py, test_commands.py, test_container.py,
│   └── test_logging.py, test_llm_provider.py, test_benchmark.py
└── integration/test_cloud_generation.py   # new: a Claude model for real, skipped without the settings

README.md, docs/decisions.md
```

**Structure Decision**: The existing application. The new provider and the choices go with the
other providers, in `app/generation`, where the services that use them already are. The tabs'
shared component goes beside the tabs. No new command and no new service: `ask`, `summarize`,
`doctor` and `reindex-all` grow options and lines, and the existing services grow arguments.

## Complexity Tracking

None.
