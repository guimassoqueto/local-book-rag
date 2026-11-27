# Bug Fix: the cloud profiles' reasoning goes back to `low`

- **Slug**: cloud-reasoning-medium
- **Fixed**: 2026-11-26
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`cloud_profiles.anthropic.reasoning` and `cloud_profiles.openai.reasoning` in
`config/models.yaml` are `low` again, undoing #27's change to that file, as the owner decided. The
configuration now matches the tests that pin the shipped profiles, `docs/decisions.md`,
`README.md`, its own comments, and the effort the real models were checked at on 2026-11-20.

## Changes

| File                 | Change   | Notes                                                                  |
| -------------------- | -------- | ---------------------------------------------------------------------- |
| `config/models.yaml` | modified | `reasoning: medium` → `low` in `cloud_profiles.anthropic` and `.openai` |

## Diff Highlights (optional)

```diff
   anthropic:
     ...
-    reasoning: medium
+    reasoning: low
   openai:
     ...
-    reasoning: medium
+    reasoning: low
```

`git diff 27780d3~1 -- config/models.yaml` is empty: the file is again as it was before #27.

## Tests Added or Updated

- None, as the assessment said. `tests/unit/test_config.py::test_the_shipped_configuration_holds_anthropics_profile`
  and `::test_the_shipped_configuration_holds_openais_profile` already pin `low`, and are the
  regression check: a later change of the effort fails them.

## Local Verification

- Commands run:
  - `make test` → 1341 passed, 86 deselected (the integration tests), in 27.65s. Before the fix:
    2 failed, 1339 passed.
  - `make lint-check` → "All checks passed!", 150 files already formatted.
  - `git diff 27780d3~1 -- config/models.yaml` → empty.
- Manual checks: none. No real-model run, since the effort returns to the value the cloud
  integration tests passed at on 2026-11-20 (assessment, Risks & Considerations).

## Deviations from Assessment

None.

## Follow-ups

- No new bead. What let #27 merge with the two tests failing is already iss-az3, "make test runs
  on every pull request".
- A running stack sends `medium` until `make up` rebuilds the app image, which recreates the app
  container and empties the library (README, Running). It is the owner's to run, when convenient.
