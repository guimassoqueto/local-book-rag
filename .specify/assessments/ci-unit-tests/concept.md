# Concept: a required check that runs the unit tests and lint on every pull request

- **Slug**: ci-unit-tests
- **Created**: 2026-11-26
- **Recommended option**: B, one required check on each pull request

Three options against `problem.md`. The owner's answers there set the bar: a pull request whose unit
tests or lint fail can't merge, and lint counts as much as the tests. Facts are from `research.md`
unless named; two were read for this stage:

- **No one can bypass `main`'s rules.** `protect-main` has no bypass actors
  (`"bypass_actors": []`, `"current_user_can_bypass": "never"`, from
  `gh api repos/guimassoqueto/local-book-rag/rulesets/26818040`). A required check would
  block the owner too, unless the rule is edited or a bypass is added.
- **Lint uses the venv's ruff.** `make lint-check` runs `uv run ruff check .` and
  `uv run ruff format --check .` (`Makefile:86-88`). The pre-commit hook also runs `.venv/bin/ruff`
  (`.pre-commit-config.yaml:15,43,50`), ruff 0.17.6 in `uv.lock`. So any environment synced from the
  lock lints the same way the hook does.

## Options

### Option A — A local gate, no CI

- **Sketch**: The checks stay on the owner's machine, but stop being optional there. A `pre-push`
  hook runs `make lint-check` and `make test` (about 30 s) and refuses the push when either fails.
  The agents' flows already say to run them before a pull request, and would keep saying so.
  Nothing on GitHub changes.
- **Appetite**: small (hours).
- **Trade-offs**: It adds no workflow, makes no download and contacts no third party, and the
  owner's `.venv` already has what the suite needs. It would have caught #27, whose lock broke the
  owner's local `.venv` the same way. But it doesn't meet the owner's bar. `--no-verify` skips it, a
  commit made on GitHub never meets it, a clone without the hooks installed has none, and nothing
  on the pull request says whether it ran. A breakage still *can* merge: the goal "can't merge"
  fails outright.
- **Rabbit holes**: A 30-second wait on every push is the kind of friction that gets
  `--no-verify` used. The hook runs against whatever `.venv` holds, which can differ from the lock
  if `make install` wasn't run after a change to it.

### Option B — One required check on each pull request

- **Sketch**: Every pull request gets one check, which installs the project from `uv.lock` on a
  clean runner and runs `make lint-check` and `make test`. It installs the `evaluation` extra but
  not `reranking`, so it downloads 0.36 GB and no torch. `protect-main` then requires it to pass
  before a merge. The owner sees it on the pull request like `pr-title`, but a red one stops the
  merge. It needs no secret, and the run sends ragas no analytics (iss-6fu). Downloads are allowed
  (packages, tiktoken's `o200k_base`, the Hugging Face file), with uv's own cache kept between runs.
- **Appetite**: small (a day or two, including replaying #27 on a pull request to show that it
  stops).
- **Trade-offs**: It meets the goals that matter most: the merge is stopped (goal 1). Both of #27's
  breakages are caught, because the `evaluation` extra makes `test_ragas_llm.py` run instead of
  skip (goal 2). No secret is needed and nothing goes to a third party (goal 5). It reuses the
  `make` targets, so CI and the owner run the same commands. What it gives up:
  - Its environment isn't the owner's: no torch. No unit test needs torch, so the results are the
    same, but they are two environments.
  - A run depends on outside hosts (PyPI, tiktoken's blob store, the Hugging Face Hub). An outage
    there turns a pull request red until it is run again (goal 4, measured, not prevented).
  - The time per run is a guess of a few minutes (goal 3, unmeasured).
- **Rabbit holes**:
  - **The check has to report on every pull request.** A required check that a pull request
    never triggers leaves it waiting forever. So no path filters: docs-only pull requests, such
    as this assessment's, run it too.
  - **Forcing a merge.** With no bypass actor, a required check stops the owner as well. An
    emergency merge then means editing the ruleset, unless a bypass for the owner's admin role is
    added with the rule (goal 6). Which of the two is the owner's choice.
  - **Python on `PATH`.** `python-preference = "only-system"` means uv won't fetch a Python, so
    the runner must provide 3.13 first. The uv version has to stay in step with `.tool-versions`.
  - **A skip passes silently.** If the `evaluation` extra ever stops being installed, the tests
    that would catch the next #27 skip, and the check stays green. The spec decides whether a skip
    for a missing extra fails the run.
  - **Recording it.** The constitution's Development Workflow says how a change lands on `main`.
    Making a green check a condition of merging likely changes that section, which is an amendment
    through `/speckit-constitution`. `README.md` and `docs/decisions.md` record it too
    (Principle VIII).

### Option C — Option B, plus a sealed suite

- **Sketch**: Everything in B, and the run no longer depends on anything outside the lock. The
  suite runs with the network off after installing: tiktoken's file and anything the Hugging Face
  library fetches come from a cache or the repository. A test skipped for a missing extra fails the
  run instead of passing. `pr-title` becomes required beside it, since the same ruleset change can
  carry both.
- **Appetite**: medium (a week, as a budget), mostly in the test setup, possibly in the code that
  loads tokenizers.
- **Trade-offs**: It wins the strongest version of goal 4: a red result can only mean the change
  broke something. It also closes B's silent-skip hole, and the title that picks the release would
  be enforced too. It costs more work in `tests/` and possibly `app/`, with files to keep in step,
  such as a cached `o200k_base`. All of it guards against failures that haven't happened yet: no
  run has gone red for an outside reason, since nothing runs. `pr-title` being required is outside
  the problem as defined.
- **Rabbit holes**: Making the suite work offline touches how tokenizers are found, which
  `docs/decisions.md` shaped around real failures (Principle V). The Hugging Face library's own
  fetches, such as the agent registry, are its behavior, not this repository's, and can change
  with a release. Turning skips into failures needs a rule for which skips are allowed: the
  integration tests' own skips must stay skips.

## Recommendation

**Option B.** It is the smallest option that meets the owner's bar. A pull request that breaks the
unit suite or lint can't merge (goal 1). Replayed, #27's two breakages are stopped before merge
(the success metric), because the run installs exactly the extra whose absence would skip them.
It costs a small budget, an eighth of the bead's feared download (0.36 of 2.88 GB), and no
secret.

Option A fails the owner's answer outright: a breakage could still merge. Option C answers risks
that the evidence doesn't show yet: no outside outage has failed a run, and the silent skip needs
the install to change first. Its parts stay available if B's measurements call for them. A
monthly count of red results unrelated to the change, kept above zero, would justify the sealed
suite. A skip found in a green run would justify the skip rule.

Two things go with B:

- **iss-6fu first.** The goal "a run sends nothing to a third party" is met for the app as a
  whole, and for CI with no workaround of its own, once ragas's analytics are off in the code.
  Fixing it first (a small bug fix) keeps the CI change from carrying its own copy of that switch.
- **Decide forcing with the rule.** Goal 6 needs a decision when `protect-main` gains the
  required check: either a bypass for the owner, or an emergency means editing the ruleset.

## Out of Scope (for the recommended option)

- Running `make test-integration`, benchmarks or real models in CI (Principle V).
- Installing or testing the `reranking` extra (torch, sentence-transformers, transformers).
- Building, testing or publishing the Docker image; changing `release.yml`.
- Closing beads from CI (`docs/decisions.md:868-869`).
- A sealed, offline suite, and turning skips into failures (Option C), unless B's metrics call for
  them.
- Requiring `pr-title`. It's a one-line addition to the same ruleset change, but outside this
  problem. The owner can add it.
- Making a run without the `evaluation` extra pass, which means guarding
  `tests/unit/test_generation_metrics.py:90`: B always installs the extra.
- More than one Python version or platform. The lock resolves for Linux x86_64 and Python 3.13
  only (`pyproject.toml:6,72`).
- Coverage reports, test timing dashboards, or caching beyond uv's own.

## Assumptions to Validate

- A clean GitHub runner installs the `evaluation` environment and runs lint and the unit suite in a
  few minutes. Unmeasured: the first pull request measures it.
- The suite passes on a runner as it did locally from empty caches: no hidden dependence on a GPU,
  Docker, `.env`, or a file only the owner's machine has.
- `ubuntu-latest` is Linux x86_64 and can provide Python 3.13 on `PATH`, which the lock's
  `environments` marker and `python-preference = "only-system"` need.
- Standard runners are free for a public repository. The repository is public today; this is
  general knowledge, not checked.
- A required check that every pull request triggers, docs-only ones included, costs little enough
  to be accepted on all of them.
- PyPI, tiktoken's blob store and the Hugging Face Hub fail rarely enough that red runs from
  outside causes stay near zero.
- iss-6fu's fix is small, and turns ragas's analytics off wherever ragas is imported, in the image,
  the benchmarks and the tests, so the run needs nothing of its own.
- The owner accepts that a required check stops them too, with forcing done by bypass or by editing
  the ruleset.
