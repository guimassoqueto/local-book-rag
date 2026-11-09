---

description: "Task list for choosing the default LLM by measurement"
---

# Tasks: Choosing the default LLM by measurement

**Input**: Design documents from `specs/002-gemma4-default-llm/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: included. The spec doesn't ask for them, but the rule's arithmetic decides the verdict,
and the constitution's Development Workflow asks for automated tests for every significant
component. Plan R8 lists what they cover. Within each story, the tests come first and must fail
before the implementation.

**Organization**: grouped by user story. The phases follow the order the work has to happen in,
which isn't the order of priority:
1. US1 produces the verdict on (a) to (d).
2. US3, the switch, runs only if all four passed, and its integration run is condition (e).
3. US2, the records, comes last either way, because it records the final verdict.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story a task belongs to (US1, US2, US3)

## Path Conventions

A single Python project, with `app/`, `config/`, `tests/`, `benchmarks/experiments/` and
`devtools/` at the repository root (plan.md, Project Structure).

- **In the Bash tool**, run
  `export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"` before `make` or
  `uv`.
- **`dl …`** stands for running the development script in the container, as
  [quickstart.md](quickstart.md) defines it:
  `docker compose exec -T app python - … < devtools/default_llm.py`.
- **Long runs** (T018 to T020) take minutes to hours. Run them in the background, and wait to be
  notified. Don't poll.

---

## Phase 1: Setup

**Purpose**: confirm the state the confirmation depends on, changing nothing.

- [X] T001 Check the starting state, and stop on any surprise. Don't pull a model: a new pull can
  bring new weights under the same tag. Check that:
  - the branch is `feat/gemma4-default-llm`, at `4e7284b` or later, with a clean tree;
  - `docker compose ps` shows `app`, `ollama` and `chromadb` running;
  - `docker compose exec ollama ollama list` lists `gpt-oss:20b`, `gemma4:12b` and
    `qwen3-embedding:0.6b`;
  - `benchmarks/workspace/71026d902d/` and the three files in `benchmarks/books/` exist;
  - `make test` passes.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the two experiments and the script's skeleton, which every later task builds on. Per
FR-004, nothing in `app/` or `config/` changes in this phase or in Phase 3.

**⚠️ CRITICAL**: no user story can start until this phase is complete.

- [X] T002 [P] Create `benchmarks/experiments/default_llm_generation.yaml` as in
  [contracts/configuration.md](contracts/configuration.md):
  - `name: default_llm_generation` and `kind: generation`;
  - the `judge` block copied byte for byte from `benchmarks/experiments/generation.yaml`;
  - only the variants `gpt_oss_20b` and `gemma4_12b`, as they are written there.
- [X] T003 [P] Create `benchmarks/experiments/default_llm_summarization.yaml` the same way, from
  `benchmarks/experiments/summarization.yaml`, with `kind: summarization` and its judge block
  (`reasoning: medium`).
- [X] T004 [P] Create `devtools/default_llm.py` with:
  - **A module docstring** saying:
    - that it is the confirmation of `specs/002-gemma4-default-llm`;
    - that four subcommands run in the container, with
      `docker compose exec -T app python - <subcommand> … < devtools/default_llm.py`;
    - that `verdict` runs on the host, with
      `uv run python devtools/default_llm.py verdict …`;
    - that it stays after the decision, as the record of how the numbers were made (FR-016).
  - **`main(argv: Sequence[str] | None = None) -> int`**, an `argparse` parser with the five
    subcommands and arguments of [contracts/devtool.md](contracts/devtool.md). Exit 2 on bad
    arguments (argparse's own), 1 on a failed check, 0 otherwise.
  - **`if __name__ == "__main__": sys.exit(main())`**, which also holds under `python -`.
  - **Constants**: `BASELINE = "gpt_oss_20b"`, `CANDIDATE = "gemma4_12b"`, and
    `RESULTS = Path("benchmarks/results")`.
  - **Imports**: only `app`, the application's own dependencies (`yaml`) and the standard library.
    The script is piped to the container, so it can import nothing next to it. Leave each
    subcommand's body raising `NotImplementedError` for now.
- [X] T005 Create `tests/unit/test_default_llm_devtool.py` (depends on T002 to T004).
  - **A module-level loader**:
    `importlib.util.spec_from_file_location("default_llm", PROJECT / "devtools" / "default_llm.py")`,
    registered in `sys.modules` before `exec_module`, with
    `PROJECT = Path(__file__).resolve().parents[2]`.
  - **The experiments' tests**, for each confirmation experiment:
    - its `load_experiment(...).judge` equals its source experiment's `judge`;
    - its variants' names are exactly `("gpt_oss_20b", "gemma4_12b")`;
    - each variant's `overrides` equals the same-named variant's in the source experiment.
  - **A test** that `main(["bogus"])` raises `SystemExit` with code 2.

  `make test` passes. The existing `test_every_variant_is_a_valid_configuration` already covers
  the two new files.

**Checkpoint**: the experiments load, and the script's skeleton parses its arguments.

---

## Phase 3: User Story 1 - A verdict the numbers can't be fitted to (Priority: P1) 🎯 MVP

**Goal**: run the confirmation against the committed rule, and get a verdict on conditions (a) to
(d) that follows from the recorded numbers and reading alone.

**Independent Test**: `git log` shows the rule's commit (`4e7284b`) and the tooling's commit (T017)
older than every confirmation run's `results.json` date. `verdict` reproduces `verdict.md` from
the recorded files, with every condition backed by a number or a reading.

### Tests for User Story 1 (write first, and see them fail)

All in `tests/unit/test_default_llm_devtool.py`, one after another, since they share the file. Use
`tests.fakes.FakeLLM` and `make_stats` for providers, and build rows as plain dicts with the
fields of the real rows (`rows.jsonl`: `variant`, `question`, `book`, `category`, `abstained`, and
the metric fields).

- [X] T006 [US1] Tests for the recorder (research R5, [records](contracts/records.md#promptsjsonl)):
  - **A pass-through record**: `RecordingLLM(inner, sink, label=lambda: ("gemma4_12b",
    "Inheritance"))` returns `inner`'s `Generation` unchanged from `generate`, and yields `inner`'s
    events unchanged from `stream`. It appends one record with the fields `variant`, `chapter`,
    `model`, `estimate_tokens`, `prompt_tokens`, `window`, `max_tokens` and `finish_reason`, where:
    - `estimate_tokens` is `sum(inner.count_tokens(m.content) for m in messages)`;
    - `prompt_tokens` is the generation's `stats.prompt_tokens`;
    - `window` is `inner.context_size()`.
  - **Delegation**: `model`, `context_size()` and `count_tokens()` delegate to `inner`.
  - **The patch**:
    - inside `recording_llms(sink, label)`, `app.container.create_llm_provider` returns a
      `RecordingLLM`;
    - after the block exits, even through an exception, it is the original function again;
    - `app.evaluation.benchmark.create_llm_provider`, the judge's path, is never replaced.
- [X] T007 [US1] Tests for `compare_environment(expected, actual, models, dataset_expected,
  dataset_actual) -> list[Check]`, where `Check` holds `name`, `expected`, `actual` and `ok`.
  - Identical environments give only `ok` checks.
  - Each of these gives one check that isn't `ok`, naming what differs:
    - a different digest for one model;
    - a model missing from the reference;
    - a different Ollama version;
    - a different dataset checksum.
- [X] T008 [US1] Tests for `load_reading(path)` and `missing_entries(entries, required)`
  ([records](contracts/records.md#readingyaml)).
  - **`load_reading` raises `ReadingError` (a `ValueError`) for**:
    - an error kind outside `unsupported_claim`, `misattribution`, `unanswered_part`,
      `abstention_with_evidence` and `false_citation`;
    - a `kind` outside `answer`, `summary`, `probe_reply` and `probe_summary`;
    - a `probe_reply` without `label`, or with one other than `abstains` or `answers`;
    - a `label` on any other kind;
    - non-empty `errors` with an empty `note`.
  - **`missing_entries`** names each `(item, kind, model)` that is required and absent.
- [X] T009 [US1] Tests for `decide(generation_rows, summarization_rows, prompts, probe, reading,
  safety_margin, integration) -> Verdict`, covering every condition of spec FR-002.
  - **(a)**:
    - gemma4 lower on `faithfulness` on every question fails (a), naming `faithfulness`;
    - equal rows pass;
    - multi-section correctness pairs only `category == "multi_section"` rows;
    - rows with `answer_correctness: None` are left out of the pairs;
    - every interval equals `app.evaluation.report.paired_difference(rows, BASELINE, CANDIDATE,
      metric)` exactly.
  - **(b)**:
    - wrong abstentions are rows with `abstained` true and `category != "unanswerable"`;
    - 3 against 0 passes, and 0 against 0 fails;
    - seconds and steps pass only with an interval that excludes zero, from `total_seconds` and
      `steps`;
    - the novel's coverage is the mean `argument_coverage` of the `book == "quincas_borba"` rows,
      and passes only when gemma4's is higher.
  - **(c)**:
    - an error kind in gemma4's entry and not in gpt-oss's, in 3 multi-section `answer` items,
      fails;
    - in 2 such items, it passes;
    - in 2 `summary` or `probe_summary` items, it fails.
  - **(d)**: each blocking finding fails on its own:
    - gemma4 answers `quincas_borba_unanswerable_04` (`whole_library`, `insufficient_evidence`
      false) in more runs than gpt-oss;
    - gemma4 has more `marker` replies that aren't shown as abstentions and whose `probe_reply`
      entry has `label: abstains`;
    - gemma4's `analytical` record has an `error`, or a `detected_language` other than its
      `book_language`, while gpt-oss's has neither;
    - a gemma4 prompt record has `prompt_tokens - estimate_tokens > safety_margin * window`;
    - gemma4's median `wait_seconds` over its `whole_library` records is more than 1.0 s above
      gpt-oss's.

    Each one passes when gpt-oss has the same failure.
  - **(e)**:
    - with (a) to (d) passing, `pending` gives the verdict `pending`, `failed` gives `keep`, and
      `passed` gives `switch`;
    - any of (a) to (d) failing gives `keep` whatever the integration state.

### Implementation for User Story 1

All in `devtools/default_llm.py`, one after another.

- [X] T010 [US1] Implement `RecordingLLM` and the `recording_llms(sink, label)` context manager
  (research R5). The context manager replaces `app.container.create_llm_provider` with a function
  that wraps the original's result, and restores it in a `finally`. T006 passes.
- [X] T011 [US1] Implement `compare_environment` and the `preflight` subcommand (research R4,
  [contract](contracts/devtool.md)). It reads, from the live stack:
  - `runtime.version()`;
  - `runtime.model_info(model).digest` for every model the experiment uses: each variant's
    `apply_overrides(settings, variant.overrides).llm.model`, `judge.model`, `judge.embedding_model`
    and `settings.embedding.model`;
  - `dataset_checksum(Path("benchmarks/datasets"))`.

  It compares them with `--like`'s and `--dataset-like`'s `results.json["environment"]`, prints
  one `ok` or `DIFFERS` line per check with both values, and exits 1 on any difference. T007
  passes.
- [X] T012 [US1] Implement `summarize` ([contract](contracts/devtool.md)):
  - **Refuses** an experiment whose `kind` isn't `summarization`, with exit 1.
  - **Runs**: `container = build_container()`, then
    `BenchmarkRunner(container.settings, container.environment, say=say).run(experiment,
    arguments.limit)`, inside `recording_llms`.
    - `say` prints each message, and keeps the variant and chapter of the last one shaped
      `"<variant>: summarizing <chapter>"`, for the recorder's label.
    - The chapter in that message is cut at 50 characters by the runner. The label keeps it as
      it is, and `packets` matches it against the rows by prefix.
  - **Writes** the records to `prompts.jsonl` in the directory `run` returns, then prints that
    directory.
- [X] T013 [US1] Implement `probe` (research R6, [contract](contracts/devtool.md)).
  - **Opening the workspace**:
    - `settings = load_settings(EnvironmentSettings().config_dir)`;
    - refuse a `--workspace` other than `index_key(settings)`;
    - `environment = EnvironmentSettings().model_copy(update={"data_dir":
      environment.benchmarks_dir / "workspace" / key})`.
  - **For each model, gpt-oss:20b then gemma4:12b**:
    - `assemble(apply_overrides(settings, {"llm": {"model": model}}), environment,
      collection_prefix=f"bench_{key}_v")`, inside `recording_llms`;
    - map each dataset book to the catalog book whose `checksum` equals its `sha256`, with status
      `indexed`, and refuse if one is missing;
    - never call `reset_everything`, `recover`, `add_book` or `save`.
  - **Each reply**:
    - iterate `container.questions.stream(question, filters, language)`;
    - start a clock at the `RetrievalResult` event, and stop it at the first `TextDelta`;
    - record the final `Answer`'s `insufficient_evidence`, `text`, the cited passages' numbers
      and `invented_citations`.
  - **The order, per model**:
    1. a warm-up: the dataset's first answerable question, with its book filter, untimed;
    2. `quincas_borba_unanswerable_04` and `think_python_multi_section_04` with
       `RetrievalFilters()`, 3 runs each;
    3. the 15 unanswerable questions, with
       `Workspace(container, settings, books, {}).filters(question)`, in Spanish, French, German
       and Italian;
    4. `container.summaries.summarize(book_id, <number of "Inheritance">, "analytical")`, with
       `detect_language(summary.text)` against the book's language, and any `BookRagError`
       recorded as `error`.
  - **Writes**:
    - `probe.jsonl`, appended line by line;
    - the recorder's `prompts.jsonl`;
    - `environment.json`, with the date, `runtime.version()`, each model's digest, and `complete`.
  - **`--smoke`**: one warm-up, one run of each whole-library question, one marker reply per
    language, no `analytical` summary, and `complete: false`.
- [X] T014 [US1] Implement `packets` ([contract](contracts/devtool.md), research R7), opening the
  workspace as T013 does.
  - **Multi-section**: for each of the 15 `multi_section` questions, rebuild the passages with
    `container.retrieval.search(question.question, workspace.filters(question),
    settings.retrieval).passages`. Recompute
    `context_recall([c.chunk_id for c in chunks], relevant_chunks(question, chunks_of_book))`,
    and write any difference from the row's `evidence_in_context` at the top of the packet.
  - **Summaries**:
    - every `gemma4_12b` row of `--summarization` with `factual_consistency <= 0.5`, with the
      `gpt_oss_20b` row of the same chapter;
    - from each `--earlier` run, "Inheritance" and "Fruitful functions", where gemma4 scored 0.5,
      with gpt-oss's rows of the same run and chapter.

    Each packet has the chapter's chunks, from `container.books.chunks(book_id)` filtered by
    chapter number.
  - **`probe.md`**: every `marker` reply with `insufficient_evidence` false, and both
    `analytical` summaries.
  - **`reading.skeleton.yaml`**: every required entry, with `errors: []`, `note: ""`, and
    `label: null` for a `probe_reply`.
  - **`index.md`**: the list of all packets.
- [X] T015 [US1] Implement `load_reading`, `missing_entries`, `decide` and the `verdict`
  subcommand (research R12, [records](contracts/records.md#verdictmd)).
  - **Reads**: `safety_margin` from `load_settings(Path("config")).generation.context`.
  - **Refuses**, with exit 1:
    - a run whose `results.json` has `complete` false;
    - a probe whose `environment.json` has `complete` false;
    - variants other than exactly `BASELINE` and `CANDIDATE`;
    - an invalid or incomplete reading.
  - **Writes**: `specs/002-gemma4-default-llm/verdict.md`, in the contract's order, with the
    commit given as `--commit`, and the SHA-256 of `reading.yaml`. It prints the same text.
  - T008 and T009 pass.
- [X] T016 [US1] Check the tooling before committing it:
  - **Locally**:
    - `make test`, and `make lint-check`;
    - `uv run ruff check devtools/default_llm.py` and
      `uv run ruff format --check devtools/default_llm.py`. `devtools` is excluded from the
      project-wide lint, but an explicit path is still checked.
  - **Against the stack**:
    - `dl preflight` for both experiments, as in [quickstart.md](quickstart.md) steps 1 and 2.
      Expect every line `ok`.
    - `dl summarize benchmarks/experiments/default_llm_summarization.yaml --limit 1`. Expect
      `complete: false`, and a `prompts.jsonl` with both variants' lines and no judge lines.
    - `dl probe --workspace 71026d902d --smoke`. Expect `complete: false`, and `data/` unchanged.

  Delete neither smoke directory. They are sampled, decide nothing (FR-005), and `verdict`
  refuses them. Don't read their numbers.
  - **Done 2026-11-09**:
    - 835 unit tests passing, lint clean;
    - preflight `ok` on every line for both experiments;
    - `default_llm_summarization_20261109T040045599208Z`: `complete: false`, 3 chapters per
      variant, 28 prompts recorded, all from the variants' own models, none from the judge;
    - `default_llm_probe_smoke_20261109T041047009259Z`: 1 warm-up, 2 whole-library and 4
      marker replies per model, no errors, every wait timed;
    - `data/metadata/catalog.db` unchanged.
- [X] T017 [US1] Commit T002 to T016 as `chore: add the default LLM confirmation's tooling`.
  - `git diff a647e1a -- app config` must be empty (FR-004).
  - Note the commit's hash: it goes into `verdict.md` with `--commit`.
  - **Done 2026-11-09**: `f6f53a8`, with `git diff a647e1a -- app config` empty.
- [X] T018 [US1] Run the generation confirmation, about 2 h, as in [quickstart.md](quickstart.md)
  step 1:
  1. `dl preflight` against the generation reference, which must exit 0;
  2. then `make benchmark EXPERIMENT=default_llm_generation`;
  3. then `benchmark-report --baseline gpt_oss_20b` on its results.

  If preflight says `DIFFERS`, stop, and amend the spec with the versions used before the run
  (spec, Edge Cases). Check that `complete` is true, with 90 rows per variant. If the run doesn't
  complete, replace it once (FR-005).
  - **Done 2026-11-09**: preflight `ok` on every line, then
    `default_llm_generation_20261109T041359173775Z`, `complete: true`, 90 rows per variant. The
    report was read only for completeness: the verdict reads it in T023.
- [X] T019 [US1] Run the summarization confirmation, about 25 min, as in quickstart step 2:
  1. `dl preflight`;
  2. then `dl summarize benchmarks/experiments/default_llm_summarization.yaml`, without
     `--limit`.

  Check:
  - `complete` is true, with 6 rows per variant and none `failed`;
  - `prompts.jsonl` holds every inference of both variants, and no judge inference.
  - **Done 2026-11-09**: preflight `ok` on every line, then
    `default_llm_summarization_20261109T060210125028Z`, `complete: true`, 6 rows per variant,
    none failed.
    - `prompts.jsonl`: 50 lines, 29 from gpt-oss:20b under its variant and 21 from gemma4:12b
      under its own, so none of them is the judge's.
    - gpt-oss's `prompt_tokens − estimate_tokens` is 75 on every line. gemma4's runs from −40
      to +277.
    - Four gpt-oss map steps stopped at `length`, at 900 tokens: one in "Fruitful functions",
      three in "Inheritance". These go to the reading (T022).
- [X] T020 [US1] Run `dl probe --workspace 71026d902d`, about 20 min, as in quickstart step 3.
  Check:
  - `probe.jsonl` has, per model, 1 `warmup`, 6 `whole_library`, 60 `marker` and 1 `analytical`
    line;
  - `environment.json` says `complete: true`;
  - `git status` shows nothing changed in `data/`.
  - **Done 2026-11-09**: `default_llm_probe_20261109T062308173324Z`, `complete: true`, with the
    same digests as preflight.
    - Per model, 1 `warmup`, 6 `whole_library`, 60 `marker` and 1 `analytical` line, none with
      an error. Every wait is timed except the warm-ups', which aren't by design.
    - `git status` shows nothing in `data/`, and `data/metadata/catalog.db` keeps its
      modification time of 2026-11-07 09:42:29.
- [X] T021 [US1] Run `dl packets` with the directories from T018 to T020, and with `--earlier`
  `benchmarks/results/summarization_20261108T170744515174Z` and
  `benchmarks/results/summarization_20261108T213459590645Z`, as in quickstart step 4.
  - Copy its `reading.skeleton.yaml` to `specs/002-gemma4-default-llm/reading.yaml`.
  - Note any packet that reports rebuilt passages differing from its row.
  - **Done 2026-11-09**: `default_llm_reading_20261109T064021244039Z`.
    - 15 multi-section packets, 5 summary packets and `probe.md`.
    - No packet reports rebuilt passages that differ from its row.
    - The skeleton has 50 entries:
      - 30 answers;
      - 10 summaries: two chapters from the confirmation, where gemma4 scored 0.5 or lower on
        factual consistency, and three from the earlier runs;
      - 2 `analytical` summaries;
      - 8 probe replies, all gemma4's. None of gpt-oss's 60 marker replies is shown as an answer.
- [X] T022 [US1] Do the reading. Read every packet against its passages or chapter, and fill
  `specs/002-gemma4-default-llm/reading.yaml`.
  - **Errors**: for each entry, list the FR-006 error kinds found, each with a `note` that says
    where, such as the passage or sentence.
  - **Labels**: for each `probe_reply`, set `label`: `abstains` if it says the passages don't hold
    the answer, `answers` if it answers.
  - **The two models**: read both models' entries for an item side by side, and judge each by the
    same standard.
  - **Where the reading departs from the judge's score**: note it, since the score still decides
    (spec, Edge Cases).
  - **Done 2026-11-09**: every entry has a note. The file's header says how it was read.
    - **Summaries**: only unsupported claims and misattributions are counted. Their citations
      come from the application's lookup, not from the model (constitution VII).
    - **gemma4-only errors**: one, an `unanswered_part` in `on_liberty_multi_section_02`, and a
      borderline one.
    - **The 8 probe replies**: all abstain, without the marker. Four were written in Portuguese
      instead of the Spanish or French asked for. Two make side claims the book doesn't support.
    - **Where the reading departs from the judge**: in several places, noted entry by entry.
      - gemma4's 0.5 for factual consistency on the summaries isn't borne out by what the
        reading found.
      - gpt-oss scored 1.000 on summaries with unsupported claims.
- [X] T023 [US1] Run `uv run python devtools/default_llm.py verdict … --integration pending
  --commit <T017's hash>`, as in quickstart step 5. Commit `reading.yaml` and `verdict.md` as
  `docs: record the default LLM confirmation's reading and verdict`.
  - **Done 2026-11-09**: **keep gpt-oss:20b**, since (b) and (d) failed.
    - **(a) passed**: nothing gated is worse.
    - **(b) failed**: the summary speed wins don't repeat with an interval excluding zero:
      −13.5 s (−33.4 to +2.1) and −1.33 steps (−3.33 to +0.000).
    - **(c) passed**: one gemma4-only error, against a threshold of 3.
    - **(d) failed**: 8 unrecognized abstentions for gemma4 and 0 for gpt-oss (Spanish 2, French 2,
      German 4).
    - **(e)**: not run.
  - **The tool's rendering, fixed before this verdict was written**:
    - `render_verdict` printed an unrun (e) as "Failed: pending", and named it among the failed
      conditions. contracts/records.md says it is `pending`, and that the verdict names the
      conditions that failed.
    - The fix and its test are in their own commit. `decide` and the rule are unchanged, and the
      runs started from `f6f53a8`.

**Checkpoint**: `verdict.md` gives (a) to (d).
- **If any failed**, the verdict is "keep gpt-oss:20b": skip Phase 4, and go to Phase 5.
- **If all passed**, the verdict is "pending": go to Phase 4.

---

## Phase 4: User Story 3 - Answers and summaries from gemma4:12b (Priority: P3)

**Only if T023's verdict is "pending".** This phase applies the switch, and its integration run is
condition (e). If (e) fails, T034 reverts it.

**Skipped, 2026-11-09**: T023's verdict is "keep gpt-oss:20b", since (b) and (d) failed. T024 to
T034 stay unchecked, because none of them ran.

**Goal**: gemma4:12b answers and summarizes by default, gpt-oss:20b stays the judge, and
`pull-models --all` is the checked, documented way to get the judge.

**Independent Test**: on the stack, with `config/models.yaml` switched:
- a question and a summary come from gemma4:12b;
- `make test-integration` passes;
- a generation benchmark at `LIMIT=1` runs, judged by gpt-oss:20b.

### Tests for User Story 3 (write first, and see them fail)

- [ ] T024 [US3] In `tests/unit/test_config.py`, in the file's style (`config_dir`, `edit_config`,
  `pytest.raises(ConfigurationError, match=...)`):
  - the project's `llm_profiles` all set `exact_token_count`: true for `gpt-oss:20b`, false for
    `gemma4:12b`;
  - a profile without the key is refused at startup, with a message naming
    `exact_token_count` (data-model.md: "**exact_token_count** (bool, required)");
  - the project's `llm.model` is `gemma4:12b`.
- [ ] T025 [P] [US3] In `tests/unit/test_benchmark.py`, add a test parametrized over `EXPERIMENTS`
  that, for every experiment with a `judge`, `judge.model` is in the project's
  `settings.llm_profiles`, and `judge.embedding_model` in `settings.embedding_profiles` (research
  R10).
- [ ] T026 [P] [US3] In `tests/unit/test_ollama_runtime.py`, change the missing-model test (line 48)
  to match `pull-models --all` as well as `pull-models`.

### Implementation for User Story 3

- [ ] T027 [US3] In `app/config/settings.py`, add `exact_token_count: bool` to `LLMProfile`,
  required, with no default.
  - Add a line to the class docstring: whether the tokenizer counts a prompt exactly as the
    runtime does, which the integration test checks.
  - Don't touch `TokenizerConfig`, which the index fingerprint and the workspace keys include
    (research R9, constitution III).
- [ ] T028 [US3] In `config/models.yaml`:
  - set `llm.model: gemma4:12b`;
  - add `exact_token_count` to every `llm_profiles` entry, after `tokenizer`, with the comments
    of [contracts/configuration.md](contracts/configuration.md): true for gpt-oss:20b, false for
    gemma4:12b, and provisionally true for `qwen3.5:9b` and `qwen3:14b` until T033 measures them.

  Change nothing else (FR-009).
- [ ] T029 [P] [US3] In `tests/unit/test_llm_provider.py:52`, build the `LLMProfile` with
  `exact_token_count=True`.
- [ ] T030 [P] [US3] In `app/utils/ollama_runtime.py`, change the `ModelNotFoundError` message to:
  ``f"Model '{model}' is not on the Ollama server. Download it with `book-rag pull-models`, or with
  `book-rag pull-models --all` if only the benchmarks use it."``
- [ ] T031 [P] [US3] In `tests/integration/test_generation.py`, make
  `test_the_token_estimate_matches_the_runtime_count` run once per entry of
  `settings.llm_profiles`, parametrized by model name (research R9):
  - **The provider**: built with `create_llm_provider(apply_overrides(settings, {"llm": {"model":
    model}}), runtime)`.
  - **Skip** with `pytest.skip`, naming the model, when `runtime.model_info(model)` raises
    `ModelNotFoundError`.
  - **Tolerance**: an `exact_token_count` profile keeps `abs=2`. Any other profile uses
    `rel=settings.generation.context.safety_margin` of the measured count.
- [ ] T032 [P] [US3] In `README.md` (FR-010, FR-013):
  - **Questions**: rewrite the sentence ending "for `gpt-oss` they match Ollama's count exactly".
    Say that the default, gemma4:12b, has an approximate tokenizer that
    `generation.context.safety_margin` absorbs, and that each LLM profile says whether its count
    is exact (`exact_token_count`).
  - **Configuration**: add one sentence that the default LLM is gemma4:12b, chosen by the
    confirmation recorded in `docs/decisions.md`, with gpt-oss:20b kept as the benchmarks' judge.
  - **Benchmarks**: after the `pull-models --all` line, say that `--all` brings every candidate and
    every judge, and that plain `make pull-models` brings only the default LLM and the embedding
    model, not the judge.
- [ ] T033 [US3] Run the switch's checks, which are condition (e):
  1. `make lint-check` and `make test`;
  2. `docker compose exec app book-rag pull-models --all`, which should download nothing new;
  3. `make restart`;
  4. `make test-integration`;
  5. `docker compose exec app book-rag doctor --inference`, which should report gemma4:12b.

  Then:
  - Set each qwen profile's `exact_token_count` in `config/models.yaml` from its measured count:
    true if within 2 tokens, false otherwise. Rerun the token test for them.
  - Run `make benchmark EXPERIMENT=default_llm_generation LIMIT=1`. It must start, with
    gpt-oss:20b judging. It is a sample that decides nothing: don't read its numbers.

  A failure that comes only from assuming gpt-oss is the default is fixed in the check (FR-012).
  Any other failure fails (e).
- [ ] T034 [US3] Run `verdict` again, with `--integration passed` or `--integration failed`.
  - **On "switch to gemma4:12b"**: commit T024 to T033 as `feat: make gemma4:12b the default LLM`,
    and `verdict.md` with it.
  - **On "keep"**: revert T024 to T033 (`git checkout -- app config tests README.md`, or
    `git revert` if they were committed), and record the failure as a follow-up for T037. Then
    commit `verdict.md`.

**Checkpoint**: the final verdict is in `verdict.md`, and `config/` matches it.

---

## Phase 5: User Story 2 - The default's reason, on record (Priority: P2)

**Goal**: whichever way the rule went, a reader of `docs/decisions.md` knows what the default LLM
is, which runs chose it, and why. `docs/benchmark-results.md` holds the confirmation.

**Independent Test**: a reader of `docs/decisions.md` alone can say what the default is, which runs
chose it, and why (SC-005). On a "keep", `git diff a647e1a -- app config tests` shows only
`tests/unit/test_default_llm_devtool.py` (FR-016).

- [X] T035 [P] [US2] In `docs/decisions.md`, add an entry to the Generation section, in the file's
  style (a bold sentence, then why), headed **The default LLM is chosen by a rule fixed before its
  runs.** It covers:
  - **The default**: gemma4:12b or gpt-oss:20b, as `verdict.md` says.
  - **The runs it rests on**: the two confirmation runs' directories and dates, and T017's commit.
  - **The rule**, in one sentence per condition, with how each came out, from `verdict.md`.
  - **Why gpt-oss:20b was the first default**: `.TASK/task.md` § 3.1 recommended it, for
    "Reasoning and summarization", with gemma4:12b as the alternative, before the comparison its
    § 15.3 asked for.
  - **On a switch**:
    - the departure from the first version's spec (FR-014);
    - gpt-oss:20b kept as the judge, since a new judge would have to pass the known-answer checks
      again;
    - `exact_token_count` on `LLMProfile` rather than `TokenizerConfig`, because of the index
      fingerprint;
    - the judge brought by `pull-models --all`.
  - **On a "keep"**: which conditions failed, and what would reopen the question.
- [X] T036 [P] [US2] In `docs/benchmark-results.md`, add a section `## Default LLM` before
  Recommendations. It records:
  - T017's commit;
  - the dates, the Ollama version and the digests;
  - both runs' tables for the two models, with the paired differences of (a) and (b);
  - the reading's summary: error kinds per model, multi-section and summaries;
  - the probe's results:
    - the trap per model;
    - the unrecognized abstentions per language and model;
    - the `analytical` summaries;
    - the largest undercount against the margin;
    - the median waits.

  Then:
  - **The opening paragraph**: add the commit the confirmation ran on.
  - **The "(default)" labels** in the Generation and Summarization tables follow the verdict.
  - **Recommendations**:
    - on a switch, "The defaults stay as they are" and the gemma4 item say it was done;
    - on a "keep", the gemma4 item points to the reason in `docs/decisions.md`.
  - **Reproducing**: add the two confirmation experiments, and the script's subcommands from
    [quickstart.md](quickstart.md).
- [X] T037 [US2] Under `verdict.md`'s Follow-ups, list every failure the reading or the probe found
  that needs a prompt or parser change, such as footnote markers cited as sources, or the marker in
  a language it isn't recognized in. Give each one a line to become its own `fix/` or `feat/`
  branch. Fix none of them here (SC-006).
- [X] T038 [US2] Check this story's independent test:
  - SC-005, by reading `docs/decisions.md` alone;
  - on a "keep", FR-016, with `git diff a647e1a -- app config tests`;
  - on a switch, that the diff in `app/` is only T027 and T030.

  Commit T035 to T037 as `docs: record the default LLM and why`.
  - **Done 2026-11-09**:
    - **SC-005**: the entry in `docs/decisions.md` names the default, the two runs and their
      commit, and how each condition came out.
    - **FR-016**: `git diff a647e1a -- app config tests` shows only
      `tests/unit/test_default_llm_devtool.py`, the script's own tests.
    - **FR-017**: nothing touched the embedding model, chunking or the index.

**Checkpoint**: both outcomes are recorded where constitution VIII asks.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T039 Run `make lint-check`, `make test` and `uv run pre-commit run --all-files`, and fix
  whatever fails. Check that every step of [quickstart.md](quickstart.md) that applies to the
  verdict ran as written, and correct the quickstart where it didn't.
  - **Done 2026-11-09**: all three pass, with 836 unit tests.
    - Steps 1 to 3, 5 and 7 ran as written.
    - Step 4 now says to start from the packets' `reading.skeleton.yaml`, and that a marker
      reply's claims are checked against the workspace's chunks, since the probe keeps no
      passages.
- [X] T040 Write the pull request's title, by outcome (research R13). Don't open the PR unless the
  user asks for it.
  - a switch is `feat: make gemma4:12b the default LLM`;
  - a "keep" is `docs: record why gpt-oss:20b stays the default LLM`.
  - **Done 2026-11-09**: a "keep", so `docs: record why gpt-oss:20b stays the default LLM`. No PR
    opened.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after T001. T002, T003 and T004 are independent, and T005 needs all
  three.
- **US1 (Phase 3)**:
  - The tests T006 to T009 come first, then the implementation T010 to T015, all in two files and
    so one after another.
  - T016 needs T010 to T015, and T017 needs T016.
  - The runs follow in a fixed order: T018, T019, T020, T021. The reading T022 needs T021, and the
    verdict T023 needs T022.
- **US3 (Phase 4)**:
  - Only if T023 says "pending".
  - Its tests T024 to T026 come first.
  - T027 comes before T028, and T029 to T032 can follow in parallel.
  - T033 needs all of them, and T034 needs T033.
- **US2 (Phase 5)**: after T023 on a "keep", or after T034 on a switch. T035 and T036 can run in
  parallel. T037 can start after T023, and T038 comes last.
- **Polish (Phase 6)**: after Phase 5.

### User Story Dependencies

- **US1 (P1)**: depends only on Phase 2.
- **US3 (P3)**: depends on US1's verdict on (a) to (d), and decides (e).
- **US2 (P2)**: depends on the final verdict, from US1 alone or from US1 and US3.

### Parallel Opportunities

- T002, T003 and T004: three different files.
- T025 and T026, then T029 to T032: different files, once T027 and T028 are in.
- T035 and T036: two different documents.
- The long runs T018 to T020 can't overlap: they share the GPU, and preflight has to pass right
  before each one.

---

## Parallel Example: User Story 3

```bash
# Tests in different files, after T024:
Task: "T025 every experiment's judge has a profile, in tests/unit/test_benchmark.py"
Task: "T026 the missing-model message names pull-models --all, in tests/unit/test_ollama_runtime.py"

# After T027 and T028:
Task: "T029 LLMProfile with exact_token_count, in tests/unit/test_llm_provider.py"
Task: "T030 the missing-model message, in app/utils/ollama_runtime.py"
Task: "T031 the token test per pulled profile, in tests/integration/test_generation.py"
Task: "T032 the default, its token counts and the judge's download, in README.md"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 and Phase 2: the experiments and the script's skeleton, tests green.
2. Phase 3 up to T017: the tooling tested, smoke-checked and committed, with `app/` and `config/`
   untouched.
3. T018 to T023: the runs, the reading and the verdict on (a) to (d).
4. **Stop and validate**: `verdict.md` reproduces from the recorded files.

### Incremental Delivery

1. **US1**: a verdict on (a) to (d), from a rule committed before the runs.
2. **US3, only if they passed**: the switch, and (e) on the real models.
3. **US2**: the records. The feature isn't done without them (constitution VIII).

Each step is committed, so a "keep" stops cleanly after US1 and goes straight to US2.

---

## Notes

- [P] tasks are in different files, with no dependency on an unfinished task.
- The [Story] label maps a task to its user story.
- Tests are written first, and must fail before the implementation.
- Commit after each task or logical group, with conventional messages of at most 72 characters.
- Nothing in `app/` or `config/` changes before the runs (FR-004). Nothing in prompts, output
  parsing, the judge or `benchmark-report` changes at all.
- No run is repeated to settle the judge's noise. Only a run that didn't complete is replaced, once
  (FR-005).
- Smoke and sample runs (T016, T033) decide nothing, and their numbers aren't read.

---

## Phase 7: Convergence

- [X] T041 CRITICAL: Record the probe's full environment, as a benchmark result records it, per
  Constitution VI (partial)
  - **The gap**: `probe` writes `environment.json` with only the date, the Ollama version, the
    digests, the workspace and `complete` (`_probe` in `devtools/default_llm.py`). A benchmark's
    `results.json` also records the dataset's checksum, the full configuration, each model's
    quantization, the hardware, Python and the package versions (`_describe_environment` in
    `app/evaluation/benchmark.py`). The probe's waits, token counts and marker replies depend on
    them.
  - **The tool**: make `probe` write those fields too, and the commit it ran from. Call
    `_describe_environment` rather than copying it, if that needs no change to `app/` (FR-016).
    Test the fields in `tests/unit/test_default_llm_devtool.py`.
  - **The probe already run**: don't run it again. In the Default LLM section of
    `docs/benchmark-results.md`, say what `default_llm_probe_20261109T062308173324Z` ran with,
    from what is recorded:
    - it ran from `f6f53a8`, in the same `app` and `ollama` containers as
      `default_llm_summarization_20261109T060210125028Z` just before it (neither restarted between
      them), whose `results.json` holds the hardware, Python, packages and configuration;
    - the dataset's checksum, recomputed, is `767e4cceb315`, and `benchmarks/datasets` last
      changed in `826c977`, before both.
  - Leave `verdict.md` and `reading.yaml` as they are. The verdict doesn't move: (d) failed on
    unrecognized abstentions, which no environment field changes.
  - **Done 2026-11-09**:
    - **The tool**: `probe_environment` adds to the runner's own `_describe_environment` the
      override applied for each model, the workspace, the commit and `complete`. The probe takes
      `--commit`, since the container has no git. `app/` is unchanged.
    - **Tests**: two new ones, written first and seen failing. 838 unit tests pass, and lint is
      clean.
    - **Smoke pass** (`default_llm_probe_smoke_20261109T115315936970Z`):
      - its `environment.json` has every field `results.json` has, plus the four above;
      - the dataset is `767e4cceb315`, the digests are the confirmation's, and quantization,
        hardware, Python and packages are filled;
      - no errors, and nothing was written to `data/` or the workspace;
      - it is a smoke pass, and decides nothing.
    - **The records**:
      - `docs/benchmark-results.md` says what the confirmation's probe ran with, and that its own
        record is the shorter one;
      - the contract, the quickstart and Reproducing pass `--commit`.
    - `verdict.md` still reproduces from the recorded files, and `reading.yaml` is unchanged.
