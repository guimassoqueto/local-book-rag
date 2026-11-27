# Bug Verification: RAGAS's usage analytics are turned off in the code

- **Slug**: ragas-analytics
- **Tested**: 2026-11-26
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The assessment's reproduction no longer produces an event: building the judge logs no payload
where it logged one `embedding_usage` event before. That holds with a leftover
`RAGAS_DO_NOT_TRACK=false` in the environment, and when RAGAS is imported before `app.evaluation`.
A control without `app.evaluation` still logs the event, so the checks can tell. The new tests,
the unit suite and lint pass.

## Checks Performed

Every reproduction ran with RAGAS's debug switch, `__RAGAS_DEBUG_TRACKING=true`, which logs an
event's payload instead of posting it, and with an empty `HOME`. Nothing was sent.

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | the assessment's step 1: `test_generation_metrics.py::test_the_judges_client_reaches_ollama_…` with `-o log_cli=true --log-cli-level=INFO` | pass | 0 "Tracking Payload" lines; before the fix, 1 |
| A leftover value | the same, with `RAGAS_DO_NOT_TRACK=false` set | pass | 0 lines: the switch is set outright |
| RAGAS imported first | `python -c`: import `ragas` and `ragas._analytics`, then `app.evaluation.generation_metrics`, then `track(EmbeddingUsageEvent(...))` | pass | 0 lines: RAGAS reads the switch at its first event, not at import |
| Control | the same event, without importing `app.evaluation` | pass (logs, as expected) | 1 line: the checks above would see an event |
| The CLI's path | `app/main.py:313,324` | pass | `benchmark` imports `app.evaluation.benchmark`, so the package runs first |
| New tests | `uv run pytest tests/unit/test_ragas_analytics.py` | pass | 3 passed; without the fix, 3 failed (fix.md) |
| Regression suite | `make test` | pass | 1344 passed, 86 deselected (integration) |
| Lint | `make lint-check` | pass | All checks passed, 151 files already formatted |
| A real benchmark run | `book-rag benchmark` in the app container | skipped | Needs the stack, the models and the GPU, and the image rebuilt (`make up` empties the library). The judge code is unchanged, so no scores can move |

## Output Excerpts

```text
== 1. reproduction, debug switch, empty HOME
0
== 2. same, with a leftover RAGAS_DO_NOT_TRACK=false
0
== 3. ragas imported first, then app.evaluation, then an event
0
== control: the same event without importing app.evaluation
1
$ uv run pytest tests/unit/test_ragas_analytics.py
3 passed in 0.53s
$ make test
===================== 1344 passed, 86 deselected in 27.05s =====================
```

## Residual Risks

- **RAGAS still writes its ID file locally.** It builds each event, and so creates
  `~/.local/share/ragas/uuid.json`, before it checks the switch: check 1's empty `HOME` had the
  file afterwards. Nothing is posted. This is RAGAS's behavior, and only the posting breaks
  Principle I.
- **The image wasn't checked.** The fix runs wherever `app.evaluation` is imported, which the
  benchmark commands do (`app/main.py:313,324`). The image takes it at the next `make up`.
- **A future import outside the package.** A module outside `app/evaluation` that imported RAGAS
  and made it track before importing `app.evaluation` would still send events. Nothing does today
  (`grep` of `app/` for `ragas`), and the package's docstring and `docs/decisions.md` say why the
  switch lives there.
- **A RAGAS release could change the switch or how it posts.** A new name for the switch, or
  reading it before the package sets it, would make the tests fail, since the post would reach
  the recorder. Posting some other way than `requests.post`, such as through a session, would
  slip past the recorder, and the tests would pass while events went out. They use RAGAS's private
  `_analytics` module, so a release that moves it makes them error, not pass.

## Recommendation

Close the bug once its pull request merges: verified against the assessment's reproduction, with
a control showing that the check sees an event, and no regression in the suite or lint. That
merge also unblocks iss-az3.
