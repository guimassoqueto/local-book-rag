# Problem Definition: a change that breaks the unit suite or lint can merge into `main` unseen

- **Slug**: ci-unit-tests
- **Created**: 2026-11-26
- **Inputs used**: intake.md, research.md, the owner's answers (below)

The idea arrived as a solution: "make test runs on every pull request". This file states the
problem that solution is meant to solve, so the options in `/speckit-assess-shape` can be weighed
against it. Every figure comes from `research.md` unless another source is named.

## Owner's Answers (2026-11-26)

Given before this definition was written, to two questions with suggested options:

- **What success means**: "Can't merge". A pull request that breaks the unit suite stops at the
  merge. Seeing it red and deciding to merge anyway isn't enough.
- **Scope**: "Tests and lint". A pull request that breaks `make lint-check` counts too, not only
  one that breaks `make test`.

## Problem Statement

Nothing checks a pull request's unit tests or lint before it merges into `main`. They run only
when someone remembers to run them, and the rules on `main` require no check at all. So a change
that breaks them merges as easily as one that doesn't, and stays unseen until someone happens to
run the suite. #27 did exactly that, on 2026-11-22. #28 and #30 merged on top of it, and
v0.10.0 and v0.10.1 were released from a red suite, with the benchmark judge broken, before it was
found by chance four days later.

## Affected Users & Stakeholders

- **Users**:
  - **The owner as maintainer**, who reviews and merges every pull request, including those
    agents write. Today, knowing whether a pull request leaves the suite green means running it by
    hand on that branch. When that step is skipped, as for #27, #28 and #30, a breakage passes
    review (`research.md` § Users & Demand).
  - **The owner as researcher**, running benchmarks from the image. #27's lock broke the
    generation benchmark's judge too, not only the tests (`research.md` § Market & Context).
  - **The agents that write pull requests here**, and the bug and feature flows they follow. A
    fix starts from a suite that may already be red for unrelated reasons, as
    `.specify/bugs/ragas-downgrade` did: its record had to report two failures that weren't its
    own.
- **Stakeholders**:
  - **The owner as sole decider**, who sets `main`'s rules (`protect-main`) and keeps the
    constitution: Principle I (nothing goes to a third party nobody chose), V (unit tests use
    fakes, so the real models are checked separately), and the Development Workflow (every change
    lands through a squash-merged pull request whose title picks the release).
  - **The `release` workflow**, which publishes a release from whatever merges with a `fix`,
    `perf` or `feat` title, red suite or not (`git tag --points-at 76a15d3` is v0.10.0,
    `42eaf59` is v0.10.1).
- [NEEDS CLARIFICATION: does anyone outside the owner open pull requests, or rely on the
  releases? The repository is public, but `research.md` found only the owner.]

## Goals

- A pull request whose unit tests or lint fail can't be merged into `main`, without the owner
  having to remember to run anything.
- What it checks covers the breakage #27 made: a lock that installs a dependency the code can't
  import, and a configuration that drifts from the tests that pin it. Both would have been stopped.
- The check gives each pull request a clear pass or fail, soon enough that waiting for it is never
  a reason to skip it.
- A red result means the change broke something, not that an outside service was slow or down.
- A run sends nothing to a third party nobody chose (Principle I), and needs no secret.
- A merge the owner deliberately forces, in an emergency, stays possible.

## Non-Goals

- Running `make test-integration`, the benchmarks or anything else on the real models. They need
  Ollama, the models and a GPU, and stay a manual step (Principle V).
- Checking the reranking path's real dependencies (torch, sentence-transformers, transformers): no
  unit test exercises them (`research.md` § Data & Constraints).
- Building, testing or publishing the Docker image.
- Changing the `release` workflow, or what a title decides.
- Closing beads from CI, which would need a credential to the private tracker
  (`docs/decisions.md:868-869`).
- Finding out whether `make test` failed on `main` before #27.

## Success Metrics

- **A pull request with failing unit tests or lint can't be merged.** (Baseline: it can. The
  `protect-main` ruleset has no `required_status_checks` rule.)
- **#27's two breakages, replayed on a pull request, are stopped before merge**: its lock, with
  ragas 0.3.1, and its change of the cloud profiles' reasoning. (Baseline: both merged, and stayed
  on `main` four days, through two releases.)
- **Breakages of the unit suite or lint that reach `main`**: 0. (Baseline: 1 known in 60 commits,
  #27, which stayed through three merges.)
- **Time from a push to the result**. (Baseline: none in CI. Locally the suite runs in 28 to 33
  s. [NEEDS CLARIFICATION: what wait is acceptable?])
- **Red results unrelated to the change, such as a download that failed**: counted per month,
  aiming at 0. (Baseline: unknown, since nothing runs. The suite downloads from two outside hosts
  on a cold start.)
- **Usage events sent to a third party per run**: 0. (Baseline: ragas posts one each time the
  judge is built, which the unit tests do: iss-6fu.)

## Cost of Inaction

Breakages like #27 keep reaching `main` whenever the manual step is skipped. They are found later
by whoever runs the suite next, usually while working on something else, which then has to stop
and fix them first, as `specs/010-beads-issue-tracking` did. Meanwhile releases go out from a red
suite. When the breakage is in a dependency, it reaches the image too: #27's lock broke the
benchmark judge, which is what decides a model or a default here. The cost of each occurrence
grows with the merges stacked on top, each of which might hide or compound the first. Doing
nothing costs nothing up front, and the only known occurrence so far is #27.

## Open Questions

- [NEEDS CLARIFICATION: what wait for a result is acceptable on a pull request? `research.md`
  guesses a minute or two on a GitHub runner, unmeasured.]
- [NEEDS CLARIFICATION: should the unit suite run without the `evaluation` extra at all, with the
  unguarded test at `tests/unit/test_generation_metrics.py:90` made to skip, or should the suite
  require the extra? Skipping would let a no-extra run pass, and would again skip what #27 broke.]
- [NEEDS CLARIFICATION: should a run reach the network for tiktoken's `o200k_base` and the Hugging
  Face Hub, or work from files it doesn't download each time? It decides how often an outside
  outage can turn a run red.]
- [NEEDS CLARIFICATION: is iss-6fu, ragas's analytics, fixed first, or does the check carry its
  own way to keep a run from sending them?]
- [NEEDS CLARIFICATION: once `main` can require a check, should `pr-title` be required too?
  Today it is advisory like everything else, though the release workflow reads that title to pick
  the version bump.]
- [NEEDS CLARIFICATION: does anyone besides the owner open pull requests or use the releases?]
