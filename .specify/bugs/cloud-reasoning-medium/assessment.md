# Bug Assessment: #27 set the cloud profiles' reasoning to `medium`, against the tests and the docs

- **Slug**: cloud-reasoning-medium
- **Created**: 2026-11-26
- **Source**: pasted text (bead iss-e5z, recorded while running `make test` for
  `specs/010-beads-issue-tracking`), with the owner's decision on the setting
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> 27780d3 (chore: update dependencies, #27) changed cloud_profiles.anthropic.reasoning and
> cloud_profiles.openai.reasoning in config/models.yaml from low to medium, but
> tests/unit/test_config.py still asserts profile.reasoning == 'low' (lines 197 and 248), so
> test_the_shipped_configuration_holds_anthropics_profile and ..._openais_profile fail. Either the
> tests follow the new setting, or the setting goes back; docs/decisions.md (Cloud models) records
> why low was chosen, so a change of it needs its reason there too. Found while running make test
> for specs/010-beads-issue-tracking.

The owner's decision (2026-11-26): the setting goes back to `low` on both cloud profiles,
Anthropic and OpenAI. The owner first meant to keep `medium`; told that keeping it meant giving
its reason in `docs/decisions.md` and checking it on the real models, the owner chose `low`.

## Symptom

`make test` fails 2 of 1,341 unit tests: the two that check the shipped cloud profiles expect
`reasoning: low`, and the configuration holds `medium`. Expected: the suite passes, and every
cloud request is sent at the effort that `docs/decisions.md`, `README.md` and the configuration's
own comments describe, and that the real models were checked at. Today every request to Claude or
OpenAI is sent at `medium`, an effort nothing checked and nothing records.

## Reproduction

Ran 2026-11-26 on `main` (`42eaf59`), on branch `fix/cloud-reasoning-medium`:

1. `uv run pytest tests/unit -q`
2. Two failures, nothing else:

   ```text
   tests/unit/test_config.py:197: AssertionError    (- low  + medium)
   tests/unit/test_config.py:248: AssertionError
   FAILED tests/unit/test_config.py::test_the_shipped_configuration_holds_anthropics_profile
   FAILED tests/unit/test_config.py::test_the_shipped_configuration_holds_openais_profile
   2 failed, 1339 passed in 27.99s
   ```

The two tests have failed since #27 merged. Until #31 they were hidden, since the suite stopped at
collection on the ragas import (`.specify/bugs/ragas-downgrade`), and no CI runs it (iss-az3).

## Suspected Code Paths

- `config/models.yaml:124` (`cloud_profiles.anthropic.reasoning: medium`) and `:159`
  (`cloud_profiles.openai.reasoning: medium`): the two values #27 changed from `low`
  (`git show 27780d3 -- config/models.yaml`, its only change to the file).
- `tests/unit/test_config.py:197` and `:248`: assert `"low"`, which is right.
- What already says `low`, and stays as it is:
  - `config/models.yaml:153-158`, OpenAI's comment: "OpenAI advises low over none or minimal. At
    low, the three models reasoned no tokens at all on the integration tests' questions".
  - `docs/decisions.md:428` and `:561`, each profile's values and their reasons, and `:456` and
    `:548`, the checks on the real models of 2026-11-20, which ran at `low`.
  - `README.md:519-520`: "OpenAI's models, at the effort `low` that their profile sets, often
    don't reason at all on these tasks".
- `app/generation/anthropic_provider.py:230-231` sends the profile's effort as `output_config`;
  the OpenAI provider sends it as the request's reasoning effort. No code changes.

## Root Cause Hypothesis

High confidence. #27, a dependency chore, also changed a default of both cloud profiles, which
updated neither the tests that pin the shipped profiles nor the docs that record the setting and
why. Nothing ran the unit tests on that pull request: the suite stopped at collection on the ragas
import from the same commit, and no workflow runs `make test` on pull requests (iss-az3).

## Proposed Remediation

**Preferred**: set `cloud_profiles.anthropic.reasoning` and `cloud_profiles.openai.reasoning` in
`config/models.yaml` back to `low`, undoing #27's change to that file and nothing else. The tests,
`docs/decisions.md`, `README.md` and the comments then all agree with the configuration again, and
the effort is the one the real models were checked at on 2026-11-20 (`docs/decisions.md:436-456`
for Claude, `:540-566` for OpenAI). `gpt-oss`, in `llm_profiles`, is at `low` already
(`config/models.yaml:53`) and isn't touched.

**Alternatives**:

- Keep `medium`, and bring the tests, `docs/decisions.md`, `README.md` and OpenAI's comment into
  line, with the reason for it and a paid run of the cloud integration tests at `medium` to check
  that `reasoning_tokens: 4000` still holds (Principles V and VIII). Ruled out by the owner.
- Change only the two tests to `medium`: `make test` passes, but everything else keeps describing
  `low`, which Principle VIII doesn't allow.

**Files likely to change**:

- `config/models.yaml` (two lines)

**Tests to add or update**:

- None: `test_the_shipped_configuration_holds_anthropics_profile` and
  `test_the_shipped_configuration_holds_openais_profile` already pin `low`, and pass once the
  configuration does. `make test` passing in full is the check.

## Risks & Considerations

- **No real-model run is needed.** The effort returns to the value the cloud integration tests
  passed at on 2026-11-20, on Claude's three models and OpenAI's three, and nothing else in the
  profiles changed since. Between #27 and this fix, cloud requests ran at `medium`; nothing was
  recorded from them.
- **No index, no library.** The effort shapes generation only: no fingerprint, collection or
  journaled operation is touched (Principles II and III).
- **Taking it in.** The configuration is baked into the app image, so a running stack sends
  `medium` until `make up` rebuilds it, which recreates the app container and empties the library
  (README, Running).

## Open Questions

- None: the owner chose `low`.
