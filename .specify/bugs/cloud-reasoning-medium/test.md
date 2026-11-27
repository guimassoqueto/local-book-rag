# Bug Verification: the cloud profiles' reasoning goes back to `low`

- **Slug**: cloud-reasoning-medium
- **Tested**: 2026-11-26
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The assessment's reproduction, the two shipped-profile tests, no longer fails, and the shipped
configuration loads with `low` for both cloud profiles. The whole unit suite passes and lint is
clean, so the fix broke nothing.

## Checks Performed

| Check                   | Command / Action                                                                                                    | Result  | Notes                                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------- | ------- | ---------------------------------------------------------------------------------------------- |
| Reproduction (post-fix) | `uv run pytest tests/unit/test_config.py::test_the_shipped_configuration_holds_{anthropics,openais}_profile`        | pass    | The two tests the assessment reproduced failing: 2 passed                                      |
| Shipped configuration   | `load_settings(Path("config"))` (`app/config/loader.py`), printing each profile's `reasoning`                       | pass    | `anthropic: low`, `openai: low`; `gpt-oss:20b: low`, the others `False`, as before #27         |
| New / updated tests     | none                                                                                                                | n/a     | The fix added none: the two tests above already pinned `low` (fix.md)                          |
| Config tests            | `uv run pytest tests/unit/test_config.py`                                                                           | pass    | 53 passed                                                                                      |
| Regression suite        | `make test`                                                                                                         | pass    | 1341 passed, 86 deselected (integration); before the fix 2 failed, 1339 passed                 |
| Lint                    | `make lint-check`                                                                                                   | pass    | All checks passed, 150 files already formatted                                                 |
| Real models             | `make test-integration` / `tests/integration/test_cloud_generation.py`                                              | skipped | Paid and network-dependent; the effort returns to the value they passed at on 2026-11-20       |
| Running stack           | `doctor`, `make up`                                                                                                 | skipped | `make up` recreates the app container and empties the library; the owner's to run              |

## Output Excerpts

```text
$ uv run pytest tests/unit/test_config.py::test_the_shipped_configuration_holds_anthropics_profile \
    tests/unit/test_config.py::test_the_shipped_configuration_holds_openais_profile -q
2 passed in 0.02s

cloud {'anthropic': 'low', 'openai': 'low'}
local {'gpt-oss:20b': 'low', 'gemma4:12b': False, 'qwen3.5:9b': False, 'qwen3:14b': False}

$ make test
===================== 1341 passed, 86 deselected in 27.78s =====================

$ make lint-check
All checks passed!
150 files already formatted
```

## Residual Risks

- No cloud request was sent at `low` after the fix. The claim that `low` works rests on the
  integration tests of 2026-11-20 (`docs/decisions.md`, Cloud models), and the Anthropic and
  OpenAI SDK versions in `uv.lock` have moved since (#27, #28). A change of the SDKs isn't this
  bug's, and the unit tests' fakes, built from the SDKs' own types, passed.
- A stack built before this fix still sends `medium` until `make up` rebuilds the app image.
- What let the change merge unnoticed, no CI running `make test`, remains: iss-az3.

## Recommendation

Close the bug once its pull request merges: verified against the assessment's reproduction, with
no regression in the unit suite or lint. The real-model check isn't needed for a return to the
checked value, and is left to the next cloud run.
