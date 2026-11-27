# Idea Intake: `make test` runs on every pull request

- **Slug**: ci-unit-tests
- **Created**: 2026-11-26
- **Source**: pasted text (bead iss-az3, recorded in `.specify/bugs/ragas-downgrade/fix.md`,
  Follow-ups); related repo paths: `.github/workflows/`, `Makefile` (`test`), `pyproject.toml`
  (`[project.optional-dependencies]`, `[tool.uv]`, `[tool.uv.sources]`)
- **Type**: improvement

## Idea (as captured)

> "CI (.github/workflows/) only checks the PR title (pr-title.yml) and releases (release.yml); no
> workflow runs the unit tests. make test failed at collection from 27780d3 (#27) on, and #28 and
> #30 merged with it failing. A workflow running make test on pull requests would have stopped
> #27. Its worth is uncertain because the image's dependencies include CUDA torch from the
> pytorch-cu134 index (pyproject.toml, tool.uv.sources), several GB on every run, unless CI
> installs without the reranking extra or from a CPU index. Found in
> .specify/bugs/ragas-downgrade/fix.md, Follow-ups."

Added by the owner on 2026-11-26, when starting the assessment:

> "Since then: #27 also changed both cloud profiles' reasoning from low to medium, which two unit
> tests caught only once the suite could run again (.specify/bugs/cloud-reasoning-medium, iss-e5z,
> fixed in #32). On main (08c25aa), make test passes: 1341 passed, 86 deselected."

## Restated

A GitHub Actions workflow that runs the unit tests, `make test`, on every pull request, so that a
change that breaks them is seen before it merges. What is uncertain is whether that is worth what
each run costs to install, since the project's dependencies include CUDA builds of torch.

## Origin & Context

- **Raised by**: the agent, as a follow-up of the `ragas-downgrade` bug fix (#31), recorded as a
  bead on 2026-11-26; picked up by the owner on 2026-11-26.
- **Trigger**: #27 (`27780d3`, a dependency chore) broke the unit suite twice, and nothing
  noticed. Its lock moved ragas from 0.4.4 to 0.3.1, so collection stopped at an ImportError
  (iss-30k, fixed in #31). It also changed the cloud profiles' reasoning, which two tests caught
  only once the suite ran again (iss-e5z, fixed in #32). The suite was found broken while working
  on `specs/010-beads-issue-tracking`, after #28 and #30 had merged.
- **Current state, as found** (facts, not assessment):
  - `.github/workflows/` holds two workflows. `pr-title.yml` runs on pull requests (`opened`,
    `edited`, `synchronize`, `reopened`) and checks only the title. `release.yml` runs on pushes
    to `main`.
  - `make test` is `uv run pytest -m "not integration"` (`Makefile:93-94`). The constitution says
    the unit tests need no services: real files, real SQLite, embedded ChromaDB, fake models.
  - `torch`, `sentence-transformers` and `transformers` are the `reranking` extra, and `ragas`,
    `numpy`, `pandas` and `scikit-learn` the `evaluation` extra (`pyproject.toml:39-50`).
    `[tool.uv.sources]` takes `torch` and `torchvision` from the `pytorch-cu134` index
    (`pyproject.toml:85-92`).
  - `[tool.uv]` uses only interpreters on `PATH`, never a uv-managed one
    (`python-preference = "only-system"`), and resolves for Linux x86_64 only (`environments`).
    Locally, asdf provides Python 3.13 (`.tool-versions`).
  - The repository is public (`gh repo view --json visibility`, 2026-11-26).
  - `main` takes changes only through pull requests, squash merged (the constitution's
    Development Workflow).

## First-Glance Unknowns

- [NEEDS CLARIFICATION: which extras does the unit suite need to collect and pass? Does any unit
  test import `torch`, `sentence-transformers` or `ragas`, or can CI install without `reranking`,
  or without both extras, and still run all 1,341 tests?]
- [NEEDS CLARIFICATION: how long does a run take, and how much does it download, with and without
  the CUDA wheels, and with a CPU index for torch? Can a cache of uv's downloads make a repeat run
  cheap?]
- [NEEDS CLARIFICATION: would installing torch from a CPU index in CI, against the lock that names
  `pytorch-cu134`, test the same dependencies the image ships, or a different resolution?]
- [NEEDS CLARIFICATION: should the check be required before a merge (a branch rule on `main`), or
  only reported? Which rules does `main` have today?]
- [NEEDS CLARIFICATION: does anything else belong in the same run, such as `make lint-check`, or
  would that be a separate idea?]
- [NEEDS CLARIFICATION: how often would it have caught something? #27 is one case; are there
  others in the history where `make test` was broken on `main`?]
