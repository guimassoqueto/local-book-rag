# Idea Research: `make test` runs on every pull request

- **Slug**: ci-unit-tests
- **Created**: 2026-11-26
- **Evidence confidence (overall)**: high

Most of the evidence is measured on this machine, on `main` at `08c25aa`. Two scratch
environments were built from `uv.lock` (`uv sync --frozen`, with no extra and with
`--extra evaluation`), and the unit suite (`pytest -m "not integration"`) ran in each, with
`HOME`, `XDG_CACHE_HOME`, `TMPDIR`, `HF_HOME` and `TIKTOKEN_CACHE_DIR` pointing at empty
directories, the way a fresh CI runner would start. What a GitHub runner does is not measured: those
claims are marked as assumptions.

## Users & Demand

- The only user is the owner, who reviews and merges every pull request, some of them written by
  agents. No one else contributes. — [source: `git log main`, the constitution's Development
  Workflow; ASSUMPTION that there is no outside contributor] (confidence: medium)
- **Observed, not stated**: three pull requests in a row merged with `make test` failing. #27
  broke the suite in two independent ways, and #28 and #30 merged on top of it. The breakage was
  found by chance, while working on `specs/010-beads-issue-tracking`, four days later.
  — [source: `.specify/bugs/ragas-downgrade/assessment.md`, `.specify/bugs/cloud-reasoning-medium/assessment.md`,
  beads iss-30k and iss-e5z] (confidence: high)
- Since the history began (2026-11-06), `main` has 60 commits, the pull requests running up to #32. The
  #27 breakage is the only known case of `make test` failing on `main`. Earlier commits weren't
  re-run. — [source: `git log --oneline main`] (confidence: medium, since earlier breakage could
  have gone unrecorded)
- The owner picked this bead as the next piece of work, at priority 2, after the two fixes.
  — [source: this session, 2026-11-26] (confidence: high)

## Prior Art

- **This repository's workflows.** `pr-title.yml` runs on `pull_request` (`opened`, `edited`,
  `synchronize`, `reopened`) with `permissions: {}` on `ubuntu-latest`. `release.yml` runs on
  pushes to `main`, using `actions/checkout@v5` and a pinned commitizen. Neither installs the
  project or runs a test. — [source: `.github/workflows/pr-title.yml`, `.github/workflows/release.yml`]
  (confidence: high)
- **No earlier decision against CI tests.** `docs/decisions.md` mentions CI only to say why a
  bead closes in a session, not in CI: the workflows would need a credential to the private
  tracker (`docs/decisions.md:868-869`). `specs/010-beads-issue-tracking` requires that `make test`,
  `make lint-check` and CI pass without beads (FR-025, SC-005), which treats CI as existing or
  expected. Nothing records a choice not to run the tests in CI. — [source: grep of
  `docs/decisions.md`, `README.md`, `specs/*/spec.md`, `specs/*/plan.md`] (confidence: high)
- **The local hooks.** The pre-commit hook runs ruff and other file checks on staged files, and the
  commit-msg hook checks the header. Neither runs the tests. A commit made on GitHub, or with
  `--no-verify`, skips them. — [source: the hook output on `30e4f0a` in this session; ASSUMPTION
  for GitHub and `--no-verify`] (confidence: high)
- **Elsewhere**: a workflow that runs a Python project's tests on each pull request is the
  ordinary GitHub Actions setup, and uv's own GitHub action (`astral-sh/setup-uv`) installs uv
  and caches its downloads. — [ASSUMPTION: general knowledge, not fetched] (confidence: medium)

## Market & Context

- **What the owner does today**: runs `make test` by hand. It runs in about 28 s on the full
  `.venv` (`make test`, this session), but nothing makes anyone run it. #27, #28 and #30 merged
  without it. — [source: `Makefile:93-94`, the two bug records] (confidence: high)
- **The cost of doing nothing**: a breakage stays unseen until someone runs the suite. #27's ragas
  downgrade also broke the generation benchmark's judge, not only the tests: the image ships the
  same lock. — [source: `.specify/bugs/ragas-downgrade/assessment.md`, Symptom] (confidence: high)
- **What unit tests can't catch**: the failures behind most of `docs/decisions.md` came from real
  models and real books, which the unit tests' fakes don't show (Principle V). CI can't run
  `make test-integration` without Ollama, the models and a GPU. So a test workflow only covers the
  class of failure #27 belonged to: imports, dependencies, configuration drift and logic covered
  by unit tests. — [source: the constitution, Principle V; `Makefile:97-98`] (confidence: high)

## Data & Constraints

- **The unit suite needs the `evaluation` extra, not `reranking`.**

  | Environment               | Packages | Wheels to download | Installed size | Unit suite                                         |
  | ------------------------- | -------- | ------------------ | -------------- | -------------------------------------------------- |
  | No extra (`uv sync`)      | 186      | 0.23 GB            | 728 MB         | 1 failed, 1333 passed, 1 module skipped, in 30.9 s |
  | `--extra evaluation`      | 220      | 0.36 GB            | 1.2 GB         | **1341 passed**, in 33.2 s                         |
  | `--all-extras` (`.venv`)  | 247      | 2.88 GB            | 6.6 GB         | 1341 passed, in 27.7 s (`make test`)               |

  The download sizes are the sums of the `size` fields of the `cp313` manylinux x86_64 wheels in
  `uv.lock` for each environment's packages. Of the 2.88 GB, 2.48 GB is torch, its NVIDIA
  libraries and triton, which only the `reranking` extra brings. — [source: scratch environments
  and `uv.lock`, this session] (confidence: high)
- **No unit test imports torch.** No module in `tests/unit` imports torch, sentence-transformers or
  transformers. `app/retrieval/reranker.py:29-55` imports them inside its methods, and the only
  test that needs them, `tests/integration/test_reranking.py:43`, calls
  `pytest.importorskip("torch")`. The bead's question about a CPU index for torch doesn't arise
  for the unit suite. — [source: grep of `tests/unit` and `app/`] (confidence: high)
- **Without `evaluation`, the suite doesn't catch #27.** `tests/unit/test_ragas_llm.py:13`
  skips the whole module when ragas isn't installed (`importorskip`), and that module's import of
  `app/evaluation/ragas_llm.py` is what failed under ragas 0.3.1. Without the extra, #27's ragas
  downgrade would have been skipped, not caught. #27's other change, the cloud profiles' reasoning,
  is caught in both environments. — [source: `tests/unit/test_ragas_llm.py:13-14`;
  `.specify/bugs/ragas-downgrade/assessment.md`] (confidence: high)
- **One test isn't guarded.** `tests/unit/test_generation_metrics.py:90`
  (`test_the_judges_client_reaches_ollama_with_its_own_key_whatever_the_environment_says`) fails
  with `ModuleNotFoundError: No module named 'ragas'` without the extra, where
  `test_ragas_llm.py` skips. Locally it never shows, because `make install` installs every extra
  (`Makefile:13-14`). `make test` as written is `uv run pytest`, and in a fresh environment
  `uv run` installs no extra, so in CI it would fail on this test. — [source: the no-extra run,
  `Makefile:13-14,93-94`] (confidence: high)
- **The unit suite uses the network.** Starting from empty caches, a run downloaded
  `o200k_base` for tiktoken (3.6 MB, into `TIKTOKEN_CACHE_DIR`) and huggingface_hub's agent
  registry (9 KB, `HF_HOME/.agent_harnesses.json`, which `huggingface_hub/constants.py:224-226`
  says is fetched from the Hub). It also created `~/.local/share/ragas/uuid.json`, ragas's analytics
  ID, so ragas tried to post a usage event to a third party (bead iss-6fu, below). The constitution
  says the unit tests need no services; they still need the internet the first time. — [source:
  the empty-cache runs, this session] (confidence: high)
- **Python and uv.** `requires-python = ">=3.13,<3.14"` (`pyproject.toml:6`), and
  `.tool-versions` pins Python 3.13.18 and uv 0.13.7. `[tool.uv]` uses only interpreters on
  `PATH` (`python-preference = "only-system"`, `pyproject.toml:70`), so a runner has to put 3.13
  on `PATH` itself. `environments` limits the lock to Linux x86_64 (`pyproject.toml:72`).
  — [source: `pyproject.toml`, `.tool-versions`] (confidence: high)
- **The tests need no secret.** The unit tests use fakes and an embedded ChromaDB, and the cloud
  integration tests are deselected by `-m "not integration"`, so a workflow can run with
  `permissions: {}` and no secret, like `pr-title.yml`. — [source: the constitution, Development
  Workflow; `Makefile:93-94`; the empty-HOME runs, which had no `.env`] (confidence: high)
- **`main`'s rules require no check.** The one ruleset, `protect-main` (active, on the default
  branch), forbids deletion and force pushes and requires a pull request with 0 approvals. It
  has no `required_status_checks` rule, so even `pr-title` is advisory: a failing check doesn't
  block a merge. There is no classic branch protection. — [source:
  `gh api repos/guimassoqueto/local-book-rag/rulesets/26818040`, `…/branches/main/protection`
  (404)] (confidence: high)
- **Cost on GitHub.** The repository is public (`gh repo view --json visibility`), and GitHub
  Actions minutes on standard runners are free for public repositories. — [source for public:
  `gh`; ASSUMPTION for the pricing, general knowledge] (confidence: medium)
- **Time on a runner.** Locally, a warm-cache `uv sync` took 0.12 to 0.15 s, which says nothing
  about a cold runner. A runner downloading 0.36 GB and running the suite is likely to take a
  minute or two. — [ASSUMPTION: not measured on GitHub] (confidence: low)

## Evidence Against the Idea

- **A check that doesn't block helps only if someone looks.** `main`'s ruleset requires no status
  check (above), and pr-title's check is advisory today. #27 merged with a red suite because
  nobody ran it. A red check that nobody reads, or that doesn't stop the merge, may not have stopped
  #27 either. It is worth only as much as the attention it gets, unless it is made required.
  — [source: the ruleset] (confidence: medium)
- **It covers a narrow class of failure.** The unit tests' models are fakes. What `docs/decisions.md`
  records as the costly failures, such as citations misparsed, prompts cut by Ollama or judges that
  score without reading, came from real models and books, which no runner here can reach (Principle V).
  — [source: the constitution, Principle V] (confidence: high)
- **One known incident.** The only known breakage on `main` is #27. That one was costly: three
  merges and four days unseen, and the benchmark judge broken too. Still, one incident is thin
  evidence of how often a breakage would recur. — [source: `git log`, the bug records]
  (confidence: medium)
- **It adds upkeep and some fragility.** A workflow pins actions and a uv version that have to
  follow `.tool-versions`. The suite downloads from three outside hosts on a cold start (tiktoken's
  blob store, the Hugging Face Hub, ragas's analytics endpoint), so an outage there could fail a run
  for reasons unrelated to the change. — [source: the empty-cache runs; ASSUMPTION for upkeep]
  (confidence: medium)
- **The cost the bead feared doesn't stand.** The bead doubted the idea's worth because of
  several GB of CUDA torch on each run. The unit suite needs none of it: 0.36 GB instead of
  2.88 GB. This removes an argument against the idea, not one for it. — [source: the measurements
  above] (confidence: high)

## Gaps & Open Questions

- [NEEDS CLARIFICATION: should the check be required before merging (a `required_status_checks`
  rule in `protect-main`), or advisory like pr-title? It decides whether the idea would have
  stopped #27.]
- [NEEDS CLARIFICATION: does `make lint-check` belong in the same run? It needs nothing beyond
  the dev group, which every environment above installs.]
- [NEEDS CLARIFICATION: should the unguarded test at `tests/unit/test_generation_metrics.py:90`
  skip without ragas, like `test_ragas_llm.py`, or should the suite require the `evaluation` extra
  outright? The first would let a no-extra run pass, and would again skip what #27 broke.]
- [NEEDS CLARIFICATION: how long a run takes on a GitHub runner, cold and with uv's cache.
  Measurable only by running it.]
- [NEEDS CLARIFICATION: should CI keep the unit suite off the network (`HF_HUB_OFFLINE`, a
  cached tiktoken file, `RAGAS_DO_NOT_TRACK`), or accept the downloads?]
- Whether an earlier commit of `main` also failed `make test` wasn't checked: re-running the suite
  on 60 commits, each with its own lock, was out of proportion.

## Found Along the Way

- **iss-6fu**, "RAGAS sends usage analytics to a third party from every judge run" (bug, P2,
  `discovered-from` iss-az3). ragas 0.4.4 posts usage events to `t.explodinggradients.com` unless
  `RAGAS_DO_NOT_TRACK=true` (`ragas/_analytics.py:37-49,223-233`), and nothing in the repository sets it.
  The judge's `embedding_factory` (`app/evaluation/generation_metrics.py:84-91`) sends one with the
  local embedding model's name and a persistent random ID. So does the unit test at
  `tests/unit/test_generation_metrics.py:90`, and so would every CI run. This goes against
  Principle I.

## Sources

- No URL was fetched. Everything above comes from the repository, `uv.lock`, the installed
  packages' source in `.venv`, commands run in this session (`uv sync`, `pytest`, `gh api`,
  `gh repo view`, `git log`), and the records in `.specify/bugs/`. Claims about GitHub's pricing
  and actions are marked `ASSUMPTION`.
