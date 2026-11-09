# Quickstart: running the confirmation and applying the rule

How to validate this feature from start to end. The commands are those of
[contracts/devtool.md](contracts/devtool.md), and the records those of
[contracts/records.md](contracts/records.md).

## Prerequisites

- The stack is up (`make up`), with gpt-oss:20b, gemma4:12b and qwen3-embedding:0.6b in Ollama.
  `book-rag pull-models` brings the first and the last, and `pull-models --all` brings all three.
  Don't pull a model again: a new pull can bring new weights under the same tag, which preflight
  would then refuse.
- The benchmark books are fetched and validated (`book-rag fetch-benchmark-books`,
  `validate-benchmark`).
- `benchmarks/workspace/71026d902d` exists. It is the default configuration's workspace, which the
  earlier runs used. Keep it: no ingestion code has changed since it was built (research R3).
- The commit that holds the spec's corrections, the two experiments and the development script is
  checked out, and `git diff a647e1a -- app config` is empty. Note its hash for `verdict.md`.
- `make test` passes, including `tests/unit/test_default_llm_devtool.py`.

The shorthand below stands for the container invocation:

```sh
dl() { docker compose exec -T app python - "$@" < devtools/default_llm.py; }
```

## 1. Generation (about 2 h)

```sh
dl preflight benchmarks/experiments/default_llm_generation.yaml \
  --like benchmarks/results/generation_20261108T175100527075Z \
  --dataset-like benchmarks/results/summarization_20261108T213459590645Z
make benchmark EXPERIMENT=default_llm_generation
docker compose exec app book-rag benchmark-report --baseline gpt_oss_20b \
  benchmarks/results/default_llm_generation_<stamp>
```

**Expect**:
- every preflight line `ok`, and exit 0;
- `results.json` with `complete: true`, two variants and 90 questions each;
- the report's paired table against `gpt_oss_20b`.

If preflight says `DIFFERS`, stop. The spec is amended with the versions actually used before the
run, never after (the spec's edge cases).

## 2. Summarization (about 25 min)

```sh
dl preflight benchmarks/experiments/default_llm_summarization.yaml \
  --like benchmarks/results/generation_20261108T175100527075Z \
  --dataset-like benchmarks/results/summarization_20261108T213459590645Z
dl summarize benchmarks/experiments/default_llm_summarization.yaml
```

**Expect**:
- six chapters per variant, none `failed`;
- `prompts.jsonl` next to the rows, with every inference of both variants and none of the
  judge's.

gpt-oss's lines should show a small, steady `prompt_tokens − estimate_tokens`: what its chat
template adds.

## 3. The probe (about 20 min)

```sh
dl probe --workspace 71026d902d --commit "$(git rev-parse --short HEAD)"
```

**Expect**: `probe.jsonl` with these lines per model:
- 1 `warmup`;
- 6 `whole_library`;
- 60 `marker`;
- 1 `analytical`.

`environment.json` records what a benchmark's `results.json` does, with the commit and
`complete: true`.

The real library's `data/` is untouched: `git status` and the catalog's modification time show
no change.

## 4. The reading

```sh
dl packets --generation benchmarks/results/default_llm_generation_<stamp> \
  --summarization benchmarks/results/default_llm_summarization_<stamp> \
  --probe benchmarks/results/default_llm_probe_<stamp> \
  --earlier benchmarks/results/summarization_20261108T170744515174Z \
            benchmarks/results/summarization_20261108T213459590645Z
```

Copy the packets' `reading.skeleton.yaml` to `specs/002-gemma4-default-llm/reading.yaml`. Then
read each packet against its passages, and record it there.

No packet should report rebuilt passages that differ from the run's. If one does, its question is
read against the rebuilt passages, and `verdict.md` says so.

The probe keeps no passages for its marker replies. A reply's claims beyond its abstention are
checked against the book's chunks, in
`benchmarks/workspace/<key>/processed/<book>/r1/chunks.jsonl`.

## 5. The verdict on (a) to (d)

```sh
uv run python devtools/default_llm.py verdict \
  --generation benchmarks/results/default_llm_generation_<stamp> \
  --summarization benchmarks/results/default_llm_summarization_<stamp> \
  --probe benchmarks/results/default_llm_probe_<stamp> \
  --reading specs/002-gemma4-default-llm/reading.yaml --integration pending \
  --commit <the tooling commit's hash>
```

**Expect**: `verdict.md` with each condition's numbers.

- **If any of (a) to (d) failed**: the verdict is "keep gpt-oss:20b". Go to step 7.
- **If all four passed**: the verdict is "pending". Go to step 6.

## 6. Only if (a) to (d) passed: the switch, and (e)

Apply the switch as [contracts/configuration.md](contracts/configuration.md) describes: `llm.model`,
`exact_token_count` in every LLM profile, the integration test, the missing-model message, the
judge-profile test and the README. Then:

```sh
docker compose exec app book-rag pull-models --all   # nothing new to download
make restart                                         # the server rereads config/models.yaml
make test
make test-integration
docker compose exec app book-rag doctor --inference
```

**Expect**:
- both test suites pass;
- the token-count test runs once per pulled model:
  - exact for gpt-oss, within 2 tokens;
  - within 10% for gemma4;
  - for the two qwen models, whatever their profiles now say, which this run sets.
- `doctor` reports gemma4:12b answering.

Then:

```sh
uv run python devtools/default_llm.py verdict … --integration passed    # or failed
```

If (e) failed, revert the switch's commits. The verdict is "keep", and the failure is a
follow-up.

## 7. The records

- `docs/decisions.md`:
  - the default, and the runs it rests on;
  - the rule, and how each condition came out;
  - why gpt-oss:20b was the first default;
  - on a switch, the departure from the first version's spec.
- `docs/benchmark-results.md`:
  - the confirmation runs, with their commit, dates, versions and numbers;
  - the reading's summary, and the probe's results;
  - the "(default)" labels and Recommendations following the verdict.
- `README.md`, on a switch only: the default and its reason, its token counts, and the judge
  coming with `pull-models --all`.
- `verdict.md`: every follow-up that needs a prompt or parser change.

**Expect, on a "keep"**: `git diff a647e1a -- app config tests` is empty, except
`tests/unit/test_default_llm_devtool.py` (FR-016).
