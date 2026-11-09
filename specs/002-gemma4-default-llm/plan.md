# Implementation Plan: Choosing the default LLM by measurement

**Branch**: `feat/gemma4-default-llm` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-gemma4-default-llm/spec.md`

## Summary

The default LLM is chosen by the rule the spec fixed before any run, FR-002: it switches to
gemma4:12b only if five conditions hold in a confirmation, and otherwise stays gpt-oss:20b. The
plan builds what the confirmation needs, then runs it, and then ships whichever outcome the rule
gives.

- **Before the runs**, nothing in `app/` or `config/` changes:
  - two experiment files, each with only the two models and the earlier runs' judge;
  - one development script, `devtools/default_llm.py`, that:
    - checks the versions before each run;
    - runs the summarization confirmation while it records every whole prompt;
    - probes what the benchmark doesn't cover;
    - prepares the reading;
    - applies the rule.
- **The runs**: in the `app` container, on the benchmark workspace the earlier runs used, so the
  retrieved passages are the same ([research](research.md) R3).
- **Only on a switch**:
  - `llm.model` becomes gemma4:12b;
  - LLM profiles gain a required `exact_token_count`, outside the index fingerprint (R9);
  - the token-count integration test checks every pulled model against its profile;
  - the judge's download through `pull-models --all` becomes a checked, documented step (R10).
- **Either way**: `docs/decisions.md` and `docs/benchmark-results.md` record the default and its
  reason.

Planning found three errors in the spec's facts, and corrected them before any run, as FR-001
allows (R1):
- the benchmark has 15 multi-section questions, not 13;
- the novel's coverage was measured once on today's key points, not twice;
- FR-016 would have deleted the confirmation's tooling on a "keep".

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed by uv

**Primary Dependencies**: the application's own: `app.evaluation` (the runner, `paired_difference`
and `dataset_checksum`), `app.container.assemble`, and the question-answering and summary
services. Ollama 0.40.15, pinned by digest. No new dependency.

**Storage**: none in the application. The confirmation writes result directories under
`benchmarks/results/`, which stay out of git. It also writes `reading.yaml` and `verdict.md` in this
feature's directory, which are committed. The benchmark workspace is read, not changed.

**Testing**:
- `make test`, with a new `tests/unit/test_default_llm_devtool.py` for the rule's arithmetic, the
  recorder and `reading.yaml`;
- the runs themselves, for the parts that need the stack;
- on a switch, `make test-integration`, which is condition (e).

**Target Platform**: Linux, the `app` container of the Docker Compose stack. RTX 5060 Ti with 16 GB,
Ryzen 9 9950X3D, 60 GB of RAM, as in the earlier runs.

**Project Type**: a single Python application, with its benchmarks and development scripts

**Performance Goals**: none for the application. The machine time is about 2 h for generation,
25 min for summarization and 20 min for the probe (R13).

**Constraints**:
- No change to `app/` or `config/` before the runs (FR-004).
- No change to prompts, output parsing, the judge or `benchmark-report`.
- Nothing joins the index fingerprint or the workspace key.
- The probe writes nothing to the library or the workspace.
- One confirmation run of each kind.

**Scale/Scope**:
- 2 models;
- 90 questions and 6 chapters per run;
- 15 multi-section pairs and about 10 summaries to read;
- 136 probe replies and summaries;
- on a switch, 4 LLM profiles and 1 integration test.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --- | --- | --- | --- |
| I. Local-first, model-independent | All inference is local, the judge included. Model names appear only in configuration and experiments. What differs between models is a profile setting, validated at startup | Pass | Pass: `exact_token_count` is a required `LLMProfile` field. The integration test reads it instead of a model name. The development script takes model names from the experiment files |
| II. The library is never at risk | No change to books, catalog or index. Benchmarks and probes stay in `benchmarks/workspace` and the `bench_*` collections | Pass | Pass: the runs use the runner as it is. The probe builds the workspace's container and only asks and summarizes, never saving. No step runs `docker compose down -v` |
| III. Index integrity | No change to the embedding model, chunking or anything in the fingerprint. No reindex | Pass | Pass: the new field is on `LLMProfile`, which neither `current_configuration()` nor `index_key()` reads. Putting it on `TokenizerConfig` was rejected for that reason (R9) |
| IV. One service layer | No business logic in `app/main.py` or `app/interface` | Pass | Pass: neither changes. `pull-models` stays as it is (R10). The probe calls the services |
| V. Verified on real models and books | No prompt, parser or judge change. A model switch is checked on the real models | Pass | Pass: the confirmation and the probe run the real models, and `make test-integration` with gemma4 configured is condition (e). Ingestion is untouched |
| VI. Measured, not assumed | The baseline is `gpt_oss_20b`, the rule's metrics are named, and only intervals that exclude zero count. Outputs are read before concluding. The judge is unchanged | Pass | Pass: the rule is applied by code committed before the runs, using `paired_difference` with the report's seed. Preflight checks digests, Ollama and the dataset. The workspace is valid, since ingestion code is unchanged (R3). Results record environment, `complete` and commit |
| VII. Every answer traceable | Answers and summaries are made as today, and the no-evidence path is checked | Pass | Pass: citation accuracy and abstention quality are gated in (a). The probe counts abstentions the application doesn't show as such, in four languages, and the trap |
| VIII. Decisions are recorded | README, `docs/decisions.md` and `docs/benchmark-results.md` are planned. `docs/decisions.md` was read first | Pass | Pass: it records no reason for the first default, and `.TASK/task.md` § 3.1 gives it, as the spec says. The records are planned for both outcomes |
| Development workflow | uv, ruff, `make test`, branch `feat/…`, conventional commits, PR title by outcome | Pass | Pass: the dataset is unchanged, so no `validate-benchmark`. The PR is `feat:` on a switch and `docs:` on a "keep" (R13) |

No violation, so Complexity Tracking stays empty.

`AGENTS.md`'s extra steps (`/speckit-clarify`, `/speckit-checklist`, `/speckit-analyze`) don't
apply. The feature touches no lifecycle, journal, fingerprint, prompt, citation parsing, judge or
metric: seconds and steps are paired by the development script, and `benchmark-report` stays as
it is (R12).

## Project Structure

### Documentation (this feature)

```text
specs/002-gemma4-default-llm/
├── spec.md              # The rule, fixed before the runs (corrected during planning)
├── plan.md              # This file
├── research.md          # Phase 0: facts re-checked, workspace, preflight, prompts, probe, rule
├── data-model.md        # Phase 1: the records, the new profile field, how the decision moves
├── quickstart.md        # Phase 1: the run sequence, step by step
├── contracts/
│   ├── configuration.md # The two experiments, exact_token_count, llm.model
│   ├── devtool.md       # devtools/default_llm.py: its five subcommands
│   └── records.md       # prompts.jsonl, probe.jsonl, reading.yaml, verdict.md
├── checklists/
│   └── requirements.md  # From /speckit-specify
├── reading.yaml         # Written during the reading, committed
├── verdict.md           # Written by the verdict subcommand, committed
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
# Before the runs: measuring only
benchmarks/experiments/default_llm_generation.yaml     # two variants, the generation judge
benchmarks/experiments/default_llm_summarization.yaml  # two variants, the summarization judge
devtools/default_llm.py                                # preflight, summarize, probe, packets, verdict
tests/unit/test_default_llm_devtool.py                 # the rule, the recorder, reading.yaml, the judge blocks

# Only on a switch
config/models.yaml                    # llm.model: gemma4:12b; exact_token_count in each LLM profile
app/config/settings.py                # LLMProfile.exact_token_count, required
app/utils/ollama_runtime.py           # the missing-model message mentions pull-models --all
tests/integration/test_generation.py  # the token-count test, once per pulled profile
tests/unit/test_benchmark.py          # every experiment's judge has a profile
tests/unit/test_llm_provider.py       # LLMProfile built with the new field
README.md                             # the default and its reason, its token counts, the judge's download

# Either way
docs/decisions.md                     # the default, the rule, the first default's reason
docs/benchmark-results.md             # the confirmation, the reading, the probe, labels, Recommendations
```

**Structure Decision**: the confirmation's tooling lives in one development script, as the
historical spelling measurement did (`devtools/measure_historical_spelling.py`). It isn't in
`app/`, so on a "keep" the application is unchanged (FR-016), and the tooling stays as the record of
how the numbers were made. It runs in the `app` container by piping it to the container's Python,
because `devtools/` is neither in the image nor mounted (R8). A switch touches only where the
default and the profiles already live.

## Complexity Tracking

No violations.
