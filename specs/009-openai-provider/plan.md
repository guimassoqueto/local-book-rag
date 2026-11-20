# Implementation Plan: OpenAI models for chat and summaries, opt-in

**Branch**: `feat/openai-provider` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-openai-provider/spec.md`

## Summary

OpenAI's models that reason join Claude's as cloud models that the user picks per request, through
the structure that `specs/008` built. Without the two new settings, nothing changes:
- **Configuration.** `OPENAI_API_KEY` and `OPENAI_MODELS` in `.env`, passed to the app container,
  read as Anthropic's are. One profile, `cloud_profiles.openai`: `o200k_base`, a 64K window,
  effort `low`, 4,000 tokens of reasoning room, 120 s of silence (R6, R8).
- **The provider.** `OpenAICloud` and `OpenAILLMProvider` in `app/generation/openai_provider.py`,
  registered in `CLOUD_PROVIDERS` after Anthropic. Each request goes to OpenAI's Responses API,
  streamed, with the prompt's messages, a token limit, the effort and a reasoning summary, and
  nothing else: not stored, no tools, no sampling settings (R1, R2). The stream is read into the
  same text, reasoning and stats as Claude's (R3), and every failure maps to 008's reasons (R4).
- **Shared changes that serve every provider** (FR-022): a new reason, out of credit (R5); each
  provider kind names the efforts it takes, checked at startup (R6); a name that two providers
  allow, or that is the local model's, stops the app (R7); the retry waits move to one shared
  place (R9).
- **Nothing above `app/generation` changes**: the services, the tabs and the commands reach
  OpenAI through 008's interfaces, its label and its reasons (SC-011).
- **Records.** `README.md` and `docs/decisions.md` (R12).

**How.**
- **The real models first.** The integration tests run the three allowed models from the host,
  before the stack is recreated, and record how close the token estimate is (R11, R13).
- **The key stays with the provider**: the client gets the key and OpenAI's address explicitly,
  and the judges' client of OpenAI's library keeps pointing at Ollama (R10).

`research.md` holds the 13 decisions behind this.

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed with uv.

**Primary Dependencies**:
- **Added as a direct dependency**: `openai`, OpenAI's official SDK for Python, already locked at
  3.3.0 through RAGAS, with `uv add --raw openai`. It reaches the Responses API, streamed, the
  Models API and typed errors.
- **Unchanged**: `anthropic`, Gradio, pydantic and pydantic-settings, tiktoken, Ollama's client
  with LlamaIndex, RAGAS.

**Storage**: Unchanged. A saved summary from an OpenAI model records `provider: openai`, in 008's
layout. No volume and no mount.

**Testing**: pytest.
- `make test`: one new test file, `tests/unit/test_openai_provider.py`. `tests/fakes.py` gains
  OpenAI's SDK as the provider reads it, and `tests/conftest.py` a fixture that gives the
  container a fake client. Ten test files gain cases: `test_config.py`, `test_model_choices.py`,
  `test_generation_metrics.py`, `test_benchmark.py`, `test_provider_kinds.py`,
  `test_commands.py`, `test_question_answering.py`, `test_summarization.py`,
  `test_library_rebuild.py` and `test_interface.py`. `test_anthropic_provider.py` passes unchanged
  (R11).
- `make test-integration`: `tests/integration/test_cloud_generation.py` runs every implemented
  provider whose settings are exported, each skipped on its own otherwise; it spends a few cents
  per model. It runs first alone from the host, before the stack is touched, then with the whole
  suite on the stack (`quickstart.md` § 2, § 10a).
- On the stack: `quickstart.md`.

**Target Platform**: The Docker Compose stack on the owner's Linux machine, as for 008: the app
container reaches `api.openai.com` over HTTPS for a request that picked an OpenAI model or a check
the owner asked for, and at no other time. It runs v0.8.0 now, with the owner's *História* as
`book_001`.

**Project Type**: A single Python application: a Gradio interface and the `book-rag` commands, over
one service layer.

**Performance Goals**:
- **The local model and Claude**: no added work beyond the startup checks of R6 and R7, and no
  request to OpenAI.
- **An OpenAI answer** streams from the first text delta.
- **A failure** costs at most the profile's 120 s of silence, waited once, or the retries' 2 and 6
  seconds; an exhausted account or a refused stream fails at once.

**Constraints**:
- **Local by default**, and nothing goes to OpenAI without a choice; a check sends the key and the
  allowed models' names (FR-012, FR-017).
- **A request is not stored at OpenAI and enables no tool** (FR-012).
- **The key is never written** anywhere, and only OpenAI's provider holds it (FR-004, FR-020).
- **The same search and prompts** for every model (FR-008, FR-021).
- **No change to the services, the tabs or the commands** (FR-022, SC-011).
- **Claude unchanged**, the retry helper's move included (FR-021).
- **The history stays untouched**: `specs/001` to `specs/008` (FR-027).
- **The release**: a `feat:` title, so v0.9.0 unless another release comes first.

**Scale/Scope**:
- **New modules**: `app/generation/openai_provider.py`.
- **Changed modules**: `app/generation/cloud.py`, `app/generation/anthropic_provider.py` (the
  retry helper's move, `efforts`), `app/generation/base.py` (`OUT_OF_CREDIT`),
  `app/generation/factory.py` (efforts and names checked), `app/config/settings.py` (the efforts'
  names), `app/container.py` (registration).
- **Configuration and deployment**: `config/models.yaml`, `docker-compose.yml`,
  `devtools/.env.sample`, `pyproject.toml` and `uv.lock`.
- **Records**: `README.md` and `docs/decisions.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --------- | ----- | --------------- | ------------ |
| I. Local-first and model-independent | Nothing goes to OpenAI unless the user put one of its models in the request's sequence, and then only the prompt's messages: the question and its passages, or the chapter and what was made from it (FR-012). The request asks OpenAI not to store it, and enables no tool; it sends no identifier, metadata or sampling setting (R2). The one other contact is a check the user asks for, which sends the key and the names (FR-017). Embeddings, reranking, benchmarks and judges stay local: the benchmarks build Ollama providers only and refuse an OpenAI name before they run (FR-019), and the judges' client of OpenAI's library keeps Ollama's address and its own key (FR-020, R10). Without the settings, the app works as on `main` (FR-002, SC-001). The key lives in a `SecretStr`, reaches only the SDK's client, which gets OpenAI's address explicitly, and no error carries the SDK's request or OpenAI's message (R4, R10). The models are named only in `OPENAI_MODELS`; OpenAI has one profile, validated at startup, whose effort must be one OpenAI names (R6). What differs between OpenAI's models is nothing: the profile serves the models that reason (Clarifications). The class is named only in `app/container.py`. No code names or branches on a model. | Pass | Pass: `contracts/configuration.md`, `contracts/providers.md`; R2, R4, R6, R8, R10. |
| II. The library is never at risk | No operation on the books, the catalog or the index changes. Setting `.env` recreates the app container at `make up`, which empties the library: the README says so (FR-024), and `quickstart.md` § 0 and § 3 say it before the command, *História* named. The paid checks run first, from the host, so that the library is emptied only once they pass (R13). No volume or mount. No benchmark code changes. | Pass | Pass: `quickstart.md`, § 0, § 2, § 3, § 11; R13. |
| III. Index integrity | No embedding or chunking setting, template, index tokenizer or metadata field changes; the profile's tokenizer counts prompts only. No reindex (FR-021). | Pass | Pass: `data-model.md`, Unchanged. |
| IV. One service layer | No rule moves into a tab or a command; none of them changes (SC-011). The new rules live in the factory (efforts, names) and the provider (failures, retries); the services keep the sequences' rules (FR-028). | Pass | Pass: `contracts/providers.md`; R5, R6, R7. |
| V. Verified on real models and real books | A new reader of model output, the provider's reading of OpenAI's stream, terminal states and errors, runs on the three real models through the integration tests, from the host, before the stack is touched: `gpt-6-luna`, `gpt-6.1-terra` and `gpt-6.2-sol` (FR-026, SC-003). Expected: citations that resolve, in `[n]` or a form the app already normalizes; the marker, or abstentions in words caught by the reply check once turned on; a summary cited by lookup; a reasoning summary or none. The prompts, the judges and ingestion don't change, so no book or benchmark runs beyond the quickstart's checks on *On Liberty*. Every long call goes through a provider in `app/generation`, fitted to the profile's window first; `truncation: disabled` makes OpenAI refuse what doesn't fit instead of cutting it (R2). No OpenAI-compatible endpoint of Ollama's is used (FR-023). | Pass | Pass: `quickstart.md` § 2, § 5 to § 8; R1 to R4, R11. |
| VI. Measured, not assumed | No gain in quality or speed is claimed, and no default changes: the local model stays the default. No benchmark has anything to decide, and none runs. No judge or metric changes. The token estimate, assumed close, is measured on the real models and recorded (SC-009). | Pass | Pass: R6, R11. |
| VII. Every answer traceable to its passages | An OpenAI answer is read by the same code as every other: citations resolved, invented ones reported, the marker shown as an abstention, the reply check when the profile asks (FR-008). A summary cites by lookup (FR-009). No tool is enabled, so the reply can come from the passages only (FR-012). Every answer and summary records the model OpenAI reported and the failures before it (FR-013). For OpenAI, the integration tests and the quickstart check the citations and the abstentions (SC-003); the generation benchmark still watches the local model. | Pass | Pass: `contracts/providers.md`; R2, R3, R11. |
| VIII. Decisions are recorded | Tasks update `README.md` (its opening, "Cloud models", Deployment notes, Configuration) and `docs/decisions.md` ("Cloud models": FR-025's decisions and the measurements). `docs/decisions.md` was read first: its Ollama OpenAI-compatible endpoint entry is why the provider uses OpenAI's own API; its Claude entries (no server-side fallbacks, no temperature, 120 s once, the approximate tokenizer) are kept for OpenAI. The delivered specs aren't edited. | Pass | Pass: R12. |

No violation: Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/009-openai-provider/
├── spec.md
├── plan.md                 # this file
├── research.md             # R1–R13
├── data-model.md           # settings, profile, kinds' efforts, startup rules, out of credit, records
├── quickstart.md           # tests, the real models before the stack, the stack, every story, the key
├── contracts/
│   ├── configuration.md    # .env, Compose, cloud_profiles.openai, what startup does
│   └── providers.md        # CloudProvider.efforts, the shared waits, the OpenAI provider, what the user sees
├── checklists/
│   └── requirements.md
└── tasks.md                # /speckit-tasks
```

### Source Code (repository root)

```text
app/
├── config/settings.py          # CloudProfile.reasoning takes every provider's effort names (R6)
├── container.py                # CLOUD_PROVIDERS gains "openai": OpenAICloud (R8)
└── generation/
    ├── base.py                 # FailureReason.OUT_OF_CREDIT and its words (R5)
    ├── cloud.py                # CloudProvider.efforts; RETRY_WAITS, RETRIED, retry_wait() (R6, R9)
    ├── anthropic_provider.py   # efforts; calls the shared retry_wait(), behavior unchanged (R9)
    ├── openai_provider.py      # new: OpenAICloud and OpenAILLMProvider (R1 to R4, R10)
    └── factory.py              # each profile's effort checked against its kind; names allowed twice, or the local model's, refused (R6, R7)

config/models.yaml              # cloud_profiles.openai
docker-compose.yml              # OPENAI_API_KEY, OPENAI_MODELS
devtools/.env.sample            # the two settings, empty, explained
pyproject.toml, uv.lock         # openai, direct

tests/
├── fakes.py                    # OpenAI's SDK as the provider reads it: events, responses, errors, a model; FakeCloud.efforts
├── conftest.py                 # the openai_client fixture: the container's provider gets a FakeOpenAIClient
├── unit/
│   ├── test_openai_provider.py      # new: request, stream, stats, terminal states, failures, retries, check, the key
│   ├── test_config.py               # the efforts' names
│   ├── test_model_choices.py        # OpenAI's settings; efforts per kind; names offered twice or the local model's; order; mixed sequences
│   ├── test_generation_metrics.py   # the judges' client with OPENAI_API_KEY and OPENAI_BASE_URL set; every OpenAI client given a key and an address (SC-008)
│   ├── test_benchmark.py            # an experiment or a judge naming an OpenAI model refused (FR-019)
│   ├── test_provider_kinds.py       # no service, tab or command names OpenAI (SC-011); no OpenAI model named in app/
│   ├── test_commands.py             # ask --model and doctor with OpenAI
│   ├── test_question_answering.py   # answers, declines and mixed fallbacks through the service
│   ├── test_summarization.py        # summaries from OpenAI, and a step that fails
│   ├── test_library_rebuild.py      # reindex-all keeps an OpenAI summary
│   ├── test_interface.py            # mixed notices; the Research tab for an OpenAI answer
│   └── test_anthropic_provider.py   # unchanged, passing after R9
└── integration/
    └── test_cloud_generation.py     # every provider whose settings are exported, each model; token ratios printed

README.md, docs/decisions.md
```

**Structure Decision**: The existing application. The provider goes beside Anthropic's, in
`app/generation`, behind 008's interfaces. No new service, tab or command: the change stops at
`app/generation`, `app/config` and the container's registration.

## Complexity Tracking

None.
