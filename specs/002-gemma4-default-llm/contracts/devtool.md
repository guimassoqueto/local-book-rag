# Contract: `devtools/default_llm.py`

One file, five subcommands. It imports only `app`, the packages the application already depends
on (such as `yaml`), and the standard library, so it runs in the `app` container with nothing
installed. Every subcommand exits 0 on success, 1 on a failed check, and 2 on bad arguments.

## Running it

In the container, where the earlier benchmarks ran:

```sh
docker compose exec -T app python - <subcommand> [arguments] < devtools/default_llm.py
```

On the host, for `verdict` only, which reads files and calls no service:

```sh
uv run python devtools/default_llm.py verdict [arguments]
```

Paths are relative to the working directory: `/app` in the container, the repository on the
host. `benchmarks/` is the same directory in both.

## `preflight EXPERIMENT --like RUN --dataset-like RUN`

Before a confirmation run: are the versions the same as the earlier runs'?

- **Reads**: the experiment file, and the `environment` in each reference run's `results.json`.
- **Checks**, against the live stack:
  - the Ollama version, against `--like`;
  - the digest of every model the experiment uses (variants, judge, judge's embedding model,
    configured embedding model), against `--like`;
  - `dataset_checksum(benchmarks/datasets)`, against `--dataset-like`.
- **Prints**: one line per check, `ok` or `DIFFERS`, with both values.
- **Exits 1** if anything differs, or if a model is missing from Ollama or from the reference.

## `summarize EXPERIMENT [--limit N]`

The summarization confirmation.

- **Does**: builds the container with `build_container()`, then calls
  `BenchmarkRunner(container.settings, container.environment).run(load_experiment(EXPERIMENT),
  limit)`. That is the same call as `book-rag benchmark`. While it runs, every provider
  `app.container.assemble` creates is wrapped in the recorder.
- **`--limit N`**: a smoke pass of N chapters per book, to catch a crash before the real run. Its
  results say `complete: false`, so they decide nothing (FR-005), and `verdict` refuses them. The
  confirmation itself runs without `--limit`.
- **Writes**: the usual results directory, plus `prompts.jsonl` in it
  ([records](records.md#promptsjsonl)).
- **Refuses**: an experiment whose kind isn't `summarization`.

## `probe --workspace KEY [--smoke]`

The probe of FR-008, against `benchmarks/workspace/KEY`. It reads the workspace and writes nothing
into it.

- **`--smoke`**: one warm-up, one whole-library run of each question, and one marker reply per
  language, with no `analytical` summary. Its `environment.json` says `complete: false`, so
  `verdict` refuses it. The probe itself runs without `--smoke`, and writes `complete: true`.

- **Does**: for each model, gpt-oss:20b then gemma4:12b, and in this order:
  1. one warm-up question, not timed;
  2. the two whole-library questions, 3 runs each;
  3. the 15 unanswerable questions in Spanish, French, German and Italian;
  4. one `analytical` summary of *Think Python*'s "Inheritance", through the recorder.
- **Writes**: `benchmarks/results/default_llm_probe_<stamp>/`, holding:
  - `probe.jsonl` ([records](records.md#probejsonl));
  - `prompts.jsonl`;
  - `environment.json`: the date, the Ollama version, the digest of each model used, and
    `complete`.
- **Refuses**: a workspace that doesn't hold the three benchmark books, indexed.

## `packets --generation RUN --summarization RUN --probe DIR --earlier RUN...`

The material for the reading.

- **Writes**: `benchmarks/results/default_llm_reading_<stamp>/`, with one Markdown file per item
  that FR-006 and FR-008 name to be read, and an `index.md` listing them:
  - **`multi_section/<question>.md`**:
    - the question, its expected answer and its evidence quotes;
    - the passages, retrieved again in the workspace;
    - both answers, with their scores.
  - **`summaries/<chapter>__<run>.md`**:
    - the chapter's chunks;
    - both models' summaries, with their scores.
  - **`probe.md`**:
    - every marker reply not shown as an abstention;
    - both `analytical` summaries.
  - **`reading.skeleton.yaml`**: one entry for every item and model that a complete
    `reading.yaml` needs ([records](records.md#readingyaml)). Each has `errors: []` and an empty
    `note`, plus `label: null` for a `probe_reply`. It is copied to the feature's directory and
    filled in during the reading.
- **Checks**: each multi-section question's rebuilt passages against its row's
  `evidence_in_context`. A difference is written at the top of the packet, never hidden.

## `verdict --generation RUN --summarization RUN --probe DIR --earlier RUN... --reading FILE --integration STATE --commit HASH [--output FILE]`

Applies FR-002, as research R12 describes.

- **`--earlier`**: the same earlier runs as `packets`, which settle what a complete reading holds.
- **`--output`**: where `verdict.md` goes. By default, `specs/002-gemma4-default-llm/verdict.md`.

- **STATE** is `passed`, `failed` or `pending`.
- **HASH** is the commit the runs started from, recorded in `verdict.md`'s inputs, since the
  containers have no `.git`.
- **Writes**: `specs/002-gemma4-default-llm/verdict.md` ([records](records.md#verdictmd)), and
  prints it.
- **Exits 1**:
  - if `reading.yaml` is invalid or incomplete ([records](records.md#readingyaml));
  - if a run or the probe isn't `complete`;
  - if a run's variants aren't exactly `gpt_oss_20b` and `gemma4_12b`.

  A verdict of "keep" isn't a failure: it exits 0.
