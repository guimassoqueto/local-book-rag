---

description: "Task list for historical spelling in lexical search"
---

# Tasks: Historical spelling in lexical search

**Input**: Design documents from `specs/001-historical-spelling/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/configuration.md](contracts/configuration.md), [quickstart.md](quickstart.md)

**Tests**: included. FR-003 asks for the pairs at risk to be kept as permanent tests, and the
constitution's Development Workflow asks for automated tests for every significant component.
Within each story, the tests come first and must fail before the implementation.

**Organization**: grouped by user story, so that each story can be implemented and tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story a task belongs to (US1, US2, US3)

## Path Conventions

A single Python project: `app/`, `config/`, `tests/unit/`, `benchmarks/experiments/` and
`devtools/` at the repository root (plan.md, Project Structure). In the Bash tool, run
`export ASDF_DATA_DIR="$HOME/.asdf" PATH="$HOME/.asdf/shims:$HOME/.asdf:$PATH"` before `make` or
`uv`.

---

## Phase 1: Setup

**Purpose**: get the word list for the measurement. It stays outside the repository (research R1).

- [X] T001 Download and unpack Debian's `wbrazilian` 3.0~beta4-25, outside the repository, into
  `/tmp/wbrazilian`:
  `mkdir -p /tmp/wbrazilian && cd /tmp/wbrazilian && apt-get download wbrazilian && dpkg-deb -x wbrazilian_*.deb extracted`.
  Check that `/tmp/wbrazilian/extracted/usr/share/dict/brazilian` exists, with about 275,000 lines.
  Install nothing, and don't copy it into the repository.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the setting and its plumbing, which every story needs.

**⚠️ CRITICAL**: no user story can start until this phase is complete.

- [X] T002 In `app/config/settings.py`, add a required `historical_spelling: bool` field, with no
  default, to `BM25Config`. Add a `model_validator(mode="after")` to `BM25Config` that raises
  `ValueError("bm25.historical_spelling needs bm25.stemming")` when `historical_spelling` is true
  and `stemming` is false (data-model.md: "`historical_spelling: true` together with
  `stemming: false` is refused, with a message that names both keys").
- [X] T003 [P] In `config/retrieval.yaml`, add `historical_spelling: true` under `retrieval.bm25`,
  after `stemming`. Use the comment from contracts/configuration.md: Portuguese books only, needs
  stemming, no reindex.
- [X] T004 [P] In `tests/unit/test_config.py`, add three tests in the file's style (`config_dir`,
  `edit_config`, `pytest.raises(ConfigurationError, match=...)`):
  - the project's configuration has `settings.retrieval.bm25.historical_spelling` true
  - removing the key fails, matching `historical_spelling`
  - `historical_spelling: true` with `stemming: false` fails, matching `bm25.stemming`
- [X] T005 [P] In `tests/unit/test_index_service.py`, add
  `test_historical_spelling_can_change_without_a_reindex`, written like
  `test_the_query_template_can_change_without_a_reindex`. Build the index with the project's
  settings, then build an `IndexService` with `retrieval.bm25.historical_spelling` turned off,
  and assert `not service.needs_reindex()` (FR-006; data-model.md: the setting doesn't join the
  index fingerprint).
- [X] T006 In `tests/unit/test_bm25.py`, add `historical_spelling=False` to the module's `CONFIG`,
  so that the existing tests keep testing today's behavior. Add a second
  `HISTORICAL = CONFIG.model_copy(update={"historical_spelling": True})` for the new tests.
- [X] T007 In `app/retrieval/bm25.py`, give `Tokenizer.__init__` a keyword parameter,
  `historical_spelling: bool = False`, and store whether folding applies: `language == "pt"`,
  stemming on and `historical_spelling` true. Make `BM25Retriever.retrieve` and
  `BM25Retriever._tokenize_book` pass `self._config.historical_spelling`. No folding yet, so the
  tokens are unchanged.
- [X] T008 Run `make test` over `tests/unit/`. Everything passes, the three new config tests and the
  fingerprint test included (depends on T002 to T007).

**Checkpoint**: the setting exists, is validated, and reaches the tokenizer.

---

## Phase 3: User Story 1 - Ask in today's spelling about a book in the old one (Priority: P1) 🎯 MVP

**Goal**: a modern spelling in the question finds the old spelling in a Portuguese book, and every
modern word stays apart from every other (FR-001 to FR-005, FR-008, SC-003 to SC-006).

**Independent Test**: with `HISTORICAL`, a "Sofia" search of Portuguese chunks returns the one
that says "Sophia", with its text unchanged. All 28 pairs give equal tokens, and every curated
pair gives different ones.

### Tests for User Story 1 (write first, and see them fail)

- [X] T009 [US1] In `tests/unit/test_bm25.py`, add a test parametrized over the spec's 28
  pairs, with each pair as the test's id. The pairs: sofia/sophia, ele/elle, ela/ella, eles/elles,
  benedita/benedicta, teófilo/theophilo, comissão/commissão, frase/phrase, marquês/marquez,
  diretor/director, apesar/apezar, teresa/thereza, filósofo/philosopho, cupê/coupé, ano/anno,
  fato/facto, ofício/officio, aparecer/apparecer, cena/scena, compreendê/comprehende,
  alegoria/allegoria, assinasse/assignasse, tipográfico/typographico,
  constelação/constellação, alegando/allegando, tipo/typo, catástrofes/catastrophes and
  súdito/subdito. For each, `Tokenizer("pt", True, historical_spelling=True).tokenize()` must give
  equal tokens for both spellings (SC-004).
- [X] T010 [US1] In `tests/unit/test_bm25.py`, add a test parametrized over the curated
  collision pairs, checking that each gives different tokens with historical spelling on (FR-003,
  SC-005):
  - **The known ones**: facção/facão, pacto/pato, sessão/seção, seção/cessão, signo/sino,
    coser/cozer, selo/zelo, gnomo/nome and garoupa/garupa.
  - **One per pattern that needed kept keys** (research R3): Mathias/mate, Levy/leva, Bello/bel,
    espectador/espetar, compacta/compatível, cacto/catar, magna/man, abdicar/adição, reze/rês and
    Bahamas/Baamas.
- [X] T011 [US1] In `tests/unit/test_bm25.py`, add retriever tests on Portuguese chunks with
  `HISTORICAL`, written like `test_portuguese_is_stemmed_and_accents_do_not_matter`:
  - a "Sofia" query returns the chunk containing "Sophia", whose `chunk.text` is exactly the text
    given (FR-005)
  - a "Sophia" query still returns it (FR-004)
  - "filósofo" and "Teresa" return chunks containing "philosopho" and "Thereza" (spec, US1
    scenario 3)
- [X] T012 [US1] In `tests/unit/test_bm25.py`, add tests that the tokens are unchanged, byte
  for byte, from those of a tokenizer without the feature (FR-008, SC-003):
  - language `"en"` with the feature on
  - no language, with the feature on
  - `"pt"` with the feature off
  - `"pt"` with stemming off and the feature on, as `model_copy` allows despite the validator
  - for every case, on a text containing old spellings such as "Sophia elle anno philosopho typo"

### Implementation for User Story 1

- [X] T013 [US1] In `app/retrieval/bm25.py`, add the patterns as module constants, in
  data-model.md's order:
  - **Before stemming**: y → i.
  - **After stemming and accent stripping, compiled once**:
    - `ph`→`f`
    - `th`→`t`
    - "doubled b, c, d, f, g, k, l, m, n, p, t → single (not r or s)" (`([bcdfgklmnpt])\1`→`\1`)
    - `ct`→`t`
    - `gn`→`n`
    - `bd`→`d`
    - "sc → c at the start of the key, before e or i" (`^sc(?=[ei])`→`c`)
    - "z → s at the end of the key" (`z$`→`s`)
    - "h between two vowels → removed" (`(?<=[aeiou])h(?=[aeiou])`→ empty)
    - `oup`→`up`

  Add `_KEPT_KEYS: frozenset[str] = frozenset()` for now (T016 fills it), with a comment pointing
  to `devtools/measure_historical_spelling.py`.
- [X] T014 [US1] In `app/retrieval/bm25.py`, make `Tokenizer.tokenize` fold keys when folding
  applies, following data-model.md's "How a word becomes a key":
  1. The plain key: stemmed, stripped of accents.
  2. If it is in `_KEPT_KEYS`, keep it.
  3. Otherwise, if the word contains `y`, re-stem it with y → i, and strip its accents.
  4. Apply the patterns that run after stemming.

  - **Speed (research R5)**: compute each distinct word's key once per `tokenize` call, as a dict
    over `set(tokens)`.
  - **When folding doesn't apply**: keep today's code path unchanged.
  - **For the script (T015)**: expose the steps as module-level functions, so the script reuses
    them instead of repeating them.
  - **The docstring**: say what folding does and that it never touches the text.
- [X] T015 [US1] Write `devtools/measure_historical_spelling.py`, taking the word list's path as
  its only argument (research R7):
  - **What it reuses**: the patterns and the key steps, imported from `app/retrieval/bm25.py`.
  - **Over the list's words**: casefold the words. Compute each plain key. Repeat until no
    collision is left: any modern key that would fold to the same key as another modern key is
    kept unchanged.
  - **What it prints**: the word count, the key count, how many keys change, the kept keys
    grouped by the pattern that touches them, the remaining collisions, and the 28 pairs matched.
  - **When it exits with an error**: if a collision remains, if fewer than 28 pairs match, or if
    the computed kept keys differ from `_KEPT_KEYS`. Then it prints both sets' differences.
  - **Its docstring**: how to get the list (T001), and that it isn't kept in the repository.
- [X] T016 [US1] Run `uv run python devtools/measure_historical_spelling.py
  /tmp/wbrazilian/extracted/usr/share/dict/brazilian`. Paste the computed kept keys into
  `_KEPT_KEYS` in `app/retrieval/bm25.py`, sorted, and run it again until it exits 0. Research R3
  found 97 with this version. Keep the output for T023 (depends on T001, T013 to T015).
- [X] T017 [US1] Run `uv run pytest tests/unit/test_bm25.py -q`, then `make test`. T009 to T012
  pass, and so does everything that passed before. Then check the real book, which is US1's
  Independent Test, without the stack:
  - **Tokenize it**: read the text of `benchmarks/books/quincas-borba.epub` as research R5 did,
    and tokenize it with `Tokenizer("pt", True)` and with `historical_spelling=True`.
  - **The 28 words**: for each modern word in the spec's Context table, its key must be absent
    from the plain tokens and present among the folded ones.
  - **Speed (SC-006)**: time both tokenizations, best of five. The book has about 81,700 tokens
    in about 450 passages, so multiply the difference by 1,300 / 450 before comparing it with
    50 ms. That overestimates, since a larger book repeats more of its words, and its keys are
    computed once per distinct word.
  - **Done 2026-11-08**:
    - Speed: 47 ms off, 39 ms on, so 9 ms faster (−25 ms scaled), within SC-006.
    - The 28 words: all present among the folded tokens. 27 were absent from the plain ones.
      apesar wasn't: the book prints it twice besides "apezar" 15 times. The spec's Context
      had counted it among the missing words by mistake, and is corrected.
    - The pair lists live in `tests/historical_spelling.py`, shared with the measurement script.
      The bd collision is abdicai/adição, which the measurement found, not abdicar/adição.

**Checkpoint**: User Story 1 works and is tested, and is the MVP.

---

## Phase 4: User Story 2 - Measure it against search without it (Priority: P2)

**Goal**: the retrieval benchmark compares search with and without the feature, and the result
decides the default (SC-001, SC-002, SC-003).

**Independent Test**: the experiment's four variants load and validate, which
`test_every_variant_is_a_valid_configuration` in `tests/unit/test_benchmark.py` already checks for
every file in `benchmarks/experiments/`. A run's rows then give the paired differences for
*Quincas Borba*.

- [X] T018 [P] [US2] Create `benchmarks/experiments/historical_spelling.yaml` with
  `name: historical_spelling`, `kind: retrieval` and a description: old Portuguese spellings in
  lexical search, with and without, alone and in the default configuration, the reranker on the
  GPU as in `retrieval.yaml`. Give it these four variants, exactly as in data-model.md:
  - `bm25_exact_spelling`:
    `retrieval: {strategy: bm25, reranker: {enabled: false}, bm25: {historical_spelling: false}}`
  - `bm25_historical_spelling`: the same with `historical_spelling: true`
  - `default_exact_spelling`:
    `retrieval: {strategy: hybrid, fusion: {method: rrf}, reranker: {enabled: true}, bm25: {historical_spelling: false}}`,
    plus `reranker: {device: cuda}`
  - `default_historical_spelling`: the same with `historical_spelling: true`
- [X] T019 [US2] Run `uv run pytest tests/unit/test_benchmark.py -q`. The new file validates
  (depends on T018).
- [X] T020 [US2] With the stack up and the benchmark books fetched (quickstart prerequisites), run
  `make benchmark EXPERIMENT=historical_spelling`, which reads
  `benchmarks/experiments/historical_spelling.yaml`. Note the result directory under
  `benchmarks/results/`, and the commit it ran on (depends on T017, T018).
- [X] T021 [US2] Run quickstart.md's scenario 4:
  - `benchmark-report --baseline bm25_exact_spelling`
  - the paired-difference snippet on the `quincas_borba` rows

  Decide each criterion:
  - **SC-001**: Recall@5 has an interval above zero, for `bm25_historical_spelling`. Recall@5 alone
    decides. MRR and the other metrics are reported.
  - **SC-002**: no metric has an interval wholly below zero, for `default_historical_spelling`.
  - **SC-003**: the `think_python` and `on_liberty` rows are identical across each pair of variants.

  If SC-001 or SC-002 fails, set `historical_spelling: false` in `config/retrieval.yaml` (spec,
  Assumptions). Keep the numbers for T024 (depends on T020).
  - **Done 2026-11-09**, run `historical_spelling_20261109T021510676164Z`, on commit `608e9a4`:
    - **SC-001 fails**: Recall@5 +0.030 on *Quincas Borba*, interval −0.030 to +0.120.
    - **SC-002 passes**: 0.000 on every metric.
    - **SC-003 passes**: 0 of 50 English questions differ.
    - **Result**: `historical_spelling: false` in `config/retrieval.yaml`, as the spec settled.

**Checkpoint**: the effect is measured, and the default is decided.

---

## Phase 5: User Story 3 - Search a modern edition with words copied from an old one (Priority: P3)

**Goal**: an old spelling in the question finds the modern spelling in a Portuguese text (FR-001,
the other direction).

**Independent Test**: with `HISTORICAL`, a "Theophilo" search of a modern Portuguese chunk returns
the one that says "Teófilo".

- [X] T022 [P] [US3] In `tests/unit/test_bm25.py`, add retriever tests on modern Portuguese chunks
  with `HISTORICAL`: "Theophilo" returns the chunk with "Teófilo", and "philosopho" the one with
  "filósofo" (spec, US3 scenario 1). Run `uv run pytest tests/unit/test_bm25.py -q`. They pass with
  no new code, since folding is symmetric: if one fails, T014 is wrong (depends on T014).

**Checkpoint**: all three stories work, each tested on its own.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: the records that constitution VIII requires before the feature is done.

- [X] T023 [P] In `docs/decisions.md`, add an entry to the Indexing section, near "BM25 is built
  in memory for each search scope", in the file's style (a bold sentence, then why). It covers:
  - **The patterns, and where they apply**: y → i before stemming, because Snowball's Portuguese
    stemmer doesn't take y for a vowel, and tipo/typo failed otherwise. The others go on the key,
    where they collide less.
  - **The measurement**: `wbrazilian` 3.0~beta4-25, with its word and key counts, how many keys
    change, 0 collisions and 28 of 28 pairs.
  - **How collisions are resolved**: the kept keys and their count by pattern. Some are variants
    of one word or name, such as Souza/Sousa and Tereza/Teresa, kept apart to stay on the safe side.
  - **facto/fato**: a known false match for European Portuguese readers (spec, Edge Cases).
  - **Why it needs stemming, and stays out of the index fingerprint.**
  - **Where the measurement lives**: `devtools/measure_historical_spelling.py` reruns it after any
    change to a pattern.
- [X] T024 [P] In `docs/benchmark-results.md`, add a section for the experiment, with the commit it
  ran on (T020) and the numbers and intervals from T021:
  - *Quincas Borba* for both pairs of variants, and the default configuration's differences
    whatever they are (SC-002)
  - that the English books are unchanged

  Update the Known limitations item "The novel's old spelling" to what remains, such as the names
  kept apart. Add the run to "Changes these benchmarks led to" if the default changed.
- [X] T025 [P] In `README.md`, in the Retrieval section:
  - **The `bm25` row of the strategy table**: add old Portuguese spellings matching the modern
    ones.
  - **A short paragraph**, saying:
    - what `bm25.historical_spelling` does, only for Portuguese books
    - that turning it on or off needs no reindex, only `docker compose restart app`
    - that it needs `stemming`
    - that the text shown is never changed
- [X] T026 Run `make lint-check`, `make test` and `uv run pre-commit run --all-files`, and fix
  whatever fails. If *Quincas Borba* is in the library, run quickstart.md's scenario 5 (depends on
  T023 to T025).
  - **Done 2026-11-09**:
    - lint clean, 776 unit tests passing, `pre-commit run --all-files` clean
    - scenario 5 on `book_003`: with the setting on, the "D. Sophia" passage's BM25 score rose
      from 1.276 to 1.887, and two more Sophia passages entered through BM25

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none. T001 is needed only by T016.
- **Foundational (Phase 2)**: blocks every story. T002 comes before T003 to T007, which can run in
  parallel except T006 and T007: T006 edits the tests that exercise T007.
- **US1 (Phase 3)**: after Phase 2. Its tests T009 to T012 come before T013 to T017.
- **US2 (Phase 4)**: needs Phase 2 for the setting. T018 and T019 can be written alongside US1,
  but the run (T020) needs US1 done.
- **US3 (Phase 5)**: needs T014, and only adds tests.
- **Polish (Phase 6)**: T023 needs T016's output, T024 needs T021's numbers, and T026 comes last.

### User Story Dependencies

- **US1 (P1)**: depends only on Phase 2.
- **US2 (P2)**: the experiment file is independent. Measuring needs US1's folding, or both
  variants would be the same.
- **US3 (P3)**: the same folding read the other way, so it depends on US1's implementation, not
  on its tests.

### Parallel Opportunities

- T003, T004 and T005 in Phase 2, all [P], in different files from T002 once it's done.
- T009 to T012 share `tests/unit/test_bm25.py`, so they aren't [P]: write them one after another.
- T018 next to Phase 3, since it is a different file.
- T023, T024 and T025: three different documents.

---

## Parallel Example: User Story 1

```bash
# The US1 tests share one file, so they're written one after another:
Task: "T009 28 pairs give equal tokens, in tests/unit/test_bm25.py"
Task: "T010 curated collision pairs stay apart, in tests/unit/test_bm25.py"
Task: "T011 Sofia finds Sophia with the text unchanged, in tests/unit/test_bm25.py"
Task: "T012 other languages and switch off give identical tokens, in tests/unit/test_bm25.py"

# Alongside US1, a different file:
Task: "T018 the four-variant experiment, in benchmarks/experiments/historical_spelling.yaml"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 and Phase 2: the setting validated and wired, tests green.
2. Phase 3: the folding, the measurement and the kept keys, then the tests green.
3. **Stop and validate**: T017, including the SC-006 timing.

### Incremental Delivery

1. MVP: US1, matching that is tested and measured against the word list.
2. US2: the benchmark run decides whether the default stays on (SC-001, SC-002).
3. US3: the reverse direction, a test only.
4. Polish: README, decisions and benchmark results. The feature isn't done without them
   (constitution VIII).

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group, with conventional messages of at most 72 characters
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence

---

## Phase 7: Convergence

- [X] T027 In `specs/001-historical-spelling/contracts/configuration.md`, reword the "Not a boolean" row to match what the code does, which is what it does for every boolean in `config/`: `historical_spelling` accepts anything pydantic reads as a boolean (`true`, `"yes"`, `"1"`), and only other values (`"maybe"`, `3`) fail at startup. Leave `BM25Config` unchanged. Per plan: contracts/configuration.md (partial)
