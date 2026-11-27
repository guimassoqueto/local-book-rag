# Bug Assessment: `make update` moved ragas back to 0.3.1, and `make test` stops at collection

- **Slug**: ragas-downgrade
- **Created**: 2026-11-26
- **Source**: pasted text (bead iss-30k, recorded while running `make test` for
  `specs/010-beads-issue-tracking`)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> Since 27780d3 (chore: update dependencies, #27), uv.lock pins ragas 0.3.1 where it pinned 0.4.4.
> ragas 0.3.1's ragas.llms.base has no InstructorBaseRagasLLM, which app/evaluation/ragas_llm.py
> imports, so collecting tests/unit/test_ragas_llm.py raises ImportError and make test stops before
> running anything (1 error during collection). The benchmarks' RAGAS judges import the same module.
> Likely the resolver's answer to the langchain-community<0.4.2 constraint in pyproject.toml; uv lock
> --upgrade --dry-run would show. Found while running make test for specs/010-beads-issue-tracking.

## Symptom

`make test` collects 1,420 tests, fails to import `tests/unit/test_ragas_llm.py`, and stops with
"Interrupted: 1 error during collection", having run none of them. Expected: the suite runs. The
same import fails in the app image, which installs the same lock, so the generation benchmark
can't judge an answer.

## Reproduction

Ran 2026-11-26 on `main` (`76a15d3`). `.venv` has ragas 0.3.1, as the lock does; five unrelated
packages (`langchain-classic`, `langchain-core`, `langchain-text-splitters`, `langsmith`,
`transformers`) are a patch release behind #28's lock, which `uv sync --all-extras` will close:

1. `make test`
2. Collection fails:

   ```text
   app/evaluation/ragas_llm.py:11: in <module>
       from ragas.llms.base import InstructorBaseRagasLLM
   E   ImportError: cannot import name 'InstructorBaseRagasLLM' from 'ragas.llms.base'
   ...
   !!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
   ======================= 86 deselected, 1 error in 3.37s ========================
   make: *** [Makefile:94: test] Error 2
   ```

On the stack, not run, read from the code: `book-rag benchmark` with a generation experiment
imports `ragas_llm` lazily, in `RagasJudge._metrics` (`app/evaluation/generation_metrics.py:79-87`).
`score()` reads `self._metrics` outside the `try` that turns a failing metric into `None`, so the
`ImportError` stops the run at the first answerable question that the model answers. The retrieval,
summary and performance benchmarks don't import ragas.

## Suspected Code Paths

- `uv.lock`, package `ragas` — 0.3.1 since `27780d3`, 0.4.4 at `79ae086` just before it. That
  commit changed no line of `pyproject.toml`, only the lock (and `config/models.yaml`,
  `devtools/.env.sample`).
- `pyproject.toml:48` — `ragas` is listed with no bound, in the `evaluation` extra, as the
  convention asks (`uv add --raw`). So 0.3.1 satisfies everything the project states.
- `pyproject.toml:73-74` — `constraint-dependencies = ["langchain-community<0.4.2"]`. **Not the
  cause**: `langchain-community` was 0.4.1 before and after `27780d3`, and every ragas from 0.3.0
  to 0.4.4 requires it without a bound.
- `app/evaluation/ragas_llm.py:11,20` — `ProviderLLM` subclasses `InstructorBaseRagasLLM`, which
  ragas 0.3.1 doesn't have.
- `app/evaluation/generation_metrics.py:84-87` — also imports `ragas.metrics.collections`; with
  0.4.4 both imports work (checked, below).
- `Makefile:22-23` — `make update` is `uv sync --all-extras --upgrade`: it re-resolves everything
  to the newest versions and writes the lock without showing what moved down.
- `Dockerfile:22,27` — `uv sync --frozen --all-extras`: every image built since `27780d3` has
  ragas 0.3.1.

## Root Cause Hypothesis

A transitive cap made the resolver give up ragas rather than jiter. `make update` in #27 raised
`openai` from 3.3.0 to 3.57.0, and with it `jiter`, which `openai` and `anthropic` depend on, to
0.19.0. ragas 0.3.2 and every later release require `instructor` (with no bound), and the newest
`instructor`, 1.18.0, requires `jiter<0.19,>=0.6.1` (1.17.0, the one locked before, requires
`jiter<0.15` and `rich<15`). With `ragas` unbounded, the newest resolution that keeps `jiter`
0.19.0 is ragas 0.3.1, the last release without `instructor`, and the resolver took it: the lock
lost `instructor` and `scikit-network`, and ragas moved from 0.4.4 to 0.3.1 among 15 packages that
moved up. Confidence: **high**. The requirements come from PyPI's metadata for `instructor` 1.17.0
and 1.18.0 and for each ragas release from 0.3.0 to 0.4.4. In a scratch copy of the project, adding
`ragas>=0.4.4` makes `uv lock --dry-run` answer exactly "Add instructor v1.18.0, Update jiter
v0.19.0 -> v0.18.0, Update ragas v0.3.1 -> v0.4.4, Add scikit-network v0.33.5", and nothing else.

Why unit tests didn't catch it at #27: they did. `make test` has failed at collection since
`27780d3`, and #28 and #30 merged after it. CI runs no tests: `.github/workflows/` holds only
`pr-title.yml`, which checks the title with commitizen, and `release.yml`.

## Proposed Remediation

**Preferred**: give ragas a floor where the project already keeps its dependency workarounds, and
lock again without upgrading anything else:

1. `pyproject.toml`, `[tool.uv]`: `constraint-dependencies = ["langchain-community<0.4.2",
   "ragas>=0.4.4"]`, with a comment on why: `ProviderLLM` subclasses `InstructorBaseRagasLLM`,
   which the ragas that `make update` could otherwise pick doesn't have, and 0.4.4 is the version
   the judges were verified on. A constraint, not a bound in `dependencies`, keeps the dependency
   lists unpinned as the convention asks, and keeps the bound next to the other one that exists
   for ragas.
2. `uv lock` (not `--upgrade`), then `uv sync --all-extras`. Checked in a scratch copy: it moves
   only ragas (0.3.1 → 0.4.4), `jiter` (0.19.0 → 0.18.0), and adds `instructor` 1.18.0 and
   `scikit-network` 0.33.5. `uv lock --upgrade --dry-run` with the constraint keeps the same four,
   so the next `make update` can't undo the fix.
3. `docs/decisions.md`, beside "`langchain-community<0.4.2`" (line 58): a line for `ragas>=0.4.4`
   and why (constitution VIII). The README describes no dependency bound, so it stays as it is.

**Alternatives**:
- *`jiter<0.19` as the constraint.* It also brings ragas 0.4.4 back today, but it caps a package
  the project doesn't use directly, for a reason that belongs to `instructor`, and it stays in
  place after `instructor` lifts its cap. It also leaves ragas unbounded, so the next transitive
  cap would drop it again.
- *Revert `uv.lock`'s ragas lines to `79ae086`'s.* It doesn't hold: `instructor` 1.17.0 can't
  live with `jiter` 0.19 or `rich` 15, and the next `make update` resolves to 0.3.1 again.
- *Make `ragas_llm.py` work with 0.3.1.* It would mean rewriting the judge for an older API, which
  the constitution would then require to be proven again (VI), to keep a version nobody chose.

**Files likely to change**:
- `pyproject.toml`
- `uv.lock`
- `docs/decisions.md`

**Tests to add or update**:
- None new. `tests/unit/test_ragas_llm.py` already fails at import with ragas 0.3.1, which is the
  regression check: the fix is proven by `make test` collecting every test. Checked ahead of the
  fix, in an ephemeral overlay that leaves `.venv` and the lock as they are
  (`uv run --with ragas==0.4.4 --with instructor==1.18.0 --with jiter==0.18.0 --with openai==3.57.0
  pytest -m "not integration"`): **1,339 passed, 2 failed**. The two failures are
  `test_the_shipped_configuration_holds_anthropics_profile` and `..._openais_profile`
  (`tests/unit/test_config.py:197,248`), the separate bug iss-e5z, which the fix doesn't touch.
- `make check-updates` after the fix: it should list no ragas line.

## Risks & Considerations

- **The judges run with a new pair of libraries.** ragas returns to 0.4.4, the version the
  generation benchmark's judges were proven on, but with `instructor` 1.18.0 (was 1.17.0) and
  `openai` 3.57.0 (was 3.3.0), a combination no benchmark has run. `ProviderLLM` overrides
  `generate` and `agenerate`, so `instructor` sends nothing; `openai` serves `embedding_factory`
  for answer relevance and correctness, through Ollama's OpenAI-compatible endpoint, for
  embeddings only. The judges' prompts, reasoning and model don't change, so constitution VI's
  re-proof doesn't strictly apply; V's real-model check is the open question below.
- **Checking it on the stack costs the library.** A new `uv.lock` rebuilds the image, and
  `make up` then recreates the app container, which deletes the library, its logs and
  `benchmarks/workspace` (constitution II). The dataset and experiments have to be copied in again
  (README, Benchmarks).
- **No recorded result is affected.** `docs/benchmark-results.md` records no run after
  `27780d3`, and a generation run with ragas 0.3.1 would have stopped before writing one. Each
  result records its ragas version (`_TRACKED_PACKAGES`, `app/evaluation/benchmark.py:65-73`).
- **Index, library, prompts: untouched.** The change is in the `evaluation` extra's resolution;
  no embedding, chunking or fingerprint setting moves (III), and nothing in `app/` changes.
- **Scope** (`AGENTS.md`). Two things this bug shows belong to Follow-ups, not to the fix: `make
  update` writes a downgrade without saying so (`make check-updates` lists it, but among the
  upgrades), and nothing runs `make test` before a merge, which let #27, #28 and #30 merge with
  it failing.

## Open Questions

- Should the fix be checked on the stack with a sampled generation benchmark, so that
  faithfulness, relevance and correctness are seen scoring with ragas 0.4.4, `instructor` 1.18.0
  and `openai` 3.57.0? It isn't required by the constitution's letter (the judges themselves don't
  change), and it empties the library (Risks). Recommended, unless the owner would rather wait
  for the next benchmark run they make anyway.
