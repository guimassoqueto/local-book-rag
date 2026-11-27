# Bug Fix: RAGAS's usage analytics are turned off in the code

- **Slug**: ragas-analytics
- **Fixed**: 2026-11-26
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`app/evaluation/__init__.py`, empty until now, sets `RAGAS_DO_NOT_TRACK=true` outright. Every module
that imports RAGAS is in that package, so the switch is set before RAGAS first reads and caches it,
in the image, the benchmarks, the unit tests and CI alike. Three unit tests lock it in, and
`docs/decisions.md` records the switch and why it lives in code.

## Changes

| File                                | Change   | Notes                                                                              |
| ----------------------------------- | -------- | ---------------------------------------------------------------------------------- |
| `app/evaluation/__init__.py`        | modified | Was empty: a docstring saying why, and `os.environ["RAGAS_DO_NOT_TRACK"] = "true"` |
| `tests/unit/test_ragas_analytics.py` | added    | Three tests; the module skips without RAGAS, like `test_ragas_llm.py`              |
| `docs/decisions.md`                 | modified | Evaluation: "RAGAS sends no analytics, and its switch is in the code."             |

## Diff Highlights (optional)

```python
# app/evaluation/__init__.py
"""The benchmarks, their metrics and their judges.

RAGAS posts usage analytics to its authors (t.explodinggradients.com) when a judge is built and on
each embedding request, unless RAGAS_DO_NOT_TRACK is "true". ...
"""

import os

os.environ["RAGAS_DO_NOT_TRACK"] = "true"
```

## Tests Added or Updated

- `tests/unit/test_ragas_analytics.py::test_building_the_judge_posts_nothing`: builds the RAGAS
  judge, as `test_generation_metrics.py:90` does, with `requests.post` in `ragas._analytics`
  recorded instead of sent. Nothing may be posted. This is the event the assessment reproduced.
- `tests/unit/test_ragas_analytics.py::test_an_embedding_request_posts_nothing`: has RAGAS track
  an `EmbeddingUsageEvent`, as its embeddings do on each request (which needs a server to happen
  for real). Nothing may be posted.
- `tests/unit/test_ragas_analytics.py::test_a_value_left_in_the_environment_doesnt_turn_the_analytics_back_on`:
  with `RAGAS_DO_NOT_TRACK=false` in the environment, reloading `app.evaluation` leaves it `true`.

The fixture clears `do_not_track`'s cache before and after each test, so the switch is read from the
environment as it stands, not from whatever an earlier test cached. The event in the second test
carries its own `user_id`, so the test doesn't write RAGAS's ID file into the developer's home.

## Local Verification

- Commands run:
  - `uv run pytest tests/unit/test_ragas_analytics.py` without the fix (`git stash` of
    `app/evaluation/__init__.py`): 3 failed. With it: 3 passed.
  - The assessment's reproduction, with RAGAS's debug switch (`__RAGAS_DEBUG_TRACKING=true`, which
    logs a payload instead of posting it) and an empty `HOME`: 0 "Tracking Payload" lines, where it
    logged one `embedding_usage` event before.
  - `make test`: 1344 passed, 86 deselected (the integration tests), in 27.02s. Before: 1341.
  - `make lint-check`: "All checks passed!", 151 files already formatted.
- Manual checks: none. No benchmark was run: the change touches no prompt, parser or judge logic,
  only whether RAGAS posts its analytics (assessment, Risks & Considerations).

## Deviations from Assessment

None.

## Follow-ups

- No new bead. The assessment's one note for the owner stands without one: Hugging Face's and
  Gradio's telemetry switches live only in the Dockerfile, but the unit suite reaches neither.
- The image takes the fix with `make up`, which recreates the app container and empties the library
  (README, Running). The new container starts without RAGAS's old ID.
- iss-az3 (a required CI check running `make test`) was blocked on this bead. Once it merges, the
  CI run needs no switch of its own (`.specify/assessments/ci-unit-tests/decision.md`).
