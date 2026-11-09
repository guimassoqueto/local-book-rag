# Research: Choosing the default LLM by measurement

Phase 0 of the plan. Every fact below was checked on 2026-11-09 against the code on `main` at
`a647e1a`, and against the earlier runs' result files in `benchmarks/results/`.

## R1. The spec's facts, checked against the result files

- **Decision**: three corrections, made in the spec before any run, as FR-001 allows. They are
  recorded in its "Corrections during planning":
  - **15 multi-section questions, not 13.** The handoff's 13 were the pairs both models had scored,
    because gpt-oss abstained on `quincas_borba_multi_section_03` and `_05`.
  - **The novel's coverage was seen once.** On today's key points, only the latest run measured it.
    In the run before, both models had 0.267 on the novel, against key points that `826c977` then
    rewrote.
  - **FR-016's "no code or test" would have deleted the confirmation's own tooling** on a "keep".
    It now protects `config/`, `app/` and the application's tests.
- **Confirmed as the spec states them**:

  | Fact | Value | Source |
  | --- | --- | --- |
  | Wrong abstentions, full run | gpt-oss 3, gemma4 0 | `rows.jsonl`: `abstained`, with a category other than `unanswerable` |
  | gemma4 consistency 0.5 | "Inheritance" in both runs, "Fruitful functions" in the latest | both summarization runs' rows |
  | Summary seconds and steps, latest run | −69.4 s (−142.5 to −4.7), −6.3 steps (−12.7 to −0.3) | paired bootstrap over 6 chapters, 4,000 resamples |
  | Today's dataset | `767e4cceb315…`, the same as the latest summarization run's | `dataset_checksum` |
  | Generation run's dataset | `f69da2332857…`, differing only in `chapter_key_points.jsonl` | `git log -- benchmarks/datasets` |
  | Digests in all three runs | gemma4:12b `6114515d63c1…`, gpt-oss:20b `f38aa0c53da5…`, qwen3-embedding:0.6b `ac6da0dfba84…` | each `results.json` |
  | Ollama | 0.40.15 in every run, pinned by digest in `docker-compose.yml` | `docker-compose.yml:6` |
- **One note on the latest run**: gpt-oss also scored 0.5 on "Inheritance" there, so the reading
  of that chapter has both models' summaries in question.

## R2. Running two variants

- **Decision**: two new experiment files, `benchmarks/experiments/default_llm_generation.yaml` and
  `default_llm_summarization.yaml`. Each is a copy of `generation.yaml` or `summarization.yaml`
  with the same judge block, byte for byte, and only the variants `gpt_oss_20b` and `gemma4_12b`.
- **Rationale**:
  - Configuration only: nothing in `app/` changes before the runs (FR-004).
  - The variant names stay those of the earlier runs, so `benchmark-report --baseline gpt_oss_20b`
    pairs them, and their rows read next to the old ones.
  - `tests/unit/test_benchmark.py` already validates every experiment file it finds, and its check
    of the kinds covered still holds.
- **Alternatives considered**:
  - **A `--variant` filter on `book-rag benchmark`**: a change to the command and the runner just
    before the runs, which FR-004 asks to avoid.
  - **Running the four-variant experiments**: twice the time, and the qwen models are out of scope.

## R3. The benchmark workspace

- **Decision**: reuse `benchmarks/workspace/71026d902d`, the default configuration's workspace that
  the earlier runs used, as it is.
- **Rationale**:
  - Constitution VI asks for a fresh workspace after a change to the ingestion code. None was
    made since the workspace was built (2026-11-07 09:44):
    - `9f90a13` added `language_name()` to `app/ingestion/language.py`, which prompts use and
      chunking doesn't;
    - `608e9a4` and `1228aeb` changed lexical search, which stores nothing.
  - Retrieval is deterministic, so the generation run gets the same passages as the earlier runs.
    Then the comparison resamples only the models and the judge.
  - This feature changes nothing in `index_key()` or the index fingerprint (R9).
- **Alternative considered**: deleting the workspace, which reindexes three books for nothing,
  and risks changing the passages, which would separate the confirmation from the runs it
  confirms.

## R4. Checking versions before each run (FR-004)

- **Decision**: a `preflight` subcommand of the development script (R8) checks three things against
  a reference run's `results.json`:
  - the Ollama version;
  - the digest of every model the experiment uses: its variants, its judge and its embedding model;
  - the dataset checksum.

  It reads them with the calls `BenchmarkRunner._describe_environment` uses: `runtime.version()`,
  `runtime.model_info()` and `dataset_checksum()`. It exits non-zero on any difference, naming
  it. The references are:
  - for both runs' versions, `generation_20261108T175100527075Z`;
  - for the dataset, `summarization_20261108T213459590645Z`, since the generation run's checksum
    predates the key points.
- **Rationale**: the spec asks for the check before each run starts, and a run's own record of
  versions is only read afterwards. Reading the expected values from the earlier run, instead of
  typing them into the script, makes "the same as before" literal.
- **Alternative considered**: comparing the recorded versions after each run, which finds a
  mismatch an hour or two too late.

## R5. Seeing every whole summary prompt (FR-008, the tokenizer)

- **Decision**: the development script runs the summarization confirmation itself, through
  `BenchmarkRunner.run`. Its results directory is the one `make benchmark` would write. While it
  runs, it wraps every LLM provider that `app.container.assemble` creates in a recorder. For each
  inference, the recorder adds a line to `prompts.jsonl`, in the results directory, with:
  - the model;
  - the estimate, as the sum of `count_tokens` over the messages' contents, which is how the
    summarizer measures prompts (`_frame_tokens`, `_batches`);
  - Ollama's own count, `prompt_eval_count`;
  - the window, `context_size()`;
  - the reply limit, `max_tokens`;
  - the finish reason.

  The judge isn't recorded: the runner builds it through its own import of `create_llm_provider`,
  which the wrapper doesn't touch.
- **The blocking test**: for gemma4, Ollama's count minus the estimate is more than
  `safety_margin × window`, 819 tokens at 8,192. gpt-oss's tokenizer is exact (R9), so its own
  lines measure what the chat template adds, the part of the difference no tokenizer counts.
- **Rationale**:
  - **The prompts have to be the confirmation's own.** The summarizer sets no seed
    (`ChapterSummarizer._parameters`), so rerunning a summary wouldn't reproduce its merges and
    final prompt, which are the ones sized to the window.
  - **Wrapping changes nothing that summarizes**, so FR-004 holds: the recorder passes every call
    through and only reads the results.
  - **The probe's `analytical` summaries go through the same recorder.**
- **Alternatives considered**:
  - **Adding the counts to the summarization rows**: a change to the runner before the runs, and a
    new field in the rows that the report could start reading as a metric.
  - **The inference log**: it has Ollama's count of every call, but not the estimate.
  - **Rerunning the six summaries in the probe**: different prompts, as above.

## R6. The probe

- **Decision**: a `probe` subcommand that runs in the `app` container against the benchmark
  workspace of R3, never the real library. For each model, it builds the workspace's container with
  `assemble()` and `llm.model` overridden in memory, through `apply_overrides`, as each benchmark
  variant does. It writes `benchmarks/results/default_llm_probe_<stamp>/probe.jsonl`, and an
  `environment.json` with the Ollama version and digests. It writes nothing else: no summary is
  saved, and no book is added or removed.
  - **The trap, and the first visible word**:
    - It asks `quincas_borba_unanswerable_04` and `think_python_multi_section_04` with no filter,
      3 times each per model, through `QuestionAnsweringService.stream`.
    - The wait is timed from the `RetrievalResult` event to the first `TextDelta`: from retrieval's
      end, through fitting the passages, to the first text the reader sees, after any reasoning
      and after the marker and citation filters.
    - Each model gets one untimed warm-up question first, so its load time isn't counted. The
      performance experiment does the same.
    - Median of 6 waits per model. The trap's 3 runs count for the trap too.
  - **The marker in other languages**:
    - The 15 unanswerable questions are asked of their book, with the benchmark's filters
      (`Workspace.filters`), and `language` set to Spanish, French, German and Italian, the names
      in `generation.response_languages`.
    - For each reply, it records the text and `Answer.insufficient_evidence`, which is what the
      chat tab and the command line show as an abstention.
    - Every reply not shown as an abstention is read, and labelled as one of two things: it says
      the passages don't hold the answer, or it answers. A reply that says the passages don't hold
      the answer, without being shown as an abstention, is an unrecognized abstention.
  - **The long summary**:
    - `summaries.summarize(book, "Inheritance", "analytical")` per model, with the recorder of R5.
    - "Doesn't finish" means it raises an error. Its incomplete steps are recorded and read.
    - Its language is checked with `detect_language`, against the book's.
- **Rationale**:
  - The workspace holds exactly the three benchmark books, indexed the way the benchmarks
    measured them, and nothing the probe does can reach the library (constitution II).
  - Overriding the model in memory leaves `config/` untouched, as the research's Probe A did.
  - Timing from the service's own events measures what the reader waits for, without wrapping
    anything.
- **Alternatives considered**:
  - **The real library**: it would have to hold the same three books, and the probe would read
    it with no need to.
  - **Timing `time_to_first_token`**: it counts reasoning tokens, which the reader doesn't see.

## R7. Reading packets and the reading record (FR-006, FR-007)

- **Decision**: a `packets` subcommand, run in the container, writes one Markdown packet per item
  to read, into `benchmarks/results/default_llm_reading_<stamp>/`.
  - **For each of the 15 multi-section questions**:
    - the question, its expected answer and its evidence quotes;
    - the passages, retrieved again in the workspace exactly as the generation run did;
    - both models' answers, with their scores.
  - **For each summary FR-006 names**:
    - the chapter's chunks;
    - both models' summaries of it, from the confirmation and, for the two *Think Python*
      chapters, from the earlier runs;
    - their scores.
  - **The probe's `analytical` summaries**, and its replies that weren't shown as abstentions.

  The reading itself is recorded in `specs/002-gemma4-default-llm/reading.yaml`, item by item, in
  the format of [contracts/records.md](contracts/records.md).
- **Rationale**:
  - The generation rows don't store the passages. Retrieval is deterministic, so they can be
    rebuilt. The packet checks them against each row's `evidence_in_context`, and says so if one
    differs.
  - A structured record lets the verdict apply FR-006's definition mechanically, while each
    item's note carries what was read.
- **Alternative considered**: a free-form `reading.md`, which would leave counting the error kinds
  to hand, where the rule is easiest to bend.

## R8. One development script, run inside the container

- **Decision**: `devtools/default_llm.py`, a single file with five subcommands: `preflight`,
  `summarize`, `probe`, `packets` and `verdict`.
  - **The first four run in the `app` container**, where the earlier runs ran, by piping the file
    to the container's Python:

    ```sh
    docker compose exec -T app python - <subcommand> … < devtools/default_llm.py
    ```

    `devtools/` isn't in the image, and the container mounts only `benchmarks/`, `config/`,
    `data/` and `logs/`. So the script imports nothing but `app`, and writes under
    `benchmarks/results/`.
  - **`verdict` runs on the host**, with `uv run`: it only reads result files and `reading.yaml`.
- **Rationale**:
  - Running in the same container keeps the hardware, packages and Ollama endpoint the same as in
    the runs it confirms.
  - One file keeps the recorder, the probe and the rule together, and the feature's directory
    points to one place.
  - It stays after a "keep", as the record of how the numbers were made (FR-016).
- **Testing**: the rule's arithmetic decides the verdict, so it gets unit tests. So do the
  recorder and the reading of `reading.yaml`. `tests/unit/test_default_llm_devtool.py` loads the
  script by path with `importlib`, and feeds it synthetic rows, prompts and readings. The parts
  that need the stack are exercised by the runs themselves.
- **Alternatives considered**:
  - **`docker compose run` with `devtools/` mounted**: a second app container next to the
    running one.
  - **A module in `app/evaluation`**: application code for a one-off decision, which FR-016 would
    then have to keep on a "keep".

## R9. Telling an exact tokenizer from an approximate one (FR-011)

- **Decision**: a new required field on `LLMProfile`, `exact_token_count: bool`. It is set in each
  of the four LLM profiles in `config/models.yaml`:
  - gpt-oss:20b: true, because Probe B measured 1.000 on every chunk;
  - gemma4:12b: false, because Probe B measured 0.941 to 1.043;
  - the two qwen profiles: the value the integration test measures (below).
- **Where it can't go**: it can't go on `TokenizerConfig`, which the embedding profiles share:
  - `IndexService.current_configuration()` puts `embedding_profile.tokenizer.model_dump()` into
    the fingerprint;
  - `index_key()` hashes `embedding_profile.model_dump()`.

  A new field there would change every index's fingerprint and every workspace's key. `doctor`
  would then report the library out of date, and new books would be refused until `reindex-all`,
  which constitution III and FR-017 rule out.
- **Required, without a default**:
  - Defaulting to true would let a new approximate profile pass the integration test's exact
    check, or fail it for the wrong reason.
  - Defaulting to false would quietly loosen the check for exact ones.

  Like every setting, it is validated at startup.
- **The integration test**: `test_the_token_estimate_matches_the_runtime_count` runs once for every
  LLM profile whose model is on the Ollama server, and skips the others.
  - An exact profile is held to its current 2 tokens.
  - An approximate one is held to `safety_margin` of the measured count, 10%.

  So the test checks the field itself, for every model pulled. The values of the qwen profiles
  come from running it once, with `pull-models --all`: true if they match within 2 tokens.
  Measuring a profile isn't re-opening the qwen comparison.
- **When**: only on a switch. On a "keep", `config/`, `app/` and the tests stay as they are
  (FR-016), and the field waits for a change that needs it.
- **Alternatives considered**:
  - **A measured error bound per profile**, checked against the margin at startup: more than
    FR-011 asks for, and a cross-setting rule of its own.
  - **Keying the tolerance on the tokenizer's name**: model-specific behavior outside a profile,
    against constitution I.

## R10. Getting the judge onto a machine (FR-010)

- **Decision**: `pull-models` stays as it is:
  - plain, it brings the two models the application uses;
  - `--all`, every model with a profile.

  `--all` always brings the judge, because a judge must have an LLM profile: `_judge_llm` makes
  the judge `llm.model`, and validation refuses a model without one. Three changes make the step
  deliberate:
  - **A unit test** asserts that every experiment's `judge.model` has an LLM profile, and its
    `judge.embedding_model` an embedding profile. The guarantee is then checked, not assumed.
  - **The README's Benchmarks section** says that `--all` brings every candidate and every judge,
    and that plain `pull-models` doesn't bring the judge.
  - **The missing-model error** (`ModelNotFoundError` in `app/utils/ollama_runtime.py`) now says
    to use `pull-models --all` for a model only the benchmarks use. Today it says plain
    `pull-models`, which wouldn't bring the judge.
- **A missing judge stops a run before any work**: `BenchmarkRunner.run` describes the
  environment first, which calls `model_info` on the judge. A missing model raises
  `ModelNotFoundError`, naming it.
- **Rationale**: no change to `app/main.py` (constitution IV), and no 12.5 GB download for a reader
  who never benchmarks.
- **Alternatives considered**:
  - **A `--judges` flag** that reads `benchmarks/experiments/`: more logic in the command layer.
  - **Always pulling the judge**.

## R11. Nothing depends on the default being gpt-oss (FR-012)

- **Decision**: the search is done. Nothing needs to change for the switch beyond R9 and R10.
- **What it found**:
  - **In `app/`**: gpt-oss is named only in comments and docstrings that explain a workaround
    (`citations.py`, `prompts.py`, `question_answering.py`, `language.py`, `summary_metrics.py`,
    `verdicts.py`). None branches on it.
  - **In `tests/unit`**: `gpt-oss:20b` is fixture data (`test_ollama_runtime.py`,
    `test_interface.py`, `test_health_service.py`, `test_llm_provider.py`), a judge fixture
    (`test_benchmark.py:359`), and the generation experiment's four candidates
    (`test_benchmark.py:72`). None reads the configured default.
  - **In `tests/integration`**: only the token-count test assumes anything about the configured
    model (R9). The others run whatever is configured, which is what condition (e) needs.

## R12. Applying the rule (FR-002)

- **Decision**: the `verdict` subcommand reads the two confirmation runs' rows, `prompts.jsonl`,
  `probe.jsonl` and `reading.yaml`, and takes the integration result as `--integration
  passed|failed|pending`. It writes each condition, with the numbers behind it, to
  `specs/002-gemma4-default-llm/verdict.md`.
  - **(a)**: it calls `app.evaluation.report.paired_difference`, the report's own function, with
    its seed and 4,000 draws:
    - on the six generation metrics, over all rows;
    - on `answer_correctness`, over the `multi_section` rows;
    - on the six summary metrics.
  - **(b)**:
    - the count of wrong abstentions, as in R1;
    - `paired_difference` on `total_seconds` and `steps`;
    - the mean `argument_coverage` over the two `quincas_borba` rows.
  - **(c)**: FR-006's definition, applied to `reading.yaml`.
  - **(d)**: FR-008's five blocking findings, from `probe.jsonl`, the probe's reading labels and
    `prompts.jsonl`.
  - **(e)**: the flag.

  The verdict is "switch" only if all five pass. With `--integration pending`, it reports (a)–(d)
  and no verdict, which is how it is run before the switch is tried.
- **Rationale**:
  - The same function and seed as `benchmark-report`, so its intervals match the report's to the
    digit.
  - The rule is applied by code committed before the runs, so the verdict follows from the
    numbers alone (SC-001).
- **Not a metric change**: `benchmark-report` stays as it is. Seconds and steps are paired by the
  script, so the extra Spec Kit steps for a metric change don't apply (the checklist's caveat).

## R13. Order, commits and the pull request

- **Decision**:
  1. **Before any run**, one commit holds:
     - the spec's corrections;
     - the two experiment files;
     - the development script and its tests.

     `git diff a647e1a` then shows no change to `app/` or `config/`, which is what FR-004 asks.
     The commit's hash is recorded with the runs, since the containers have no `.git`.
  2. **The runs**: preflight, generation (`make benchmark`), preflight, summarization (the script),
     then the probe and the packets.
  3. **The reading**: `reading.yaml`.
  4. **The verdict on (a)–(d)**, with `--integration pending`.
  5. **Only if all four pass**:
     - the switch: `llm.model`, `exact_token_count`, the integration test, the error message, the
       judge test and the README;
     - then `make test` and `make test-integration`;
     - then the verdict again, with the result of (e).

     If (e) fails, the switch's commits are reverted.
  6. **The records**: `docs/decisions.md` and `docs/benchmark-results.md`, and the follow-ups.
- **The pull request's title** decides the release:
  - a switch is `feat: make gemma4:12b the default LLM`, a minor release;
  - a "keep" changes no behavior, so it is `docs: record why gpt-oss:20b stays the default LLM`,
    with no release. The branch keeps its `feat/` name either way.
- **Machine time**, from the earlier runs:
  - generation with two models, about 2 h: about 36 s per question and model, nearly all of it
    judging;
  - summarization, about 25 min;
  - the probe, about 20 min. Most of it is the 120 marker replies, and the 12 whole-library
    questions at 12 to 20 s of retrieval each.
