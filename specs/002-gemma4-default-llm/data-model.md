# Data Model: Choosing the default LLM by measurement

Phase 1 of the plan. Nothing here is stored by the application: the books, catalog and index are
untouched. These are the records the confirmation writes, the one setting a switch adds, and how
the decision moves from rule to verdict. The exact formats are in
[contracts/records.md](contracts/records.md) and
[contracts/configuration.md](contracts/configuration.md).

## Entities

### Confirmation experiment

Two files in `benchmarks/experiments/`, `default_llm_generation` and `default_llm_summarization`.

- **name**: the file's stem. It names the results directory, `<name>_<stamp>`.
- **kind**: `generation` or `summarization`.
- **judge**: the same block as in `generation.yaml` or `summarization.yaml`, unchanged:
  - `model`: gpt-oss:20b;
  - `embedding_model`: qwen3-embedding:0.6b;
  - `max_tokens`: 6000;
  - `reasoning`: `low` for generation, `medium` for summarization.
- **variants**: exactly `gpt_oss_20b` and `gemma4_12b`, each overriding only `llm.model`.

**Validation**: `tests/unit/test_benchmark.py` checks that every variant is a valid configuration,
and, new with the switch, that every judge has a profile (R10).

### Confirmation run

A results directory written by `BenchmarkRunner.run`: `results.json`, `rows.jsonl`, `rows.csv`
and `summary.csv`, as for every run. The summarization run also has a `prompts.jsonl`.

- **environment**, from `results.json`:
  - date;
  - dataset checksum;
  - Ollama version;
  - every model's digest and quantization;
  - hardware;
  - the full configuration.
- **complete**: has to be true. A sampled or interrupted run decides nothing (FR-005).
- **commit**: the hash checked out when the run started. It is recorded by hand in `verdict.md`,
  since the container has no `.git`.

**Validation**: `preflight` passes before the run starts (R4).

### Prompt record

One line of `prompts.jsonl` per inference of a summarized chapter, the judge's excluded.

- **variant**, **chapter**: which summary, from the runner's progress messages.
- **model**.
- **estimate_tokens**: the sum of `count_tokens` over the prompt's messages.
- **prompt_tokens**: Ollama's `prompt_eval_count`.
- **window**: `context_size()`.
- **max_tokens**: the reply limit of that call.
- **finish_reason**: Ollama's `done_reason`.

**Derived**: `undercount = prompt_tokens − estimate_tokens`. A gemma4 line blocks the switch when
`undercount > safety_margin × window` (FR-008).

### Probe record

One line of `probe.jsonl` per reply or summary the probe asked for.

- **kind**: one of `warmup`, `whole_library`, `marker` or `analytical`.
- **model**.
- **item**: a question id, or the chapter.
- **language**: set for `marker`, null otherwise.
- **run**: 1 to 3, for `whole_library`.
- **For a reply**:
  - `insufficient_evidence`, what the application shows as an abstention;
  - `text`;
  - `citations`;
  - `invented_citations`;
  - `wait_seconds`, from the end of retrieval to the first visible text.
- **For a summary**:
  - `text`;
  - `steps`;
  - `incomplete_steps`;
  - `detected_language` and `book_language`;
  - `error`, set when it didn't finish.

Its prompts go to the probe's own `prompts.jsonl`.

### Reading record

`specs/002-gemma4-default-llm/reading.yaml`. One entry per item read.

- **item**: a question id, or a chapter with its run.
- **kind**: one of `answer`, `summary`, `probe_reply` or `probe_summary`.
- **model**.
- **errors**: a list drawn from the five kinds of FR-006:
  - `unsupported_claim`;
  - `misattribution`;
  - `unanswered_part`;
  - `abstention_with_evidence`;
  - `false_citation`.

  The list is empty when none was found.
- **label**: for `probe_reply` only:
  - `abstains`, when it says the passages don't hold the answer;
  - `answers`, otherwise.
- **note**: what was read, in a sentence or two. It is required when `errors` isn't empty.

**Validation**: the `verdict` subcommand refuses a record that has:
- an unknown error kind, or an unknown `kind`;
- a `probe_reply` without a label;
- an item missing that FR-006 and FR-008 require: the 15 multi-section questions for both models,
  and every summary FR-006 names.

**Derived**: a systematic weakness is an error kind found in gemma4's entry and not in gpt-oss's
entry for the same item, in 3 or more multi-section items, or in 2 or more summaries, the probe's
included.

### Verdict

`specs/002-gemma4-default-llm/verdict.md`, written by the `verdict` subcommand.

- **For each condition, (a) to (e)**:
  - every number or count it rests on, with intervals where it has them;
  - the threshold;
  - pass or fail.
- **verdict**: `switch to gemma4:12b`, `keep gpt-oss:20b`, or `pending`, when (e) hasn't run.
- **inputs**: the results directories, the commit, and the checksum of `reading.yaml`.

Follow-ups are added below it by hand: every failure that needs a prompt or parser change, each
to become its own bug or feature (SC-006).

### LLM profile, on a switch only

`LLMProfile` in `app/config/settings.py` gains one field.

- **exact_token_count** (bool, required): whether the profile's tokenizer counts a prompt exactly
  as Ollama does. It isn't part of `TokenizerConfig`, which the index fingerprint includes (R9).

## How the decision moves

```text
rule committed ──► preflight ──► generation run ──► preflight ──► summarization run
                                                                       │
             reading.yaml ◄── packets ◄── probe ◄──────────────────────┘
                  │
                  ▼
   verdict (a)–(d), integration pending
        │                               │
   any fails                       all pass
        │                               │
        ▼                               ▼
   keep gpt-oss:20b           switch applied ──► make test, make test-integration
        │                               │
        │                   (e) fails ──┴── (e) passes
        │                       │                 │
        │      revert switch, keep gpt-oss:20b    switch to gemma4:12b
        ▼                       ▼                 ▼
               records: docs/decisions.md, docs/benchmark-results.md, README on a switch
```

A run that doesn't complete is replaced once, at the same place in the sequence (FR-005). A
preflight that fails stops the sequence until the spec is amended or the versions match (the
spec's edge cases).
