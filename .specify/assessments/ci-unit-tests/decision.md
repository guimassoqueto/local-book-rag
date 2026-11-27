# Decision: a required check that runs the unit tests and lint on every pull request

- **Slug**: ci-unit-tests
- **Decided**: 2026-11-26
- **Verdict**: go
- **Artifacts reviewed**: intake.md, research.md, problem.md, concept.md

## Scorecard

| Criterion | Rating | Justification |
|-----------|--------|---------------|
| Problem validity | strong | #27 broke the unit suite in two independent ways and merged. #28 and #30 merged on top, and v0.10.0 and v0.10.1 were released from a red suite with the benchmark judge broken. It was found by chance four days later. Nothing checks a pull request's tests or lint, and `protect-main` requires no check (`research.md`, `problem.md`). |
| Evidence strength | adequate | What the check needs is measured, not assumed: with only the `evaluation` extra, the unit suite passes in full from empty caches (1341 tests, 0.36 GB, no torch). Without that extra, what #27 broke is skipped. The ruleset's lack of required checks and bypass actors was read from the API. What isn't measured: the time on a GitHub runner, how often outside hosts fail a run, and how often a breakage would recur, since #27 is the only known one (`research.md` § Evidence Against). |
| Value vs. inaction | adequate | Inaction costs nothing up front, and there is one known incident in 60 commits. That incident was costly: two releases from a red suite, a broken benchmark judge, and a later fix that started from failures not its own. The recommended option costs a day or two and nothing per run on a public repository (`problem.md` § Cost of Inaction, `concept.md`). |
| Feasibility / appetite | strong | Option B is small. It reuses the `make` targets, needs no secret and no change to the application, and its environment is already known to pass. Replaying #27 on a pull request gives a direct acceptance test (`concept.md`). |
| Strategic fit | strong | The Development Workflow already makes every change land through a squash-merged pull request, and gives every significant component automated tests. `specs/010-beads-issue-tracking` already expects CI to pass (FR-025, SC-005). It keeps Principle I once iss-6fu is fixed, and leaves Principle V's real-model checks where they are. |
| Risk posture | adequate | The risks are named, each with a way through. A required check must report on every pull request, so no path filters. Forcing a merge needs a bypass or a ruleset edit, since nobody can bypass today. Python must be on `PATH`. A skip for a missing extra would pass silently. Outside outages turn runs red. Recording it probably needs a constitution amendment. Two are left open, to be settled in specification: how to force a merge, and whether a skip fails the run (`concept.md` § Rabbit holes). |

## Verdict & Rationale

**Go, with Option B: one required check on each pull request.**

The problem is real and was costly the one time it happened: three merges and two releases on a
red suite. The owner set the bar: a breakage can't merge, and lint counts too. Option B is the
smallest option that meets it, and the evidence for what it needs is measured: the `evaluation`
extra is enough, and is also what makes the check catch #27. Evidence strength is adequate rather
than strong because the recurrence rate and the run time on GitHub are unknown. Neither changes
the call: the option is cheap, and its first pull request measures the time. Option A doesn't
meet the owner's bar. Option C answers risks that no evidence shows yet, and its parts stay
available if B's metrics call for them.

Two conditions come with the go:

- **iss-6fu lands first.** "A run sends nothing to a third party" (the problem's goal) should hold
  for the whole application, not only CI. Fixed in the code, ragas's analytics are off wherever
  ragas is imported, and the check needs no switch of its own. In the tracker, iss-6fu now blocks
  iss-az3.
- **The specification settles how to force a merge** (goal 6): a bypass for the owner added with
  the required check, or a temporary edit of the ruleset. Today nobody can bypass `protect-main`.

## If needs-clarification

- Not applicable.

## If go — Handoff to `/speckit-specify`

- **Problem**: nothing checks a pull request's unit tests or lint before it merges into `main`, so a
  breakage merges unseen. #27 did, through three merges and two releases, with the benchmark judge
  broken, for four days.
- **Chosen approach**: Option B. Every pull request gets one check that installs the project from
  `uv.lock` on a clean runner, with the `evaluation` extra and without `reranking`. It runs
  `make lint-check` and `make test`, and `protect-main` requires it to pass before a merge. It
  needs no secret, runs on every pull request with no path filters, and keeps uv's own cache between
  runs.
- **In scope**:
  - The check.
  - The required-check rule in `protect-main`, and how the owner forces a merge in an emergency.
  - Replaying #27's two breakages on a pull request, to show that both are stopped.
  - `README.md` and `docs/decisions.md` (Principle VIII).
  - The constitution's Development Workflow, if a green check becomes a condition of merging,
    through `/speckit-constitution`.
- **Out of scope**:
  - `make test-integration`, benchmarks and real models.
  - The `reranking` extra.
  - The Docker image, and `release.yml`.
  - Closing beads from CI.
  - A sealed, offline suite, and turning skips into failures (Option C), unless B's metrics call
    for them.
  - Making a run without the `evaluation` extra pass.
  - More than one Python version or platform.
  - Coverage reports.
  - Requiring `pr-title`, unless the owner adds it to the same ruleset change.
- **Success metrics**:
  - A pull request with failing unit tests or lint can't merge (baseline: it can).
  - #27's lock, with ragas 0.3.1, and its change of the cloud profiles' reasoning are each
    stopped on a pull request (baseline: both merged).
  - Breakages of the unit suite or lint that reach `main`: 0 (baseline: 1 known in 60 commits).
  - Time from a push to the result, measured on the first pull request (baseline: none; 28 to
    33 s locally).
  - Red results unrelated to the change, counted per month, aiming at 0 (baseline: unknown).
  - Usage events sent to a third party per run: 0 (baseline: one each time the judge is built,
    until iss-6fu).
- **Carried-forward open questions**:
  - How the owner forces a merge in an emergency: a bypass actor, or editing the ruleset.
  - What wait for a result is acceptable.
  - Whether a skip for a missing extra fails the run. Concept B leaves it to the spec, and Option
    C would make it fail.
  - Whether the suite may reach tiktoken's blob store and the Hugging Face Hub, or should use
    cached files. B accepts the downloads, and counts the red runs they cause.
  - Whether `pr-title` becomes required in the same change.
  - Whether the constitution's Development Workflow is amended, and how (MINOR, since it adds a
    condition to how a change lands).
  - Whether anyone besides the owner opens pull requests or uses the releases.
