# Bug Verification: `make update` moved ragas back to 0.3.1, and `make test` stops at collection

- **Slug**: ragas-downgrade
- **Tested**: 2026-11-26
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The bug no longer reproduces. `make test` collects every test, 1,427 against 1,420 before, the
difference being `tests/unit/test_ragas_llm.py`'s 7. A frozen install of the lock, without dev
tools, as the image installs it, imports the generation benchmark's judge. `make update` would
keep ragas at 0.4.4. `make test` still exits non-zero, on the two failures of the separate bug
iss-e5z, which the collection error used to hide. They aren't a regression of this fix.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | `make test` | pass | Collects 1,427 tests with no error; before, "1 error during collection". 1,339 passed, 2 failed (iss-e5z). |
| The image's install | `UV_PROJECT_ENVIRONMENT=<scratch> uv sync --frozen --no-dev --extra evaluation`, then imports `ragas.metrics.collections`'s three metrics, `embedding_factory`, `ProviderLLM`, `RagasJudge` | pass | The Dockerfile's command (`--frozen --no-dev`) without the `reranking` extra, kept out of a RAM-backed `/tmp` for its CUDA torch; the judge doesn't import it. |
| The regression check catches the bug | `uv run --with ragas==0.3.1 pytest tests/unit/test_ragas_llm.py` | pass | Fails at collection with the original `ImportError`, so `make test` stops again if ragas ever falls back. |
| Tests of the changed path | `uv run pytest tests/unit/test_ragas_llm.py tests/unit/test_generation_metrics.py tests/unit/test_benchmark.py` | pass | 66 passed. |
| Lock matches `pyproject.toml` | `uv lock --check` | pass | Resolved 247 packages, the lock is up to date. |
| The next `make update` keeps the fix | `make check-updates` | pass | No ragas, instructor, jiter or scikit-network line. |
| Regression suite | `make test` | pass, with 2 known failures | The 2 are `tests/unit/test_config.py:197,248`, iss-e5z: `reasoning` is `medium` since #27, and they expect `low`. They fail on `main`'s config whatever ragas is; the assessment's overlay run showed the same two. |
| Lint | `make lint-check` | pass | All checks passed, 150 files already formatted. |
| The judges on the real models | a sampled generation benchmark on the stack | skipped | The assessment's open question, not taken up by the owner. The new lock rebuilds the image, and `make up` recreates the app container, deleting the library, its logs and `benchmarks/workspace`. |

## Output Excerpts

`make test`:

```text
collected 1427 items / 86 deselected / 1341 selected
FAILED tests/unit/test_config.py::test_the_shipped_configuration_holds_anthropics_profile
FAILED tests/unit/test_config.py::test_the_shipped_configuration_holds_openais_profile
================ 2 failed, 1339 passed, 86 deselected in 27.51s ================
```

The frozen, no-dev install:

```text
frozen no-dev env: ragas 0.4.4 | instructor 1.18.0 | jiter 0.18.0 | openai 3.60.0 | judge imports ok
```

The regression check, against ragas 0.3.1:

```text
E   ImportError: cannot import name 'InstructorBaseRagasLLM' from 'ragas.llms.base'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

## Residual Risks

- **A correction to the assessment.** Its Risks and Open Questions name `openai` 3.57.0, which
  #27 locked. `main`'s lock, and this fix's, has `openai` 3.60.0, which #28 brought. The
  combination no benchmark has run is ragas 0.4.4 with `instructor` 1.18.0 and `openai` 3.60.0.
  The assessment's overlay run used 3.57.0. Every check above ran on 3.60.0.
- **The judges haven't scored on the real models with these versions.** They import, and their
  unit tests pass, but those use fakes. `ProviderLLM` sends the judge's prompts through this
  project's own provider, so neither `instructor` nor `openai` touches them. `openai` serves
  only the embeddings for answer relevance and correctness, through Ollama's OpenAI-compatible
  endpoint. A failing metric is logged as "judge failed" and left out, not scored as zero
  (`RagasJudge.score`), so the next generation run would show it.
- **`make test` isn't green until iss-e5z is fixed.**

## Recommendation

Merge the fix: the bug is gone, the lock holds against the next `make update`, and
`test_ragas_llm.py` stops the suite if it ever comes back. iss-30k closes when the pull request
merges. Before the next generation result is trusted, its `rows.csv` should show the three RAGAS
metrics scored, with no "judge failed" events in the run's log, as the first run with these
versions. iss-e5z is the next fix, so that `make test` passes.
