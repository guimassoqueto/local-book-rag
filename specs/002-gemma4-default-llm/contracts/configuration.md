# Contract: configuration

What this feature adds to the files the application and the benchmarks read. Both are validated
at startup, or when an experiment loads: an unknown key is an error.

## The confirmation experiments (before the runs)

`benchmarks/experiments/default_llm_generation.yaml`:

```yaml
name: default_llm_generation
kind: generation
description: >-
  Confirms the comparison of gpt-oss:20b and gemma4:12b before choosing the default LLM
  (specs/002-gemma4-default-llm), on identical retrieved contexts, with gpt-oss:20b judging.

judge:                       # the same block as generation.yaml, byte for byte
  model: gpt-oss:20b
  embedding_model: qwen3-embedding:0.6b
  max_tokens: 6000
  reasoning: low

variants:
  - name: gpt_oss_20b
    overrides:
      llm: {model: "gpt-oss:20b"}

  - name: gemma4_12b
    overrides:
      llm: {model: "gemma4:12b"}
```

`benchmarks/experiments/default_llm_summarization.yaml` is the same, with `kind: summarization`
and the judge block of `summarization.yaml` (`reasoning: medium`).

**Guarantees**:
- **The variant names match the earlier runs'**, so `benchmark-report --baseline gpt_oss_20b`
  pairs them, and rows compare by name.
- **Each judge block equals its source experiment's.** A unit test compares them, so the two
  can't drift.

## `exact_token_count` (on a switch only)

`config/models.yaml`, in every entry of `llm_profiles`:

```yaml
llm_profiles:
  gpt-oss:20b:
    tokenizer:
      kind: tiktoken
      name: o200k_harmony
    # Probe B: 1.000 against Ollama's count on every chunk.
    exact_token_count: true
    reasoning: low

  gemma4:12b:
    tokenizer:
      kind: tiktoken
      name: o200k_base
    # An approximation: 0.941 to 1.043 of Ollama's count on 24 chunks, which
    # generation.context.safety_margin absorbs.
    exact_token_count: false
    reasoning: false
```

**Rules**:
- **Required in every LLM profile**: a profile without it stops the app at startup, naming the
  model. No default (research R9).
- **A boolean**: true means the estimate matches Ollama's count within 2 tokens, on the
  integration test's text, net of a one-character prompt.
- **Not in `embedding_profiles`**, and not in `TokenizerConfig`, so the index fingerprint and every
  workspace key stay as they are (constitution III, FR-017).
- **Read by the integration test only**, which holds an exact profile to 2 tokens and an
  approximate one to `generation.context.safety_margin` of the measured count. The application's
  behavior doesn't change.

## `llm.model` (on a switch only)

```yaml
llm:
  provider: ollama
  model: gemma4:12b
```

Every other setting stays as it is: `context_size`, `temperature` and `max_tokens`, the task
overrides in `generation.yaml`, gemma4's profile, and the experiments' judge (FR-009).
