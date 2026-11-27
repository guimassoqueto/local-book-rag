# Bug Fix: `make update` moved ragas back to 0.3.1, and `make test` stops at collection

- **Slug**: ragas-downgrade
- **Fixed**: 2026-11-26
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

ragas gets a floor, `ragas>=0.4.4`, in `[tool.uv] constraint-dependencies`, beside the
`langchain-community` bound that already exists for it, and `uv.lock` is resolved again without
upgrading anything else. ragas is back at 0.4.4, so `app/evaluation/ragas_llm.py` imports, `make
test` collects every test, and the next `make update` can't drop it again.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `pyproject.toml` | modified | `constraint-dependencies` gains `"ragas>=0.4.4"`, with a comment on why. |
| `uv.lock` | modified | `uv lock`, not `--upgrade`: ragas 0.3.1 → 0.4.4, jiter 0.19.0 → 0.18.0, instructor 1.18.0 and scikit-network 0.33.5 added. No other package moves. |
| `docs/decisions.md` | modified | Dependencies: a paragraph for `ragas>=0.4.4`, after `langchain-community<0.4.2`, including that it holds `jiter` below 0.19 for `anthropic` and `openai` too (added after review). |

## Diff Highlights (optional)

```toml
# ragas 0.4.3 imports langchain_community.chat_models.vertexai, which 0.4.2 removed.
# Unbounded, ragas fell to 0.3.1, its last release without instructor, when jiter outgrew
# instructor's cap, and 0.3.1 has no InstructorBaseRagasLLM, which the judge subclasses.
# 0.4.4 is the version the judges were verified on.
constraint-dependencies = ["langchain-community<0.4.2", "ragas>=0.4.4"]
```

The lock's package versions, `HEAD` against the working tree, read from both with `tomllib`:

```text
instructor: None -> 1.18.0
jiter: 0.19.0 -> 0.18.0
ragas: 0.3.1 -> 0.4.4
scikit-network: None -> 0.33.5
```

## Tests Added or Updated

- None, as the assessment planned. `tests/unit/test_ragas_llm.py` is the regression check: with
  ragas 0.3.1 it fails at import, and stops the whole of `make test` at collection.

## Local Verification

- `uv lock` → "Added instructor v1.18.0, Updated jiter v0.19.0 -> v0.18.0, Updated ragas v0.3.1 ->
  v0.4.4, Added scikit-network v0.33.5", the four the assessment predicted.
- `uv sync --all-extras` → ragas 0.4.4, instructor 1.18.0, jiter 0.18.0 in `.venv`. It also
  brought five packages to #28's lock, which `.venv` was a patch release behind
  (`langchain-classic` 1.1.0, `langchain-core` 1.8.5, `langchain-text-splitters` 1.2.0,
  `langsmith` 0.16.2, `transformers` 5.24.1): `.venv` only, the lock doesn't change for them.
- `make test` → **1339 passed, 2 failed, 86 deselected**, against "1 error during collection"
  before. The two failures are `test_the_shipped_configuration_holds_anthropics_profile` and
  `test_the_shipped_configuration_holds_openais_profile` (`tests/unit/test_config.py:197,248`,
  `reasoning` is `medium` where they expect `low`): the separate bug iss-e5z, which this fix
  doesn't touch, and the same two that failed in the assessment's overlay run.
- `uv run pytest tests/unit/test_ragas_llm.py tests/unit/test_generation_metrics.py` → 22 passed.
- The generation benchmark's lazy imports (`ragas.metrics.collections`'s three metrics,
  `ragas.embeddings.base.embedding_factory`, `ProviderLLM`) → import without error.
- `make check-updates` → no ragas, instructor, jiter or scikit-network line: with the constraint,
  `make update` resolves them where they are now.
- `make lint-check` → all checks passed.
- Not run: a generation benchmark on the stack, the assessment's open question. The new lock
  rebuilds the image, and `make up` would recreate the app container, deleting the library, its
  logs and `benchmarks/workspace`. Left to the owner, for `/speckit-bug-test` or the next
  benchmark run.

## Deviations from Assessment

None.

## Follow-ups

- **iss-wf8**, "make update lowers a package without saying so" (chore, P3, `discovered-from`
  iss-30k): `make update` wrote ragas 0.4.4 → 0.3.1 among 15 packages that moved up, and `make
  check-updates` lists a downgrade the same way as an upgrade.
- **iss-az3**, "make test runs on every pull request" (idea, P2, `discovered-from` iss-30k): no
  workflow runs the unit tests, so #27, #28 and #30 merged with `make test` failing. Its worth
  depends on what installing the dependencies costs in CI, CUDA torch included.
- **iss-voa**, "A generation benchmark crashes if the RAGAS judge can't be built" (bug, P3,
  `discovered-from` iss-30k): `RagasJudge.score()` reads `self._metrics` outside the `try` that
  turns a failing metric into `None` (`app/evaluation/generation_metrics.py:102`), so this bug's
  `ImportError` would have ended a run at its first answered question. Found in the assessment,
  and raised again by the review.
- **iss-hdq**, "Benchmark results don't record the judge's instructor and openai versions" (bug,
  P3, `discovered-from` iss-30k): `_TRACKED_PACKAGES` (`app/evaluation/benchmark.py:68`) leaves
  out both, so a result from before this fix and one after it, both on ragas 0.4.4, record the
  same packages. Raised by the review of #31.
- iss-wf8 now also covers packages that `make update` holds back without saying so, such as
  `jiter`, which this fix's floor keeps below 0.19 for `anthropic` and `openai` (a comment on
  the bead).
