# Research: Issues found during development, tracked in beads

Everything here was checked on 2026-11-26 with `bd` 1.3.4 (`7ef2fd05e`), the version installed on
the owner's machine, in a scratch setup: a tracker clone and a project clone, each with a bare git
repository standing in for its GitHub remote. What wasn't run is marked as such. The beads
documentation read is at `https://beads.gascity.com` (worktrees, git integration, Claude Code,
Codex, sync setup, configuration, routing, `bd prime`); GitHub's, on repository security
advisories, temporary private forks and rulesets.

## R1. How this repository reaches the tracker: a `.beads/redirect` file, written per clone

**Decision**: The tracker is one beads workspace, in a clone of the private tracker repository,
kept beside this one (`../<tracker>` by default). This repository reaches it through
`.beads/redirect`, a file holding the path of the tracker's `.beads` directory, relative to this
repository's root (`../<tracker>/.beads`). The file is written by `make beads` (contracts/make-beads.md)
and never committed: beads' own `.gitignore` lists `redirect` among the machine-local files.

**Checked**:

- From the project, `bd where` resolves the tracker's `.beads` "via redirect", and `bd create`,
  `bd list`, `bd ready`, `bd close` and `bd dolt push` act on the tracker. After them, the project's
  `.beads/` held only `redirect`, and `git status` showed nothing else.
- A relative path is resolved from the directory that holds `.beads`: `../tracker/.beads` works,
  `../../tracker/.beads` (relative to `.beads` itself) doesn't.
- A linked worktree of the project (`git worktree add`) finds the tracker through the main
  checkout's redirect, without a redirect of its own.
- A redirect whose target is missing prints a warning on every command, and commands fail as with
  no workspace.

**Alternatives considered**:

- **`BEADS_DIR` in the environment**, which beads documents for "a separate issue-tracker
  repository shared by many code worktrees". It wins over everything, but lives in a shell
  profile: an agent or an IDE started outside that shell doesn't see it, and nothing in the clone
  says the tracker exists. The redirect is found by every `bd` started anywhere in the clone.
- **`bd init` here, with its Dolt remote pointed at the tracker repository.** Each repository
  would have a database of its own, and two databases can't share one remote's `refs/dolt/data`:
  it isn't one tracker. `bd init` would also wire the remote to this repository's `origin` first,
  and commit its files to the current branch (it did so in the scratch tracker: "bd init:
  initialize beads issue tracking").
- **Contributor routing** (`bd init --contributor`, `routing.contributor`), which sends new beads to
  a planning repository "that is never pushed upstream". It keeps a database here too, and is made
  for a contributor's private notes on someone else's project, not for one tracker of many
  repositories.
- **The shared server** (`bd init --shared-server`, `--global`): one Dolt server for all projects.
  It needs a running `dolt sql-server` on each machine, and its sync is the same Dolt remote.

## R2. The tracker repository and its sync

**Decision**: A new private GitHub repository of the owner's, `<owner>/<tracker>`, whose name and
issue prefix the owner confirms before it is created (proposed: `issues`, prefix `iss`). It is
initialized once, in its own clone, with
`bd init --prefix <prefix> --skip-agents --skip-hooks --non-interactive`, which wires its Dolt
remote to the clone's `origin`, the private repository. Beads are stored there under
`refs/dolt/data`; its `main` branch holds only what `bd init` commits (`.beads/config.yaml`,
`.beads/metadata.json`, `.beads/README.md`, the `.gitignore`s) and a README of the owner's. A new
machine clones it and runs `bd bootstrap`, which finds `refs/dolt/data` on `origin` and wires it as
the Dolt remote.

**Checked**: `bd dolt push` run from the project pushed `refs/dolt/data` to the tracker's remote,
and the project's remote kept `refs/heads/main` only. A fresh clone of the tracker, after
`bd bootstrap`, listed the bead created from the project. The tracker's remote also gets
`refs/heads/__dolt_remote_info__`, a branch Dolt keeps; it is private there.

**Rationale**: `local-book-rag` is public. It was made private for a few hours on 2026-11-26, and
its visibility may change again. Anyone can fetch every ref of a public repository, so beads'
default, `refs/dolt/data` on this repository's `origin`, would publish every issue then, and the
owner's other repositories would each need a tracker of their own.

## R3. Which repository a bead belongs to: a `repo:<name>` label

**Decision**: Every bead carries the label `repo:<name>`, `repo:local-book-rag` here, and every
listing an agent makes for this repository filters on it (`bd ready --label repo:local-book-rag`,
`bd list --label …`). The tracker has one issue prefix for all repositories.

**Checked**: `bd ready --label repo:project` listed the project's beads and left out the others;
`bd label add` adds the label to an existing bead.

**Alternatives considered**: A prefix per repository: a beads store has one `issue_prefix`, and a
bead with another prefix needs an explicit `--id` and `--force`, or a route to another store.
`source_repo`: beads sets it only when it hydrates issues from other repositories
(`repos.additional`), which isn't this setup.

## R4. Kinds: three of beads' types, and two custom ones

**Decision**:

| Kind (spec) | beads type | Flow (AGENTS.md) |
| --- | --- | --- |
| bug | `bug` | `/speckit-bug-assess`, `-fix`, `-test` |
| vulnerability | `vulnerability` (custom) | by visibility (R8) |
| feature | `feature` | `/speckit-specify` … |
| idea | `idea` (custom) | `/speckit-assess-intake` … |
| trivial | `chore` | none |

The custom types are registered once in the tracker: `bd config set types.custom "idea,vulnerability"`.

**Checked**: `types.custom` is stored in the database, not in `config.yaml`, and reached a second
clone with `bd dolt pull`. `bd create -t vulnerability` and `bd ready -t vulnerability` work.

**Alternatives considered**: A `security` label on a `bug`: easy to leave out, and `-t` can't
select it. Beads' `spike` for an idea: a spike is time-boxed research, not an idea whose worth an
assessment decides.

## R5. Links and lifecycle

**Decision**:

- **Found from**: `--deps discovered-from:<id>` when the work it came from has a bead. Work started
  without a bead (a feature the owner starts directly, as this one) gets a bead, in progress, when
  it starts, so what is found from it can link to it. A seeded item, which has none, records where
  it was listed in `metadata.found_in`.
- **Record**: `--spec-id <path>` (`specs/NNN-<slug>`, `.specify/bugs/<slug>`,
  `.specify/assessments/<slug>`).
- **Pull request**: `--external-ref gh-<n>`; for a vulnerability fixed through an advisory, the
  advisory's ID. Two beads can share it: one pull request can close several.
- **Status**: `open` → `in_progress` (`bd update <id> --status in_progress`; not `--claim`, whose
  lease of a few minutes, kept alive by `bd heartbeat` and reaped by `bd reclaim`, is for
  short-lived workers under a supervisor, while a change here lasts days) → `closed`
  (`bd close <id> --reason "Merged in #<n>"`). A pull request closed unmerged:
  `bd update <id> --status open`, links kept. An assessment ending in `kill`, or finding no bug:
  `bd close <id> --reason "<why>; see <record>"`.
- **Closing on merge** is done in a session, not by CI: before listing work, the agent checks each
  of this repository's beads in progress that has a pull request (`gh pr view <n> --json state`),
  and closes or reopens it. This repository's CI gets no credential to the tracker.

**Checked**: `--spec-id`, `--external-ref`, `--metadata`, `--deps discovered-from:` and
`close --reason` on real beads; two beads with the same `external_ref` (no uniqueness).

## R6. Agent context: a committed `.beads/PRIME.md`, and hooks written by hand

**Decision**:

- **`.beads/PRIME.md`**, committed, replaces beads' default session text (contracts/prime.md). A
  `PRIME.md` in the local clone's `.beads` wins over the resolved workspace's, and over the
  default; it is read in linked worktrees too. It holds this repository's commands (with the label)
  and the session protocol, and points to `AGENTS.md`'s Issues section for the rules. The tracker's
  memories (`bd remember`) are still appended to it.
- **Claude Code**: `.claude/settings.json`, committed, with one `SessionStart` hook that runs
  `devtools/beads-hook.sh claude`. SessionStart fires again after compaction, so no other event is
  needed (beads' Claude Code page says so).
- **Codex**: `.codex/hooks.json` and `.codex/config.toml` (`[features] hooks = true`), committed,
  with beads' four events (`SessionStart`, `PreCompact`, `PostCompact`, `UserPromptSubmit`), each
  running `devtools/beads-hook.sh codex <event>`.
- **`devtools/beads-hook.sh`** (contracts/agent-hooks.md) checks for `bd` 1.3.4 or later and for a
  reachable tracker. With both, it runs `bd prime --hook-json` (Claude Code) or
  `bd codex-hook <event>` (Codex). Without, it gives Claude Code, and Codex's `SessionStart`, a one-line
  context saying beads isn't available and why, exits 0, and does nothing on the other events.

**Checked**: The default `bd prime` text says "Use beads for ALL task tracking", which contradicts
FR-011 (tasks stay in `tasks.md`), and "Do NOT use MEMORY.md files", which contradicts the agents'
own memory. With a `PRIME.md` in the project's `.beads`, `bd prime --hook-json` and
`bd codex-hook SessionStart` both returned its text. In a clone without a tracker, `bd prime
--hook-json` returns an empty context and exits 0, `PRIME.md` or not, and `bd where` exits 1.

**Found while implementing**: `bd prime` reads `.beads/PRIME.md` only from the directory it runs
in. Run from `app/`, it found the tracker through the root's redirect, but gave beads' default text.
So `devtools/beads-hook.sh` runs `bd` from the repository's root, whatever the session's directory
is, and the hooks name the script by an absolute path: `$CLAUDE_PROJECT_DIR` in Claude Code,
`git rev-parse --show-toplevel` in Codex.

**Not run**: `bd setup claude` and `bd setup codex`. Claude Code's auto mode refused to let the
agent run them, even in a scratch repository, because they install agent hooks. What they write is
taken from beads' documentation: `bd setup claude` writes the hook into `.claude/settings.json` and
a beads section into `CLAUDE.md`. `bd setup codex` writes `.codex/hooks.json`, `.codex/config.toml`,
a managed section into `AGENTS.md`, and a beads skill into `.agents/skills/beads/`. The CLAUDE.md
section breaks FR-021. The managed AGENTS.md section and the skill would bring back beads' default
workflow text. So the hooks are written by hand, in the shapes the documentation gives ("Manual
Setup", "Manual Fallback"), and no beads skill is added. Codex isn't installed on the owner's
machine, so a live Codex session is part of the quickstart only if the owner installs it (§ 8).

## R7. Git hooks: none of beads'

**Decision**: Beads' git hooks aren't installed, in this repository or in the tracker
(`--skip-hooks`). The pre-commit framework keeps `.git/hooks/pre-commit` and `commit-msg`.

**Rationale**: With the Dolt backend, beads' hooks only run "chained hooks" around commits, merges,
pushes and checkouts, and add agent-identity trailers to commit messages; issue data never travels
in git commits. Nothing here needs them, and `bd hooks install` would add sections to the hooks
pre-commit generates.

## R8. Vulnerabilities, by visibility

**Decision**: Recorded as `vulnerability` beads, with their details in the tracker. The fix's path
is set by the repository's visibility when the fix starts:

- **Private**: the usual bug flow. Nothing in the repository is public.
- **Public** (now): a draft repository security advisory on `local-book-rag`, and the fix in its
  temporary private fork, with its bug record. The advisory is published once the fix merges.
  Both can be scripted with `gh api`: `POST /repos/{owner}/{repo}/security-advisories` opens the
  draft, `POST …/security-advisories/{ghsa_id}/forks` makes the fork, and a `PATCH` with
  `"state": "closed"` closes an advisory that isn't to be published.

**Checked in GitHub's documentation**: repository security advisories exist for public
repositories only. In a temporary private fork, "status checks do not run on pull requests", and
"GitHub won't enforce any of the protection rules that you may have set up for the branch you're
trying to merge the changes in to"; all of the advisory's pull requests are merged at once, from
the advisory. So `pr-title` neither runs nor blocks.

**Not run yet**: the advisory path. The trial runs it up to the merge (quickstart.md § 6), and
stops there: a made-up fix isn't merged into `main`. So one consequence stays unchecked until a
real vulnerability is fixed this way. An advisory's merge doesn't go through this repository's
squash merge of a conventional title, and the release workflow bumps from conventional commits, so
such a fix may release nothing until the next `fix:` merge.

Private vulnerability reporting, which lets someone else report a vulnerability into a draft
advisory, is off on `local-book-rag`. The spec doesn't ask for it, so it stays off.

## R9. Sync: pull at the start, push at the end, no auto-push

**Decision**: `dolt.auto-push` stays off. `PRIME.md`'s protocol pulls before listing work
(`bd dolt pull`) and pushes at the end of the session (`bd dolt push`), and the owner can run either
at any time. Offline, beads are written to the local database and pushed by the next push.

**Rationale**: Beads' configuration reference keeps auto-push opt-in "because concurrent pushes to
git-protocol Dolt remotes can corrupt or strand remote history when multiple writers race". Two
machines that wrote before syncing merge on pull, as Dolt merges rows.

## R10. The seed: what is still open of the existing backlog

**Decision**: The tracker is seeded with the 18 beads of data-model.md, The seed. A read of the
three fix reports' Follow-ups and of `docs/benchmark-results.md`'s Recommendations and Known
limitations, checked against later commits, specs and code, found 25 items. Four were done or
moot: the OpenAI branch's merge note, *História*'s back matter (`aa54d1b`), the retrieval rows'
chunk IDs (`16eeda4`), and the publisher's pages, the same item as the back matter. Of the 21 left,
three pairs are duplicates, each seeded once: gemma4 as the default LLM (a Follow-up and a
Recommendation), the judge's noise (a Recommendation and a Known limitation), and the abstentions
of models without the reply check (a Follow-up and a Known limitation). Two spot checks confirmed
the inventory:
`Makefile:69` is still `docker compose up -d --build`, and `app/generation/summarization.py:47`
still writes `## References`.

## R11. The constitution: a MINOR amendment to the Development Workflow

**Decision**: Recording found work in beads is a convention every change keeps, as Spec Kit is, so
it belongs in the constitution's Development Workflow, with the how in `AGENTS.md`. The amendment
adds one bullet, **Beads**, and changes no principle: 3.0.0 → 3.1.0 (a section materially
expanded). It goes through `/speckit-constitution`, which only the owner can start, before the pull
request is merged (tasks).

## R12. Visibility also decides whether `main` is protected

While the repository was private, GitHub Free didn't enforce `protect-main`: it applies rulesets to
public repositories only, and the API answered "Upgrade to GitHub Pro or make this repository
public". `main` took direct pushes, though the constitution's Development Workflow and the README
say it doesn't. Once the repository was public again, the API reported `protect-main` with
`enforcement: active`. Nothing to record as a bead now. `docs/decisions.md` notes it beside the
vulnerability rule, since the same switch decides both.

## R13. Beads' usage metrics

Beads' anonymous usage metrics are on for the owner's user (`~/.config/bd/config.yaml`).
`bd metrics` says they hold command names, the version and the platform, never issues, paths,
remotes or identity. Nothing in the tracker reaches them, so nothing changes. The README says how
to turn them off (`bd metrics off`).
