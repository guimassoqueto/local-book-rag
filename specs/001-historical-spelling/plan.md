# Implementation Plan: Historical spelling in lexical search

**Branch**: `feat/historical-spelling` | **Date**: 2026-11-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-historical-spelling/spec.md`

## Summary

Lexical search on Portuguese books will treat old and modern spellings as one word (Sophia and
Sofia, elle and ele, facto and fato), in both directions. It does so by folding the keys that BM25
already computes, never the text.

- **The patterns:** ten patterns run on the stemmed, accent-free key: ph, th, doubled consonants,
  ct, gn, bd, a leading sc, z at the end, an h between vowels, oup. y → i runs before stemming,
  because the Portuguese stemmer doesn't take y for a vowel.
- **The kept keys:** 97 modern keys that would otherwise collide with another modern key pass
  through unchanged.
- **The measurement:** checked against the 274,246-word Brazilian word list, these give 0
  collisions and match all 28 of the spec's pairs ([research](research.md) R3).
- **The switch:** a required `bm25.historical_spelling` setting, refused without stemming, is on
  by default.
- **The benchmark:** a four-variant experiment measures it against search without it.

Nothing stored changes, so nothing is reindexed.

## Technical Context

**Language/Version**: Python 3.13 (asdf), managed by uv

**Primary Dependencies**: bm25s, PyStemmer (Snowball Portuguese) and pydantic, all already in
place. No new runtime dependency. The word list is used only by a development script, and isn't
committed.

**Storage**: none touched. The BM25 index is built in memory for each search scope, and ChromaDB
and the catalog are unchanged.

**Testing**: pytest (`make test`), and the retrieval benchmark
(`make benchmark EXPERIMENT=historical_spelling`) on the real books

**Target Platform**: Linux, the `app` container of the Docker Compose stack

**Project Type**: a single Python application. The commands and Gradio sit over `app/services`

**Performance Goals**: SC-006, at most 50 ms more for the first search of a 1,300-passage book.
Computing each distinct word's key once takes 39 ms for the whole novel, against 47 ms today (R5).

**Constraints** (from the plan's input):
- The code change stays in `app/retrieval/bm25.py`, `app/config/settings.py` and
  `config/retrieval.yaml`.
- No runtime dependency.
- No reindex.

Outside the code: tests, one experiment file, one development script, and the documentation.

**Scale/Scope**: one setting, eleven patterns, 97 kept keys, Portuguese books only

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Before research | After design |
| --- | --- | --- | --- |
| I. Local-first, model-independent | No inference, no model name. The new setting is validated at startup | Pass | Pass: a required field with a validator against `stemming: false` |
| II. The library is never at risk | No change to books, catalog or index. The benchmark stays in `benchmarks/workspace` | Pass | Pass: the experiment's four variants share one workspace |
| III. Index integrity | No embedding or chunking change. Nothing joins the fingerprint | Pass | Pass: the setting changes only how search matches, like the query template, so it stays out of the fingerprint |
| IV. One service layer | No change to `app/interface`, `app/main.py` or the services | Pass | Pass: the change is inside the retriever |
| V. Verified on real books | No prompt or model-output parser. A change to matching is checked on a real book | Pass | Pass: the retrieval benchmark on *Quincas Borba*, and the measurement on a real word list |
| VI. Measured, not assumed | An experiment with a baseline variant, the paired bootstrap, and a reproducible record | Pass | Pass: baselines `bm25_exact_spelling` and `default_exact_spelling`, read per book. No judge is involved, since retrieval metrics are deterministic. Ingestion is untouched, so the workspace stays valid |
| VII. Every answer traceable | The passages and citations the reader sees are unchanged | Pass | Pass: only keys are folded, never text |
| VIII. Decisions are recorded | README, `docs/decisions.md` and `docs/benchmark-results.md` are updated | Pass | Pass: they are planned as tasks, the measurement's record included |
| Development workflow | uv, ruff, `make test`, branch `feat/…`, a `feat:` PR | Pass | Pass: the dataset is unchanged, so `validate-benchmark` isn't needed |

No violation, so Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-historical-spelling/
├── plan.md              # This file
├── research.md          # Phase 0: word list, pattern placement, collisions, switch, speed, benchmark
├── data-model.md        # Phase 1: the setting, the patterns, the kept keys, the key pipeline
├── quickstart.md        # Phase 1: how to validate it
├── contracts/
│   └── configuration.md # Phase 1: the setting's contract
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
app/retrieval/bm25.py                           # Tokenizer: the patterns, the kept keys, a key per distinct word
app/config/settings.py                          # BM25Config.historical_spelling, refused without stemming
config/retrieval.yaml                           # historical_spelling: true, then false once the benchmark failed SC-001
benchmarks/experiments/historical_spelling.yaml # the four variants
devtools/measure_historical_spelling.py         # the FR-003 measurement, repeatable (R7)
tests/unit/test_bm25.py                         # pairs, curated collisions, switch, other languages, retrieval
tests/unit/test_config.py                       # the setting is required, and refused without stemming
README.md                                       # Retrieval: what lexical search does with old spellings
docs/decisions.md                               # the patterns, where they apply, the measurement and its kept keys
docs/benchmark-results.md                       # the experiment's results; the old-spelling limitation updated
```

**Structure Decision**: the feature lives where lexical matching already lives. `Tokenizer` gains
the folding, and `BM25Retriever` passes it the setting. `app/retrieval/factory.py` already hands
`config.bm25` to the retriever, so the wiring doesn't change. The patterns and the kept keys are
constants in `app/retrieval/bm25.py`, as the plan's input asks, and the development script imports
them from there instead of repeating them.

## Complexity Tracking

No violations.
